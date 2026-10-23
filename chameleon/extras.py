from .common import *
import hashlib
from .itemdef import add_particle_modifier, copy_particle_modifiers, resolve_prefabs, flatten_style
from .kv import kv_base
from .itemdef import is_modifier_key
from .vpk_io import *
from .kv import *
from .models import *
from .resolver import *
# ==============================================================================
# RIVER COLOR VPK BUILDER
# ==============================================================================

class RiverColorVPKBuilder:
    """
    River look = one of the game's OWN water materials. Dota's river vials are materials/water/water_econ_dota_*.vmat_c
    (electrified, slime, oil, chrome, potion ...) and water_dota_blood.vmat_c; the default river is
    materials/water/water_generic_*.vmat_c. Choosing a colour copies the chosen vial material over the default one(s).
    Nothing is invented or byte-patched: only files that exist in the game are used.
    """
    DEFAULT_PREFIX = "materials/water/water_generic_"
    VIAL_PREFIXES = ("materials/water/water_econ_dota_", "materials/water/water_dota_")

    def __init__(self, vpk_readers: List[VPKReader]):
        self.vpk_readers = vpk_readers
        self.color = ""                  # "" = default, else a key from options()
        self._opts: Optional[Dict[str, str]] = None

    def options(self) -> Dict[str, str]:
        if self._opts is None:
            found: Dict[str, str] = {}
            for r in self.vpk_readers:
                for fp in r.files:
                    if fp.endswith(".vmat_c") and fp.startswith(self.VIAL_PREFIXES):
                        key = fp.rsplit("/", 1)[-1][:-len(".vmat_c")]
                        for pre in ("water_econ_dota_", "water_dota_"):
                            if key.startswith(pre):
                                key = key[len(pre):]
                        found.setdefault(key, fp)
            self._opts = found
        return self._opts

    def default_materials(self) -> List[str]:
        """Every water material that is not a vial: water_generic_* (incl. the slope variant) and any other base water
        material a map may use. Replacing only one family was why the river was applied on some maps and not on others."""
        vials = set(self.options().values())
        out = set()
        for r in self.vpk_readers:
            for fp in r.files:
                if fp.startswith("materials/water/") and fp.endswith(".vmat_c") and fp not in vials \
                        and "econ" not in fp and "/water_dota_" not in fp:
                    out.add(fp)
        return sorted(out)

    def set_color(self, name: str):
        self.color = name if name in self.options() else ""

    def clear(self):
        self.color = ""

    def add_to(self, builder: 'VPKBuilder') -> int:
        if not self.color or self.color not in self.options():
            return 0
        src = self.options()[self.color]
        data = None
        for r in self.vpk_readers:
            if src in r.files:
                data = r.extract_to_bytes(src)
                break
        if not data:
            return 0
        targets = self.default_materials() or [src]
        for t in targets:
            builder.add_data(data, t)
        return len(targets)

# ==============================================================================
# BACKGROUND VPK BUILDER
# ==============================================================================

