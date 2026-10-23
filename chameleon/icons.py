from .qt import *
from .common import *
from .vpk_io import *
from .models import *
from .iconsrc import IconSource

# ==============================================================================
# ICON MANAGER
#
# Threading: QPixmap lives in the GUI thread only. The worker thread produces PNG BYTES; results travel through a Qt
# signal to the _Hub (GUI thread) which decodes, caches and notifies the page.
#
# Settings (Settings > Icons):
#   source : applies to HERO pictures. auto = Steam CDN first, then game files | game = game files only | cdn = Steam CDN only
#            Item icons always come from the game files (the CDN does not serve them).
#   cast   : hero pictures read from the game files that have a yellow cast are rejected
# The disk cache file name contains the profile, so changing a setting never shows icons made under another one.
# ==============================================================================

HERO_CDN = ["https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/{short}.png",
            "https://cdn.akamai.steamstatic.com/apps/dota2/images/dota_react/heroes/{short}.png"]


class _Worker(QThread):
    done = Signal(str, bytes)          # cache_key, png bytes (empty = not found in the VPKs)

    def __init__(self, readers):
        super().__init__()
        self.source = IconSource(readers)
        self.queue: List[tuple] = []
        self.mutex = QMutex()
        self.cond = QWaitCondition()
        self.running = True

    def add(self, task: tuple):
        self.mutex.lock()
        self.queue.append(task)
        self.cond.wakeAll()
        self.mutex.unlock()

    def clear_queue(self):
        self.mutex.lock()
        self.queue.clear()
        self.mutex.unlock()

    def stop(self):
        self.running = False
        self.cond.wakeAll()

    def run(self):
        while self.running:
            self.mutex.lock()
            if not self.queue:
                self.cond.wait(self.mutex, 400)
            task = self.queue.pop(0) if self.queue else None
            self.mutex.unlock()
            if task is None:
                continue
            kind, key, a, b, cast = task
            try:
                png = self.source.hero_icon(a, cast) if kind == "hero" else self.source.item_icon(a, b, False)
            except Exception as e:
                log.error("icon worker %s: %s", key, e)
                png = None
            self.done.emit(key, png or b"")


class _Hub(QObject):
    icon_ready = Signal(str, str)      # cache_key, base64 png (scaled)

    def __init__(self):
        super().__init__()
        self.cache: Dict[str, QPixmap] = {}
        self.pending: Set[str] = set()
        self.worker: Optional[_Worker] = None
        self.nam = QNetworkAccessManager(self)
        self.stats = {"requested": 0, "from_vpk": 0, "from_cdn": 0, "from_disk": 0, "missing": 0}
        self.paths: Dict[str, str] = {}
        self.replies: List[QNetworkReply] = []
        self.source = "auto"
        self.cast = True

    @property
    def profile(self) -> str:
        return f"{self.source}{int(self.cast)}"

    def reset(self):
        self.cache.clear()
        self.pending.clear()
        self.paths.clear()
        for r in list(self.replies):
            r.abort()
        self.replies.clear()
        if self.worker:
            self.worker.clear_queue()

    # ---- helpers (GUI thread only)
    @staticmethod
    def to_b64(pm: QPixmap, size: int = 128) -> str:
        if pm.isNull():
            return ""
        scaled = pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        buf = QByteArray()
        qb = QBuffer(buf)
        qb.open(QIODevice.OpenModeFlag.WriteOnly)
        scaled.save(qb, "PNG")
        return base64.b64encode(bytes(buf.data())).decode("ascii")

    def file_for(self, key: str) -> Path:
        return ICONS_DIR / f"v5_{self.profile}_{key}.png"

    def _store(self, key: str, data: bytes) -> bool:
        pm = QPixmap()
        if not data or not pm.loadFromData(data) or pm.isNull():
            return False
        self.cache[key] = pm
        try:
            self.file_for(key).write_bytes(data)
        except OSError:
            pass
        self.pending.discard(key)
        self.icon_ready.emit(key, self.to_b64(pm))
        return True

    def from_disk(self, key: str) -> Optional[QPixmap]:
        f = self.file_for(key)
        if f.exists() and f.stat().st_size > 100:
            pm = QPixmap(str(f))
            if not pm.isNull():
                self.cache[key] = pm
                return pm
        return None

    # ---- worker result
    @Slot(str, bytes)
    def on_worker_done(self, key: str, data: bytes):
        if data and self._store(key, data):
            self.stats["from_vpk"] += 1
            return
        self.stats["missing"] += 1
        self.pending.discard(key)          # nothing found: the page shows its own placeholder

    def cdn_for(self, key: str, then_game=None):
        """Hero portraits only. `then_game` is called when the CDN has nothing (or is unreachable)."""
        if not key.startswith("hero_"):
            if then_game:
                then_game()
            return
        self._cdn(key, [u.format(short=key[len("hero_"):]) for u in HERO_CDN], then_game)

    def _cdn(self, key: str, urls: List[str], then_game=None):
        if not urls:
            if then_game:
                then_game()
            else:
                self.stats["missing"] += 1
                self.pending.discard(key)
            return
        req = QNetworkRequest(QUrl(urls[0]))
        req.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, f"Chameleon/{APP_VERSION}")
        reply = self.nam.get(req)
        self.replies.append(reply)
        profile = self.profile

        def finished():
            data = bytes(reply.readAll())
            if reply in self.replies:
                self.replies.remove(reply)
            reply.deleteLater()
            if profile != self.profile:                # settings changed while downloading: drop the result
                return
            if self._store(key, data):
                self.stats["from_cdn"] += 1
            else:
                self._cdn(key, urls[1:], then_game)
        reply.finished.connect(finished)


