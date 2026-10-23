from .qt import *
from .common import *
from .vpk_io import *
from .kv import *
from .slots import *
from .models import *
from .resolver import *
from .extras import *
from .cleanup import *
from .database import *
from .gameinfo import *
from .applier import *
from .presets import *
from .icons import *
# ==============================================================================
# BRIDGE
# ==============================================================================

def pretty_name(raw: str) -> str:
    """Readable name from a localized text or an internal token like '#DOTA_Item_Crown_Cursor' / 'crown_cursor_pack'."""
    s = str(raw or "").strip().lstrip("#")
    if " " in s and not s.isupper():
        return s
    for pre in ("DOTA_Item_", "DOTA_Wearable_", "dota_item_", "item_"):
        if s.startswith(pre):
            s = s[len(pre):]
    return s.replace("_", " ").strip().title() or str(raw)


from .iconsrc import choose_icon_path


class ChameleonBridge(QObject):
    statusChanged = Signal(str)
    dbLoaded = Signal(bool)
    applyResult = Signal(bool)
    iconReady = Signal(str, str)
    progressChanged = Signal(int, str, str)
    launchResult = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.window = None
        self.database = None
        self.applier = None
        self.preset_manager = PresetManager()
        self.config = DEFAULT_CONFIG.copy()
        self._db_ready = False

    def _connect_icons(self):
        hub = IconManager._hub()
        if not getattr(self, "_icons_connected", False):
            hub.icon_ready.connect(self.iconReady)
            self._icons_connected = True

    def set_window(self, window):
        self.window = window

    def set_database(self, database):
        self.database = database

    def set_applier(self, applier):
        self.applier = applier

    def mark_db_ready(self):
        self._db_ready = True

    @Slot(result=str)
    def get_heroes(self):
        if not self.database:
            return "[]"
        heroes = []
        for hn, hd in sorted(self.database.heroes.items(), key=lambda x: x[1].get("display_name", "")):
            heroes.append({"name": hn, "display_name": hd.get("display_name", hn), "attribute": hd.get("attribute", ""), "item_count": len(hd.get("items", []))})
        return json.dumps(heroes)

    @Slot(str, result=str)
    def get_hero_skins(self, hero_name):
        if not self.database:
            return "[]"
        return json.dumps([self._item_to_dict(s) for s in self.database.get_hero_skins(hero_name)])

    @Slot(result=str)
    def get_catalog(self):
        """Groups -> categories with item counts (what the Catalog page draws)."""
        if not self.database:
            return "[]"
        groups = []
        for gid, cats in self.database.CATEGORY_GROUPS:
            entries = [{"id": c, "count": len(self.database.category_items(c))} for c in cats]
            groups.append({"id": gid, "cats": entries})
        return json.dumps(groups)

    @Slot(str, result=str)
    def get_category_items(self, category):
        if not self.database:
            return "[]"
        items = self.database.category_items(category)
        try:
            return json.dumps([self._item_to_dict(item) for item in items.values()])
        except Exception as e:
            log.error(f"Error getting category items: {e}")
            return "[]"

    @Slot(result=str)
    def get_favorites(self):
        out = []
        for n in (self.config.get("favorites", []) or []):
            it = self.database.items.get(n) if self.database else None
            if it:
                out.append(self._item_to_dict(it))
        return json.dumps(out)

    @Slot(str, result=bool)
    def toggle_favorite(self, item_name):
        fav = list(self.config.get("favorites", []) or [])
        now = item_name not in fav
        if now:
            fav.append(item_name)
        else:
            fav.remove(item_name)
        self.config["favorites"] = fav
        if self.window:
            self.window.save_config()
        return now

    @Slot(result=str)
    def get_favorite_names(self):
        return json.dumps(self.config.get("favorites", []) or [])

    BUILTIN_LAUNCH = [
        {"name": "Default", "params": "-novid"},
        {"name": "Performance", "params": "-novid -high -nojoy"},
        {"name": "Low latency", "params": "-novid -high +fps_max 0"},
        {"name": "Windowed borderless", "params": "-novid -windowed -noborder"},
        {"name": "Console", "params": "-novid -console"},
        {"name": "DirectX 11", "params": "-novid -dx11"},
        {"name": "Vulkan", "params": "-novid -vulkan"},
    ]
    LAUNCH_FLAGS = [("-novid", "Skip intro video"), ("-console", "Enable console"), ("-high", "High CPU priority"),
                    ("-windowed", "Windowed"), ("-noborder", "Borderless"), ("-fullscreen", "Fullscreen"),
                    ("-dx11", "DirectX 11"), ("-vulkan", "Vulkan"), ("-nojoy", "Disable joystick")]

    def _launch_state(self):
        custom = [p for p in (self.config.get("launch_presets") or []) if isinstance(p, dict) and p.get("name")]
        allp = [dict(p, builtin=True) for p in self.BUILTIN_LAUNCH] + [dict(p, builtin=False) for p in custom]
        sel = self.config.get("launch_preset") or "Default"
        if sel not in [p["name"] for p in allp]:
            sel = "Default"
        return allp, sel

    def launch_params(self) -> str:
        allp, sel = self._launch_state()
        for p in allp:
            if p["name"] == sel:
                return p["params"]
        return self.config.get("launch_parameters", "")

    @Slot(result=str)
    def get_launch_presets(self):
        allp, sel = self._launch_state()
        return json.dumps({"presets": allp, "selected": sel, "flags": self.LAUNCH_FLAGS})

    @Slot(str, str)
    def save_launch_preset(self, name, params):
        name = (name or "").strip()[:40]
        params = re.sub(r"[^\w\s\-\+\.\=:/,]", "", params or "").strip()[:300]
        if not name or name in [p["name"] for p in self.BUILTIN_LAUNCH]:
            self.statusChanged.emit("Failed: choose another preset name")
            return
        custom = [p for p in (self.config.get("launch_presets") or []) if p.get("name") != name]
        custom.append({"name": name, "params": params})
        self.config["launch_presets"] = custom
        self.config["launch_preset"] = name
        self.config["launch_parameters"] = params
        if self.window:
            self.window.save_config()
        self.statusChanged.emit(f"Selected: launch preset {name}")

    @Slot(str)
    def delete_launch_preset(self, name):
        self.config["launch_presets"] = [p for p in (self.config.get("launch_presets") or []) if p.get("name") != name]
        if self.config.get("launch_preset") == name:
            self.config["launch_preset"] = "Default"
        if self.window:
            self.window.save_config()

    @Slot(str)
    def select_launch_preset(self, name):
        allp, _ = self._launch_state()
        for p in allp:
            if p["name"] == name:
                self.config["launch_preset"] = name
                self.config["launch_parameters"] = p["params"]
                if self.window:
                    self.window.save_config()
                self.statusChanged.emit(f"Selected: launch preset {name}")
                return

    @Slot(str, int, result=bool)
    def apply_style(self, item_name, style_id):
        if not self.applier:
            return False
        ok = self.applier.apply_style(item_name, style_id)
        if ok:
            self.statusChanged.emit(f"Style set: {item_name} -> {style_id}")
        return ok

    @Slot()
    def browse_background(self):
        if not self.window:
            return
        p = QFileDialog.getOpenFileName(self.window, "Select a background video", "", "Video or picture (*.webm *.mp4 *.mov *.mkv *.avi *.gif *.png *.jpg *.jpeg *.webp)")[0]
        if p:
            self.set_background(p)
            self.statusChanged.emit(f"Selected: background {Path(p).name}")

    @Slot()
    def clear_all_overrides(self):
        if not self.applier:
            return
        self.applier.active_overrides.clear()
        self.applier.active_styles.clear()
        self.statusChanged.emit("All overrides cleared")

    @Slot(str, result=bool)
    def clear_style(self, item_name):
        if not self.applier:
            return False
        return self.applier.clear_style(item_name)

    @Slot(str, result=str)
    def get_active_style(self, item_name):
        if not self.applier:
            return ""
        style_id = self.applier.active_styles.get(item_name)
        return str(style_id) if style_id is not None else ""

    @Slot(str)
    def remove_override(self, key):
        if not self.applier:
            return
        if key in self.applier.active_overrides:
            del self.applier.active_overrides[key]
        self.statusChanged.emit(f"Removed: {key}")

    @Slot(str)
    def set_background(self, path):
        if not self.applier:
            return
        self.applier.set_background(path)
        self.config["background_path"] = path
        self.statusChanged.emit("Background set")

    @Slot(str)
    def set_river_color(self, color_name):
        if not self.applier:
            return
        self.applier.set_river_color("" if color_name == "default" else color_name)
        self.config["river_color"] = color_name
        self.statusChanged.emit(f"River color: {color_name}")

    @Slot(str, result=str)
    def get_hero_catalog(self, hero_name):
        if not self.database:
            return "{}"
        cat = self.database.get_hero_catalog(hero_name)
        return json.dumps({
            "slots": [{"slot": g["slot"], "title": g["title"], "items": [self._item_to_dict(i) for i in g["items"]]}
                      for g in cat["slots"]],
            "arcanas": [self._item_to_dict(i) for i in cat["arcanas"]],
            "personas": [self._item_to_dict(i) for i in cat["personas"]],
            "taunts": [self._item_to_dict(i) for i in cat["taunts"]],
            "gems": [self._item_to_dict(i) for i in cat.get("gems", [])],
        })

    @Slot(result=str)
    def get_applied_counts(self):
        """How many mods are picked per hero and per hero slot - drives the badges in the UI."""
        per_hero: Dict[str, int] = {}
        per_slot: Dict[str, int] = {}
        if self.applier:
            for key in self.applier.active_overrides:
                parts = key.split("::")
                if parts[0] in ("hero", "bugged") and len(parts) >= 3:
                    per_hero[parts[1]] = per_hero.get(parts[1], 0) + 1
                    per_slot[f"{parts[1]}::{parts[2]}"] = per_slot.get(f"{parts[1]}::{parts[2]}", 0) + 1
                elif parts[0] == "taunt" and len(parts) >= 2:
                    per_hero[parts[1]] = per_hero.get(parts[1], 0) + 1
                    per_slot[f"{parts[1]}::taunt"] = 1
                elif parts[0] == "gem" and len(parts) >= 2:
                    per_hero[parts[1]] = per_hero.get(parts[1], 0) + 1
                    per_slot[f"{parts[1]}::gem"] = 1
        return json.dumps({"heroes": per_hero, "slots": per_slot})

    @Slot(result=str)
    def get_build_report(self):
        """What the last Apply actually did, item by item (modifier counts, packed files, problems)."""
        return json.dumps(getattr(self.applier, "last_report", {}) if self.applier else {}, default=str)

    @Slot(result=str)
    def get_item_languages(self):
        return json.dumps(self.database.available_languages() if self.database else [])

    @Slot(result=str)
    def get_background_state(self):
        if not self.applier:
            return "{}"
        bg = self.applier.background_builder
        return json.dumps({"path": bg.background_path, "layout_installed": bg.layout_installed(), "target": bg.VIDEO_TARGET,
                           "ffmpeg": bool(bg.ffmpeg_path()), "image": bool(bg.background_path and bg.is_image(Path(bg.background_path))),
                           "method": self.config.get("bg_method", "layout")})

    @Slot(result=bool)
    def install_background_layout(self):
        if not self.applier:
            return False
        self.statusChanged.emit("Downloading menu layout files...")
        ok, msg = self.applier.background_builder.install_layout()
        self.statusChanged.emit(("Selected: " if ok else "Failed: ") + msg)
        return ok

    @Slot(result=str)
    def get_featured(self):
        """Random showcase of arcanas / personas / immortals / legendaries for the Home page."""
        if not self.database:
            return "[]"
        import random
        pool = [i for i in self.database.items.values()
                if (i.is_arcana or i.is_persona or str(i.rarity).lower().replace("rarity_", "") in ("immortal", "legendary", "ancient"))
                and i.used_by_hero and not self.database.is_system_item(i)]
        random.shuffle(pool)
        out = []
        for it in pool[:12]:
            d = self._item_to_dict(it)
            hd = self.database.heroes.get(it.used_by_hero, {})
            d["hero"] = it.used_by_hero
            d["hero_name"] = hd.get("display_name", it.used_by_hero)
            out.append(d)
        return json.dumps(out)

    @Slot(result=int)
    def clear_icon_cache(self):
        return IconManager.clear_disk_cache()

    @Slot(result=str)
    def get_icon_stats(self):
        return json.dumps(IconManager.stats())

    @Slot(result=str)
    def get_river_colors(self):
        opts = self.applier.river_color_builder.options() if self.applier else {}
        return json.dumps(["default"] + sorted(opts.keys()))

    @Slot(result=str)
    def get_active_overrides(self):
        if not self.applier:
            return "{}"
        return json.dumps({
            "overrides": self.applier.active_overrides,
            "styles": self.applier.active_styles,
            "river_color": self.applier.river_color_builder.color,
            "background": self.applier.background_builder.background_path
        })

    @Slot(result=str)
    def get_presets(self):
        return json.dumps(self.preset_manager.list_presets())

    @Slot(result=str)
    def get_config(self):
        return json.dumps(self.config)

    @Slot(result=str)
    def get_status(self):
        if not self.database or not self._db_ready:
            return json.dumps({"status": "loading", "items": 0, "heroes": 0, "vpk": False, "dota_path": self.config.get("dota_path", "")})
        gi = GameInfoManager(Path(self.config.get("dota_path", "")))
        return json.dumps({"status": "ready", "items": len(self.database.items), "heroes": len(self.database.heroes), "vpk": gi.is_injected() if self.config.get("dota_path") else False, "dota_path": self.config.get("dota_path", ""), "stale": self._is_stale(gi)})

    def _is_stale(self, gi) -> bool:
        """The mod is registered but Dota was updated since the last Apply -> it must be applied again."""
        try:
            last = self.config.get("applied_sig", "")
            return bool(gi.is_injected() and last and self.database and last != self.database._game_signature())
        except Exception:
            return False

    @Slot(result=str)
    def get_cache_size(self):
        return json.dumps({"size": CleanupManager.get_cache_size(), "formatted": CleanupManager.format_size(CleanupManager.get_cache_size())})

    @Slot(result=str)
    def get_pack_report(self):
        if not self.applier:
            return json.dumps({"items": {}, "total_files": 0, "total_kb": 0})
        report = getattr(self.applier, "last_pack_report", {}) or {}
        total_files = sum(r["files"] for r in report.values())
        total_kb = sum(r["bytes"] for r in report.values()) / 1024
        return json.dumps({"items": report, "total_files": total_files, "total_kb": round(total_kb, 1)})

    @Slot(str, int, result=str)
    def get_hero_icon(self, hero_name, size):
        key, b64 = IconManager.request("hero", hero_name, "", size)
        return b64

    @Slot(str, str, int, result=str)
    def get_item_icon(self, combined_name, icon_path, size):
        item_name = combined_name.split("@@@")[0]
        key, b64 = IconManager.request("item", item_name, icon_path, size)
        return b64

    @Slot(str, str, str, str)
    def apply_skin(self, category, hero, item_name, slot):
        if not self.applier:
            return
        ok = True
        if category in ("hero", "heroes"):
            ok = self.applier.apply_hero_skin(hero, item_name, slot)
        elif category == "taunts":
            ok = self.applier.apply_taunt(hero, item_name)
        elif category == "gems":
            ok = self.applier.apply_gem(hero, item_name)
        elif category == "bugged":
            ok = self.applier.apply_bugged_item(hero, item_name)
        else:
            ok = self.applier.apply_category(category, item_name)
        self.statusChanged.emit(f"Selected: {item_name}" if ok else f"Failed: {item_name} cannot be applied here")

    @Slot()
    def apply_all(self):
        if not self.applier:
            return
        self.applier.config = self.config
        self.statusChanged.emit("Applying changes...")
        def apply_thread():
            def cb(msg):
                if msg.startswith("@@"):
                    try:
                        pct, stage, detail = msg[2:].split("|", 2)
                        self.progressChanged.emit(int(pct), stage, detail)
                    except ValueError:
                        pass
                else:
                    self.statusChanged.emit(msg)
            success = self.applier.commit(progress_callback=cb)
            self.applyResult.emit(success)
        threading.Thread(target=apply_thread, daemon=True).start()

    @Slot()
    def restore_all(self):
        if not self.applier:
            return
        self.applier.restore()
        self.statusChanged.emit("Restored.")

    @Slot()
    def launch_dota(self):
        if not self.applier:
            return
        params = self.launch_params()
        success = self.applier.launch_dota(params)
        self.launchResult.emit(success)
        if success:
            self.statusChanged.emit("Launching Dota 2")
        else:
            self.statusChanged.emit("Failed to launch Dota 2")

    @Slot(str)
    def save_preset(self, name):
        if not self.applier:
            return
        self.preset_manager.save_preset(
            name,
            self.applier.active_overrides.copy(),
            {},
            {"styles": {k: v for k, v in self.applier.active_styles.items()}},
            {},
            self.applier.river_color_builder.color,
            self.applier.background_builder.background_path
        )
        self.statusChanged.emit(f"Preset saved: {name}")

    @Slot(str)
    def load_preset(self, name):
        preset = self.preset_manager.load_preset(name)
        if not preset or not self.applier:
            return
        ap = self.applier
        ap.active_overrides.clear()
        ap.active_styles.clear()
        db = self.database
        for key, item_name in preset.get("overrides", {}).items():
            parts = key.split("::")
            if item_name not in db.items:
                continue
            if parts[0] in ("hero", "bugged", "taunt", "cat"):          # current key format: restore as saved
                ap.active_overrides[key] = item_name
            elif parts[0] == "hero":
                ap.apply_hero_skin(parts[1], item_name)
            else:                                                         # keys written by older versions: ward, courier ...
                cat = {"ward": "wards", "courier": "couriers", "weather": "weather", "terrain": "terrain", "music": "music",
                       "tower": "towers", "announcer": "announcers", "mega_kills": "mega_kills", "loading_screen": "loadings"}.get(key)
                if cat:
                    ap.apply_category(cat, item_name)
        settings = preset.get("settings", {})
        for k, v in (settings.get("styles") or {}).items():
            if k in db.items:
                ap.active_styles[k] = v
        if preset.get("river_color"):
            ap.set_river_color(preset["river_color"])
        if preset.get("background_path"):
            ap.set_background(preset["background_path"])
        self.statusChanged.emit(f"Loaded preset: {name}")

    @Slot(str)
    def delete_preset(self, name):
        self.preset_manager.delete_preset(name)
        self.statusChanged.emit(f"Deleted: {name}")

    @Slot()
    def clear_cache(self):
        c, s = CleanupManager.clear_cache()
        self.statusChanged.emit(f"Cleared {c} cache files")

    @Slot()
    def clear_icons(self):
        c, s = CleanupManager.clear_icons()
        self.statusChanged.emit(f"Cleared {c} icons")

    @Slot()
    def clear_backups(self):
        c, s = CleanupManager.clear_backups()
        self.statusChanged.emit(f"Cleared {c} backups")

    @Slot()
    def clear_logs(self):
        c, s = CleanupManager.clear_logs()
        self.statusChanged.emit("Cleared logs")

    @Slot()
    def clear_all_cache(self):
        c, s = CleanupManager.clear_all()
        self.statusChanged.emit(f"Cleared all: {c} files")

    @Slot()
    def cleanup_mod(self):
        if not self.applier:
            return
        self.applier.restore()
        self.statusChanged.emit("Mod deleted, game restored.")

    @Slot(float, float, bool, bool)
    def save_hud_settings(self, hud_scale, minimap_scale, pack_resources, show_rarity_colors):
        self.config["hud_scale"] = hud_scale
        self.config["minimap_scale"] = minimap_scale
        self.config["pack_resources"] = pack_resources
        self.config["show_rarity_colors"] = show_rarity_colors
        if self.window:
            self.window.save_config()
        self.statusChanged.emit("Settings saved")

    @Slot(str, str)
    def set_option(self, key, value):
        """Whitelisted string options from the settings page."""
        allowed = {"pack_mode": {"minimal", "full"}, "patch_hero_model": {"true", "false"},
                   "language": {"en", "ru"}, "item_language": None, "patch_signatures": {"true", "false"},
                   "particle_swap": {"off", "hero", "all"},
                   "icon_field": {"inventory", "auto", "preview"}, "icon_source": {"auto", "game", "cdn"},
                   "icon_fix_cast": {"true", "false"}, "default_mode": {"auto", "replace", "create"},
                   "bg_method": {"layout", "files"}, "effect_mode": {"slot", "hero", "both"}, "ui_density": {"s", "m", "l"}}
        if key not in allowed or (allowed[key] is not None and value not in allowed[key]):
            return
        if key == "item_language" and not re.fullmatch(r"[a-z_]{3,20}", value or ""):
            return
        self.config[key] = (value == "true") if key in ("patch_hero_model", "patch_signatures", "icon_fix_cast") else value
        if key in ("icon_source", "icon_fix_cast"):
            IconManager.configure(self.config.get("icon_source", "auto"), self.config.get("icon_fix_cast", True))
        if key == "patch_signatures" and self.applier:
            self.applier.gameinfo.sign = (value == "true")
        if self.window:
            self.window.save_config()
        self.statusChanged.emit("Settings saved")

    @Slot(str)
    def set_launch_params(self, params):
        self.config["launch_parameters"] = params
        if self.window:
            self.window.save_config()
        self.statusChanged.emit(f"Launch params: {params}")

    @Slot(bool)
    def set_auto_restore(self, val):
        self.config["auto_restore_on_exit"] = val
        if self.window:
            self.window.save_config()
        self.statusChanged.emit("Settings saved")

    @Slot(bool)
    def set_auto_apply(self, val):
        self.config["auto_apply_on_select"] = val
        if self.window:
            self.window.save_config()
        self.statusChanged.emit("Settings saved")

    @Slot(str)
    def set_dota_path(self, path):
        self.config["dota_path"] = path
        if self.window:
            self.window.save_config()
        self.statusChanged.emit(f"Dota path: {path}")

    @Slot(result=str)
    def browse_dota_path(self):
        if not self.window:
            return ""
        p = QFileDialog.getExistingDirectory(self.window, "Select Dota 2 Directory")
        if p:
            self.config["dota_path"] = p
        if self.window:
            self.window.save_config()
        return p

    @Slot()
    def rebuild_database(self):
        if DATA_FILE.exists():
            DATA_FILE.unlink()
        self.statusChanged.emit("Database cache deleted. Restart to rebuild.")

    @Slot()
    def save_config(self):
        if self.window:
            self.window.save_config()
        self.statusChanged.emit("Settings saved")

    @Slot()
    def start_move(self):
        if self.window and self.window.windowHandle():
            self.window.windowHandle().startSystemMove()

    @Slot(str)
    def start_resize(self, edge):
        if self.window and self.window.windowHandle():
            edges = {
                'n': Qt.Edge.TopEdge, 's': Qt.Edge.BottomEdge, 'e': Qt.Edge.RightEdge, 'w': Qt.Edge.LeftEdge,
                'ne': Qt.Edge.TopEdge | Qt.Edge.RightEdge, 'nw': Qt.Edge.TopEdge | Qt.Edge.LeftEdge,
                'se': Qt.Edge.BottomEdge | Qt.Edge.RightEdge, 'sw': Qt.Edge.BottomEdge | Qt.Edge.LeftEdge
            }
            self.window.windowHandle().startSystemResize(edges.get(edge, Qt.Edge.LeftEdge))

    @Slot()
    def minimize_window(self):
        if self.window:
            self.window.showMinimized()

    @Slot()
    def toggle_maximize_window(self):
        if self.window:
            if self.window.isMaximized():
                self.window.showNormal()
            else:
                self.window.showMaximized()

    @Slot()
    def close_window(self):
        if self.window:
            self.window.close()

    def _item_to_dict(self, item: SkinItem) -> dict:
        display_name = pretty_name(item.localized_name if item.localized_name and not item.localized_name.startswith("#") else item.name)
        for prefix in ["Item ", "Default "]:
            if display_name.startswith(prefix):
                display_name = display_name[len(prefix):]
        meta = []
        if item.rarity:
            meta.append(item.rarity.title())
        if item.is_arcana:
            meta.append("ARCANA")
        if item.is_immortal:
            meta.append("IMMORTAL")
        if item.is_persona:
            meta.append("PERSONA")
        if item.is_gem:
            meta.append("GEM")
        if item.is_bugged:
            meta.append("BUGGED")
        if item.item_slot:
            meta.append(item.item_slot.upper())
        if item.gem_type and item.is_gem:
            meta.append(item.gem_type.upper())
        ability_count = len(item.ability_overrides)
        if ability_count > 0:
            meta.append(f"{ability_count} ABILITY OVRS")
        style_count = len(item.styles)
        if style_count > 0:
            meta.append(f"{style_count} STYLES")
        
        raw_token = ""
        if item.raw_item_data:
            raw_token = item.raw_item_data.get("item_name", "")
        
        return {
            "name": item.name, 
            "display_name": display_name, 
            "localized_name": item.localized_name if item.localized_name != item.name else "",
            "raw_token": raw_token,
            "rarity": item.rarity, "icon_path": choose_icon_path(item.raw_item_data or {}, self.config.get("icon_field", "inventory"), item.icon_path if self.config.get("icon_field") == "auto" else ""), "is_arcana": item.is_arcana, "is_persona": item.is_persona, "is_immortal": item.is_immortal, "is_bugged": item.is_bugged, "is_gem": item.is_gem, "item_slot": item.item_slot, "item_type": getattr(item, 'item_type', ''), "gem_type": item.gem_type, "meta": " · ".join(meta[:4]), "used_by_hero": item.used_by_hero, "ability_overrides": [{"ability_id": ao.ability_id, "icon": ao.icon} for ao in item.ability_overrides], "styles": [{"id": s.style_id, "name": s.name} for s in item.styles], "slots": getattr(item, 'slots', [item.item_slot] if item.item_slot else [])
        }

# ==============================================================================
# HTML UI (same as original but with v13.0 branding)
