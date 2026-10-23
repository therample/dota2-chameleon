"""
dota.signatures support (ported from Dota2 Mod Manager's patcher-signatures.ts).

Why: the client checks game/dota/gameinfo_branchspecific.gi against the hashes in game/bin/win64/dota.signatures.
After the mod folder is registered in that .gi file the hash no longer matches Valve's entry, which can block online
matchmaking ("verify integrity of game files"). Mod managers therefore append ONE line after the DIGEST line with the
SHA1+CRC of the patched file, and take it off again on restore. This module does exactly that, nothing else:
  * only the line for gameinfo_branchspecific.gi is ever added or removed;
  * Valve's own entry (before DIGEST) is never touched;
  * the pristine signature list is backed up once.
Windows only (Valve ships no dota.signatures on Linux).
"""
import hashlib
import re
import zlib
from pathlib import Path
from typing import Optional, Tuple

SIG_PREFIX = "...\\..\\..\\dota\\gameinfo_branchspecific.gi"


def fileHashes(data: bytes) -> Tuple[str, str]:
    """(SHA1 uppercase hex, CRC32 little-endian uppercase hex) exactly as the signature list writes them."""
    sha1 = hashlib.sha1(data).hexdigest().upper()
    crc = (zlib.crc32(data) & 0xFFFFFFFF).to_bytes(4, "little").hex().upper()
    return sha1, crc


def signature_line(data: bytes) -> str:
    sha1, crc = fileHashes(data)
    return f"{SIG_PREFIX}~SHA1:{sha1};CRC:{crc}"


def _split(text: str):
    lines = text.splitlines()
    digest = next((i for i, l in enumerate(lines) if l.startswith("DIGEST:")), -1)
    return lines, digest


def has_patch(text: str) -> bool:
    lines, digest = _split(text)
    return digest != -1 and any(l.startswith(SIG_PREFIX + "~") for l in lines[digest + 1:])


def strip_patch(text: str) -> str:
    lines, digest = _split(text)
    if digest == -1:
        return text
    kept = [l for i, l in enumerate(lines) if i <= digest or not l.startswith(SIG_PREFIX + "~")]
    while kept and not kept[-1].strip():
        kept.pop()
    return "\r\n".join(kept) + "\r\n"


def add_patch(text: str, data: bytes) -> str:
    base = strip_patch(text)
    lines, digest = _split(base)
    if digest == -1:
        raise ValueError("dota.signatures has no DIGEST line - format changed, not touching it")
    return base.rstrip("\r\n") + "\r\n" + signature_line(data) + "\r\n"


def vanilla_hashes(text: str) -> Optional[Tuple[str, str]]:
    """Valve's own recorded hashes for the file (entry BEFORE the DIGEST line)."""
    lines, digest = _split(text)
    scope = lines if digest == -1 else lines[:digest]
    for l in scope:
        m = re.search(r"gameinfo_branchspecific\.gi~SHA1:([0-9A-Fa-f]{40});CRC:([0-9A-Fa-f]{8})\s*$", l)
        if m:
            return m.group(1).upper(), m.group(2).upper()
    return None


class SignatureManager:
    def __init__(self, dota_path: Path, backup_dir: Path):
        self.path = Path(dota_path) / "game" / "bin" / "win64" / "dota.signatures"
        self.backup = Path(backup_dir) / "dota.signatures.orig"

    def available(self) -> bool:
        return self.path.exists()

    def _read(self) -> str:
        return self.path.read_bytes().decode("latin1")

    def _write(self, text: str):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_bytes(text.encode("latin1"))
        tmp.replace(self.path)

    def is_patched(self) -> bool:
        return self.available() and has_patch(self._read())

    def patch(self, branch_file_bytes: bytes) -> bool:
        """Record the hashes of the (already patched) gameinfo_branchspecific.gi. Returns False if nothing could be done."""
        if not self.available():
            return False
        text = self._read()
        if not self.backup.exists():
            self.backup.parent.mkdir(parents=True, exist_ok=True)
            self.backup.write_bytes(strip_patch(text).encode("latin1"))
        try:
            self._write(add_patch(text, branch_file_bytes))
        except ValueError:
            return False
        return True

    def restore(self) -> bool:
        if not self.available():
            return True
        text = self._read()
        if has_patch(text):
            self._write(strip_patch(text))
        return True
