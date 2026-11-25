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
        self.gameinfo = GameInfoManager(dota_path, sign=bool((config or {}).get('patch_signatures', True)))
        self.active_overrides: Dict[str, str] = {}
        self._data_changed = False
        self.disabled: set = set()
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
            return False                       # taunts are not supported
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
        self._drop_overlaps(hero_name, key)
        return True

    def _targets(self, key: str) -> set:
        p = key.split("::")
        if len(p) < 3:
            return set()
        if p[2] == CARRIER_SLOT:
            c = self._taunt_carrier(p[1])
            return {c} if c else set()
        return set(self.database.slot_resolver.targets_for(p[1], p[2])[0])

    def _drop_overlaps(self, hero: str, key: str):
        """Two picks that land on the same default item stack up into nonsense: the new pick replaces the older one."""
        mine = self._targets(key)
        for k in list(self.active_overrides):
            if k != key and k.startswith(f"hero::{hero}::") and mine & self._targets(k):
                del self.active_overrides[k]
                self.disabled.discard(k)

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
        self._gem_styles(hero_name, item_name)
        return True

    def _gem_styles(self, hero: str, gem_name: str):
        """The gem's colour is inherited by the hero's chosen items: their style whose name matches the gem (Abysm, Summer Warmth ...)."""
        gem = self.database.items.get(gem_name)
        words = {w for w in re.findall(r"[a-z]{4,}", f"{gem_name} {gem.localized_name if gem else ''}".lower()) if w not in ("gem", "gems")}
        if not words:
            return
        for k, iname in list(self.active_overrides.items()):
            if not k.startswith(f"hero::{hero}::"):
                continue
            it = self.database.items.get(iname)
            for st in (it.styles if it else []) or []:
                if any(w in str(st.name).lower() for w in words):
                    self.active_styles[iname] = st.style_id
                    break

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

    def set_background(self, path: str):
        self.background_builder.set_background(path)

    def set_river_color(self, color_name):
        self.river_color_builder.set_color(color_name)
        return True

        return True

    # ================================================================== where the mod is installed
    # One method: our own folder next to Dota's, registered in gameinfo_branchspecific.gi, with one dota.signatures line.
    @property
    def mod_dir(self) -> Path:
        return self.dota_path / "game" / MOD_FOLDER_NAME

    @property
    def pak_path(self) -> Path:
        return self.mod_dir / "pak01_dir.vpk"

    def is_enabled(self) -> bool:
        """The mod is switched off while its pak is named *.vpk.off (nothing is deleted)."""
        return not Path(str(self.pak_path) + ".off").exists()

    def set_enabled(self, on: bool) -> bool:
        pak, off = self.pak_path, Path(str(self.pak_path) + ".off")
        if on and off.exists():
            off.replace(pak)
            return True
        if not on and pak.exists():
            pak.replace(off)
            return True
        return False

    def is_active(self) -> bool:
        return bool(self.gameinfo.is_injected() or self.pak_path.exists() or Path(str(self.pak_path) + ".off").exists())

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

    # ---- stock paths: keep models after a reconnect (technique of Dota2 Mod Manager) ----
    # The server names the STOCK model paths; after a reconnect the client only loads those. So the chosen model is written under
    # the stock path (a file swap) and the model modifier is dropped, instead of pointing items_game at a path that is not loaded.
    def _all_files(self) -> Dict[str, str]:
        if getattr(self, "_files_cache", None) is None:
            self._files_cache = {fp.lower(): fp for r in self.database.vpk_readers for fp in r.files}
        return self._files_cache

    def _sound_cursor_swaps(self, cat: str, src: dict, defaults: List[dict]) -> int:
        """
        Announcers / mega-kills: the pack's sound-event script is written over the default pack's script (file swap), because the
        data change alone does not change the sound. Cursors: the pack's .cur/.ani files are written over the stock cursor files.
        """
        files, idx, n = self._all_files(), self._base_index(), 0
        mods = [v for k, v in (src.get("visuals") or {}).items() if is_modifier_key(k) and isinstance(v, dict)]
        if cat == "cursors":
            for v in mods:
                folder = normalise_path(str(v.get("modifier") or "")).rstrip("/") + "/"
                if folder == "/":
                    continue
                for low, real in files.items():
                    if low.startswith(folder) and low.endswith((".cur", ".ani")):
                        stock = "resource/cursor/" + low[len(folder):]
                        if stock in files and files[stock] != real:
                            self._swap_pairs[files[stock]] = real
                            n += 1
            return n
        if cat == "shaders":
            # post-processing: the game draws the map through one material - the chosen one is written over it
            stock = "materials/dev/deferred_post_process.vmat_c"
            for s in self.database._all_strings(src.get("visuals", {})):
                low = s.lower().replace(".vmat\"", ".vmat")
                cand = low if low.endswith(".vmat_c") else (low + "_c" if low.endswith(".vmat") else "")
                if cand and cand in files and stock in files and files[cand] != files[stock]:
                    self._swap_pairs[files[stock]] = files[cand]
                    return 1
            return 0
        if cat == "emblems":
            ring = "particles/ui_mouseactions/selected_ring.vpcf_c"
            for v in mods:
                if str(v.get("type", "")).lower() == "particle_create":
                    cand = normalise_path(str(v.get("modifier") or "")).lower() + "_c"
                    if cand in files and ring in files and files[cand] != files[ring]:
                        self._swap_pairs[files[ring]] = files[cand]
                        return 1
            return 0
        def names(vs):
            return [str(v.get("modifier") or "").lower() for v in vs if str(v.get("type", "")).lower() == "announcer" and v.get("modifier")]
        pack = names(mods)
        stock_script = "soundevents/voscripts/game_sounds_vo_announcer.vsndevts_c"
        if cat == "announcers" and stock_script in files:
            for pn in pack:
                hit = next((r for l, r in files.items() if l.startswith("soundevents/voscripts/") and l.endswith(".vsndevts_c") and pn in l), None)
                if hit and hit != files[stock_script]:
                    self._swap_pairs[files[stock_script]] = hit
                    return 1
        dflt = [x for d in defaults for x in names([m for k, m in (d.get("visuals") or {}).items() if is_modifier_key(k) and isinstance(m, dict)])]
        for pn in pack:
            for dn in dflt[:1]:
                if not dn or dn == pn:
                    continue
                for low, real in files.items():
                    if low.startswith("soundevents/") and low.endswith(".vsndevts_c") and pn in low:
                        stock = low.replace(pn, dn)
                        if stock in files and files[stock] != real:
                            self._swap_pairs[files[stock]] = real
                            n += 1
        return n

    def _m(self, item: dict, vis: dict, types=None) -> int:
        self._data_changed = True
        return merge_asset_modifiers(item, vis, types) if types else merge_asset_modifiers(item, vis)

    def _unit_model(self, name: str) -> Optional[str]:
        if not name:
            return None
        m = (getattr(self.database, "hero_models", None) or {}).get(name)
        if isinstance(m, str) and m:
            return m
        units = getattr(self, "_unit_models", None)
        if units is None:
            units = {}
            try:
                for r in self.database.vpk_readers:
                    if "scripts/npc/npc_units.txt" in r.files:
                        raw = (r.extract_to_bytes("scripts/npc/npc_units.txt") or b"").decode("utf-8", "ignore")
                        root = KeyValueParser(raw).parse()
                        root = root.get("DOTAUnits", root)
                        for k, v in root.items():
                            if isinstance(v, dict) and isinstance(v.get("Model"), str):
                                units[k] = v["Model"]
                        break
            except Exception as ex:
                log.warning("npc_units.txt not read: %s", ex)
            self._unit_models = units
        return units.get(name)

    MODEL_TYPES = ("model", "entity_model", "entity_clientside_model")

    @classmethod
    def _is_complex(cls, src: dict) -> bool:
        """
        Items that carry more than a plain model (a bird on the shoulder, attachments, hidden body groups, animations, effects) must keep
        ALL their data: swapping only the model file under the stock path loses how it is attached to the hero.
        """
        vis = src.get("visuals") or {}
        if not isinstance(vis, dict):
            return False
        if any(not is_modifier_key(k) and k not in ("skip_model_combine",) for k in vis):
            return True
        if any(is_modifier_key(k) and isinstance(v, dict) and str(v.get("type", "")).lower() not in cls.MODEL_TYPES for k, v in vis.items()):
            return True
        return any(k in src for k in ("hide_bodygroups", "attachment", "bodygroups", "bodygroup", "attachments"))

    def _prune_model_swaps(self, src: dict, hero: Optional[str] = None) -> dict:
        if not self.config.get("stock_models", True) or self._is_complex(src):
            return src
        vis = src.get("visuals")
        if not isinstance(vis, dict):
            return src
        idx = self._base_index()
        for k in list(vis):
            v = vis[k]
            if not (is_modifier_key(k) and isinstance(v, dict)):
                continue
            if str(v.get("type", "")).lower() not in ("model", "entity_model", "entity_clientside_model"):
                continue
            new = v.get("modifier")
            asset = str(v.get("asset") or "")
            if not looks_like_resource(new):
                continue
            old = asset if ".vmdl" in asset.lower() else self._unit_model(asset or hero or "")
            if not looks_like_resource(old):
                continue
            old_c, new_c = idx.resolve(normalise_path(old)), idx.resolve(normalise_path(new))
            if old_c and new_c and old_c != new_c:
                self._swap_pairs[old_c] = new_c
                del vis[k]                      # the file swap replaces the modifier
        return src

    def _override_item(self, default: dict, src: dict, hero_scoped: bool) -> dict:
        res = build_override(default, src, hero_scoped=hero_scoped)
        if self.config.get("stock_models", True) and not self._is_complex(src):
            stock, paid = default.get("model_player"), src.get("model_player")
            if looks_like_resource(stock) and looks_like_resource(paid) and normalise_path(stock) != normalise_path(paid):
                idx = self._base_index()
                sc, pc = idx.resolve(normalise_path(stock)), idx.resolve(normalise_path(paid))
                if sc and pc:
                    self._swap_pairs[sc] = pc
                    res["model_player"] = stock   # stock path stays; its file now holds the chosen model
                    vis = src.get("visuals") or {}
                    if not any(is_modifier_key(k) and isinstance(v, dict) for k, v in vis.items()):
                        return default            # nothing else to change: the file swap alone is the whole mod (no items_game needed)
        self._data_changed = True
        return res

    def _stock_files(self) -> Dict[str, bytes]:
        idx, out = self._base_index(), {}
        for old_c, new_c in self._swap_pairs.items():
            got = idx.read(new_c)
            if got:
                out[old_c] = got[1]
        return out

    def _generate_modified_items_game(self) -> Tuple[str, Dict[str, str]]:
        loaded = self._load_items_game()
        if not loaded:
            return "", {}
        data, root, items, prefabs = loaded
        report: List[dict] = []
        hero_models: Dict[str, str] = {}
        self._final_sources: List[Tuple[str, dict, Optional[str]]] = []   # (item, source block, hero short name)
        self._swap_pairs: Dict[str, str] = {}
        courier_fx: List[Tuple[str, str, dict]] = []
        courier_ids: List[str] = []
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
            if key in self.disabled:
                continue
            src = self._source_block(item_name, items, prefabs)
            if src is None:
                report.append({"key": key, "item": item_name, "error": "item not found in items_game"})
                continue
            parts = key.split("::")
            kind = parts[0]
            src = self._prune_model_swaps(src, parts[1] if kind in ("hero", "bugged", "gem") and len(parts) > 1 else None)
            item = self.database.items.get(item_name)

            if kind in ("hero", "bugged") and len(parts) >= 3 and item and item.is_persona and parts[2] in ("persona", "persona_selector", CARRIER_SLOT):
                hero = parts[1]
                pslot = str(src.get("item_slot", "") or "persona_selector")
                ids = resolver.get_default_ids(hero, pslot) or resolver.get_default_ids(hero, "persona_selector")
                note = ""
                for iid in ids:
                    items[iid] = self._override_item(items[iid], src, True)
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
                        items[iid] = self._override_item(items[iid], src, True)
                    if used != slot and slot != CARRIER_SLOT:
                        note = f"hero has no '{slot}' default - applied through its '{used}' default item"
                else:
                    # no default item for this slot: attach the item's effects/animations/model swap to the hero's
                    # main default item instead of silently dropping it (this is why some arcanas "did nothing")
                    carrier = self._taunt_carrier(hero)
                    if carrier:
                        n = self._m(items[carrier], src.get("visuals", {}))
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

            elif kind == "gem" and len(parts) >= 2:
                hero = parts[1]
                carrier = self._taunt_carrier(hero)
                gem = self.database.items.get(item_name)
                word = self.database.gem_word(gem) if gem else ""
                vis = dict(src.get("visuals", {}) or {})
                vis.update(self.database.hero_gem_mods(hero, word) if word else {})
                n = self._m(items[carrier], vis) if carrier else 0
                record(key, item_name, [carrier] if carrier else [], src, hero)
                if not carrier or not n:
                    report[-1]["error"] = "this hero has nothing that changes with this gem" if carrier else "hero has no default item to carry the gem"
                else:
                    report[-1]["note"] = f"{word or 'gem'}: {n} modifier(s) of the hero's own items switched on"
            elif kind == "cat" and len(parts) >= 3 and parts[1] == "courier_effects":
                courier_fx.append((key, item_name, src))      # attached to the courier itself, after the courier skin is applied

            elif kind == "cat" and len(parts) >= 3:
                cat = parts[1]
                own = items.get(str(item.item_id), {}) if item else {}
                ids = find_default_ids(items, resolve_prefabs(own, prefabs), prefabs)
                mode = self.config.get("default_mode", "auto")
                notes: List[str] = []
                if cat in ("announcers", "mega_kills", "cursors", "shaders", "emblems") and mode != "create":
                    n_sw = self._sound_cursor_swaps(cat, src, [items[i] for i in ids])
                    if n_sw:
                        notes.append(f"{n_sw} game file(s) swapped (the sound / cursor files themselves)")
                if mode == "create":
                    ids = []                                  # never touch Valve's own defaults
                else:
                    for iid in ids:
                        items[iid] = self._override_item(items[iid], src, False)
                carriers: List[str] = []
                emode = self.config.get("effect_mode", "slot")
                if cat in self.EFFECT_CATS and mode != "replace" and emode in ("hero", "both"):
                    carriers = self._all_carriers()
                    n = sum(self._m(items[c], src.get("visuals", {})) for c in carriers)
                    if carriers:
                        notes.append(f"also attached to the main item of {len(carriers)} heroes ({n} modifier(s))")
                want_slot = (cat in self.MODEL_CATS) or (cat in self.EFFECT_CATS and emode in ("slot", "both"))
                if (want_slot and mode == "auto") or mode == "create" or (not ids and not carriers):
                    extra = self._create_default(items, resolve_prefabs(own, prefabs), src)
                    if extra:
                        ids = ids + [extra]
                        notes.append(f"created base item #{extra}" + (" next to Valve's default" if len(ids) > 1 else ""))
                if cat == "couriers":
                    courier_ids.extend(ids)
                record(key, item_name, ids + carriers, src)
                if notes:
                    report[-1]["note"] = "; ".join(notes)
                if not ids and not carriers:
                    report[-1]["error"] = (f"no default (baseitem) entry found for slot '{src.get('item_slot', '')}' / "
                                           f"prefab '{src.get('prefab', '')}'")

            else:
                report.append({"key": key, "item": item_name, "error": "unknown override kind"})

        for key, item_name, src in courier_fx:
            cids = list(dict.fromkeys(find_default_ids(items, {"prefab": "courier", "item_slot": "courier"}, prefabs) + courier_ids))
            n = sum(self._m(items[c], src.get("visuals", {})) for c in cids)
            record(key, item_name, cids, src)
            if not cids:
                report[-1]["error"] = "no courier found to attach the effect to"
            elif not n:
                report[-1]["error"] = "this courier effect has nothing to attach"
            else:
                report[-1]["note"] = f"attached to the courier itself ({n} modifier(s)), like a built-in gem"
        root["items"] = items
        self.last_report = {"overrides": report}
        if hero_models:
            self._data_changed = True
        return KeyValueWriter.write(data), self._patched_hero_files(hero_models)

    def _create_hero_default(self, items: dict, hero: str, slot: str, src: dict) -> str:
        self._data_changed = True
        ids = [int(k) for k in items if str(k).isdigit()]
        new_id = str(max(ids + [0]) + 1)
        base = {"name": f"Default {slot} {hero.replace('npc_dota_hero_', '')}", "prefab": "default_item", "baseitem": "1",
                "item_slot": slot, "used_by_heroes": {hero: "1"}}
        items[new_id] = build_override(base, src, hero_scoped=True)
        return new_id

    def _create_default(self, items: dict, own: dict, src: dict) -> Optional[str]:
        self._data_changed = True
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
    EFFECT_CATS = {"emblems", "head_effects", "teleport_effects", "blink_effects", "death_effects", "kill_effects",
                   "shaders"}
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
            self._data_changed = False
            self.mod_dir.mkdir(parents=True, exist_ok=True)
            for old in list(self.mod_dir.glob("pak*_dir.vpk")) + list(self.mod_dir.glob("pak*_dir.vpk.off")):
                old.unlink()
            stage("scan", 1, "Preparing")

            stage("build", 0, "Rewriting items_game")
            items_text, extra_scripts = self._generate_modified_items_game()
            if not items_text:
                say("Error: items_game.txt not available - rebuild the database in Settings")
                return False
            builder = VPKBuilder()
            if self._data_changed:
                builder.add_data(items_text.encode("utf-8"), "scripts/items/items_game.txt")
                for path, text in extra_scripts.items():
                    builder.add_data(text.encode("utf-8"), path)
            else:
                self.last_report["items_game"] = "not needed"      # light mod: only swapped files, no items_game copy
            stage("build", 1, f"{len(self.last_report.get('overrides', []))} item(s)")

            stock = self._stock_files()
            for pth, data in stock.items():
                builder.add_data(data, pth)
            if stock:
                self.last_report["stock_models"] = len(stock)
            if self.pack_resources:
                stage("resources", 0, "Collecting resources")
                files = self._collect_pack_files(lambda m: None)
                n = max(1, len(files))
                for i, (vpk_path, data) in enumerate(files.items(), 1):
                    builder.add_data(data, vpk_path)
                    if i % 8 == 0 or i == n:
                        stage("resources", i / n, f"{i}/{n} files")
            stage("resources", 1, "Resources ready")

            stage("extras", 0, "River")
            if self.river_color_builder.color:
                self.river_color_builder.add_to(builder)
            stage("extras", 0.4, "River")
            if self.background_builder.background_path:
                n_bg = self.background_builder.add_to(builder, lambda m: stage("extras", 0.5, m),
                                                      int(self.config.get("bg_blur", 0) or 0), int(self.config.get("bg_dim", 10) or 0))
                self.last_report["background"] = {"replaced": list(self.background_builder.last_replaced), "error": self.background_builder.last_error}
            stage("extras", 0.8, "River")
            stage("extras", 1, "Extras ready")

            stage("write", 0, "Writing the mod file")
            pak = self.pak_path
            builder.build_standalone(pak)
            self.write_autoexec()
            stage("write", 1, "Mod file written")

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
            msg = f"Done! {pak.name}: {len(builder._path_index)} files."
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
