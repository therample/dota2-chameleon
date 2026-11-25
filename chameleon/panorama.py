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


# Classic containers (REDI + DATA) for the resources we write. The REDI blocks were recorded for these exact paths; only the 4-byte
# source CRC inside REDI depends on the text. This is the format the game accepts for Panorama sources (Valve's own newer files cannot
# be read back as text, so nothing is read from the game's layouts here).
TEMPLATES = {'panorama/layout/dashboard_background_last_match.vxml_c': 'rQEAAAwAAwAIAAAAAgAAAFJFREkUAAAAeAEAAERBVEGAAQAADQAAAFAAAAACAAAAAAAAAAAAAADUAAAAAQAAAAQBAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAKAEAAAEAAAAAAAAAAAAAAAAAAAAAAAAAIAAAAFEAAAAAAAAAAQAAAEoAAAB6AAAAEV7nTAIAAABwYW5vcmFtYS9sYXlvdXQvZGFzaGJvYXJkX2JhY2tncm91bmRfbGFzdF9tYXRjaC52eG1sAGRvdGEAcGFub3JhbWEvbGF5b3V0L2Rhc2hib2FyZF9iYWNrZ3JvdW5kX2xhc3RfbWF0Y2gueG1sAGRvdGEAABAAAAAkAAAAAAAAAAAAAABfX19PdmVycmlkZUlucHV0RGF0YV9fXwBCaW5hcnlCbG9iQXJnAAAAIAAAAAwAAAABAAAAAAAAAENvbXBpbGVQYW5vcmFtYQBQYW5vcmFtYSBMYXlvdXQgQ29tcGlsZXIgVmVyc2lvbgAAAAAIAAAAAAAAAElzQ2hpbGRSZXNvdXJjZQARXudMAAA8cm9vdC8+', 'panorama/layout/dashboard_background_manager.vxml_c': 'rQEAAAwAAwAIAAAAAgAAAFJFREkUAAAAeAEAAERBVEGAAQAADQAAAFAAAAACAAAAAAAAAAAAAADQAAAAAQAAAAABAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAKAEAAAEAAAAAAAAAAAAAAAAAAAAAAAAAIAAAAE4AAAAAAAAAAQAAAEcAAAB0AAAAEV7nTAIAAABwYW5vcmFtYS9sYXlvdXQvZGFzaGJvYXJkX2JhY2tncm91bmRfbWFuYWdlci52eG1sAGRvdGEAcGFub3JhbWEvbGF5b3V0L2Rhc2hib2FyZF9iYWNrZ3JvdW5kX21hbmFnZXIueG1sAGRvdGEAAAAAEAAAACQAAAAAAAAAAAAAAF9fX092ZXJyaWRlSW5wdXREYXRhX19fAEJpbmFyeUJsb2JBcmcAAAAgAAAADAAAAAEAAAAAAAAAQ29tcGlsZVBhbm9yYW1hAFBhbm9yYW1hIExheW91dCBDb21waWxlciBWZXJzaW9uAAAAAAAAAAAIAAAAAAAAAElzQ2hpbGRSZXNvdXJjZQARXudMAAA8cm9vdC8+', 'panorama/layout/dashboard.vxml_c': 'jQEAAAwAAwAIAAAAAgAAAFJFREkUAAAAUAEAAERBVEFgAQAADQAAAFAAAAACAAAAAAAAAAAAAACoAAAAAQAAANgAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAAEAAAAAAAAAAAAAAAAAAAAAAAAAIAAAADsAAAAAAAAAAQAAADQAAABOAAAAEV7nTAIAAABwYW5vcmFtYS9sYXlvdXQvZGFzaGJvYXJkLnZ4bWwAZG90YQBwYW5vcmFtYS9sYXlvdXQvZGFzaGJvYXJkLnhtbABkb3RhAAAQAAAAJAAAAAAAAAAAAAAAX19fT3ZlcnJpZGVJbnB1dERhdGFfX18AQmluYXJ5QmxvYkFyZwAAACAAAAAMAAAAAQAAAAAAAABDb21waWxlUGFub3JhbWEAUGFub3JhbWEgTGF5b3V0IENvbXBpbGVyIFZlcnNpb24AAAAAAAAAAAgAAAAAAAAASXNDaGlsZFJlc291cmNlAAAAAAAAAAAAEV7nTAAAPHJvb3QvPg=='}
CRC_AT = {'panorama/layout/dashboard_background_last_match.vxml_c': 104, 'panorama/layout/dashboard_background_manager.vxml_c': 104, 'panorama/layout/dashboard.vxml_c': 104}


