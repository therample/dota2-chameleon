from .common import *
from .deps import BaseIndex, walk
from .itemdef import *
from .itemdef import merge_asset_modifiers
from .kv import kv_base, kv_set_unique
from .vpk_io import *
from .kv import *
from .slots import *
from .models import *
from .resolver import *
from .extras import *
from .database import *
from .gameinfo import *
# ==============================================================================
# SKIN APPLIER
# ==============================================================================

CARRIER_SLOT = "__main__"


class SkinApplier:
    MAX_PACK_BYTES = 1024 * 1024 * 1024

    def __init__(self, dota_path: Path, database: 'SkinDatabase', config: dict = None):
        self.dota_path = dota_path
        self.database = database
        self.config = config or {}
        self.override_dir = CACHE_DIR / "override_build"
        self.mod_dir = dota_path / "game" / MOD_FOLDER_NAME
        self.gameinfo = GameInfoManager(dota_path, sign=bool((config or {}).get('patch_signatures', True)))
        self.active_overrides: Dict[str, str] = {}
        self.pack_resources: bool = config.get("pack_resources", True)
        self.river_color_builder = RiverColorVPKBuilder(database.vpk_readers)
        self.background_builder = BackgroundVPKBuilder(database.vpk_readers)
        self._packed_resources: Set[str] = set()
        self.last_report: dict = {}
        self.last_pack_report: dict = {}
        self.active_styles: Dict[str, int] = {}

    def apply_style(self, item_name: str, style_id: int) -> bool:
        item = self.database.items.get(item_name)
        if not item or not item.styles:
            return False
        if not any(s.style_id == style_id for s in item.styles):
            return False
        self.active_styles[item_name] = style_id
        return True

    def clear_style(self, item_name: str) -> bool:
        return self.active_styles.pop(item_name, None) is not None

    # ---- one pick per (category, prefab): Dire and Radiant towers/creeps are different prefabs and can both be set
    def _cat_key(self, cat: str, item: SkinItem) -> str:
        prefab = (str(item.prefab).split() or ["x"])[0]
        return f"cat::{cat}::{prefab}"

    def apply_category(self, cat: str, item_name: str) -> bool:
        item = self.database.category_items(cat).get(item_name)
        if not item:
            return False
        if cat in ("taunts", "gems"):
            return False                     # taunts / gems need a hero: use apply_taunt / apply_gem
        key = self._cat_key(cat, item)
        self.active_overrides.pop(key, None)
        self.active_overrides[key] = item_name
        return True

    def category_of_key(self, key: str) -> str:
        parts = key.split("::")
        return parts[1] if parts[0] == "cat" and len(parts) > 1 else ""

    def apply_hero_skin(self, hero_name, item_name, item_slot=""):
        item = self.database.items.get(item_name)
        if not item:
            return False
        if item.item_slot == "taunt" or item_name in self.database.taunts:
            return self.apply_taunt(hero_name, item_name)
        for cat, items in getattr(self.database, "categories", {}).items():
            if item_name in items:
                return self.apply_category(cat, item_name)

        slot = item.item_slot or item_slot or "weapon"
        resolved = self.database.resolve_slot(hero_name, slot)
        if not resolved:
            if item.is_arcana or item.is_persona:
                resolved = CARRIER_SLOT          # arcana whose slot the hero does not have: ride on its main item
            else:
                log.warning("Hero %s has no slot '%s' - item %s not applied", hero_name, slot, item_name)
                return False
        key = f"hero::{hero_name}::{resolved}"
        self.active_overrides.pop(key, None)
        self.active_overrides[key] = item_name
        return True

    def apply_ward(self, n): return self.apply_category("wards", n)
    def apply_courier(self, n): return self.apply_category("couriers", n)
    def apply_weather(self, n): return self.apply_category("weather", n)
    def apply_terrain(self, n): return self.apply_category("terrain", n)
    def apply_music(self, n): return self.apply_category("music", n)
    def apply_tower(self, n): return self.apply_category("towers", n)
    def apply_announcer(self, n): return self.apply_category("announcers", n)
    def apply_mega_kills(self, n): return self.apply_category("mega_kills", n)

    def apply_gem(self, hero_name, item_name):
        """Socket gem effects for a hero's arcana (Terrorblade, Techies ...): one gem per hero."""
        if item_name not in self.database.categories.get("gems", {}):
            return False
        key = f"gem::{hero_name}::socket"
        self.active_overrides.pop(key, None)
        self.active_overrides[key] = item_name
        return True

    def apply_taunt(self, hero_name, item_name):
        if item_name not in self.database.taunts:
            return False
        self.active_overrides[f"taunt::{hero_name}"] = item_name
        return True

    def apply_bugged_item(self, hero_name, item_name):
        if item_name not in self.database.bugged_items:
            return False
        item = self.database.items[item_name]
        raw_slot = ""
        if item.raw_item_data:
            raw_slot = item.raw_item_data.get("item_slot", "")
        slot = raw_slot or item.item_slot or "weapon"
        if hero_name and hero_name != "all":
            resolved_slot = self.database.resolve_slot(hero_name, slot)
            if not resolved_slot:
                return False
            self.active_overrides[f"bugged::{hero_name}::{resolved_slot}"] = item_name
        else:
            for hn in self.database.heroes:
                resolved_slot = self.database.resolve_slot(hn, slot)
                if resolved_slot:
                    self.active_overrides[f"bugged::{hn}::{resolved_slot}"] = item_name
        return True

    def set_river_color(self, color_name):
        self.river_color_builder.set_color(color_name)
        return True

    def set_background(self, bg_path):
        self.background_builder.set_background(bg_path)
        return True

    def launch_dota(self, params=""):
        try:
            launch_params = params or self.config.get("launch_parameters", "")
            url = f"steam://run/570//{launch_params.replace(' ', '%20')}" if launch_params else "steam://run/570"
            webbrowser.open(url)
            log.info(f"Launching Dota 2 with params: {launch_params}")
            return True
        except Exception as e:
            log.error(f"Launch error: {e}")
            return False

    # ================================================================== items_game
    def _load_items_game(self):
        path = CACHE_DIR / "items_game.txt"
        if not path.exists():
            return None
        data = KeyValueParser(path.read_text(encoding="utf-8", errors="ignore")).parse()
        root = data.get("items_game", data)
        return data, root, root.get("items", {}), root.get("prefabs", {})

    @staticmethod
    def _hero_defaults(items: dict) -> Dict[str, Dict[str, List[str]]]:
        out: Dict[str, Dict[str, List[str]]] = {}
        for iid, d in items.items():
            if not isinstance(d, dict) or "default_item" not in str(d.get("prefab", "")).split():
                continue
            ub = d.get("used_by_heroes")
            if isinstance(ub, dict):
                for hero in ub:
                    out.setdefault(hero, {}).setdefault(d.get("item_slot", ""), []).append(iid)
        return out

    def _source_block(self, item_name: str, items: dict, prefabs: dict) -> Optional[dict]:
        """The wanted item as the game would see it: prefab-resolved, style applied, gating removed."""
        item = self.database.items.get(item_name)
        if not item:
            return None
        raw = items.get(str(item.item_id))
        if not isinstance(raw, dict):
            return None
        return flatten_style(resolve_prefabs(raw, prefabs), self.active_styles.get(item_name))

    def _generate_modified_items_game(self) -> Tuple[str, Dict[str, str]]:
        loaded = self._load_items_game()
        if not loaded:
            return "", {}
        data, root, items, prefabs = loaded
        report: List[dict] = []
        hero_models: Dict[str, str] = {}
        self._final_sources: List[Tuple[str, dict, Optional[str]]] = []   # (item, source block, hero short name)
        resolver = self.database.slot_resolver

        def record(key, item_name, ids, src, hero=None, extra=None):
            vis = src.get("visuals", {})
            short = hero.replace("npc_dota_hero_", "") if hero else None
            entry = {"key": key, "item": item_name, "targets": ids, "modifiers": modifiers_by_type(vis),
                     "replaces_particles": len(self._swaps(vis, short))}
            if extra:
                entry.update(extra)
            report.append(entry)
            self._final_sources.append((item_name, src, short))

        for key, item_name in list(self.active_overrides.items()):
            src = self._source_block(item_name, items, prefabs)
            if src is None:
                report.append({"key": key, "item": item_name, "error": "item not found in items_game"})
                continue
            parts = key.split("::")
            kind = parts[0]
            item = self.database.items.get(item_name)

            if kind in ("hero", "bugged") and len(parts) >= 3 and item and item.is_persona and parts[2] in ("persona", "persona_selector", CARRIER_SLOT):
                hero = parts[1]
                pslot = str(src.get("item_slot", "") or "persona_selector")
                ids = resolver.get_default_ids(hero, pslot) or resolver.get_default_ids(hero, "persona_selector")
                note = ""
                for iid in ids:
                    items[iid] = build_override(items[iid], src, hero_scoped=True)
                if not ids:
                    # the hero has no default persona entry: add one for this hero, like choosing the persona in the loadout
                    new_id = self._create_hero_default(items, hero, pslot, src)
                    ids = [new_id]
                    note = f"no default persona slot existed: created one for this hero (#{new_id})"
                model = entity_model(src.get("visuals", {}), hero)
                if model:
                    hero_models[hero] = model
                record(key, item_name, ids, src, hero, {"hero_model": hero_models.get(hero, "")})
                if note:
                    report[-1]["note"] = note

            elif kind in ("hero", "bugged") and len(parts) >= 3:
                hero, slot = parts[1], parts[2]
                if slot == CARRIER_SLOT:
                    ids, used = [], slot
                else:
                    resolved = resolver.resolve_slot(hero, slot) or slot
                    ids, used = resolver.targets_for(hero, resolved)
                note = ""
                if ids:
                    for iid in ids:
                        items[iid] = build_override(items[iid], src, hero_scoped=True)
                    if used != slot and slot != CARRIER_SLOT:
                        note = f"hero has no '{slot}' default - applied through its '{used}' default item"
                else:
                    # no default item for this slot: attach the item's effects/animations/model swap to the hero's
                    # main default item instead of silently dropping it (this is why some arcanas "did nothing")
                    carrier = self._taunt_carrier(hero)
                    if carrier:
                        n = merge_asset_modifiers(items[carrier], src.get("visuals", {}))
                        ids = [carrier]
                        note = f"no default for '{slot}': {n} modifier(s) attached to default item #{carrier}"
                if ids and item and (item.is_arcana or item.is_persona):
                    model = entity_model(src.get("visuals", {}), hero)
                    if model:
                        hero_models[hero] = model
                record(key, item_name, ids, src, hero, {"hero_model": hero_models.get(hero, "")})
                if not ids:
                    report[-1]["error"] = f"hero has no default item for slot '{slot}' or any other slot"
                elif note:
                    report[-1]["note"] = note

            elif kind == "taunt" and len(parts) >= 2:
                hero = parts[1]
                ids = resolver.get_default_ids(hero, "taunt")
                if ids:
                    for iid in ids:
                        items[iid] = build_override(items[iid], src, hero_scoped=True)
                    record(key, item_name, ids, src, hero)
                else:
                    # Heroes normally have NO default taunt item. The taunt is an `activity` modifier
                    # (ACT_DOTA_TAUNT -> variant) the game collects from ANY equipped item, so it rides on a default item.
                    carrier = self._taunt_carrier(hero)
                    n = merge_asset_modifiers(items[carrier], src.get("visuals", {})) if carrier else 0
                    record(key, item_name, [carrier] if carrier else [], src, hero)
                    if not carrier or not n:
                        report[-1]["error"] = "taunt has no modifiers to attach" if carrier else "hero has no default item to carry the taunt"
                    else:
                        report[-1]["note"] = f"taunt attached to default item #{carrier} ({n} modifier(s))"

            elif kind == "gem" and len(parts) >= 2:
                hero = parts[1]
                carrier = self._taunt_carrier(hero)
                n = merge_asset_modifiers(items[carrier], src.get("visuals", {})) if carrier else 0
                record(key, item_name, [carrier] if carrier else [], src, hero)
                if not carrier or not n:
                    report[-1]["error"] = "gem has no modifiers to attach" if carrier else "hero has no default item to carry the gem"
                else:
                    report[-1]["note"] = f"gem attached to default item #{carrier} ({n} modifier(s))"

            elif kind == "cat" and len(parts) >= 3:
                cat = parts[1]
                own = items.get(str(item.item_id), {}) if item else {}
                ids = find_default_ids(items, resolve_prefabs(own, prefabs), prefabs)
                mode = self.config.get("default_mode", "auto")
                notes: List[str] = []
                if mode == "create":
                    ids = []                                  # never touch Valve's own defaults
                else:
                    for iid in ids:
                        items[iid] = build_override(items[iid], src, hero_scoped=False)
                carriers: List[str] = []
                emode = self.config.get("effect_mode", "slot")
                if cat in self.EFFECT_CATS and mode != "replace" and emode in ("hero", "both"):
                    carriers = self._all_carriers()
                    n = sum(merge_asset_modifiers(items[c], src.get("visuals", {})) for c in carriers)
                    if carriers:
                        notes.append(f"also attached to the main item of {len(carriers)} heroes ({n} modifier(s))")
                want_slot = (cat in self.MODEL_CATS) or (cat in self.EFFECT_CATS and emode in ("slot", "both"))
                if (want_slot and mode == "auto") or mode == "create" or (not ids and not carriers):
                    extra = self._create_default(items, resolve_prefabs(own, prefabs), src)
                    if extra:
                        ids = ids + [extra]
                        notes.append(f"created base item #{extra}" + (" next to Valve's default" if len(ids) > 1 else ""))
                record(key, item_name, ids + carriers, src)
                if notes:
                    report[-1]["note"] = "; ".join(notes)
                if not ids and not carriers:
                    report[-1]["error"] = (f"no default (baseitem) entry found for slot '{src.get('item_slot', '')}' / "
                                           f"prefab '{src.get('prefab', '')}'")

            else:
                report.append({"key": key, "item": item_name, "error": "unknown override kind"})

        root["items"] = items
        self.last_report = {"overrides": report}
        return KeyValueWriter.write(data), self._patched_hero_files(hero_models)

    @staticmethod
    def _create_hero_default(items: dict, hero: str, slot: str, src: dict) -> str:
        ids = [int(k) for k in items if str(k).isdigit()]
        new_id = str(max(ids + [0]) + 1)
        base = {"name": f"Default {slot} {hero.replace('npc_dota_hero_', '')}", "prefab": "default_item", "baseitem": "1",
                "item_slot": slot, "used_by_heroes": {hero: "1"}}
        items[new_id] = build_override(base, src, hero_scoped=True)
        return new_id

    @staticmethod
    def _create_default(items: dict, own: dict, src: dict) -> Optional[str]:
        """Add a baseitem entry (hero-less) for a slot/prefab that has none, filled with the chosen item's data."""
        prefab = str(own.get("prefab", "") or src.get("prefab", "")).strip()
        slot = str(src.get("item_slot", "") or own.get("item_slot", "")).strip()
        if not prefab and not slot:
            return None
        ids = [int(k) for k in items if str(k).isdigit()]
        new_id = str(max(ids + [0]) + 1)
        base = {"name": f"Default {slot or prefab}", "prefab": prefab, "baseitem": "1"}
        if slot:
            base["item_slot"] = slot
        items[new_id] = build_override(base, src, hero_scoped=False)
        return new_id

    def _swaps(self, visuals: dict, hero_short: Optional[str]) -> List[Tuple[str, str]]:
        """Particle swaps allowed by the 'particle_swap' setting: off | hero (default: only that hero's own) | all."""
        mode = self.config.get("particle_swap", "hero")
        if mode == "off":
            return []
        if mode == "all" or hero_short is None:
            return particle_replacements(visuals)
        return particle_replacements(visuals, only_hero=hero_short)

    def _patched_hero_files(self, hero_models: Dict[str, str]) -> Dict[str, str]:
        """Arcana/persona also swap the hero's base model. {pak path: new text}; handles one-file-per-hero layouts."""
        out: Dict[str, str] = {}
        if not hero_models or not self.config.get("patch_hero_model", True):
            return out
        master = CACHE_DIR / "npc_heroes.txt"
        by_file: Dict[str, List[Tuple[str, str]]] = {}
        for hero, model in hero_models.items():
            src = self.database.hero_files.get(hero)
            by_file.setdefault(src or "scripts/npc/npc_heroes.txt", []).append((hero, model))
        for path, pairs in by_file.items():
            if path == "scripts/npc/npc_heroes.txt":
                if not master.exists():
                    continue
                text = master.read_text(encoding="utf-8", errors="ignore")
            else:
                text = ""
                for reader in self.database.vpk_readers:
                    if path in reader.files:
                        text = (reader.extract_to_bytes(path) or b"").decode("utf-8", errors="ignore")
                        break
                if not text:
                    continue
            data = KeyValueParser(text).parse()
            hroot = data.get("DOTAHeroes", data)
            changed = False
            for hero, model in pairs:
                block = hroot.get(hero)
                if isinstance(block, dict):
                    block["Model"] = model
                    changed = True
            if changed:
                out[path] = KeyValueWriter.write(data)
        return out

    TAUNT_CARRIER_ORDER = ("weapon", "head", "armor", "shoulder", "back", "misc", "offhand_weapon", "arms", "belt")

    def _all_carriers(self) -> List[str]:
        out: List[str] = []
        for h in self.database.slot_resolver.hero_slots:
            c = self._taunt_carrier(h)
            if c and c not in out:
                out.append(c)
        return out

    def _taunt_carrier(self, hero: str) -> Optional[str]:
        res = self.database.slot_resolver
        for slot in self.TAUNT_CARRIER_ORDER:
            ids = res.get_default_ids(hero, slot)
            if ids:
                return ids[0]
        ids = res.all_loadout_ids(hero)
        return ids[0] if ids else None

    # ================================================================== resources
    def _base_index(self) -> BaseIndex:
        idx = getattr(self, "_base_index_cache", None)
        if idx is None:
            idx = self._base_index_cache = BaseIndex(self.database.vpk_readers)
        return idx

    def _collect_pack_files(self, progress=None) -> Dict[str, bytes]:
        """
        Files that must be added to the mod pak:
          * minimal (default): ONLY particle replacements - the new particle is written under the old path.
            Everything else an item references already exists in the game's own paks, so copying it would
            just be junk.
          * full (config pack_mode = "full"): additionally every referenced resource with its dependency
            chain (models -> materials -> textures, particles -> children, `.vsnap` snapshots ...).
        """
        index = self._base_index()
        out: Dict[str, bytes] = {}
        missing_all: Dict[str, List[str]] = {}
        full = self.config.get("pack_mode", "minimal") == "full"

        for item_name, src, hero_short in self._final_sources:
            vis = src.get("visuals", {})
            for old, new in self._swaps(vis, hero_short):
                got = index.read(new)
                if not got:
                    missing_all.setdefault(item_name, []).append(new)
                    continue
                real_new, data = got
                target = old if old.endswith("_c") else old + "_c"
                out[target] = data
                if full:
                    files, miss = walk(index, [new])
                    for p, d in files.items():
                        out.setdefault(p, d)
            paths = self._meaningful_paths(src)
            if full:
                files, miss = walk(index, sorted(paths))
                for p, d in files.items():
                    out.setdefault(p, d)
                miss = {m for m in miss if not m.endswith(".vmap")}
                if miss:
                    missing_all.setdefault(item_name, []).extend(sorted(miss))
            else:
                for p in sorted(paths):
                    if not p.endswith(".vmap") and index.resolve(p) is None:
                        missing_all.setdefault(item_name, []).append(p)
            if progress:
                progress(f"  {item_name}: {len(out)} files so far")

        total = sum(len(d) for d in out.values())
        if total > self.MAX_PACK_BYTES:
            raise RuntimeError(f"Pack would be {total/1048576:.0f} MB - refusing (set pack_mode to minimal)")
        self.last_report["pack_mode"] = "full" if full else "minimal"
        self.last_report["packed_files"] = len(out)
        self.last_report["missing_references"] = missing_all
        return out

    @staticmethod
    def _meaningful_paths(src: dict) -> Set[str]:
        """Paths the game would really load for this item: model_player and the `modifier` of effect modifiers.
        (Icons, portraits, map files and stale Valve entries are not 'missing files' we should worry about.)"""
        out: Set[str] = set()
        mp = src.get("model_player")
        if looks_like_resource(mp):
            out.add(normalise_path(mp))
        vis = src.get("visuals", {})
        if isinstance(vis, dict):
            for k, v in vis.items():
                if is_modifier_key(k) and isinstance(v, dict):
                    t = str(v.get("type", "")).lower()
                    if t in ("particle_create", "particle", "entity_model", "model", "entity_clientside_model",
                             "streak_effect", "weather_effect", "particle_snapshot"):
                        m = v.get("modifier")
                        if looks_like_resource(m):
                            out.add(normalise_path(m))
        return out

    AUTOEXEC_BEGIN = "// >>> Chameleon (managed block, removed on Restore)"
    AUTOEXEC_END = "// <<< Chameleon"

    @property
    def autoexec_path(self) -> Path:
        return self.dota_path / "game" / "dota" / "cfg" / "autoexec.cfg"

    def _strip_autoexec_block(self, text: str) -> str:
        pat = re.compile(re.escape(self.AUTOEXEC_BEGIN) + r".*?" + re.escape(self.AUTOEXEC_END) + r"[ \t]*\r?\n?", re.S)
        return pat.sub("", text)

    def _autoexec_block(self) -> str:
        return ""                      # HUD / minimap tweaks were removed on purpose: Chameleon only changes cosmetics

    def write_autoexec(self):
        """Nothing is written any more; an old managed block from a previous version is removed."""
        self.remove_autoexec_block()

    def remove_autoexec_block(self):
        p = self.autoexec_path
        if not p.exists():
            return
        text = p.read_text(encoding="utf-8", errors="ignore")
        clean = self._strip_autoexec_block(text)
        if clean.strip():
            p.write_text(clean, encoding="utf-8")
        else:
            p.unlink()

    # Stages shown by the progress bar: (id, weight)
    # models of map units: replacing Valve's default alone did not show in game, an extra base item did
    MODEL_CATS = {"roshan", "ancients", "tormentor", "statues"}
    # effects shown on / around heroes. "slot" (default): a base item in the equipped slot - this is what shows in the Dota
    # loadout and what worked for the map effects / emblems. "hero": attach to the heroes' own main items instead (online).
    EFFECT_CATS = {"emblems", "head_effects", "teleport_effects", "blink_effects", "death_effects",
                   "courier_effects", "shaders"}
    CREATE_ALWAYS = MODEL_CATS | EFFECT_CATS

    STAGES = (("scan", 6), ("build", 22), ("resources", 34), ("extras", 12), ("write", 18), ("register", 8))

    def commit(self, progress_callback=None) -> bool:
        """
        Build ONE pak01_dir.vpk: patched scripts + the few resources the picks need.
        Progress is reported as "@@<percent>|<stage>|<detail>" (the UI draws the stage bar from it) plus plain text.
        """
        total_w = sum(w for _, w in self.STAGES)
        base = {}
        acc = 0
        for sid, w in self.STAGES:
            base[sid] = acc
            acc += w

        def say(msg):
            log.info(msg)
            if progress_callback:
                progress_callback(msg)

        def stage(sid, frac, detail=""):
            w = dict(self.STAGES)[sid]
            pct = int((base[sid] + w * max(0.0, min(1.0, frac))) * 100 / total_w)
            if progress_callback:
                progress_callback(f"@@{pct}|{sid}|{detail}")

        try:
            stage("scan", 0, "Preparing")
            self._packed_resources.clear()
            self.mod_dir.mkdir(parents=True, exist_ok=True)
            for old in self.mod_dir.glob("pak*_dir.vpk"):
                old.unlink()
            stage("scan", 1, "Preparing")

            stage("build", 0, "Rewriting items_game")
            items_text, extra_scripts = self._generate_modified_items_game()
            if not items_text:
                say("Error: items_game.txt not available - rebuild the database in Settings")
                return False
            builder = VPKBuilder()
            builder.add_data(items_text.encode("utf-8"), "scripts/items/items_game.txt")
            for path, text in extra_scripts.items():
                builder.add_data(text.encode("utf-8"), path)
            stage("build", 1, f"{len(self.last_report.get('overrides', []))} item(s)")

            if self.pack_resources:
                stage("resources", 0, "Collecting resources")
                files = self._collect_pack_files(lambda m: None)
                n = max(1, len(files))
                for i, (vpk_path, data) in enumerate(files.items(), 1):
                    builder.add_data(data, vpk_path)
                    if i % 8 == 0 or i == n:
                        stage("resources", i / n, f"{i}/{n} files")
            stage("resources", 1, "Resources ready")

            stage("extras", 0, "River, background, fonts")
            if self.river_color_builder.color:
                self.river_color_builder.add_to(builder)
            stage("extras", 0.4, "River, background, fonts")
            if self.background_builder.background_path:
                n_bg = self.background_builder.add_to(builder, lambda m: stage('extras', 0.5, m), self.config.get("bg_method", "layout"))
                self.last_report["background"] = {"source": self.background_builder.background_path,
                                                  "replaced": list(self.background_builder.last_replaced),
                                                  "error": self.background_builder.last_error}
                if not n_bg and self.background_builder.last_error:
                    say("Warning: " + self.background_builder.last_error)
            stage("extras", 0.8, "River, background, fonts")
            stage("extras", 1, "Extras ready")

            stage("write", 0, "Writing pak01_dir.vpk")
            builder.build_standalone(self.mod_dir / "pak01_dir.vpk")
            self.write_autoexec()
            stage("write", 1, "pak01_dir.vpk written")

            stage("register", 0, "Registering in gameinfo")
            if not self.gameinfo.inject_vpk():
                say("Error: could not patch gameinfo_branchspecific.gi")
                return False
            self.last_report["total_files"] = len(builder._path_index)
            if self.river_color_builder.color:
                self.last_report["river"] = self.river_color_builder.color
            try:
                (CACHE_DIR / "last_build_report.json").write_text(
                    json.dumps(self.last_report, indent=2, default=str), encoding="utf-8")
            except OSError:
                pass
            problems = [r for r in self.last_report.get("overrides", []) if r.get("error")]
            msg = f"Done! pak01_dir.vpk: {len(builder._path_index)} files."
            if problems:
                msg += f" {len(problems)} item(s) could not be applied - see Settings > Build report."
            try:
                self.config['applied_sig'] = self.database._game_signature()
            except Exception:
                pass
            stage("register", 1, "Done")
            say(msg)
            return True
        except Exception as e:
            log.error("Commit error: %s", e, exc_info=True)
            if progress_callback:
                progress_callback(f"Error: {e}")
            return False

    def restore(self) -> bool:
        self.active_overrides.clear()
        self.active_styles.clear()
        self.river_color_builder.clear()
        self.background_builder.clear()
        self._packed_resources.clear()
        self.gameinfo.remove_vpk()
        self.remove_autoexec_block()
        if self.mod_dir.exists():
            shutil.rmtree(self.mod_dir, ignore_errors=True)
        return True
