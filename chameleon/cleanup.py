from .common import *
# ==============================================================================
# CLEANUP MANAGER
# ==============================================================================

class CleanupManager:
    @staticmethod
    def clear_cache() -> Tuple[int, int]:
        count = 0; size = 0
        if CACHE_DIR.exists():
            for f in CACHE_DIR.rglob("*"):
                if f.is_file(): size += f.stat().st_size; f.unlink(); count += 1
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return count, size
    @staticmethod
    def clear_icons() -> Tuple[int, int]:
        count = 0; size = 0
        if ICONS_DIR.exists():
            for f in ICONS_DIR.glob("*.png"):
                if f.is_file(): size += f.stat().st_size; f.unlink(); count += 1
        return count, size
    @staticmethod
    def clear_backups() -> Tuple[int, int]:
        count = 0; size = 0
        if BACKUP_DIR.exists():
            for f in BACKUP_DIR.rglob("*"):
                if f.is_file(): size += f.stat().st_size; f.unlink(); count += 1
        return count, size
    @staticmethod
    def clear_logs() -> Tuple[int, int]:
        count = 0; size = 0
        if LOG_FILE.exists(): size = LOG_FILE.stat().st_size; LOG_FILE.unlink(); count = 1
        return count, size
    @staticmethod
    def clear_all() -> Tuple[int, int]:
        tc = 0; ts = 0
        for c, s in [CleanupManager.clear_cache(), CleanupManager.clear_icons(), CleanupManager.clear_backups(), CleanupManager.clear_logs()]:
            tc += c; ts += s
        return tc, ts
    @staticmethod
    def get_cache_size() -> int:
        size = 0
        for d in [CACHE_DIR, ICONS_DIR, BACKUP_DIR]:
            if d.exists():
                for f in d.rglob("*"):
                    if f.is_file(): size += f.stat().st_size
        if LOG_FILE.exists(): size += LOG_FILE.stat().st_size
        return size
    @staticmethod
    def format_size(size: int) -> str:
        if size < 1024: return f"{size} B"
        elif size < 1024*1024: return f"{size/1024:.1f} KB"
        elif size < 1024*1024*1024: return f"{size/1024/1024:.1f} MB"
        else: return f"{size/1024/1024/1024:.2f} GB"

