from .common import *
from .itemdef import resolve_prefabs, flatten_style, style_ids, modifiers_by_type
from .slots import NON_LOADOUT_SLOTS, slot_sort_key, slot_title
from .itemdef import looks_like_loadout_slot, is_modifier_key
from .kv import kv_base
from .vpk_io import *
from .kv import *
from .slots import *
from .models import *
from .resolver import *
from .extras import *
# ==============================================================================
# SKIN DATABASE
# ==============================================================================

class SkinDatabase:
    def __init__(self, dota_path: Path):
        self.dota_path = dota_path
        self.game_dir = dota_path / "game" / "dota"
        self.vpk_readers: List[VPKReader] = []
        self.items: Dict[str, SkinItem] = {}
        self.heroes: Dict[str, dict] = {}
        self.hero_models: Dict[str, str] = {}
        self.wards: Dict[str, SkinItem] = {}
        self.couriers: Dict[str, SkinItem] = {}
        self.weather_effects: Dict[str, SkinItem] = {}
        self.terrain_effects: Dict[str, SkinItem] = {}
        self.taunts: Dict[str, SkinItem] = {}
        self.gems: Dict[str, SkinItem] = {}
        self.bugged_items: Dict[str, SkinItem] = {}
        self.rarities: Dict[str, str] = {}
        self.qualities: Dict[str, str] = {}
        self.music_packs: Dict[str, SkinItem] = {}
        self.loading_screens: Dict[str, SkinItem] = {}
        self.effigies: Dict[str, SkinItem] = {}
        self.tower_skins: Dict[str, SkinItem] = {}
        self.announcers: Dict[str, SkinItem] = {}
        self.mega_kills: Dict[str, SkinItem] = {}
        self.resource_resolver: Optional[ResourceResolver] = None
        self._items_game_data: Optional[dict] = None
        self.slot_resolver = DynamicSlotResolver()
        self.localization: Dict[str, str] = {}
        self.item_language = "english"
        self.hero_files: Dict[str, str] = {}

    def initialize(self, progress_callback=None) -> bool:
        if DATA_FILE.exists():
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("meta", {}).get("version") != APP_VERSION:
                    log.info("App version changed, clearing database cache.")
                    DATA_FILE.unlink()
                elif data.get("meta", {}).get("item_language", "english") != self.item_language:
                    log.info("Item language changed, clearing database cache.")
                    DATA_FILE.unlink()
                elif data.get("meta", {}).get("game_sig") != self._game_signature():
                    log.info("Game files changed (Dota update), clearing database cache.")
                    DATA_FILE.unlink()
                    for stale in ("items_game.txt", "npc_heroes.txt", "dota_english.txt"):
                        (CACHE_DIR / stale).unlink(missing_ok=True)
                elif data.get("items", {}):
                    first_item = list(data["items"].values())[0]
                    if "raw_item_data" not in first_item:
                        log.info("Cache missing raw_item_data, rebuilding.")
                        DATA_FILE.unlink()
            except: pass
        
        if DATA_FILE.exists():
            if progress_callback: progress_callback("Loading cached database...")
            if self._load_from_json() and len(self.items) > 0 and len(self.heroes) > 0:
                log.info("Database JSON loaded")
                self._ensure_vpks_loaded()
                self._ensure_items_game_in_cache()
                self._parse_localization()
                self._parse_hero_models()
                self._build_dynamic_slot_map()
                self.resource_resolver = ResourceResolver(self.vpk_readers)
                return True
            try: DATA_FILE.unlink()
            except: pass
        if progress_callback: progress_callback("Parsing game files...")
        return self._parse_from_vpk(progress_callback)

    def _game_signature(self) -> str:
        """size+mtime of the game's own paks: changes when Dota updates."""
        try:
            parts = []
            for p in sorted(self.game_dir.glob("pak01_dir.vpk")):
                st = p.stat()
                parts.append(f"{p.name}:{st.st_size}:{int(st.st_mtime)}")
            return "|".join(parts)
        except OSError:
            return ""

    def _ensure_vpks_loaded(self):
        if self.vpk_readers: return
        if not self.game_dir.exists(): return
        vpk_files = sorted(self.game_dir.glob("*_dir.vpk"), key=lambda p: p.stat().st_size, reverse=True)
        for vpk_path in vpk_files:
            reader = VPKReader(vpk_path)
            if reader.files: self.vpk_readers.append(reader)
        log.info(f"Loaded {len(self.vpk_readers)} VPK readers")

    def _ensure_items_game_in_cache(self):
        if (CACHE_DIR / "items_game.txt").exists(): return
        self._ensure_vpks_loaded()
        if not self.vpk_readers: return
        for reader in self.vpk_readers:
            items_file = reader.find_file("items_game.txt")
            if items_file:
                reader.extract_file(items_file, CACHE_DIR / "items_game.txt")
                return

    def _load_tokens(self, lang: str) -> Dict[str, str]:
        """Tokens of resource/localization/dota_<lang>.txt (extracted once into the cache)."""
        fname = f"dota_{lang}.txt"
        cached = CACHE_DIR / fname
        if not cached.exists():
            for reader in self.vpk_readers:
                hit = reader.find_file(fname)
                if not hit:
                    for fp in reader.files:
                        if fp.endswith("/" + fname):
                            hit = fp
                            break
                if hit:
                    reader.extract_file(hit, cached)
                    break
        if not cached.exists():
            return {}
        raw = cached.read_bytes()
        for enc in ("utf-8-sig", "utf-16"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                text = ""
        if not text:
            text = raw.decode("utf-8", errors="ignore")
        data = KeyValueParser(text).parse()
        root = data.get("lang", data)
        tokens = root.get("Tokens", {})
        return {k: v for k, v in tokens.items() if isinstance(v, str)} if isinstance(tokens, dict) else {}

    def available_languages(self) -> List[str]:
        """Languages that ship with the game (dota_<lang>.txt present)."""
        self._ensure_vpks_loaded()
        langs = set()
        for reader in self.vpk_readers:
            for fp in reader.files:
                m = re.search(r"resource/localization/dota_([a-z_]+)\.txt$", fp)
                if m:
                    langs.add(m.group(1))
        return sorted(langs)

    def _parse_localization(self):
        if self.localization: return
        self._ensure_vpks_loaded()
        if not self.vpk_readers: return
        try:
            tokens = self._load_tokens("english")
            if self.item_language and self.item_language != "english":
                over = self._load_tokens(self.item_language)
                tokens.update({k: v for k, v in over.items() if v})      # english stays as fallback
                log.info("Overlaid %d '%s' tokens", len(over), self.item_language)
            self.localization.update(tokens)
            log.info(f"Loaded {len(self.localization)} localization tokens")
        except Exception as e:
            log.error(f"Error parsing localization: {e}")

    def _parse_hero_models(self):
        """Extracts Model paths for each hero from npc_heroes.txt."""
        heroes_path = CACHE_DIR / "npc_heroes.txt"
        if not heroes_path.exists():
            self._ensure_vpks_loaded()
            if not self.vpk_readers: return
            heroes_file = None
            for reader in self.vpk_readers:
                heroes_file = reader.find_file("npc_heroes.txt")
                if heroes_file: break
            if heroes_file:
                for reader in self.vpk_readers:
                    if heroes_file.lower() in reader.files:
                        reader.extract_file(heroes_file, CACHE_DIR / "npc_heroes.txt")
                        break
        
        if not heroes_path.exists(): return
        
        try:
            content = heroes_path.read_text(encoding="utf-8", errors="ignore")
            root = self._merged_hero_root(content)
            if not root: return

            self.hero_models.clear()
            for hero_name, hero_data in root.items():
                if not isinstance(hero_data, dict): continue
                if hero_name in ("Version", "npc_dota_hero_base"): continue
                model = hero_data.get("Model", "") or hero_data.get("model", "")
                if model:
                    self.hero_models[hero_name] = model.lower()
            log.info(f"Hero models parsed: {len(self.hero_models)}")
        except Exception as e:
            log.error(f"Error parsing hero models: {e}")

    def _build_dynamic_slot_map(self):
        items_path = CACHE_DIR / "items_game.txt"
        if not items_path.exists(): return
        try:
            content = items_path.read_text(encoding="utf-8", errors="ignore")
            parser = KeyValueParser(content)
            data = parser.parse()
            self.slot_resolver.build_from_items_game(data)
        except Exception as e: log.error(f"Error building dynamic slot map: {e}")

    def _load_from_json(self) -> bool:
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.rarities = data.get("rarities", {})
            self.qualities = data.get("qualities", {})
            for name, item_data in data.get("items", {}).items():
                used_by = item_data.get("used_by_heroes", [])
                used_by_hero = used_by[0] if isinstance(used_by, list) and used_by else (used_by if isinstance(used_by, str) else "")
                styles = []
                for sd in item_data.get("styles", []):
                    styles.append(StyleDefinition(
                        style_id=sd.get("style_id", 0), name=sd.get("name", ""),
                        model_player=sd.get("model_player", ""), asset=sd.get("asset", ""),
                        particles=sd.get("particles", []), models=sd.get("models", []),
                        materials=sd.get("materials", []), textures=sd.get("textures", []),
                        icons=sd.get("icons", []),
                        raw_data=sd.get("raw_data", {}),
                    ))
                ability_overrides = []
                for ao in item_data.get("ability_overrides", []):
                    ability_overrides.append(AbilityOverride(
                        ability_id=ao.get("ability_id", ""), icon=ao.get("icon", ""),
                        particles=ao.get("particles", []), projectiles=ao.get("projectiles", []),
                        sounds=ao.get("sounds", []), cast_effect=ao.get("cast_effect", ""),
                        hit_effect=ao.get("hit_effect", ""), modifier_effect=ao.get("modifier_effect", ""),
                        raw_data=ao.get("raw_data", {}),
                    ))
                self.items[name] = SkinItem(
                    item_id=item_data.get("id", 0), name=name,
                    prefab=item_data.get("prefab", ""), rarity=item_data.get("rarity", ""),
                    used_by_hero=used_by_hero, visual_assets=item_data.get("visual_assets", []),
                    is_arcana=item_data.get("is_arcana", False), is_persona=item_data.get("is_persona", False),
                    is_immortal=item_data.get("is_immortal", False), is_bugged=item_data.get("is_bugged", False),
                    icon_path=item_data.get("icon_path", ""), particle_effect=item_data.get("particle_effect", ""),
                    item_slot=item_data.get("item_slot", ""), item_type=item_data.get("item_type", ""),
                    quality=item_data.get("quality", ""), category=item_data.get("category", ""),
                    slots=item_data.get("slots", []),
                    model_paths=item_data.get("model_paths", []),
                    material_paths=item_data.get("material_paths", []),
                    particle_paths=item_data.get("particle_paths", []),
                    animation_paths=item_data.get("animation_paths", []),
                    texture_paths=item_data.get("texture_paths", []),
                    sound_paths=item_data.get("sound_paths", []),
                    model_player=item_data.get("model_player", ""),
                    styles=styles, ability_overrides=ability_overrides,
                    icons=item_data.get("icons", {}),
                    asset_modifiers=item_data.get("asset_modifiers", []),
                    is_loading_screen=item_data.get("is_loading_screen", False),
                    is_effigy=item_data.get("is_effigy", False), is_music=item_data.get("is_music", False),
                    is_tower=item_data.get("is_tower", False), is_base=item_data.get("is_base", False),
                    is_fountain=item_data.get("is_fountain", False), is_gem=item_data.get("is_gem", False),
                    gem_type=item_data.get("gem_type", ""), gem_particle=item_data.get("gem_particle", ""),
                    gem_color=item_data.get("gem_color", ""), socketable_slots=item_data.get("socketable_slots", []),
                    terrain_type=item_data.get("terrain_type", ""),
                    terrain_resource_path=item_data.get("terrain_resource_path", ""),
                    weather_particle_path=item_data.get("weather_particle_path", ""),
                    courier_model_path=item_data.get("courier_model_path", ""),
                    is_announcer=item_data.get("is_announcer", False),
                    is_mega_kills=item_data.get("is_mega_kills", False),
                    def_index=item_data.get("def_index", ""), class_name=item_data.get("class_name", ""),
                    internal_name=item_data.get("internal_name", ""), localized_name=item_data.get("localized_name", ""),
                    raw_item_data=item_data.get("raw_item_data", {}),
                )
            for hero_name, hero_data in data.get("heroes", {}).items():
                self.heroes[hero_name] = {
                    "name": hero_name, "display_name": hero_data.get("display_name", hero_name),
                    "attribute": hero_data.get("attribute", ""), "items": hero_data.get("items", []),
                    "icon_path": hero_data.get("icon_path", ""),
                }
            self._categorize_items()
            self._parse_bugged_items()
            log.info(f"Database loaded from JSON: {len(self.items)} items, {len(self.heroes)} heroes")
            return True
        except Exception as e:
            log.error(f"JSON load error: {e}")
            return False

    def _parse_from_vpk(self, progress_callback=None) -> bool:
        try:
            if progress_callback: progress_callback("Loading VPK files...")
            self._ensure_vpks_loaded()
            if not self.vpk_readers: return False
            items_file = None
            for reader in self.vpk_readers:
                items_file = reader.find_file("items_game.txt")
                if items_file: break
            if not items_file:
                for reader in self.vpk_readers:
                    for fp in reader.files:
                        if "items_game" in fp and fp.endswith(".txt"):
                            items_file = fp; break
                    if items_file: break
            if not items_file: return False
            for reader in self.vpk_readers:
                if items_file.lower() in reader.files:
                    reader.extract_file(items_file, CACHE_DIR / "items_game.txt")
                    break
            if progress_callback: progress_callback("Parsing localization...")
            self._parse_localization()          # BEFORE items: item and style names are resolved while parsing
            if progress_callback: progress_callback("Parsing items_game.txt...")
            content = (CACHE_DIR / "items_game.txt").read_text(encoding="utf-8", errors="ignore")
            self._parse_items_game(content)
            heroes_file = None
            for reader in self.vpk_readers:
                heroes_file = reader.find_file("npc_heroes.txt")
                if heroes_file: break
            if heroes_file:
                for reader in self.vpk_readers:
                    if heroes_file.lower() in reader.files:
                        reader.extract_file(heroes_file, CACHE_DIR / "npc_heroes.txt")
                        break
                content = (CACHE_DIR / "npc_heroes.txt").read_text(encoding="utf-8", errors="ignore")
                self._parse_heroes(content)
            else:
                self._parse_heroes_from_items()
            if progress_callback: progress_callback("Parsing hero models...")
            self._parse_hero_models()
            if progress_callback: progress_callback("Parsing localization...")
            self._parse_localization()
            for name, item in self.items.items():
                loc_token = item.raw_item_data.get("item_name", "") if item.raw_item_data else ""
                if loc_token and loc_token.startswith("#"):
                    localized = self.localization.get(loc_token[1:], "")
                    if localized: item.localized_name = localized
            if progress_callback: progress_callback("Categorizing items...")
            self._categorize_items()
            self._parse_bugged_items()
            self._build_dynamic_slot_map()
            if progress_callback: progress_callback("Saving database cache...")
            if len(self.items) > 0 and len(self.heroes) > 0: self._save_json()
            self.resource_resolver = ResourceResolver(self.vpk_readers)
            log.info(f"Database ready: {len(self.items)} items, {len(self.heroes)} heroes")
            return True
        except Exception as e:
            log.error(f"VPK parse error: {e}", exc_info=True)
            return False

    def _parse_heroes_from_items(self):
        self.heroes.clear()
        for name, item in self.items.items():
            if item.used_by_hero:
                if item.used_by_hero not in self.heroes and "npc_dota_hero_" in item.used_by_hero and "test" not in item.used_by_hero.lower() and "base" not in item.used_by_hero.lower() and "dummy" not in item.used_by_hero.lower():
                    short_name = item.used_by_hero.replace("npc_dota_hero_", "")
                    display_name = short_name.replace("_", " ").title()
                    self.heroes[item.used_by_hero] = {"name": item.used_by_hero, "display_name": display_name, "attribute": "", "items": []}
        for name, item in self.items.items():
            if item.used_by_hero and item.used_by_hero in self.heroes:
                self.heroes[item.used_by_hero]["items"].append(name)

    def _parse_items_game(self, content: str):
        parser = KeyValueParser(content)
        data = parser.parse()
        self._items_game_data = data
        root = data.get("items_game", data)
        if not isinstance(root, dict): root = {}
        items = root.get("items", {})
        if not isinstance(items, dict): return
        
        rarities_data = root.get("rarities", {})
        if isinstance(rarities_data, dict):
            for rid, rinfo in rarities_data.items():
                if isinstance(rinfo, dict): self.rarities[rid] = rinfo.get("name", "").lower()
        qualities_data = root.get("qualities", {})
        if isinstance(qualities_data, dict):
            for qid, qinfo in qualities_data.items():
                if isinstance(qinfo, dict): self.qualities[qid] = qinfo.get("name", "").lower()
        
        count = 0
        prefabs_data = root.get("prefabs", {})
        _pcache: dict = {}
        for item_id_str, item_data in items.items():
            if not isinstance(item_data, dict): continue
            try: item_id = int(item_id_str)
            except ValueError: continue
            # inherit everything the item's prefab(s) define (item_slot, rarity, visuals ...)
            if str(item_data.get("prefab", "")).strip():
                item_data = resolve_prefabs(item_data, prefabs_data, 0, _pcache)
            
            prefab = item_data.get("prefab", "")
            prefab_lower = prefab.lower()
            
            if prefab_lower in ("base", "fountain"):
                continue
                
            name = item_data.get("name", f"item_{item_id}")
            rarity = item_data.get("item_rarity", "") or item_data.get("rarity", "")
            if isinstance(rarity, str) and rarity.isdigit(): rarity = self.rarities.get(rarity, "")
            rarity_lower = str(rarity).lower()
            quality = item_data.get("item_quality", "") or item_data.get("quality", "")
            if isinstance(quality, str) and quality.isdigit(): quality = self.qualities.get(quality, "")

            item_slot = item_data.get("item_slot", "")
            slots = []
            if item_slot: slots.append(item_slot)
            am_data = item_data.get("asset_modifiers", {})
            if isinstance(am_data, dict):
                for _, am in am_data.items():
                    if isinstance(am, dict):
                        mod_slot = am.get("slot", "")
                        if mod_slot and mod_slot not in slots: slots.append(mod_slot)

            if item_slot == "taunt" or prefab_lower == "taunt":
                item_type = "taunt"
            elif prefab_lower == "arcana":
                item_type = "arcana"
            elif prefab_lower == "persona" or self._persona_like(item_data, prefab_lower, item_slot):
                item_type = "persona"
            elif prefab_lower == "courier" or item_slot == "courier":
                item_type = "courier"
            elif prefab_lower == "ward" or item_slot == "ward":
                item_type = "ward"
            elif prefab_lower == "bundle":
                item_type = "bundle"
            elif prefab_lower == "loading_screen" or item_slot == "loading_screen":
                item_type = "loading_screen"
            elif prefab_lower == "effigy":
                item_type = "effigy"
            elif prefab_lower == "music" or item_slot == "music":
                item_type = "music"
            elif prefab_lower in ("terrain", "landscape") or item_slot == "terrain":
                item_type = "terrain"
            elif prefab_lower == "weather" or item_slot == "weather":
                item_type = "weather"
            elif prefab_lower == "tower" or item_slot == "tower_skin":
                item_type = "tower"
            elif prefab_lower == "announcer" or item_slot == "announcer":
                item_type = "announcer"
            elif prefab_lower == "mega_kills" or item_slot == "kill_streak":
                item_type = "mega_kills"
            elif prefab_lower in ("gem", "kinetic", "prismatic", "ethereal", "unusual",
                                  "frozen", "autograph", "polarity", "ascendant"):
                item_type = "gem"
            elif prefab_lower == "default_item":
                item_type = "default"
            else:
                item_type = "wearable"

            category = "hero_cosmetic"
            if item_type in ("ward", "courier", "loading_screen", "effigy", "music", "terrain", "weather", "taunt", "tower", "announcer", "mega_kills", "gem"): 
                category = item_type
            elif prefab_lower == "bundle": 
                category = "bundle"
                
            icons = {}
            icon_path = (item_data.get("image_inventory", "") or item_data.get("image_browser", "") or 
                         item_data.get("icon", "") or item_data.get("image_inventory_wide", "") or 
                         item_data.get("image_large", "") or item_data.get("image_store", ""))
            if icon_path: icons["item"] = icon_path
            hero_icon = item_data.get("hero_icon", "") or item_data.get("image_hero", "")
            if hero_icon: icons["hero"] = hero_icon
            portrait = item_data.get("portrait", "") or item_data.get("image_portrait", "")
            if portrait: icons["portrait"] = portrait
            
            used_by = ""
            used_by_data = item_data.get("used_by_heroes", {})
            if isinstance(used_by_data, dict):
                for hero_name, val in used_by_data.items():
                    if str(val) == "1":
                        used_by = hero_name
                        break
                        
            model_player = item_data.get("model_player", "") or item_data.get("model", "")
            visuals = []
            model_paths = []
            material_paths = []
            particle_paths = []
            animation_paths = []
            texture_paths = []
            sound_paths = []
            particle_effect = ""
            terrain_type = item_data.get("terrain_type", "") or item_data.get("terrain", "")
            terrain_resource_path = ""
            weather_particle_path = ""
            courier_model_path = ""
            
            if model_player:
                model_paths.append(model_player)
                visuals.append(model_player)
                if prefab_lower == "courier" or item_slot == "courier": courier_model_path = model_player
                
            visuals_data = item_data.get("visuals", {})
            if isinstance(visuals_data, dict):
                for _, ve in visuals_data.items():
                    if not isinstance(ve, dict): continue
                    ve_type = ve.get("type", "")
                    for field_key, field_val in ve.items():
                        if not field_val or field_key in ("type",): continue
                        if field_key in ("asset", "model_player", "model"):
                            visuals.append(field_val); model_paths.append(field_val)
                        elif field_key == "particle":
                            visuals.append(field_val); particle_paths.append(field_val)
                            if not particle_effect: particle_effect = field_val
                            if prefab_lower == "weather": weather_particle_path = field_val
                        elif field_key == "terrain":
                            visuals.append(f"terrain:{field_val}"); terrain_type = field_val; terrain_resource_path = field_val
                        elif field_key == "animation":
                            animation_paths.append(field_val); visuals.append(field_val)
                        elif field_key in ("material", "texture"):
                            material_paths.append(field_val); texture_paths.append(field_val); visuals.append(field_val)
                        elif field_key == "sound":
                            sound_paths.append(field_val); visuals.append(field_val)
                    # asset_modifier: `asset` is what is replaced, `modifier` is the replacement
                    mod_val = ve.get("modifier", "")
                    if isinstance(mod_val, str) and "/" in mod_val:
                        ml = mod_val.lower()
                        visuals.append(mod_val)
                        if ".vmdl" in ml: model_paths.append(mod_val)
                        elif ".vpcf" in ml:
                            particle_paths.append(mod_val)
                            if not particle_effect: particle_effect = mod_val
                            if prefab_lower == "weather": weather_particle_path = mod_val
                        elif ".vsnd" in ml: sound_paths.append(mod_val)
                        elif ".vanim" in ml: animation_paths.append(mod_val)
                        elif ".vmat" in ml: material_paths.append(mod_val)
                    if ve_type == "terrain":
                        t = ve.get("value", "")
                        if t:
                            terrain_type = t; visuals.append(f"terrain:{t}"); terrain_resource_path = t
                            
            particle_data = item_data.get("attached_particle_effects", {})
            if isinstance(particle_data, dict):
                for _, pe in particle_data.items():
                    if isinstance(pe, dict):
                        particle = pe.get("particle", "")
                        if particle:
                            visuals.append(particle); particle_paths.append(particle)
                            if not particle_effect: particle_effect = particle
                            if prefab_lower == "weather": weather_particle_path = particle
                            
            style_defs = []
            styles_data = item_data.get("styles", {})
            if not (isinstance(styles_data, dict) and styles_data):
                _vis = item_data.get("visuals", {})
                styles_data = _vis.get("styles", {}) if isinstance(_vis, dict) else {}
            if isinstance(styles_data, dict):
                for style_id_str, sd in styles_data.items():
                    if not isinstance(sd, dict): continue
                    try: style_id = int(style_id_str)
                    except ValueError: continue
                    style_name = self._style_title(sd.get("name", ""), style_id)
                    style_model = sd.get("model_player", "")
                    style_asset = sd.get("asset", "")
                    style_particles = []
                    style_models = []
                    style_materials = []
                    style_textures = []
                    style_icons = []
                    if style_model: style_models.append(style_model)
                    if style_asset: style_models.append(style_asset)
                    style_visuals = sd.get("visuals", {})
                    if isinstance(style_visuals, dict):
                        for _, sve in style_visuals.items():
                            if isinstance(sve, dict):
                                sv_asset = sve.get("asset", "") or sve.get("model_player", "") or sve.get("model", "")
                                sv_particle = sve.get("particle", "")
                                sv_material = sve.get("material", "")
                                sv_texture = sve.get("texture", "")
                                sv_icon = sve.get("icon", "")
                                sv_animation = sve.get("animation", "")
                                if sv_asset: style_models.append(sv_asset)
                                if sv_particle: style_particles.append(sv_particle)
                                if sv_material: style_materials.append(sv_material)
                                if sv_texture: style_textures.append(sv_texture)
                                if sv_icon: style_icons.append(sv_icon)
                                if sv_animation: style_models.append(sv_animation)
                    style_am = sd.get("asset_modifiers", {})
                    if isinstance(style_am, dict):
                        for _, sam in style_am.items():
                            if isinstance(sam, dict):
                                sam_type = sam.get("type", "")
                                sam_asset = sam.get("asset", "") or sam.get("model_player", "") or sam.get("model", "")
                                sam_particle = sam.get("particle", "")
                                if sam_type == "particle" and sam_asset and not sam_particle:
                                    sam_particle = sam_asset; sam_asset = ""
                                if sam_asset: style_models.append(sam_asset)
                                if sam_particle: style_particles.append(sam_particle)
                                if sam_type == "icon" and sam_asset: style_icons.append(sam_asset)
                    style_def = StyleDefinition(
                        style_id=style_id, name=style_name, model_player=style_model, asset=style_asset,
                        particles=style_particles, models=style_models, materials=style_materials,
                        textures=style_textures, icons=style_icons, raw_data=copy.deepcopy(sd)
                    )
                    model_paths.extend(style_models)
                    particle_paths.extend(style_particles)
                    material_paths.extend(style_materials)
                    texture_paths.extend(style_textures)
                    style_defs.append(style_def)
                    
            asset_mods = []
            am_data = item_data.get("asset_modifiers", {})
            if isinstance(am_data, dict):
                for _, am in am_data.items():
                    if not isinstance(am, dict): continue
                    mod_type = am.get("type", "")
                    mod_asset = am.get("asset", "") or am.get("model_player", "") or am.get("model", "")
                    mod_particle = am.get("particle", "")
                    mod_slot = am.get("slot", "")
                    mod_icon = am.get("icon", "")
                    if mod_type == "particle" and mod_asset and not mod_particle:
                        mod_particle = mod_asset; mod_asset = ""
                    mod_entry = {"type": mod_type, "slot": mod_slot}
                    if mod_asset:
                        mod_entry["asset"] = mod_asset; model_paths.append(mod_asset); visuals.append(mod_asset)
                    if mod_particle:
                        mod_entry["particle"] = mod_particle; particle_paths.append(mod_particle); visuals.append(mod_particle)
                        if not particle_effect: particle_effect = mod_particle
                    if mod_icon:
                        mod_entry["icon"] = mod_icon; icons["ability"] = mod_icon
                    if mod_entry: asset_mods.append(mod_entry)
                    
            ability_overrides = []
            if isinstance(am_data, dict):
                for _, am in am_data.items():
                    if not isinstance(am, dict): continue
                    am_type = am.get("type", "").lower()
                    am_ability = am.get("ability", "") or am.get("ability_id", "")
                    if am_type in ("ability_icon", "icon", "ability_effect", "ability_particle", "ability_projectile", "ability_modifier", "ability_override"):
                        override = None
                        for ao in ability_overrides:
                            if ao.ability_id == am_ability: override = ao; break
                        if not override:
                            override = AbilityOverride(ability_id=am_ability)
                            ability_overrides.append(override)
                        am_asset = am.get("asset", "") or am.get("model_player", "") or am.get("model", "")
                        am_particle = am.get("particle", "")
                        if am_type in ("ability_icon", "icon"):
                            override.icon = am_asset
                            if am_asset: icons["ability"] = am_asset
                        elif am_type == "ability_particle":
                            if am_particle: override.particles.append(am_particle); particle_paths.append(am_particle)
                        elif am_type == "ability_projectile":
                            if am_particle: override.projectiles.append(am_particle); particle_paths.append(am_particle)
                        elif am_type == "ability_modifier":
                            if am_particle: override.modifier_effect = am_particle; particle_paths.append(am_particle)
                        elif am_type == "ability_effect":
                            if am_particle: override.particles.append(am_particle); particle_paths.append(am_particle)
                            if am_asset: override.cast_effect = am_asset

            visuals_data_check = item_data.get("visuals", {})
            if isinstance(visuals_data_check, dict):
                for _, ve in visuals_data_check.items():
                    if isinstance(ve, dict):
                        ve_type = ve.get("type", "").lower()
                        ve_ability = ve.get("ability", "") or ve.get("ability_id", "")
                        ve_asset = ve.get("asset", "") or ve.get("model_player", "")
                        ve_particle = ve.get("particle", "")
                        if ve_type in ("ability_icon", "icon") and ve_ability:
                            override = None
                            for ao in ability_overrides:
                                if ao.ability_id == ve_ability: override = ao; break
                            if not override:
                                override = AbilityOverride(ability_id=ve_ability)
                                ability_overrides.append(override)
                            override.icon = ve_asset
                            if ve_asset: icons["ability"] = ve_asset
                        elif ve_type == "ability_particle" and ve_ability:
                            override = None
                            for ao in ability_overrides:
                                if ao.ability_id == ve_ability: override = ao; break
                            if not override:
                                override = AbilityOverride(ability_id=ve_ability)
                                ability_overrides.append(override)
                            if ve_particle:
                                override.particles.append(ve_particle); particle_paths.append(ve_particle)

            # items_game stores the rarity as the bare key ("arcana"), the localized token is "rarity_arcana"
            is_arcana = (prefab_lower == "arcana" or item_type == "arcana" or
                         rarity_lower.replace("rarity_", "") == "arcana" or
                         "selfglow" in rarity_lower)
            is_persona = (prefab_lower == "persona" or item_type == "persona" or self._persona_like(item_data, prefab_lower, item_slot))
            is_immortal = "immortal" in rarity_lower
            
            bugged_qualities = {"strange", "genuine", "vintage", "haunted", "collectors", 
                                "corrupted", "ascendant", "exalted", "frozen", "cursed",
                                "merciless", "unusual"}
            quality_lower = str(quality).lower() if quality else ""
            is_bugged = quality_lower in bugged_qualities
            
            is_loading_screen = prefab_lower == "loading_screen" or item_type == "loading_screen"
            is_effigy = prefab_lower == "effigy" or item_type == "effigy"
            is_music = prefab_lower == "music" or item_type == "music"
            is_tower = prefab_lower == "tower" or item_type == "tower"
            is_base = prefab_lower == "base"
            is_fountain = prefab_lower == "fountain"
            is_announcer = prefab_lower == "announcer" or item_type == "announcer"
            is_mega_kills = prefab_lower == "mega_kills" or item_type == "mega_kills"
            is_gem = False                      # gem sockets are not supported any more
            gem_type = ""
            gem_particle = particle_effect
            gem_color = ""

            socketable_slots = []
            sockets_data = item_data.get("socket", {}) or item_data.get("sockets", {})
            if isinstance(sockets_data, dict):
                for _, sd in sockets_data.items():
                    if isinstance(sd, dict):
                        slot = sd.get("slot", "")
                        if slot: socketable_slots.append(slot)
                        
            def_index = item_data.get("def_index", str(item_id))
            class_name = item_data.get("class", "")
            internal_name = name
            loc_token = item_data.get("item_name", "") or name
            localized_name = self.localization.get(loc_token[1:] if loc_token.startswith("#") else loc_token, "") or name
            
            model_paths = list(dict.fromkeys(model_paths))
            material_paths = list(dict.fromkeys(material_paths))
            particle_paths = list(dict.fromkeys(particle_paths))
            animation_paths = list(dict.fromkeys(animation_paths))
            texture_paths = list(dict.fromkeys(texture_paths))
            sound_paths = list(dict.fromkeys(sound_paths))
            
            if name in self.items:                      # same internal name twice: keep both (they used to overwrite each other)
                name = f"{name} #{item_id}"
                internal_name = name
            self.items[name] = SkinItem(
                item_id=item_id, name=name, prefab=prefab, rarity=rarity, used_by_hero=used_by,
                visual_assets=visuals, is_arcana=is_arcana, is_persona=is_persona,
                is_immortal=is_immortal, is_bugged=is_bugged, icon_path=icon_path,
                particle_effect=particle_effect, item_slot=item_slot, item_type=item_type,
                quality=quality, category=category, slots=slots,
                model_paths=model_paths, material_paths=material_paths,
                particle_paths=particle_paths, animation_paths=animation_paths,
                texture_paths=texture_paths, sound_paths=sound_paths,
                model_player=model_player, styles=style_defs, ability_overrides=ability_overrides,
                icons=icons, asset_modifiers=asset_mods,
                is_loading_screen=is_loading_screen, is_effigy=is_effigy, is_music=is_music,
                is_tower=is_tower, is_base=is_base, is_fountain=is_fountain,
                is_gem=is_gem, gem_type=gem_type, gem_particle=gem_particle, gem_color=gem_color,
                socketable_slots=socketable_slots, terrain_type=terrain_type,
                terrain_resource_path=terrain_resource_path, weather_particle_path=weather_particle_path,
                courier_model_path=courier_model_path, is_announcer=is_announcer, is_mega_kills=is_mega_kills,
                raw_item_data=copy.deepcopy(item_data), def_index=def_index, class_name=class_name,
                internal_name=internal_name, localized_name=localized_name,
            )
            count += 1
        log.info(f"Parsed {count} items from items_game.txt")

    def _style_title(self, raw, style_id: int) -> str:
        """Readable style name: localized token, or the plain text, or "Style N"."""
        raw = str(raw or "").strip()
        if raw.startswith("#"):
            loc = self.localization.get(raw[1:], "")
            if loc:
                return loc
            raw = ""
        if raw and not re.fullmatch(r"[A-Za-z_]*_[A-Za-z0-9_]+", raw):
            return raw
        if raw:
            loc = self.localization.get(raw, "")
            if loc:
                return loc
        return f"Style {int(style_id) + 1}"

    def _merged_hero_root(self, content: str) -> dict:
        """
        npc_heroes.txt, with `#base "heroes/<file>.txt"` includes expanded. Newer Dota versions keep one file per hero;
        without this the master file has no hero blocks, so attributes/models were empty (attribute filter dead).
        `self.hero_files[hero]` remembers which pak file a hero came from (needed to patch its model).
        """
        data = KeyValueParser(content).parse()
        root = data.get("DOTAHeroes", data)
        if not isinstance(root, dict):
            return {}
        merged: dict = {}
        self.hero_files = {}
        for k, v in root.items():
            if kv_base(k) in ("#base", "#include") and isinstance(v, str):
                rel = v.replace("\\", "/").lstrip("/")
                path = rel.lower() if rel.lower().startswith("scripts/") else ("scripts/npc/" + rel.lower())
                raw = None
                for reader in self.vpk_readers:
                    if path in reader.files:
                        raw = reader.extract_to_bytes(path)
                        break
                if not raw:
                    continue
                sub = KeyValueParser(raw.decode("utf-8", errors="ignore")).parse()
                subroot = sub.get("DOTAHeroes", sub)
                for hk, hv in subroot.items():
                    if isinstance(hv, dict):
                        merged[hk] = hv
                        self.hero_files[hk] = path
            else:
                merged[k] = v
        return merged

    def _parse_heroes(self, content: str):
        root = self._merged_hero_root(content)
        for hero_name, hero_data in root.items():
            if hero_name in ("Version", "npc_dota_hero_base") or not isinstance(hero_data, dict): continue
            if any(kw in hero_name.lower() for kw in ["test", "dummy", "base", "tutorial"]): continue
            display_name = hero_data.get("workshop_guide_name", "")
            if not display_name: display_name = hero_name.replace("npc_dota_hero_", "").replace("_", " ").title()
            url = hero_data.get("url", "")
            if url: display_name = url.split("/")[-1].replace("_", " ").title()
            primary_attr = hero_data.get("AttributePrimary", "")
            attr_letter = ""
            if "AGILITY" in primary_attr: attr_letter = "agi"
            elif "STRENGTH" in primary_attr: attr_letter = "str"
            elif "INTELLECT" in primary_attr or "INTELLIGENCE" in primary_attr: attr_letter = "int"
            elif "ALL" in primary_attr: attr_letter = "uni"
            short_name = hero_name.replace("npc_dota_hero_", "")
            self.heroes[hero_name] = {"name": hero_name, "display_name": display_name, "attribute": attr_letter, "icon_path": f"panorama/images/heroes/{short_name}.png", "items": []}
        if len(self.heroes) == 0:
            self._parse_heroes_from_items()
        else:
            for name, item in self.items.items():
                if item.used_by_hero and item.used_by_hero not in self.heroes:
                    if "npc_dota_hero_" in item.used_by_hero and "test" not in item.used_by_hero.lower() and "dummy" not in item.used_by_hero.lower():
                        short_name = item.used_by_hero.replace("npc_dota_hero_", "")
                        display_name = short_name.replace("_", " ").title()
                        self.heroes[item.used_by_hero] = {"name": item.used_by_hero, "display_name": display_name, "attribute": "", "items": []}
            for name, item in self.items.items():
                if item.used_by_hero and item.used_by_hero in self.heroes:
                    self.heroes[item.used_by_hero]["items"].append(name)

    # ------------------------------------------------------------------ category engine
    # Rules are matched against the prefab-resolved item: prefab tokens, item_slot, item_type_name and name.
    # Known real values (taken from community patcher data): towers `diretowers`/`radianttowers`, creeps `direcreeps`,
    # cursors `cursor_pack`, HUD `hud_skin`, kill streak `streak_effect`, weather `weather`, terrain `terrain`.
    # Categories whose real names I could not verify use keyword rules; `python -m chameleon.diagnose --categories`
    # prints every prefab/slot/type name found in the data so a rule can be added without guessing.
    CATEGORY_GROUPS = [
        ("world", ["weather", "terrain", "shaders"]),
        ("units", ["towers", "creeps", "ancients", "roshan", "tormentor", "statues"]),
        ("items", ["wards", "couriers", "courier_effects", "emblems"]),
        ("effects", ["head_effects", "teleport_effects", "blink_effects", "death_effects"]),
        ("interface", ["hud", "cursors", "loadings", "versus"]),
        ("sound", ["music", "mega_kills", "announcers"]),
    ]
    # categories whose items may carry used_by_heroes and still belong in the (hero-less) catalog
    HERO_AGNOSTIC = {"emblems", "head_effects", "teleport_effects", "blink_effects", "death_effects",
                     "courier_effects", "statues", "gems", "shaders"}
    # (category, field, mode, tokens)   field: prefab | slot | type | any ; mode: eq | has | end
    CATEGORY_RULES = [
        # names taken from real `diagnose --categories` output
        ("head_effects", "any", "has", ("head_effect", "headeffect")),
        ("courier_effects", "any", "has", ("courier_effect", "couriereffect")),
        ("death_effects", "any", "has", ("death_effect", "deatheffect")),
        ("shaders", "any", "has", ("map_effect", "mapeffect")),
        ("teleport_effects", "any", "has", ("teleport_effect", "teleporteffect")),
        ("blink_effects", "any", "has", ("blink_effect", "blinkeffect")),
        ("statues", "any", "eq", ("heroic_statue",)),
        ("gems", "prefab", "eq", ("socket_gem",)),
        ("weather", "any", "eq", ("weather",)),
        ("terrain", "any", "eq", ("terrain", "landscape")),
        ("shaders", "any", "has", ("shader", "screen_effect", "screeneffect", "color_filter", "colorfilter", "colorcorrection",
                                   "color_correction", "screen_filter", "post_process", "postprocess", "postfx", "screen_fx")),
        ("towers", "prefab", "end", ("towers", "tower")),
        ("towers", "slot", "eq", ("tower_skin",)),
        ("creeps", "prefab", "end", ("creeps",)),
        ("creeps", "any", "has", ("lane_creep", "siege_creep", "siegecreep")),
        ("ancients", "prefab", "has", ("ancient",)),
        ("roshan", "any", "has", ("roshan",)),
        ("tormentor", "any", "has", ("tormentor", "miniboss")),
        ("emblems", "any", "has", ("emblem", "effigy", "ambient_effect", "ground_effect", "aura_effect")),
        ("wards", "prefab", "has", ("ward_observer", "ward_sentry", "ward")),
        ("wards", "slot", "eq", ("ward",)),
        ("couriers", "any", "eq", ("courier",)),
        ("hud", "any", "eq", ("hud_skin",)),
        ("cursors", "any", "eq", ("cursor_pack",)),
        ("loadings", "any", "eq", ("loading_screen",)),
        ("versus", "any", "has", ("versus",)),
        ("music", "any", "has", ("music", "soundtrack")),
        ("mega_kills", "any", "has", ("mega_kill",)),
        ("announcers", "any", "eq", ("announcer",)),
    ]
    # things that are containers / tools / gifts, never skins: treasure chests, bundles, keys ... (they often have "music" in the name)
    NOT_A_SKIN = ("treasure", "chest", "bundle", "crate", "key", "tool", "gift", "coupon", "tip", "pass", "ticket", "league", "emoticon",
                  "player_card", "ability_icon")

    # modifier `type`s / resource extensions that identify a category regardless of how Valve named the prefab
    MODIFIER_HINTS = [("music", ("music", "soundtrack")),
                      ("shaders", ("screen_shader", "color_correction", "colorcorrection", "post_process", "screen_effect", "map_shader", "shader")),
                      ("emblems", ("emblem", "effigy", "ambient_effect"))]
    EXT_HINTS = [("shaders", (".vpost",))]
    # any string inside the item (not just modifiers) that points at post-processing / colour-correction data
    PATH_HINTS = [("shaders", (".vpost", "/correction/", "color_correction", "/postprocessing/", "colorcorrection"))]

    @staticmethod
    def _persona_like(raw: dict, prefab: str, slot: str) -> bool:
        """Personas are not always prefab "persona": also by slot, type, name token or a persona modifier. Hero items only."""
        if not (isinstance(raw.get("used_by_heroes"), dict) and raw.get("used_by_heroes")):
            return False
        typ = str(raw.get("item_type_name", "")).lower()
        if "persona" in prefab or "persona" in str(slot).lower() or "persona" in typ:
            return "default" not in prefab
        tok = f"{raw.get('item_name', '')} {raw.get('name', '')}".lower()
        if "persona" in tok:
            return True
        vis = raw.get("visuals", {})
        if isinstance(vis, dict):
            for v in vis.values():
                if isinstance(v, dict) and ("persona" in str(v.get("type", "")).lower() or "persona" in str(v.get("asset", "")).lower()):
                    return True
        return False

    @staticmethod
    def _rule_hit(values, mode, tokens) -> bool:
        for v in values:
            if not v:
                continue
            v = v.lower()
            for t in tokens:
                if (mode == "eq" and v == t) or (mode == "has" and t in v) or (mode == "end" and v.endswith(t)):
                    return True
        return False

    def music_ids(self) -> Set[str]:
        """Names of the music packs that really exist in the game files (folders under soundevents/music and sounds/music)."""
        if getattr(self, "_music_ids", None) is None:
            ids: Set[str] = set()
            for reader in self.vpk_readers:
                for fp in reader.files:
                    m = re.match(r"^(?:soundevents|sounds)/music/([^/]+)/", fp)
                    if m and len(m.group(1)) >= 5:
                        ids.add(m.group(1).lower())
            self._music_ids = ids
        return self._music_ids

    def category_of(self, item: SkinItem) -> Optional[str]:
        raw = item.raw_item_data or {}
        prefabs = [p for p in str(item.prefab).lower().split() if p not in ("wearable", "default_item")]
        slot = str(item.item_slot or "").lower()
        typ = str(raw.get("item_type_name", "")).lower().replace("#dota_wearabletype_", "")
        if any(tok in x for x in prefabs + [typ] for tok in self.NOT_A_SKIN) and "key" not in slot:
            return None                         # a treasure chest / bundle / key is not a skin, whatever its name says
        field = {"prefab": prefabs, "slot": [slot], "type": [typ], "any": prefabs + [slot, typ]}
        for cat, fld, mode, tokens in self.CATEGORY_RULES:
            if self._rule_hit(field[fld], mode, tokens):
                return cat
        # data-driven fallback: what the item's modifiers / files really are
        vis = raw.get("visuals", {}) if isinstance(raw.get("visuals", {}), dict) else {}
        types = [str(v.get("type", "")).lower() for k, v in vis.items() if isinstance(v, dict)]
        paths = [str(v.get("modifier", "")).lower() for k, v in vis.items() if isinstance(v, dict)]
        for cat, toks in self.MODIFIER_HINTS:
            if any(t in ty for ty in types for t in toks):
                return cat
        for cat, exts in self.EXT_HINTS:
            if any(p.endswith(exts) or any(e in p for e in exts) for p in paths):
                return cat
        for cat, toks in self.PATH_HINTS:
            strings = [v.lower() for v in self._all_strings(raw)]
            if any(t in sv for sv in strings for t in toks):
                return cat
        if not raw.get("used_by_heroes"):
            # music packs whose prefab/slot say nothing: look at EVERY string of the item (icon path "econ/music/...",
            # name token, sound event). Treasure chests / bundles were already excluded above.
            low = [v.lower() for v in self._all_strings(raw)]
            ids = self.music_ids()
            # a modifier / name that equals the folder of a real music pack in the game files is the surest sign of a music pack
            if ids and any(sv in ids or sv.rsplit("/", 1)[-1] in ids for sv in low):
                return "music"
            # otherwise any string that says music (icon path "econ/music/...", name token ...), never a treasure chest
            if any(("music" in sv or "soundtrack" in sv) for sv in low) and not any(("treasure" in sv or "chest" in sv) for sv in low[:6]):
                return "music"
        return None

    @staticmethod
    def _all_strings(node, out=None):
        out = [] if out is None else out
        if isinstance(node, dict):
            for v in node.values():
                SkinDatabase._all_strings(v, out)
        elif isinstance(node, str):
            out.append(node)
        return out

    def _categorize_items(self):
        self.categories: Dict[str, Dict[str, SkinItem]] = {c: {} for _, cs in self.CATEGORY_GROUPS for c in cs}
        self.categories["gems"] = {}                    # not a catalog tab: offered on the hero page
        self.taunts.clear(); self.bugged_items.clear()
        real = [i for i in self.items.values() if "default_item" not in i.prefab.split() and not i.name.lower().startswith("default")]
        named = sum(1 for i in real if i.localized_name not in ("", i.name))
        self._loc_ok = bool(real) and named >= 0.5 * len(real)      # only trust the filter when localization really loaded

        for name, item in self.items.items():
            raw = item.raw_item_data or {}
            prefab = item.prefab.lower().strip()
            slot = item.item_slot.lower().strip()
            if prefab in ("base", "fountain") or slot in ("base", "fountain") or "fountain" in prefab:
                continue
            if prefab == "taunt" or slot == "taunt":
                self.taunts[name] = item
                continue
            if str(raw.get("baseitem", "")) == "1" or self.is_system_item(item, strict=False):
                continue                                   # defaults are override TARGETS, never choices
            cat = self.category_of(item)
            if cat:
                hero_bound = bool(raw.get("used_by_heroes")) and cat not in self.HERO_AGNOSTIC
                if not hero_bound:
                    self.categories[cat][name] = item
                continue
            if item.is_bugged and prefab != "default_item":
                self.bugged_items[name] = item
        c = self.categories
        # legacy views other modules still read
        self.wards, self.couriers = c["wards"], c["couriers"]
        self.weather_effects, self.terrain_effects = c["weather"], c["terrain"]
        self.music_packs, self.loading_screens, self.effigies = c["music"], c["loadings"], c["emblems"]
        self.tower_skins, self.announcers, self.mega_kills = c["towers"], c["announcers"], c["mega_kills"]
        self.gems = c["gems"]
        log.info("Categories: " + ", ".join(f"{k}={len(v)}" for k, v in c.items() if v))

    # ------------------------------------------------------------------ gems (Terrorblade / Techies arcana ...)
    @staticmethod
    def _has_effect(item: SkinItem) -> bool:
        vis = (item.raw_item_data or {}).get("visuals", {})
        return isinstance(vis, dict) and any(is_modifier_key(k) and isinstance(v, dict) for k, v in vis.items())

    def _gem_heroes(self, gem: SkinItem) -> Set[str]:
        raw = gem.raw_item_data or {}
        heroes: Set[str] = set()
        ub = raw.get("used_by_heroes")
        if isinstance(ub, dict):
            heroes |= set(ub)
        blob = " ".join(self._all_strings(raw.get("visuals", {}))).lower()
        label = f"{gem.name} {gem.localized_name}".lower()
        for h, hd in self.heroes.items():
            short = h.replace("npc_dota_hero_", "")
            disp = str(hd.get("display_name", "")).lower()
            if f"hero_{short}" in blob or f"/{short}/" in blob or short in label or (len(disp) > 4 and disp in label):
                heroes.add(h)
        return heroes

    def effect_gems(self) -> List[SkinItem]:
        """All gems that actually change something (stat-only gems have no modifiers and are never offered)."""
        return sorted((g for g in self.categories.get("gems", {}).values() if self._has_effect(g)),
                      key=lambda g: g.localized_name or g.name)

    def get_hero_gems(self, hero_name: str) -> List[SkinItem]:
        """
        Gems for a hero's arcana: those tied to the hero (by id, by name, or by the hero's particle paths in the gem).
        A hero that has an arcana but no tied gem gets every effect gem, so the choice is never missing.
        """
        gems = {g.name: g for g in self.effect_gems()}
        if not hasattr(self, "_gem_index") or self._gem_index_n != len(self.categories.get("gems", {})):
            self._gem_index = {g.name: self._gem_heroes(g) for g in self.effect_gems()}
            self._gem_index_n = len(self.categories.get("gems", {}))
        hinted = [gems[n] for n, hs in self._gem_index.items() if hero_name in hs and n in gems]
        if hinted:
            return sorted(hinted, key=lambda g: g.localized_name or g.name)
        hero = self.heroes.get(hero_name) or {}
        has_arcana = any((self.items.get(n) and self.items[n].is_arcana) for n in hero.get("items", []))
        return list(gems.values()) if has_arcana else []

    def category_items(self, cat: str) -> Dict[str, SkinItem]:
        if cat == "taunts":
            return self.taunts
        if cat == "bugged":
            return self.bugged_items
        return getattr(self, "categories", {}).get(cat, {})

    def _parse_bugged_items(self):
        for name, item in self.items.items():
            if item.is_bugged: self.bugged_items[name] = item

    def _save_json(self):
        database = {
            "meta": {"item_language": self.item_language, "game_sig": self._game_signature(), "generated": datetime.now().isoformat(), "total_items": len(self.items), "total_heroes": len(self.heroes), "version": APP_VERSION},
            "rarities": self.rarities, "qualities": self.qualities, "heroes": self.heroes, "items": {},
        }
        for name, item in self.items.items():
            database["items"][name] = {
                "id": item.item_id, "name": name, "prefab": item.prefab, "rarity": item.rarity, "icon_path": item.icon_path,
                "used_by_heroes": [item.used_by_hero] if item.used_by_hero else [],
                "visual_assets": item.visual_assets, "is_arcana": item.is_arcana, "is_persona": item.is_persona,
                "is_immortal": item.is_immortal, "is_bugged": item.is_bugged, "particle_effect": item.particle_effect,
                "item_slot": item.item_slot, "item_type": getattr(item, 'item_type', ''), "quality": getattr(item, 'quality', ''),
                "category": getattr(item, 'category', ''), "slots": getattr(item, 'slots', []),
                "model_paths": item.model_paths, "material_paths": item.material_paths, "particle_paths": item.particle_paths,
                "animation_paths": item.animation_paths, "texture_paths": getattr(item, 'texture_paths', []),
                "sound_paths": getattr(item, 'sound_paths', []), "model_player": item.model_player,
                "styles": [{"style_id": s.style_id, "name": s.name, "model_player": s.model_player, "asset": s.asset, "particles": s.particles, "models": s.models, "materials": s.materials, "textures": s.textures, "icons": s.icons, "raw_data": s.raw_data} for s in item.styles],
                "ability_overrides": [{"ability_id": ao.ability_id, "icon": ao.icon, "particles": ao.particles, "projectiles": ao.projectiles, "sounds": ao.sounds, "cast_effect": ao.cast_effect, "hit_effect": ao.hit_effect, "modifier_effect": ao.modifier_effect, "raw_data": ao.raw_data} for ao in item.ability_overrides],
                "icons": getattr(item, 'icons', {}), "asset_modifiers": item.asset_modifiers,
                "is_loading_screen": item.is_loading_screen, "is_effigy": item.is_effigy, "is_music": item.is_music,
                "is_tower": item.is_tower, "is_base": item.is_base, "is_fountain": item.is_fountain,
                "is_gem": item.is_gem, "gem_type": item.gem_type, "gem_particle": item.gem_particle, "gem_color": item.gem_color,
                "socketable_slots": item.socketable_slots, "terrain_type": item.terrain_type,
                "terrain_resource_path": item.terrain_resource_path, "weather_particle_path": item.weather_particle_path,
                "courier_model_path": item.courier_model_path, "is_announcer": item.is_announcer, "is_mega_kills": item.is_mega_kills,
                "def_index": getattr(item, 'def_index', ''), "class_name": getattr(item, 'class_name', ''),
                "internal_name": getattr(item, 'internal_name', ''), "localized_name": getattr(item, 'localized_name', ''),
                "raw_item_data": item.raw_item_data,
            }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(database, f, ensure_ascii=False)
        log.info(f"Database saved: {DATA_FILE}")

    def get_hero_skins(self, hero_name: str) -> List[SkinItem]:
        EXCLUDED_PREFABS = {"default_item", "loading_screen", "bundle", "taunt", "base", "fountain"}
        EXCLUDED_SLOTS = {"taunt", "courier", "ward", "weather", "terrain", "music",
                           "tower_skin", "announcer", "kill_streak"}
        if hero_name not in self.heroes:
            return []
        skins = []
        for item_name in self.heroes[hero_name]["items"]:
            item = self.items.get(item_name)
            if not item:
                continue
            if item.prefab.lower() in EXCLUDED_PREFABS:
                continue
            if item.item_slot.lower() in EXCLUDED_SLOTS:
                continue
            skins.append(item)
        return skins

    HIDDEN_PREFABS = {"default_item", "bundle", "base", "fountain"}
    categories: Dict[str, Dict[str, "SkinItem"]] = {}

    def is_system_item(self, item: SkinItem, strict: bool = True) -> bool:
        """Internal / placeholder entries that must never be offered as skins (raw names, defaults, bundles ...).
        strict=False (catalog categories) does NOT hide items just because their name is missing in the localization:
        many real music packs / HUDs / cursors have no token, and hiding them made categories look nearly empty."""
        prefab = set(item.prefab.lower().split())
        if prefab & self.HIDDEN_PREFABS:
            return True
        if strict and getattr(self, "_loc_ok", False) and item.localized_name in ("", item.name):
            return True            # no real localized name -> internal entry
        n = item.name.lower()
        return n.startswith(("default ", "default_", "npc_dota", "test", "deprecated", "unused"))

    def get_hero_catalog(self, hero_name: str) -> dict:
        """
        Everything for one hero, grouped by what it IS (never by name fragments):
          slots     -> ordered [{slot, title, items}]: the hero's default-item slots PLUS every real loadout slot
                       that has cosmetics (so a hero with only an offhand default still shows "weapon")
          arcanas / personas / taunts -> [items]
        """
        out = {"slots": [], "arcanas": [], "personas": [], "taunts": [], "gems": []}
        hero = self.heroes.get(hero_name)
        if not hero:
            return out
        by_slot: Dict[str, list] = {s: [] for s in self.slot_resolver.loadout_slots(hero_name)}
        for item_name in hero["items"]:
            item = self.items.get(item_name)
            if not item or self.is_system_item(item):
                continue
            if any(item_name in v for c, v in self.categories.items() if c != "gems"):
                continue                       # catalog items (effects, statues, emblems ...) are not hero cosmetics
            prefab = item.prefab.lower().strip()
            slot = (item.item_slot or "").strip()
            if item.item_type == "taunt" or slot == "taunt" or prefab == "taunt":
                out["taunts"].append(item)
            elif item.is_persona:
                out["personas"].append(item)
            elif item.is_arcana:
                out["arcanas"].append(item)
            elif slot in by_slot:
                by_slot[slot].append(item)
            elif slot and slot not in NON_LOADOUT_SLOTS and looks_like_loadout_slot(slot):
                by_slot.setdefault(slot, []).append(item)
        for slot in sorted(by_slot, key=slot_sort_key):
            if by_slot[slot]:
                out["slots"].append({"slot": slot, "title": slot_title(slot), "items": by_slot[slot]})
        out["gems"] = self.get_hero_gems(hero_name)
        return out

    def get_item(self, item_name: str) -> Optional[SkinItem]:
        return self.items.get(item_name)

    def resolve_slot(self, hero_name: str, requested_slot: str) -> Optional[str]:
        return self.slot_resolver.resolve_slot(hero_name, requested_slot)

    def get_hero_slots(self, hero_name: str) -> Dict[str, str]:
        return self.slot_resolver.get_hero_slots(hero_name)

    def get_arcana_base_slot(self, hero_name: str, item_data: dict = None) -> str:
        return self.slot_resolver.get_arcana_base_slot(hero_name, item_data)