class IconManager:
    hub: Optional[_Hub] = None

    @classmethod
    def _hub(cls) -> _Hub:
        if cls.hub is None:
            cls.hub = _Hub()
        return cls.hub

    @classmethod
    def configure(cls, source: str = "auto", cast: bool = True) -> bool:
        """Apply the icon settings. Returns True when they changed (the page must re-request its icons)."""
        hub = cls._hub()
        source = source if source in ("auto", "game", "cdn") else "auto"
        changed = (source != hub.source) or (bool(cast) != hub.cast)
        hub.source, hub.cast = source, bool(cast)
        if changed:
            hub.reset()
        return changed

    @classmethod
    def profile(cls) -> str:
        return cls._hub().profile

    @classmethod
    def clear_disk_cache(cls) -> int:
        n = 0
        for f in ICONS_DIR.glob("v*_*.png"):
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
        cls._hub().reset()
        return n

    @classmethod
    def set_vpk_readers(cls, readers: List[VPKReader]):
        hub = cls._hub()
        if readers and hub.worker is None:
            hub.worker = _Worker(readers)
            hub.worker.done.connect(hub.on_worker_done)      # queued: hub lives in the GUI thread
            hub.worker.start()

    @classmethod
    def stats(cls) -> dict:
        h = cls._hub()
        return dict(h.stats, source=h.source, cast=h.cast)

    @classmethod
    def stop_worker(cls):
        if cls.hub and cls.hub.worker:
            cls.hub.worker.stop()
            cls.hub.worker.wait(2000)

    @classmethod
    def request(cls, kind: str, name: str, icon_path: str = "", size: int = 128) -> Tuple[str, str]:
        """Returns (cache_key, base64 or ''). When '' is returned the icon arrives later via icon_ready."""
        hub = cls._hub()
        if kind == "hero":
            short = name.replace("npc_dota_hero_", "")
            key = f"hero_{short}"
            task = ("hero", key, short, "", hub.cast)
        else:
            key = "item_" + re.sub(r"[^a-zA-Z0-9_]", "_", name)
            task = ("item", key, icon_path or "", name, hub.cast)
        pm = hub.cache.get(key) or hub.from_disk(key)
        if pm is not None:
            hub.stats["from_disk"] += 1
            return key, hub.to_b64(pm, size)
        hub.stats["requested"] += 1
        if key in hub.pending:
            return key, ""
        hub.pending.add(key)
        send_to_game = lambda: hub.worker.add(task) if hub.worker else (hub.stats.__setitem__("missing", hub.stats["missing"] + 1), hub.pending.discard(key))
        if kind == "hero" and hub.source in ("auto", "cdn"):
            # portraits: Steam CDN first (always the right picture), game files only as the fallback
            hub.cdn_for(key, send_to_game if hub.source == "auto" else None)
        else:
            send_to_game()
        return key, ""