class BackgroundVPKBuilder:
    """
    Custom MAIN-MENU background video, done the way h6rd/BackgroundChanger and dota2-minify do it: the dashboard layout
    is replaced by layout files whose <Movie> points at a fixed file, and your video is written to that file
    (panorama/videos/zxc/zxc.webm). The layout files are NOT bundled (no licence in that repo): "Install" downloads
    them from the author's repository to a local cache, from where they are added to the mod.
    Only .webm (VP8/VP9) is accepted.
    """
    REPO_RAW = "https://raw.githubusercontent.com/h6rd/BackgroundChanger/main/full/"
    LAYOUT_FILES = (
        "panorama/layout/dashboard.vxml_c", "panorama/layout/dashboard_background_last_match.vxml_c",
        "panorama/layout/dashboard_background_manager.vxml_c", "panorama/layout/dashboard_page_home.vxml_c",
        "panorama/layout/hero_loadout_background_images.vxml_c", "panorama/styles/dashboard_background_last_match.vcss_c",
        "panorama/styles/hero_loadout_background_images.vcss_c", "panorama/styles/dashboard_background_manager.vcss_c",
    )
    VIDEO_TARGET = "panorama/videos/zxc/zxc.webm"
    MAX_BYTES = 200 * 1024 * 1024

    def __init__(self, vpk_readers: List[VPKReader], cache_dir: Optional[Path] = None):
        self.vpk_readers = vpk_readers
        self.cache = Path(cache_dir or (CACHE_DIR / "bgchanger"))
        self.background_path = ""
        self.last_error = ""
        self.last_replaced: List[str] = []

    def set_background(self, path: str):
        self.background_path = path or ""
        self.last_error = ""

    def clear(self):
        self.background_path = ""
        self.last_error = ""
        self.last_replaced = []

    def layout_installed(self) -> bool:
        return all((self.cache / f).exists() and (self.cache / f).stat().st_size > 100 for f in self.LAYOUT_FILES)

    def install_layout(self) -> Tuple[bool, str]:
        """Download the layout set once. Needs internet; returns (ok, message)."""
        try:
            import requests
        except ImportError:
            return False, "the 'requests' package is missing"
        for f in self.LAYOUT_FILES:
            dst = self.cache / f
            if dst.exists() and dst.stat().st_size > 100:
                continue
            try:
                r = requests.get(self.REPO_RAW + f, timeout=30)
            except Exception as ex:
                return False, f"download failed: {ex}"
            if r.status_code != 200 or len(r.content) < 100:
                return False, f"download failed for {f} (HTTP {r.status_code})"
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(r.content)
        return True, "layout files installed"

    VIDEO_EXTS = (".webm", ".mp4", ".mov", ".mkv", ".avi", ".gif", ".m4v")
    IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tga")
    BG_HINTS = ("background", "dashboard", "_bg", "bg_", "menu", "home", "main_menu", "backdrop")
    # even width/height (yuv420p needs it), at most 1080p, 30 fps: odd sizes / 4K / 60 fps are classic "black screen" causes
    SCALE = "scale='trunc(min(1920,iw)/2)*2':'trunc(min(1080,ih)/2)*2':force_original_aspect_ratio=decrease:force_divisible_by=2"

    @staticmethod
    def webm_codec(data: bytes) -> str:
        head = data[:262144]
        for tag, name in ((b"V_VP9", "vp9"), (b"V_VP8", "vp8"), (b"V_AV1", "av1"), (b"V_MPEG4", "h264")):
            if tag in head:
                return name
        return ""

    @staticmethod
    def ffmpeg_path() -> str:
        return shutil.which("ffmpeg") or ""

    def is_image(self, f: Path) -> bool:
        return f.suffix.lower() in self.IMAGE_EXTS

    def convert(self, src: Path, progress=None) -> Optional[Path]:
        """
        Normalise to what Panorama plays: VP9 in WebM, yuv420p, no audio, even size, <= 1080p, <= 30 fps (the command
        dota2-minify uses, plus the size/fps limits). A STILL IMAGE becomes a short looping VP9 clip, so a static
        background shows exactly like a picture.
        """
        ff = self.ffmpeg_path()
        if not ff:
            return None
        st = src.stat()
        img = self.is_image(src)
        key = hashlib.sha1(f"v3|{img}|{src.resolve()}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()[:16]
        out = self.cache / "converted" / f"{key}.webm"
        if out.exists() and out.stat().st_size > 1024:
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        if progress:
            progress("Converting the picture to a looping background clip..." if img else "Converting the background video (VP9, no audio)...")
        if img:
            cmd = [ff, "-y", "-loop", "1", "-framerate", "5", "-t", "4", "-i", str(src), "-vf", self.SCALE + ",format=yuv420p",
                   "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-b:v", "0", "-crf", "30", "-deadline", "good", "-cpu-used", "4",
                   "-an", str(out)]
        else:
            cmd = [ff, "-y", "-i", str(src), "-vf", self.SCALE + ",fps=30,format=yuv420p", "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p",
                   "-b:v", "0", "-crf", "34", "-deadline", "realtime", "-cpu-used", "5", "-threads", "0", "-an", str(out)]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=1800, creationflags=flags)
        except (OSError, subprocess.TimeoutExpired) as ex:
            self.last_error = f"ffmpeg failed: {ex}"
            return None
        if r.returncode != 0 or not out.exists() or out.stat().st_size < 1024:
            out.unlink(missing_ok=True)
            self.last_error = "ffmpeg could not convert this file"
            return None
        return out

    # ---- the game's own menu background videos (used by the "files" method)
    def all_videos(self) -> List[str]:
        found = set()
        for reader in self.vpk_readers:
            for fp in reader.files:
                if fp.startswith("panorama/videos/") and fp.endswith(".webm"):
                    found.add(fp)
        return sorted(found)

    def targets(self) -> List[str]:
        return [v for v in self.all_videos() if any(h in v for h in self.BG_HINTS)]

    def _read_video(self, progress=None) -> Optional[bytes]:
        f = Path(self.background_path)
        if not f.exists():
            self.last_error = f"Background file not found: {f}"
            return None
        if f.suffix.lower() not in self.VIDEO_EXTS + self.IMAGE_EXTS:
            self.last_error = "Choose a video (.webm .mp4 .mov .mkv .avi .gif) or a picture (.png .jpg .webp)."
            return None
        if f.stat().st_size > self.MAX_BYTES * 3:
            self.last_error = "Background video is larger than 600 MB."
            return None
        conv = self.convert(f, progress)
        if conv is not None:
            f = conv
        else:
            if self.last_error:
                return None
            if self.is_image(f):
                self.last_error = ("A picture is turned into a looping clip with ffmpeg, which is not installed. "
                                   "Install ffmpeg (https://ffmpeg.org) or choose a VP9 .webm.")
                return None
            # no ffmpeg: only a VP9 WebM can be trusted as-is
            head = f.read_bytes()[:262144]
            if f.suffix.lower() != ".webm" or head[:4] != b"\x1a\x45\xdf\xa3":
                self.last_error = ("ffmpeg is not installed, so this video cannot be converted. Install ffmpeg "
                                   "(https://ffmpeg.org) or choose a VP9 .webm.") if f.suffix.lower() != ".webm" else \
                                  "This file is not a valid WebM (missing EBML header)."
                return None
            if self.webm_codec(head) != "vp9":
                self.last_error = ("This WebM is not VP9 (Panorama shows a black screen for other codecs). "
                                   "Install ffmpeg so Chameleon can convert it, or re-encode it as VP9, yuv420p, no audio.")
                return None
        if f.stat().st_size > self.MAX_BYTES:
            self.last_error = "Converted background video is larger than 200 MB - use a shorter / lower resolution video."
            return None
        return f.read_bytes()

    def add_to(self, builder: 'VPKBuilder', progress=None, method: str = "layout") -> int:
        """
        method "layout": BackgroundChanger's compiled menu layouts + your clip at panorama/videos/zxc/zxc.webm.
        method "files" : your clip replaces the game's own menu background videos (no layout files needed).
        """
        self.last_replaced = []
        if not self.background_path:
            return 0
        data = self._read_video(progress)
        if data is None:
            return 0
        if method == "files":
            targets = self.targets()
            if not targets:
                self.last_error = f"No menu-background video found in the game files ({len(self.all_videos())} videos)."
                return 0
            for t in targets:
                builder.add_data(data, t)
                self.last_replaced.append(t)
            return len(targets)
        if not self.layout_installed():
            ok, msg = self.install_layout()
            if not ok:
                self.last_error = "Menu layout files are not installed: " + msg
                return 0
        for f in self.LAYOUT_FILES:
            builder.add_data((self.cache / f).read_bytes(), f)
            self.last_replaced.append(f)
        builder.add_data(data, self.VIDEO_TARGET)
        self.last_replaced.append(self.VIDEO_TARGET)
        return len(self.last_replaced)


# ==============================================================================
# FONT CHANGER  (only fonts that exist in the game files)
# ==============================================================================
