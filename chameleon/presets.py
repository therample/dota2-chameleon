from .common import *
# ==============================================================================
# PRESET MANAGER
# ==============================================================================

class PresetManager:
    def __init__(self):
        PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    def save_preset(self, name, overrides, settings=None, river_color="", background=None):
        preset = {"name": name, "version": 2, "overrides": overrides, "settings": settings or {}, "river_color": river_color,
                  "background": background or {}, "created": datetime.now().isoformat()}
        (PRESETS_DIR / f"{name}.json").write_text(json.dumps(preset, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    def load_preset(self, name):
        p = PRESETS_DIR / f"{name}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    def list_presets(self):
        return [p.stem for p in PRESETS_DIR.glob("*.json")]
    def delete_preset(self, name):
        p = PRESETS_DIR / f"{name}.json"
        if p.exists(): p.unlink(); return True
        return False

