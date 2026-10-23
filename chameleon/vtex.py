"""
Decodes the biggest mip of a compiled Source 2 texture (.vtex_c) into PNG bytes. No Qt needed.

Layout (checked against ValveResourceFormat's Texture.cs):
  resource header : u32 fileSize, u16 headerVersion, u16 version, u32 blockOffset, u32 blockCount
  block table     : blockCount x (4cc type, u32 offset(relative to the field itself), u32 size)
  DATA block      : u16 version, u16 flags, 4 x f32 reflectivity, u16 width, u16 height, u16 depth,
                    u8 format, u8 mipCount, u32 picmip0Res, u32 extraOffset, u32 extraCount, ...
  extra data      : (u32 type, u32 offset, u32 size) ...; type 3 = compressed mip sizes
  pixel data      : right after the DATA block, mips stored SMALLEST first, so mip 0 is the last one.
Formats handled: DXT1, DXT5, RGBA8888, BGRA8888, I8, IA88, embedded PNG/JPEG/WEBP (returned as is),
BC7 (only if Pillow is installed). Anything else returns None and the caller falls back to the CDN.
"""
import struct
import zlib
from typing import List, Optional, Tuple

F_DXT1, F_DXT5, F_I8, F_RGBA8888 = 1, 2, 3, 4
F_JPEG_RGBA, F_PNG_RGBA, F_JPEG_DXT5, F_PNG_DXT5 = 15, 16, 17, 18
F_BC7, F_IA88, F_BGRA8888, F_WEBP_RGBA, F_WEBP_DXT5 = 20, 22, 28, 29, 30
_EMBEDDED = {F_JPEG_RGBA, F_PNG_RGBA, F_JPEG_DXT5, F_PNG_DXT5, F_WEBP_RGBA, F_WEBP_DXT5}
_BLOCK_BYTES = {F_DXT1: 8, F_DXT5: 16, F_BC7: 16}
_BPP = {F_I8: 1, F_IA88: 2, F_RGBA8888: 4, F_BGRA8888: 4}


# ------------------------------------------------------------------ small codecs
def lz4_block_decode(src: bytes, out_size: int) -> bytes:
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        token = src[i]; i += 1
        lit = token >> 4
        if lit == 15:
            while i < n:
                b = src[i]; i += 1
                lit += b
                if b != 255:
                    break
        out += src[i:i + lit]; i += lit
        if i >= n:
            break
        off = src[i] | (src[i + 1] << 8); i += 2
        mlen = token & 15
        if mlen == 15:
            while i < n:
                b = src[i]; i += 1
                mlen += b
                if b != 255:
                    break
        mlen += 4
        start = len(out) - off
        if off <= 0 or start < 0:
            raise ValueError("bad LZ4 offset")
        for k in range(mlen):               # byte-wise: matches may overlap
            out.append(out[start + k])
    if len(out) != out_size:
        raise ValueError(f"LZ4 size mismatch {len(out)} != {out_size}")
    return bytes(out)


def _rgb565(v: int) -> Tuple[int, int, int]:
    # standard bit replication (identical to GPU / reference decoders)
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))


