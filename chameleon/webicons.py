"""
Item pictures from Steam's web servers: the market search finds the item by its name and returns an icon id that the Steam CDN serves.
Results (also misses) are cached on disk, requests are spaced out (the market search is rate limited) and everything fails quietly:
the interface then simply keeps the picture from the game files or the placeholder.
"""
import json
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote

SEARCH = "https://steamcommunity.com/market/search/render/"
IMAGE = "https://community.cloudflare.steamstatic.com/economy/image/{icon}/{size}"
MIN_GAP = 1.6                   # seconds between two market searches


def icon_url_from_search(data: dict, name: str, size: str = "256x256") -> Optional[str]:
    """Exact market_hash_name match first, otherwise the first result only when its name is the same ignoring case."""
    if not isinstance(data, dict) or not data.get("success") or not data.get("results"):
        return None
    want = name.strip().lower()
    for item in data["results"]:
        asset = item.get("asset_description", {}) or {}
        icon = asset.get("icon_url")
        if icon and str(asset.get("market_hash_name", "")).strip().lower() == want:
            return IMAGE.format(icon=icon, size=size)
    return None


class MarketIcons:
    def __init__(self, cache_file: Path, fetch_json: Optional[Callable[[str, dict], dict]] = None,
                 fetch_bytes: Optional[Callable[[str], bytes]] = None, sleep: Callable[[float], None] = time.sleep):
        self.cache_file = Path(cache_file)
        self.fetch_json, self.fetch_bytes, self.sleep = fetch_json or self._get_json, fetch_bytes or self._get_bytes, sleep
        self.lock = threading.Lock()
        self.last = 0.0
        try:
            self.urls = json.loads(self.cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.urls = {}

    @staticmethod
    def _get_json(url: str, params: dict) -> dict:
        import requests
        r = requests.get(url, params=params, timeout=10, headers={"User-Agent": "Chameleon"})
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _get_bytes(url: str) -> bytes:
        import requests
        r = requests.get(url, timeout=12, headers={"User-Agent": "Chameleon"})
        r.raise_for_status()
        return r.content

    def _save(self):
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps(self.urls), encoding="utf-8")
        except OSError:
            pass

    def url_for(self, name: str) -> Optional[str]:
        name = (name or "").strip()
        if not name:
            return None
        with self.lock:
            if name in self.urls:
                return self.urls[name] or None
            gap = MIN_GAP - (time.time() - self.last)
            if gap > 0:
                self.sleep(gap)
            self.last = time.time()
            try:
                data = self.fetch_json(SEARCH, {"query": name, "appid": 570, "norender": 1, "count": 10})
            except Exception:
                return None                                   # offline / rate limited: do not cache, try again later
            self.urls[name] = icon_url_from_search(data, name) or ""
            self._save()
            return self.urls[name] or None

    def image_for(self, name: str) -> Optional[bytes]:
        url = self.url_for(name)
        if not url:
            return None
        try:
            return self.fetch_bytes(url) or None
        except Exception:
            return None
