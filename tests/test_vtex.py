"""Texture decoder checks on hand-built .vtex_c files (formats per ValveResourceFormat's Texture.cs)."""
import struct, sys, unittest, zlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from chameleon.vtex import decode_vtex_c, lz4_block_decode, encode_png, VTex


def build(fmt, w, h, pixels: bytes, mips=1, compressed=None, lz4=False, trailer=b""):
    extra = b""
    extra_cnt = 0
    if compressed is not None:
        extra_cnt = 1
        # one extra entry: type 3, offset(raw, includes -8 bias), size ; payload: flag, mipsOffset, mips, sizes...
        payload = struct.pack("<III", 1 if lz4 else 0, 8, len(compressed)) + struct.pack(f"<{len(compressed)}i", *compressed)
        extra = struct.pack("<III", 3, 12 + 8 - 4 + 0, len(payload)) + payload
    data_hdr = struct.pack("<HH4f", 1, 0, 0, 0, 0, 0) + struct.pack("<HHH", w, h, 1) + struct.pack("<BB", fmt, mips) \
        + struct.pack("<I", 0) + struct.pack("<II", 8, extra_cnt)
    # fix the entry offset: payload starts right after the 12-byte entry; offset is relative to (entry+12) + 8 bias
    if extra:
        extra = struct.pack("<III", 3, 8, len(payload)) + payload
    data_block = data_hdr + extra
    table_pos = 16
    data_off = table_pos + 12
    head = struct.pack("<IHHII", 0, 12, 0, 8, 1)
    table = b"DATA" + struct.pack("<II", data_off - (table_pos + 4), len(data_block))
    return head + table + data_block + trailer + pixels


def png_size(png):
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", png[16:24])


def png_pixels(png):
    w, h = png_size(png)
    idat = b""
    i = 8
    while i < len(png):
        n = struct.unpack(">I", png[i:i + 4])[0]
        t = png[i + 4:i + 8]
        if t == b"IDAT":
            idat += png[i + 8:i + 8 + n]
        i += 12 + n
    raw = zlib.decompress(idat)
    return [raw[y * (w * 4 + 1) + 1:(y + 1) * (w * 4 + 1)] for y in range(h)]