def _bc1_colors(c0: int, c1: int, allow_alpha: bool):
    a, b = _rgb565(c0), _rgb565(c1)
    cols = [a + (255,), b + (255,)]
    if c0 > c1 or not allow_alpha:
        cols.append(tuple((2 * x + y) // 3 for x, y in zip(a, b)) + (255,))
        cols.append(tuple((x + 2 * y) // 3 for x, y in zip(a, b)) + (255,))
    else:
        cols.append(tuple((x + y) // 2 for x, y in zip(a, b)) + (255,))
        cols.append((0, 0, 0, 0))
    return cols


def decode_bc1(data: bytes, w: int, h: int) -> bytes:
    px = bytearray(w * h * 4)
    bw, bh = (w + 3) // 4, (h + 3) // 4
    pos = 0
    for by in range(bh):
        for bx in range(bw):
            c0, c1, bits = struct.unpack_from("<HHI", data, pos); pos += 8
            cols = _bc1_colors(c0, c1, True)
            for j in range(4):
                for i in range(4):
                    x, y = bx * 4 + i, by * 4 + j
                    if x < w and y < h:
                        px[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes(cols[(bits >> (2 * (4 * j + i))) & 3])
    return bytes(px)


def decode_bc3(data: bytes, w: int, h: int) -> bytes:
    px = bytearray(w * h * 4)
    bw, bh = (w + 3) // 4, (h + 3) // 4
    pos = 0
    for by in range(bh):
        for bx in range(bw):
            a0, a1 = data[pos], data[pos + 1]
            abits = int.from_bytes(data[pos + 2:pos + 8], "little")
            alphas = [a0, a1]
            if a0 > a1:
                alphas += [((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)]
            else:
                alphas += [((5 - k) * a0 + k * a1) // 5 for k in range(1, 5)] + [0, 255]
            c0, c1, bits = struct.unpack_from("<HHI", data, pos + 8); pos += 16
            cols = _bc1_colors(c0, c1, False)
            for j in range(4):
                for i in range(4):
                    x, y = bx * 4 + i, by * 4 + j
                    if x < w and y < h:
                        r, g, b, _ = cols[(bits >> (2 * (4 * j + i))) & 3]
                        a = alphas[(abits >> (3 * (4 * j + i))) & 7]
                        px[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes((r, g, b, a))
    return bytes(px)


def encode_png(rgba: bytes, w: int, h: int) -> bytes:
    raw = b"".join(b"\x00" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))

    def chunk(t: bytes, d: bytes) -> bytes:
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


# ------------------------------------------------------------------ container
class VTex:
    def __init__(self, data: bytes):
        self.data = data
        if len(data) < 16:
            raise ValueError("too small")
        _size, _hv, _ver, block_off, block_cnt = struct.unpack_from("<IHHII", data, 0)
        pos = 8 + block_off
        self.data_off = self.data_size = None
        for _ in range(block_cnt):
            typ = data[pos:pos + 4]
            off, size = struct.unpack_from("<II", data, pos + 4)
            if typ == b"DATA":
                self.data_off, self.data_size = pos + 4 + off, size
            pos += 12
        if self.data_off is None:
            raise ValueError("no DATA block")
        d = self.data_off
        self.version, self.flags = struct.unpack_from("<HH", data, d)
        self.width, self.height, self.depth = struct.unpack_from("<HHH", data, d + 20)
        self.format, self.mips = struct.unpack_from("<BB", data, d + 26)
        extra_off, extra_cnt = struct.unpack_from("<II", data, d + 32)
        self.compressed: Optional[List[int]] = None
        self.is_lz4 = False
        p = d + 32 + extra_off
        for _ in range(extra_cnt):
            t, o, s = struct.unpack_from("<III", data, p)
            if t == 3:                                    # COMPRESSED_MIP_SIZE
                base = p + 4 + o
                flag, mo, mc = struct.unpack_from("<III", data, base)
                self.is_lz4 = flag == 1
                self.compressed = list(struct.unpack_from(f"<{mc}i", data, base + 4 + mo)) if mc else []
            p += 12
        self.pixels_off = self.data_off + self.data_size

    def _mip_dims(self, level: int) -> Tuple[int, int]:
        return max(1, self.width >> level), max(1, self.height >> level)

    def _mip_size(self, level: int) -> int:
        w, h = self._mip_dims(level)
        if self.format in _BLOCK_BYTES:
            w, h = max(4, (w + 3) // 4 * 4), max(4, (h + 3) // 4 * 4)
            return (w * h >> 4) * _BLOCK_BYTES[self.format]
        return w * h * _BPP.get(self.format, 4)

    def mip0_bytes(self) -> bytes:
        """
        Mips are stored smallest first, so mip 0 is the LAST thing in the file. Anchoring on the end of the file
        (instead of "end of the DATA block") is what makes this independent of how many other blocks sit between the
        header and the pixels - reading from the wrong spot decodes block-table text as colours, which shows up as
        olive/yellow noise on every icon.
        """
        full = self._mip_size(0)
        size0, lz4 = full, False
        if self.compressed and self.is_lz4 and 0 < self.compressed[0] < full:
            size0, lz4 = self.compressed[0], True
        start = len(self.data) - size0
        if start < self.data_off + 8:                     # file shorter than the header claims -> not decodable
            raise ValueError("truncated texture")
        raw = self.data[start:]
        return lz4_block_decode(raw, full) if lz4 else raw


def describe_vtex_c(data: bytes) -> str:
    """One-line description of a texture (used by the diagnose tool)."""
    try:
        t = VTex(data)
        names = {1: "DXT1", 2: "DXT5", 3: "I8", 4: "RGBA8888", 15: "JPEG_RGBA8888", 16: "PNG_RGBA8888",
                 17: "JPEG_DXT5", 18: "PNG_DXT5", 19: "BC6H", 20: "BC7", 22: "IA88", 28: "BGRA8888"}
        return (f"{t.width}x{t.height} format={names.get(t.format, t.format)} mips={t.mips} "
                f"lz4={t.is_lz4} extra_sizes={t.compressed}")
    except Exception as e:
        return f"unreadable ({e})"


def yellow_cast(rgba: bytes) -> bool:
    """
    True when an image is dominated by a yellow or yellow-GREEN cast (R and G high, B far lower) - the signature of a
    mis-decoded or wrong texture. Pure green (R low) and orange/red (G low) pictures are NOT flagged.
    """
    n = len(rgba) // 4
    if n == 0:
        return False
    r = g = b = c = 0
    for i in range(0, n, 5):
        o = i * 4
        if rgba[o + 3] > 128:
            r += rgba[o]; g += rgba[o + 1]; b += rgba[o + 2]; c += 1
    if c < 3:
        return False
    r, g, b = r / c, g / c, b / c
    hi = max(r, g)
    if hi < 105 or b >= 0.5 * hi or hi - b <= 55:
        return False
    return (r >= 0.55 * g) if g >= r else (g >= 0.75 * r)


def decode_vtex_c(data: bytes, reject_yellow: bool = False) -> Optional[bytes]:
    """PNG (or the embedded JPEG/PNG/WEBP) bytes for mip 0, or None when the format isn't supported
    (or, with reject_yellow, when the decoded picture has a yellow cast and should not be trusted)."""
    try:
        tex = VTex(data)
        w, h, fmt = tex.width, tex.height, tex.format
        if w <= 0 or h <= 0 or w > 8192 or h > 8192:
            return None
        if fmt in _EMBEDDED:
            tail = tex.data[tex.data_off + 40:]      # the image file itself, not a pixel grid
            for sig in (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"RIFF"):
                i = tail.find(sig)
                if i >= 0:
                    return tail[i:]
            return None
        raw = tex.mip0_bytes()
        if fmt == F_DXT1:
            rgba = decode_bc1(raw, w, h)
        elif fmt == F_DXT5:
            rgba = decode_bc3(raw, w, h)
        elif fmt == F_RGBA8888:
            rgba = raw[:w * h * 4]
        elif fmt == F_BGRA8888:
            b = bytearray(raw[:w * h * 4]); b[0::4], b[2::4] = raw[2:w * h * 4:4], raw[0:w * h * 4:4]; rgba = bytes(b)
        elif fmt == F_I8:
            rgba = b"".join(bytes((v, v, v, 255)) for v in raw[:w * h])
        elif fmt == F_IA88:
            rgba = b"".join(bytes((raw[i], raw[i], raw[i], raw[i + 1])) for i in range(0, w * h * 2, 2))
        elif fmt == F_BC7:
            try:
                from PIL import Image                      # optional dependency
                import io
                im = Image.frombytes("RGBA", (w, h), raw, "bcn", 7)
                out = io.BytesIO(); im.save(out, "PNG"); return out.getvalue()
            except Exception:
                return None
        else:
            return None
        if len(rgba) < w * h * 4:
            return None
        if reject_yellow and yellow_cast(rgba):
            return None
        return encode_png(rgba, w, h)
    except Exception:
        return None
