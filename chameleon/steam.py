from .common import *
# ==============================================================================
# STEAM DETECTOR
# ==============================================================================

class SteamDetector:
    REG_PATHS = [r"SOFTWARE\WOW6432Node\Valve\Steam", r"SOFTWARE\Valve\Steam"]
    @staticmethod
    def detect_steam() -> Optional[Path]:
        if sys.platform == "win32":
            for reg_path in SteamDetector.REG_PATHS:
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
                    install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                    winreg.CloseKey(key)
                    p = Path(install_path)
                    if p.exists(): return p
                except Exception: continue
            for c in [Path("C:/Program Files (x86)/Steam"), Path("C:/Program Files/Steam")]:
                if c.exists(): return c
        elif sys.platform == "linux":
            home = Path.home()
            for c in [home / ".steam/steam", home / ".local/share/Steam"]:
                if c.exists(): return c
        elif sys.platform == "darwin":
            c = Path.home() / "Library/Application Support/Steam"
            if c.exists(): return c
        return None
    @staticmethod
    def detect_dota(steam_path: Path) -> Optional[Path]:
        vdf_path = steam_path / "steamapps/libraryfolders.vdf"
        libraries = [steam_path / "steamapps"]
        if vdf_path.exists():
            content = vdf_path.read_text(encoding="utf-8", errors="ignore")
            for m in re.findall(r'"path"\s+"([^"]+)"', content):
                lib = Path(m.replace("\\\\", "/")) / "steamapps"
                if lib.exists(): libraries.append(lib)
        for lib in libraries:
            dota_path = lib / "common" / "dota 2 beta"
            if dota_path.exists(): return dota_path
        return None

