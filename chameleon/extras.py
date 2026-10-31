from .common import *
import hashlib
import struct
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

    TARGET_BYTES = 12_000_000      # Dota shows a BLACK menu for a very big video: aim at 12 MB, never above 14 MB
    MAX_OUT = 14_000_000
    MAX_SECONDS = 30.0

    def _duration(self, src: Path) -> float:
        ffprobe = shutil.which("ffprobe")
        try:
            if ffprobe:
                r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
                                   capture_output=True, text=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                return float(r.stdout.strip().splitlines()[0])
            r = subprocess.run([self.ffmpeg_path(), "-i", str(src)], capture_output=True, text=True, timeout=60,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
            if m:
                return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        except Exception:
            pass
        return self.MAX_SECONDS

    def convert(self, src: Path, progress=None) -> Optional[Path]:
        """
        Prepare for Panorama: VP9 in WebM, yuv420p, no audio, even size, <= 1080p, <= 30 fps, at most 30 seconds and a file of about
        12 MB (a bigger one gives a black menu). A still picture becomes a short looping clip.
        """
        ff = self.ffmpeg_path()
        if not ff:
            return None
        st = src.stat()
        img = self.is_image(src)
        key = hashlib.sha1(f"v4|{img}|{src.resolve()}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()[:16]
        out = self.cache / "converted" / f"{key}.webm"
        if out.exists() and 1024 < out.stat().st_size <= self.MAX_OUT:
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        if progress:
            progress("Preparing the picture for the menu..." if img else "Preparing the video for the menu (VP9, about 12 MB)...")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        dur = 4.0 if img else max(1.0, min(self.MAX_SECONDS, self._duration(src)))
        bitrate = max(250_000, min(4_000_000, int(self.TARGET_BYTES * 8 / dur)))
        for attempt in range(4):
            if img:
                cmd = [ff, "-y", "-loop", "1", "-framerate", "5", "-t", "4", "-i", str(src), "-vf", self.SCALE + ",format=yuv420p",
                       "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-b:v", "0", "-crf", str(30 + attempt * 5), "-deadline", "good",
                       "-cpu-used", "4", "-an", str(out)]
            else:
                cmd = [ff, "-y", "-i", str(src), "-t", f"{dur:.2f}", "-vf", self.SCALE + ",fps=30,format=yuv420p", "-c:v", "libvpx-vp9",
                       "-pix_fmt", "yuv420p", "-b:v", str(bitrate), "-maxrate", str(int(bitrate * 1.25)), "-bufsize", str(bitrate * 2),
                       "-deadline", "realtime", "-cpu-used", "5", "-row-mt", "1", "-threads", "0", "-an", str(out)]
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=1800, creationflags=flags)
            except (OSError, subprocess.TimeoutExpired) as ex:
                self.last_error = f"ffmpeg failed: {ex}"
                return None
            if r.returncode != 0 or not out.exists() or out.stat().st_size < 1024:
                out.unlink(missing_ok=True)
                self.last_error = "ffmpeg could not convert this file"
                return None
            if out.stat().st_size <= self.MAX_OUT:
                return out
            bitrate = int(bitrate * 0.65)                    # still too big: encode again with a lower bitrate
        out.unlink(missing_ok=True)
        self.last_error = "The video stays above 14 MB even after compression - use a shorter one."
        return None

    def _game_file(self, path: str) -> Optional[bytes]:
        for r in self.vpk_readers:
            if path in r.files:
                return r.extract_to_bytes(path)
        return None

    def _add_menu(self, builder: 'VPKBuilder', video: bytes) -> int:
        """
        Native method: Valve's own dashboard layout is read from the game, its background manager is pointed at a layout of ours
        that plays the video full screen, and everything is written back as Panorama resources. Nothing is downloaded.
        """
        from . import panorama as pa
        dash = self._game_file("panorama/layout/dashboard.vxml_c")
        tpl_css = self._game_file("panorama/styles/dotastyles.vcss_c")
        if not dash or not tpl_css:
            self.last_error = "The game's menu files were not found (dashboard layout)."
            return 0
        try:
            src = pa.get_source(dash)
            pat = re.compile(r'(<DOTADashboardBackgroundManager\b[^>]*\boverride-background=")[^"]*(")')
            if len(pat.findall(src)) != 1:
                self.last_error = "This Dota version changed the menu background layout - use the other method for now."
                return 0
            patched = pat.sub(lambda m: m.group(1) + "s2r://" + pa.MENU_LAYOUT + m.group(2), src)
            files = {"panorama/layout/dashboard.vxml_c": pa.set_source(dash, patched),
                     pa.MENU_LAYOUT: pa.set_source(dash, pa.LAYOUT_XML),
                     pa.MENU_STYLE: pa.set_source(tpl_css, pa.STYLE_CSS)}
        except (pa.PanoramaError, UnicodeDecodeError, struct.error) as ex:
            self.last_error = f"Could not read the game's menu layout ({ex})."
            return 0
        for path, data in files.items():
            builder.add_data(data, path)
            self.last_replaced.append(path)
        builder.add_data(video, pa.MENU_VIDEO)
        self.last_replaced.append(pa.MENU_VIDEO)
        return len(self.last_replaced)

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
        if f.stat().st_size > self.MAX_OUT:
            self.last_error = "The video is bigger than 14 MB: Dota shows a black menu for such files. Install ffmpeg (it shrinks the video itself) or use a smaller file."
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
        if method == "menu":
            return self._add_menu(builder, data)
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
