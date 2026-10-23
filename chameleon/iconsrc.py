"""Qt-free icon lookup inside the game's VPKs (so it can be unit-tested)."""
import re
from typing import Tuple, Dict, List, Optional

from .vtex import decode_vtex_c

_STRIP_PREFIXES = ("s2r://", "panorama://", "file://")


def _clean(path: str) -> str:
    p = (path or "").replace("\\", "/").strip().lower()
    for pre in _STRIP_PREFIXES:
        if p.startswith(pre):
            p = p[len(pre):]
    p = p.lstrip("/")
    if p.startswith("panorama/images/"):
        p = p[len("panorama/images/"):]
    elif p.startswith("images/"):
        p = p[len("images/"):]
    for suf in (".vtex_c", "_png.png", "_jpg.jpg", ".png", ".jpg", ".vtex", "_png", "_jpg"):
        if p.endswith(suf):
            p = p[:-len(suf)]
            break
    return p


def candidates_from_inventory_path(icon_path: str) -> List[str]:
    """
    items_game's `image_inventory` is "econ/items/ursa/x/x" - NO extension. In the VPK the file is
    panorama/images/econ/items/ursa/x/x_png.vtex_c  (this is the lookup the old code never tried).
    """
    base = _clean(icon_path)
    if not base:
        return []
    out = []
    for suffix in ("_png", "_jpg", ""):
        out.append(f"panorama/images/{base}{suffix}.vtex_c")
    return out


def hero_candidates(short_name: str) -> List[str]:
    """Only the real portrait files. (Small minimap icons and crops were tried before and looked wrong.)"""
    sn = short_name.lower()
    return [f"panorama/images/heroes/{sn}_png.vtex_c",
            f"panorama/images/heroes/selection/npc_dota_hero_{sn}_png.vtex_c"]


def choose_icon_path(raw: dict, mode: str, fallback: str = "") -> str:
    """
    Which of the item's image fields is used as its icon.
      inventory (default): `image_inventory` ONLY - the item's own icon. Never falls back to a preview picture.
      auto:                image_inventory, then the other fields (can show a hero preview when there is no own icon).
      preview:             the big preview pictures first (hero wearing the item), then the own icon.
    """
    raw = raw or {}
    inv = str(raw.get("image_inventory") or "")
    preview = str(raw.get("image_large") or raw.get("image_store") or raw.get("image_inventory_wide")
                  or raw.get("image_browser") or "")
    others = str(raw.get("image_browser") or raw.get("icon") or raw.get("image_inventory_wide")
                 or raw.get("image_large") or raw.get("image_store") or "")
    if mode == "inventory":
        return inv
    if mode == "preview":
        return preview or inv
    return inv or others or fallback


class IconSource:
    def __init__(self, readers):
        self.readers = readers
        self._by_basename: Optional[Dict[str, str]] = None

    def _find(self, path: str):
        for r in self.readers:
            if path in r.files:
                return r
        return None

    def _folder_index(self) -> Dict[str, List[Tuple[str, str]]]:
        """folder -> [(file stem without _png/_jpg, full path)] for every picture in the game files."""
        if self._by_basename is None:
            idx: Dict[str, List[Tuple[str, str]]] = {}
            for r in self.readers:
                for p in r.files:
                    if p.startswith("panorama/images/") and p.endswith(".vtex_c"):
                        folder, _, name = p[:-len(".vtex_c")].rpartition("/")
                        for suf in ("_png", "_jpg"):
                            if name.endswith(suf):
                                name = name[:-len(suf)]
                        idx.setdefault(folder, []).append((name, p))
            self._by_basename = idx
        return self._by_basename

    def _same_folder_pick(self, base: str) -> Optional[str]:
        """
        The listed icon name can be old or slightly different from the real file (renamed files are common). Items live in their
        own folder, so look INSIDE that exact folder: the only picture there, or the closest name. Pictures from other
        folders are never used (that is what showed strange icons).
        """
        folder, _, stem = ("panorama/images/" + base).rpartition("/")
        files = self._folder_index().get(folder)
        if not files:
            return None
        if len(files) == 1:
            return files[0][1]
        import difflib
        best, score = None, 0.0
        for name, path in files:
            r = difflib.SequenceMatcher(None, stem, name).ratio() + (0.15 if "icon" in name else 0.0)
            if r > score:
                best, score = path, r
        return best if score >= 0.62 else None

    def _decode(self, path: str, reject_yellow: bool = False) -> Optional[bytes]:
        r = self._find(path)
        if r is None:
            return None
        raw = r.extract_to_bytes(path)
        if not raw:
            return None
        if raw[:4] == b"\x89PNG":
            return raw
        return decode_vtex_c(raw, reject_yellow=reject_yellow)

    def load(self, candidates: List[str], folder_base: str = "", reject_yellow: bool = False) -> Optional[bytes]:
        for c in candidates:
            png = self._decode(c, reject_yellow)
            if png:
                return png
        if folder_base and "/" in folder_base:
            hit = self._same_folder_pick(folder_base)
            if hit:
                return self._decode(hit, reject_yellow)
        return None

    def item_icon(self, icon_path: str, item_short: str = "", reject_cast: bool = False) -> Optional[bytes]:
        base = _clean(icon_path)
        return self.load(candidates_from_inventory_path(icon_path), base, reject_cast)

    def hero_icon(self, short_name: str, reject_cast: bool = True) -> Optional[bytes]:
        # hero art that decodes with a yellow cast is rejected -> the CDN portrait is used instead
        return self.load(hero_candidates(short_name), reject_yellow=reject_cast)
