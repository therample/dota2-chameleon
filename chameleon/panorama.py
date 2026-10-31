"""
Compiled Panorama resources (.vxml_c / .vcss_c / .vjs_c) are a small container whose DATA block holds the SOURCE TEXT:
  uint32 crc32(text) | uint16 0 (no image table) | text
So a layout can be read out of the game, changed as text and written back; no Valve compiler is needed and the result follows
the game's own current layout (robust against updates). All other blocks (REDI/RED2 ...) are kept as they are.
Container: uint32 file size | u16 header version | u16 resource version | u32 table offset (from this field) | u32 block count,
then 12-byte entries: name(4) | u32 offset (from the offset field + 4... i.e. relative to the entry's second word) | u32 size.
"""
import struct
import zlib
from typing import List, Tuple


class PanoramaError(ValueError):
    pass


def read_blocks(data: bytes) -> Tuple[bytes, List[Tuple[bytes, bytes]]]:
    if len(data) < 16:
        raise PanoramaError("file too short")
    size, hv, rv, table_rel, count = struct.unpack_from("<IHHII", data, 0)
    if count < 1 or count > 32:
        raise PanoramaError("unexpected block count")
    table = 8 + table_rel
    blocks = []
    for i in range(count):
        at = table + 12 * i
        name = data[at:at + 4]
        off, ln = struct.unpack_from("<II", data, at + 4)
        start = at + 4 + off
        if start < 0 or start + ln > len(data):
            raise PanoramaError("block outside the file")
        blocks.append((name, data[start:start + ln]))
    return data[:16], blocks


def get_source(data: bytes) -> str:
    _h, blocks = read_blocks(data)
    for name, body in blocks:
        if name == b"DATA":
            if len(body) < 6 or struct.unpack_from("<H", body, 4)[0] != 0:
                raise PanoramaError("DATA block has an image table / unknown layout")
            return body[6:].decode("utf-8")
    raise PanoramaError("no DATA block")


def set_source(template: bytes, text: str) -> bytes:
    """The template's container with its DATA text replaced by `text` (any other resource of the same kind works as a template)."""
    head, blocks = read_blocks(template)
    raw = text.encode("utf-8")
    body = struct.pack("<IH", zlib.crc32(raw) & 0xFFFFFFFF, 0) + raw
    blocks = [(n, body if n == b"DATA" else b) for n, b in blocks]
    if not any(n == b"DATA" for n, _ in blocks):
        raise PanoramaError("template has no DATA block")
    table_len = 12 * len(blocks)
    out = bytearray(16 + table_len)
    pos = len(out)
    entries = []
    for name, b in blocks:
        pos = (pos + 15) & ~15
        entries.append((name, pos, len(b)))
        out.extend(b"\x00" * (pos - len(out)))
        out.extend(b)
        pos = len(out)
    out[0:16] = head
    struct.pack_into("<I", out, 0, len(out))
    struct.pack_into("<II", out, 8, 8, len(blocks))          # table right after the 16-byte header
    for i, (name, off, ln) in enumerate(entries):
        at = 16 + 12 * i
        out[at:at + 4] = name
        struct.pack_into("<II", out, at + 4, off - (at + 4), ln)
    return bytes(out)


MENU_LAYOUT = "panorama/layout/chameleon_background.vxml_c"
MENU_STYLE = "panorama/styles/chameleon_background.vcss_c"
MENU_VIDEO = "panorama/videos/chameleon_background.webm"

LAYOUT_XML = ('<root><styles><include src="s2r://panorama/styles/dotastyles.vcss_c" />'
              '<include src="s2r://%s" /></styles>'
              '<Panel class="ChameleonBg" hittest="false">'
              '<MoviePanel id="ChameleonBgMovie" src="s2r://%s" repeat="true" autoplay="onload" hittest="false" />'
              '</Panel></root>' % (MENU_STYLE, MENU_VIDEO))
STYLE_CSS = (".ChameleonBg { width: 100%; height: 100%; background-color: black; }\n"
             "#ChameleonBgMovie { width: 100%; height: 100%; }\n")
