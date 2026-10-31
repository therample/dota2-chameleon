"""
Discord Rich Presence (optional). Needs the `pypresence` package and a running Discord; without either it silently does nothing.
Updates go through a small worker thread (latest state wins, at most one update per `min_interval` seconds - Discord's limit is 15 s),
so the UI never waits for Discord.
"""
import threading
import time
from typing import Callable, Optional

from .common import log

CLIENT_ID = "1563628624442298510"
REPO_URL = "https://github.com/therample/dota2-chameleon"

TEXT = {
    "en": {"details": "Open Source", "button": "Download Chameleon", "home": "In the main menu", "heroes": "Browsing heroes",
           "hero": "Choosing skins for {x}", "extras": "Browsing the catalog", "world": "Changing the world",
           "favs": "Looking at favorites", "queue": "Reviewing the selection", "launch": "Setting up the launch",
           "presets": "Managing presets", "settings": "In the settings", "apply": "Building the mod"},
    "ru": {"details": "Open Source", "button": "Скачать Chameleon", "home": "В главном меню", "heroes": "Выбирает героя",
           "hero": "Выбирает скины для {x}", "extras": "Смотрит каталог", "world": "Меняет мир",
           "favs": "Смотрит избранное", "queue": "Проверяет выбор", "launch": "Настраивает запуск",
           "presets": "Работает с пресетами", "settings": "В настройках", "apply": "Собирает мод"},
}


class DiscordRPC:
    def __init__(self, presence_cls: Optional[Callable] = None, min_interval: float = 15.0, retry_interval: float = 30.0):
        self._cls = presence_cls
        self.min_interval, self.retry_interval = min_interval, retry_interval
        self.enabled = False
        self.lang = "en"
        self._state: Optional[str] = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._thread: Optional[threading.Thread] = None
        self._rpc = None
        self._start_time = time.time()
        self._last_sent = 0.0
        self._sent_state: Optional[str] = None

    # ---- public
    def configure(self, enabled: bool, lang: str = "en"):
        self.lang = lang if lang in TEXT else "en"
        if enabled and not self.enabled:
            self.enabled = True
            self._stop = False
            if not self._thread or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="discord-rpc", daemon=True)
                self._thread.start()
            self._wake.set()
        elif not enabled and self.enabled:
            self.enabled = False
            self._wake.set()

    def set_page(self, page: str, detail: str = ""):
        t = TEXT[self.lang]
        key = page if page in t else "home"
        state = t[key].format(x=detail) if "{x}" in t[key] else t[key]
        with self._lock:
            self._state = state
        self._wake.set()

    def stop(self):
        self._stop = True
        self.enabled = False
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=1.5)
        self._close()

    # ---- worker
    def _presence(self):
        cls = self._cls
        if cls is None:
            try:
                from pypresence import Presence as cls
            except Exception:
                return None
        return cls(CLIENT_ID)

    def _close(self):
        try:
            if self._rpc:
                self._rpc.close()
        except Exception:
            pass
        self._rpc = None

    def _send(self, state: str) -> bool:
        if self._rpc is None:
            rpc = self._presence()
            if rpc is None:
                return False
            rpc.connect()
            self._rpc = rpc
        t = TEXT[self.lang]
        self._rpc.update(state=state, details=t["details"], start=self._start_time, large_image="icon",
                         buttons=[{"label": t["button"], "url": REPO_URL}])
        return True

    def _run(self):
        retry_at = 0.0
        while not self._stop:
            self._wake.wait(timeout=2.0)
            self._wake.clear()
            if self._stop:
                break
            if not self.enabled:
                if self._rpc is not None:
                    self._close()
                    self._sent_state = None
                continue
            with self._lock:
                state = self._state or TEXT[self.lang]["home"]
            now = time.time()
            if state == self._sent_state or now < retry_at or now - self._last_sent < self.min_interval:
                if state != self._sent_state:
                    self._wake.set() if now >= retry_at else None
                    time.sleep(min(0.2, self.min_interval))
                continue
            try:
                if self._send(state):
                    self._sent_state, self._last_sent = state, time.time()
                else:
                    retry_at = time.time() + self.retry_interval       # pypresence missing
            except Exception as ex:                                   # Discord closed / not installed: try again later
                log.info("Discord RPC unavailable: %s", ex)
                self._close()
                retry_at = time.time() + self.retry_interval
        self._close()