def build(path: str, text: str) -> bytes:
    import base64
    head, blocks = read_blocks(base64.b64decode(TEMPLATES[path]))
    raw = text.encode("utf-8")
    crc = struct.pack("<I", zlib.crc32(raw) & 0xFFFFFFFF)
    at = CRC_AT[path]
    out_blocks = []
    for name, b in blocks:
        if name == b"REDI":
            b = b[:at] + crc + b[at + 4:]
        elif name == b"DATA":
            b = crc + b"\x00\x00" + raw
        out_blocks.append((name, b))
    out = bytearray(16 + 12 * len(out_blocks))
    pos, entries = len(out), []
    for name, b in out_blocks:
        pos = (pos + 7) & ~7
        entries.append((name, pos, len(b)))
        out.extend(b"\x00" * (pos - len(out)))
        out.extend(b)
        pos = len(out)
    out[0:16] = head
    struct.pack_into("<I", out, 0, len(out))
    struct.pack_into("<II", out, 8, 8, len(out_blocks))
    for i, (name, off, ln) in enumerate(entries):
        e = 16 + 12 * i
        out[e:e + 4] = name
        struct.pack_into("<II", out, e + 4, off - (e + 4), ln)
    return bytes(out)


MENU_DIR = "d2chameleon"
MENU_VIDEO = MENU_DIR + "/menu_background.webm"
LAST_MATCH = "panorama/layout/dashboard_background_last_match.vxml_c"
MANAGER = "panorama/layout/dashboard_background_manager.vxml_c"

# The main-menu background is the "last match" dashboard background with the scene hidden and a video behind the buttons
# (not in the hero view). The text mirrors Valve's layout; the 2 %s are the blur style and the dim alpha.
LAST_MATCH_XML = '<root>\n    <styles>\n        <include src="s2r://panorama/styles/dotastyles.vcss" />\n        <include src="s2r://panorama/styles/dashboard_background_last_match.vcss" />\n        <include src="s2r://panorama/styles/dashboard_background_last_match_heroscale.vcss" />\n    </styles>\n    <DOTADashboardBackgroundLastMatch>\n        <DOTAScenePanel id="BackgroundScene" map="scenes/dashboard_background/dashboard_background_last_match_radiant" camera="versus_camera" light="versus_light" deferredalpha="false" renderdeferred="true" particleonly="false" style="visibility: collapse;" />\n        <MoviePanel id="ChameleonBackground" src="s2r://d2chameleon/menu_background.webm" repeat="true" autoplay="onload" hittest="false" style="width: 100%%; height: 100%%; horizontal-align: center; vertical-align: center;%s" />\n        <Panel id="ChameleonBackgroundDim" hittest="false" style="width: 100%%; height: 100%%; horizontal-align: center; vertical-align: center; background-color: #000000%s;" />\n        <Panel class="BackgroundFadeOverlay" hittest="false" style="visibility: collapse;" />\n        <Panel id="BGVignette" hittest="false" style="visibility: collapse;" />\n        <Panel id="DetailsContainer" style="visibility: collapse;">\n            <Label class="LastMatchTitle" text="#DOTA_Background_LastMatch_Title" />\n            <Label class="HeroName" text="{g:dota_hero_name:hero_id}" />\n            <Panel class="MatchInfo">\n                <Label id="Win" class="MatchOutcome Green" text="#dota_profile_recent_game_result_win" />\n                <Label id="Loss" class="MatchOutcome Red" text="#dota_profile_recent_game_result_loss" />\n                <Label id="NotScored" class="MatchOutcome" text="#dota_profile_recent_game_result_notscored" />\n                <Label class="KDALabel" text="#DOTA_Background_LastMatch_KDA" />\n                <Label class="KDA" text="{i:kills} / {i:deaths} / {i:assists}" />\n            </Panel>\n            <Panel id="Items">\n                <DOTAItemImage id="Item0" class="ItemImage" />\n                <DOTAItemImage id="Item1" class="ItemImage" />\n                <DOTAItemImage id="Item2" class="ItemImage" />\n                <DOTAItemImage id="Item3" class="ItemImage" />\n                <DOTAItemImage id="Item4" class="ItemImage" />\n                <DOTAItemImage id="Item5" class="ItemImage" />\n            </Panel>\n            <TextButton id="ViewDetailsButton" text="#DOTA_Background_LastMatch_ViewMatch" onactivate="DOTAShowLastMatchDetails()" />\n        </Panel>\n        <TextButton text="(DEBUG) Reset" id="DebugResetButton" onactivate="DOTABackgroundLastMatchDebugReset()" style="visibility: collapse;" />\n        <Panel id="MissingDataContainer" style="visibility: collapse;">\n            <Label class="MissingDataTitle" text="#DOTA_Background_LastMatch_WelcomeToDota" />\n        </Panel>\n    </DOTADashboardBackgroundLastMatch>\n</root>\n'
MANAGER_XML = '<root>\n    <styles>\n        <include src="s2r://panorama/styles/dotastyles.vcss" />\n        <include src="s2r://panorama/styles/dashboard_background_manager.vcss" />\n    </styles>\n    <DOTADashboardBackgroundManager override-background="DOTADashboardBackgroundLastMatch" />\n</root>\n'


def menu_files(blur: int = 0, dim: int = 10) -> dict:
    """{path: compiled bytes} for the menu background; blur 0-30 (gaussian), dim 0-90 percent."""
    blur = max(0, min(30, int(blur)))
    alpha = max(0, min(255, round(max(0, min(90, int(dim))) * 255 / 100)))
    last = LAST_MATCH_XML % ((" blur: gaussian(%d);" % blur) if blur else "", "%02x" % alpha)
    return {LAST_MATCH: build(LAST_MATCH, last), MANAGER: build(MANAGER, MANAGER_XML)}
