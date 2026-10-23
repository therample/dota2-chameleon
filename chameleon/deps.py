"""Reads compiled Source 2 resources out of the game's VPKs and follows their references."""
import re
from typing import Dict, List, Optional, Set, Tuple

from .common import *
from .vpk_io import VPKReader

# Every external reference type that can appear inside a compiled resource (RERL block / KV3 text).
# `.vsnap` (particle snapshots used by models for finger/weapon effects) was missing before, which is
# one reason some items had no effects when dependencies were packed.
REF_EXTS = ("vpcf", "vmdl", "vmat", "vtex", "vanim", "vagrp", "vseq", "vsnap", "vmesh", "vphys",
            "vmorf", "vsndevts", "vsnd", "vpost", "vsndstck", "vsurf", "vcompmat", "vrman", "vxml", "vcss",
            "vjs", "vsvg")
_REF_RE = re.compile(rb"([A-Za-z0-9_\-./]{4,}?\.(?:" + "|".join(REF_EXTS).encode() + rb"))(?:_c)?(?![A-Za-z0-9_])")

JUNK_SEGMENTS = ("/test/", "/_test/", "/debug/", "/_debug/", "/temp/", "/_temp/", "/wip/", "/_wip/")


class BaseIndex:
    """path -> reader over all game VPKs (first reader wins, like the game's own search order)."""

    def __init__(self, readers: List[VPKReader]):
        self.readers = readers
        self.map: Dict[str, VPKReader] = {}
        for r in readers:
            for p in r.files:
                self.map.setdefault(p, r)

    def resolve(self, path: str) -> Optional[str]:
        """Real path inside the VPKs for a logical path (`.vpcf` -> `.vpcf_c`), or None."""
        p = path.lower().replace("\\", "/").lstrip("/")
        if p in self.map:
            return p
        if not p.endswith("_c") and (p + "_c") in self.map:
            return p + "_c"
        return None

    def read(self, path: str) -> Optional[Tuple[str, bytes]]:
        real = self.resolve(path)
        if not real:
            return None
        data = self.map[real].extract_to_bytes(real)
        return (real, data) if data else None


def scan_refs(data: bytes) -> Set[str]:
    refs = set()
    for m in _REF_RE.finditer(data):
        s = m.group(1).decode("ascii", "ignore").lower()
        if "/" in s:
            refs.add(s)
    return refs


def walk(index: BaseIndex, roots, max_depth: int = 40, max_files: int = 4000) -> Tuple[Dict[str, bytes], Set[str]]:
    """Compiled files reachable from `roots` (logical paths). Returns (files, unresolved_refs)."""
    files: Dict[str, bytes] = {}
    missing: Set[str] = set()
    seen: Set[str] = set()
    stack = [(r, 0) for r in roots]
    while stack and len(files) < max_files:
        path, depth = stack.pop()
        if path in seen or depth > max_depth:
            continue
        seen.add(path)
        if any(j in path for j in JUNK_SEGMENTS):
            continue
        got = index.read(path)
        if not got:
            missing.add(path)
            continue
        real, data = got
        files[real] = data
        if real.endswith("_c"):
            for ref in scan_refs(data):
                if ref not in seen:
                    stack.append((ref, depth + 1))
    return files, missing
