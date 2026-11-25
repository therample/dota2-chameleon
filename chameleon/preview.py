"""Audio preview for music packs and announcers: finds a sound file of the pack in the game files and pulls the audio out of it."""
import re
from typing import Iterable, List, Optional, Tuple

MAX_BYTES = 6 * 1024 * 1024


def extract_audio(data: bytes) -> Optional[Tuple[str, bytes]]:
    """Valve .vsnd_c keeps the encoded audio (mp3 / wav / ogg) inside; find its signature."""
    if not data:
        return None
    for sig, mime in ((b"OggS", "audio/ogg"), (b"ID3", "audio/mpeg")):
        i = data.find(sig)
        if i >= 0:
            return mime, data[i:i + MAX_BYTES]
    i = data.find(b"RIFF")
    if i >= 0 and data[i + 8:i + 12] == b"WAVE":
        return "audio/wav", data[i:i + MAX_BYTES]
    if data.find(b"fLaC") >= 0:
        i = data.find(b"fLaC")
        return "audio/flac", data[i:i + MAX_BYTES]
    # raw MPEG frames: a sync word followed by a second valid frame header at the length the first one announces
    for m in re.finditer(rb"\xff[\xe2-\xff]", data[16:65536]):
        i = 16 + m.start()
        h = data[i:i + 4]
        if len(h) == 4 and (h[1] & 0x18) != 0x08 and (h[1] & 0x06) != 0 and (h[2] >> 4) not in (0, 15) and ((h[2] >> 2) & 3) != 3:
            br = (32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)[max(0, min(13, (h[2] >> 4) - 1))] * 1000
            sr = (44100, 48000, 32000)[(h[2] >> 2) & 3]
            ln = int(144 * br / sr) + ((h[2] >> 1) & 1)
            nxt = data[i + ln:i + ln + 2]
            if len(nxt) == 2 and nxt[0] == 0xFF and (nxt[1] & 0xE0) == 0xE0:
                return "audio/mpeg", data[i:i + MAX_BYTES]
    return None


def pick_file(paths: Iterable[str]) -> Optional[str]:
    c: List[str] = sorted(p for p in paths if p.endswith(".vsnd_c"))
    if not c:
        return None
    # never the first file by name: that is often "... are battlecup champions"; prefer a neutral, representative line
    skip = ("battlecup", "champion", "wins", "victory", "defeat", "ancient_destroyed", "tournament", "winner")
    good = [p for p in c if not any(x in p.rsplit("/", 1)[-1] for x in skip)] or c
    for want in ("menu", "main", "theme", "battle", "welcome", "hello", "ready", "start", "firstblood", "first_blood", "killing", "streak", "01"):
        for p in good:
            if want in p.rsplit("/", 1)[-1]:
                return p
    return good[len(good) // 2]


def find_sound(files: Iterable[str], kind: str, pack_names: Iterable[str]) -> Optional[str]:
    files = list(files)
    for pn in [p.lower() for p in pack_names if p]:
        if kind == "music":
            hit = pick_file(f for f in files if f.startswith("sounds/music/") and f"/{pn}/" in f"/{f[len('sounds/music/'):]}")
        else:
            hit = pick_file(f for f in files if f.startswith("sounds/vo/") and (f"/{pn}/" in f or pn in f.split("/")[2] if f.count("/") > 2 else False))
        if hit:
            return hit
    return None
