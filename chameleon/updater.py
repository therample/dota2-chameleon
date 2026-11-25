"""Update check: compares the `version` file in the repository root with the one on GitHub (main branch)."""
import re
from pathlib import Path
from typing import Callable, Optional

from .common import APP_VERSION

VERSION_URL = "https://raw.githubusercontent.com/therample/dota2-chameleon/main/version"
RELEASES_URL = "https://github.com/therample/dota2-chameleon/releases/latest"


def parse(v: str) -> tuple:
    m = re.findall(r"\d+", str(v).strip().splitlines()[0] if str(v).strip() else "")
    return tuple(int(x) for x in m) or (0,)


def local_version() -> str:
    """The `version` file next to the program (project root); falls back to the built-in number."""
    try:
        f = Path(__file__).resolve().parent.parent / "version"
        t = f.read_text(encoding="utf-8").strip()
        if t:
            return t.splitlines()[0].strip()
    except OSError:
        pass
    return APP_VERSION


def _fetch(url: str) -> str:
    import requests
    r = requests.get(url, timeout=6, headers={"User-Agent": "Chameleon-update-check"})
    r.raise_for_status()
    return r.text


def check(fetch: Optional[Callable[[str], str]] = None, current: Optional[str] = None) -> dict:
    cur = current or local_version()
    out = {"available": False, "current": cur, "latest": "", "url": RELEASES_URL}
    try:
        latest = (fetch or _fetch)(VERSION_URL).strip().splitlines()[0].strip()
    except Exception:
        return out                                   # offline / no file yet: silently nothing
    out["latest"] = latest
    out["available"] = parse(latest) > parse(cur)
    return out