class VtexTest(unittest.TestCase):
    def test_rgba8888(self):
        px = bytes([255, 0, 0, 255] * 4)
        png = decode_vtex_c(build(4, 2, 2, px))
        self.assertEqual(png_size(png), (2, 2))
        self.assertEqual(png_pixels(png)[0][:4], bytes([255, 0, 0, 255]))

    def test_mip0_is_last(self):
        smallest = bytes([1, 1, 1, 255])
        mid = bytes([2, 2, 2, 255] * 4)
        big = bytes([9, 8, 7, 255] * 16)
        png = decode_vtex_c(build(4, 4, 4, smallest + mid + big, mips=3))
        self.assertEqual(png_pixels(png)[3][:4], bytes([9, 8, 7, 255]))

    def test_bgra_swaps_channels(self):
        png = decode_vtex_c(build(28, 1, 1, bytes([10, 20, 30, 255])))
        self.assertEqual(png_pixels(png)[0][:4], bytes([30, 20, 10, 255]))

    def test_bc1_solid_red(self):
        red565 = (31 << 11)
        block = struct.pack("<HHI", red565, 0, 0)       # all indices 0 -> colour0
        png = decode_vtex_c(build(1, 4, 4, block))
        self.assertEqual(png_size(png), (4, 4))
        self.assertEqual(png_pixels(png)[2][8:12], bytes([255, 0, 0, 255]))

    def test_bc3_alpha_and_colour(self):
        green565 = (63 << 5)
        block = bytes([128, 0]) + b"\x00" * 6 + struct.pack("<HHI", green565, 0, 0)
        png = decode_vtex_c(build(2, 4, 4, block))
        self.assertEqual(png_pixels(png)[0][:4], bytes([0, 255, 0, 128]))

    def test_embedded_png_returned_as_is(self):
        inner = encode_png(bytes([1, 2, 3, 255]) * 4, 2, 2)
        out = decode_vtex_c(build(16, 2, 2, inner))
        self.assertEqual(out, inner)

    def test_lz4_compressed_mip(self):
        full = bytes([5, 6, 7, 255] * 16)               # 4x4 RGBA = 64 bytes
        # LZ4 block: 4 literals then a long overlapping match (offset 4, length 60)
        block = bytes([(4 << 4) | 15]) + full[:4] + struct.pack("<H", 4) + bytes([60 - 4 - 15])
        self.assertEqual(lz4_block_decode(block, 64), full)
        png = decode_vtex_c(build(4, 4, 4, block, compressed=[len(block)], lz4=True))
        self.assertEqual(png_pixels(png)[1][:4], bytes([5, 6, 7, 255]))

    def test_extra_blocks_between_header_and_pixels_do_not_shift_the_decode(self):
        # real files carry other blocks (resource names, ...) before the pixels; ASCII there decodes as olive/yellow noise
        junk = b"panorama/images/econ/items/ursa/claws_png.vtex  RERL REDI " * 6
        for fmt, w, h, px, probe in (
            (4, 2, 2, bytes([10, 200, 30, 255]) * 4, bytes([10, 200, 30, 255])),
            (2, 4, 4, bytes([128, 0]) + b"\x00" * 6 + struct.pack("<HHI", (63 << 5), 0, 0), bytes([0, 255, 0, 128])),
        ):
            png = decode_vtex_c(build(fmt, w, h, px, trailer=junk))
            self.assertEqual(png_pixels(png)[0][:4], probe, fmt)

    def test_mip_chain_with_trailer_still_picks_mip0(self):
        smallest, mid, big = bytes([1, 1, 1, 255]), bytes([2, 2, 2, 255] * 4), bytes([9, 8, 7, 255] * 16)
        png = decode_vtex_c(build(4, 4, 4, smallest + mid + big, mips=3, trailer=b"XYZ" * 40))
        self.assertEqual(png_pixels(png)[3][:4], bytes([9, 8, 7, 255]))

    def test_unknown_format_returns_none_not_garbage(self):
        self.assertIsNone(decode_vtex_c(build(19, 4, 4, b"\x00" * 16)))
        self.assertIsNone(decode_vtex_c(b"not a texture at all......"))


class ReferenceCrossCheck(unittest.TestCase):
    """BC1/BC3 against Pillow's independent decoder on random blocks (skipped without Pillow)."""
    def test_matches_pillow(self):
        try:
            from PIL import Image
        except Exception:
            self.skipTest("Pillow not installed")
        import random
        from chameleon.vtex import decode_bc1, decode_bc3
        rnd = random.Random(5)
        for fn, bs, fid in ((decode_bc1, 8, 1), (decode_bc3, 16, 3)):
            for _ in range(60):
                data = bytes(rnd.getrandbits(8) for _ in range(4 * 4 * bs))
                ref = Image.frombytes("RGBA", (16, 16), data, "bcn", fid).tobytes()
                self.assertEqual(fn(data, 16, 16), ref)


if __name__ == "__main__":
    unittest.main()


class RealCompiledTextures(unittest.TestCase):
    """If real .vtex_c files are available (set CHAMELEON_REAL_VTEX to a folder) every one must decode and be well formed."""
    def test_real_files(self):
        import os, glob
        root = os.environ.get("CHAMELEON_REAL_VTEX")
        if not root:
            self.skipTest("set CHAMELEON_REAL_VTEX to a folder with real .vtex_c files")
        files = glob.glob(os.path.join(root, "**", "*.vtex_c"), recursive=True)
        self.assertTrue(files)
        for f in files:
            data = open(f, "rb").read()
            png = decode_vtex_c(data)
            self.assertIsNotNone(png, f)
            w, h = png_size(png)
            self.assertEqual((w, h), (VTex(data).width, VTex(data).height), f)
