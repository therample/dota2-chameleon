"""
Qt-free logic that turns "I want item X" into "this is what the game's items_game must contain".

Why it works the way it does (checked against real item blocks used by the community patchers):
  * The game equips DEFAULT items. To show another item you rewrite the default item's block with the
    wanted item's data, keeping only the default item's identity (id/name/prefab/slot/heroes/baseitem).
  * Effects live in `visuals` as REPEATED "asset_modifier" blocks (see kv.py: duplicates are preserved).
  * A modifier may carry "style" (only valid for that style) and
    "apply_when_equipped_in_ability_effects_slot" (only valid in the ability-effects slot). Once the data is
    copied onto a default item neither condition can ever be true, so the effect would silently vanish.
    `flatten_style()` therefore keeps the chosen style's modifiers and removes the gating keys.
  * "particle" modifiers (asset -> modifier) replace an existing particle; the robust way, used by the
    community patchers, is ALSO to place the new particle under the old path (`particle_replacements`).
"""
import copy
import re
from typing import Dict, List, Optional, Set, Tuple

from .kv import DUP_SEP, kv_base, kv_set_unique

_MOD_KEY = re.compile(r"^asset_modifier\d*$")


def is_modifier_key(key) -> bool:
    """`asset_modifier` (repeated) and the older numbered form `asset_modifier0`, `asset_modifier1` ..."""
    return isinstance(key, str) and bool(_MOD_KEY.match(kv_base(key)))


# Keys that identify the DEFAULT item and are never taken from the source item.
HERO_IDENTITY_KEYS = {"name", "prefab", "item_slot", "used_by_heroes", "baseitem"}
GLOBAL_IDENTITY_KEYS = {"name", "prefab", "item_slot", "baseitem", "item_class", "player_loadout",
                        "used_by_heroes"}

GATING_KEYS = ("apply_when_equipped_in_ability_effects_slot",)

RESOURCE_EXTS = (".vpcf", ".vmdl", ".vmat", ".vtex", ".vanim", ".vagrp", ".vsnd", ".vsndevts",
                 ".vsnap", ".vmesh", ".vphys", ".vseq", ".vmorf", ".vmap", ".vpost", ".vsndstck")


# ------------------------------------------------------------------ prefabs
def _merge(base: dict, over: dict) -> dict:
    """Deep merge `over` on top of `base`. Repeated keys (asset_modifier ...) are appended, not replaced."""
    out = copy.deepcopy(base)
    for k, v in over.items():
        v = copy.deepcopy(v)
        if DUP_SEP in k or is_modifier_key(k):
            kv_set_unique(out, kv_base(k), v)
        elif k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def resolve_prefabs(item: dict, prefabs: dict, _depth: int = 0, _cache: Optional[dict] = None) -> dict:
    """Item data with everything inherited from its `prefab`(s) filled in (the item's own keys win).
    Pass the same `_cache` dict for many items: resolved prefabs are computed once (big speed-up on 30k items)."""
    if not isinstance(item, dict):
        return {}
    names = str(item.get("prefab", "")).split()
    if not names or not isinstance(prefabs, dict) or _depth > 8:
        return copy.deepcopy(item)
    key = " ".join(names)
    base = _cache.get(key) if _cache is not None else None
    if base is None:
        base = {}
        for n in names:
            pf = prefabs.get(n)
            if isinstance(pf, dict):
                base = _merge(base, resolve_prefabs(pf, prefabs, _depth + 1, _cache))
        if _cache is not None:
            _cache[key] = base
    return _merge(base, item)


# ------------------------------------------------------------------ styles
def _style_tokens(value) -> Set[str]:
    return set(re.findall(r"\d+", str(value)))


def style_ids(item: dict) -> List[str]:
    vis = item.get("visuals") if isinstance(item, dict) else None
    styles = vis.get("styles") if isinstance(vis, dict) else None
    if not isinstance(styles, dict):
        styles = item.get("styles") if isinstance(item, dict) else None
    return sorted((k for k in styles if isinstance(k, str) and k.isdigit()), key=int) if isinstance(styles, dict) else []


def flatten_style(src: dict, style_id: Optional[int]) -> dict:
    """
    Return a deep copy of `src` whose visuals contain only what applies to the chosen style
    (default: the lowest style, which is what the game shows when nothing is chosen), with the
    "style" / ability-slot gating keys removed so the modifiers apply on the default item.
    """
    out = copy.deepcopy(src)
    vis = out.get("visuals")
    if not isinstance(vis, dict):
        return out
    ids = style_ids(out)
    sid = str(style_id) if style_id is not None else (ids[0] if ids else "0")

    for k, v in list(vis.items()):
        if not isinstance(v, dict) or not is_modifier_key(k):
            continue
        if "style" in v:
            if sid not in _style_tokens(v["style"]):
                del vis[k]
                continue
            v.pop("style", None)
        for g in GATING_KEYS:
            v.pop(g, None)

    styles = vis.get("styles")
    if isinstance(styles, dict):
        chosen = styles.get(sid)
        if isinstance(chosen, dict):
            for key, val in chosen.items():
                if key in ("name", "icon", "alternate_icon", "unlock"):
                    continue
                if key == "model_player" and isinstance(val, str):
                    out["model_player"] = val
                elif is_modifier_key(key) and isinstance(val, dict):
                    kv_set_unique(vis, "asset_modifier", copy.deepcopy(val))
                elif isinstance(val, str):
                    vis[key] = val                     # e.g. "skin"
        vis.pop("styles", None)
    return out


# ------------------------------------------------------------------ override
def build_override(default_item: dict, source: dict, hero_scoped: bool = True) -> dict:
    """Default item identity + everything else from `source`."""
    keep_keys = HERO_IDENTITY_KEYS if hero_scoped else GLOBAL_IDENTITY_KEYS
    result = {k: copy.deepcopy(v) for k, v in default_item.items() if k in keep_keys}
    for k, v in source.items():
        if k in keep_keys:
            continue
        result[k] = copy.deepcopy(v)
    return result


def _is_default_entry(d: dict) -> bool:
    return (str(d.get("baseitem", "")) == "1" or "default_item" in str(d.get("prefab", "")).split()
            or str(d.get("name", "")).lower().startswith("default"))


def find_default_ids(items: dict, source: dict, prefabs: Optional[dict] = None) -> List[str]:
    """
    Default (baseitem) entries a NON-hero item (weather, terrain, ward, courier, tower, announcer, music ...)
    must replace. Real example: weather is item 555 "Default Weather" (baseitem 1, prefab weather, slot weather).
    Order of attempts: same slot -> same prefab -> same slot/prefab on any "Default ..." item.
    Hero-specific defaults (used_by_heroes) are never returned here.
    """
    slot = str(source.get("item_slot", "")).strip()
    prefab_names = set(str(source.get("prefab", "")).split()) - {"default_item", "wearable"}
    cands = []
    for iid, d in items.items():
        if not isinstance(d, dict) or not _is_default_entry(d):
            continue
        ub = d.get("used_by_heroes")
        if isinstance(ub, dict) and ub:
            continue
        full = resolve_prefabs(d, prefabs) if prefabs and not d.get("item_slot") else d
        cands.append((iid, d, str(full.get("item_slot", "")).strip(), set(str(d.get("prefab", "")).split())))
    sig = modifier_signature(source.get("visuals", {}))
    by_sig = []
    if sig:
        for iid, d in items.items():
            if not isinstance(d, dict) or not _is_default_entry(d):
                continue
            ub = d.get("used_by_heroes")
            if isinstance(ub, dict) and ub:
                continue
            if modifier_signature(d.get("visuals", {})) & sig:
                by_sig.append(iid)
    for pred in (
        lambda c: slot and c[2] == slot and str(c[1].get("baseitem", "")) == "1",
        lambda c: slot and c[2] == slot,
        lambda c: prefab_names and (c[3] & prefab_names) and str(c[1].get("baseitem", "")) == "1",
        lambda c: prefab_names and (c[3] & prefab_names),
    ):
        found = [c[0] for c in cands if pred(c)]
        if found:
            # also catch defaults that use the same (type, asset) modifiers but another slot/prefab name
            # (announcers, mega-kills, killstreak ... are not named consistently in the data)
            return found + [i for i in by_sig if i not in found]
    return by_sig


# ------------------------------------------------------------------ slot families
COSMETIC_TOKENS = {"weapon", "offhand", "head", "shoulder", "shoulders", "back", "arms", "armor", "belt", "neck",
                   "gloves", "legs", "misc", "bracer", "hands", "ambient", "accessory", "tail", "shapeshift",
                   "costume", "mask", "wings", "bag", "cape", "hat"}
# words that mark a slot as something other than a hero loadout slot
NOT_LOADOUT_TOKENS = ("hud", "cursor", "courier", "ward", "announcer", "music", "weather", "terrain", "tower", "loading",
                      "emoticon", "taunt", "persona", "ability_effects", "bundle", "kill", "streak", "effigy", "shader",
                      "versus", "river", "roshan", "tormentor", "creep", "ancient", "emblem", "high_five", "highfive")


def looks_like_loadout_slot(slot: str) -> bool:
    """Any non-empty slot name that is not one of the known non-loadout kinds counts (never hide a real hero slot)."""
    s = str(slot).lower().strip()
    return bool(s) and not any(t in s for t in NOT_LOADOUT_TOKENS)


def family_fallback(slot: str, available: List[str]) -> Optional[str]:
    """
    A hero without a default item for `slot` (e.g. only an offhand weapon exists): pick the default slot of the
    same family (shared token such as "weapon"). Returns None when nothing is related.
    """
    want = set(str(slot).lower().split("_")) - {"alt", "2", "secondary", "accessory"}
    best, best_score = None, 0
    for cand in available:
        have = set(cand.lower().split("_")) - {"alt", "2", "secondary", "accessory"}
        score = len(want & have)
        if score > best_score:
            best, best_score = cand, score
    return best


def modifier_signature(visuals: dict) -> Set[Tuple[str, str]]:
    """{(type, asset)} of every modifier that has BOTH - e.g. ("announcer", "announcer"), ("streak_effect", "top_bar_lvl1")."""
    sig: Set[Tuple[str, str]] = set()
    if isinstance(visuals, dict):
        for k, v in visuals.items():
            if is_modifier_key(k) and isinstance(v, dict) and v.get("type") and v.get("asset"):
                t = str(v["type"]).lower()
                if t in ("announcer", "streak_effect", "hud_skin", "cursor_pack", "soundscape", "weather", "music",
                         "entity_clientside_model", "map_override", "weather_effect", "mega_kills", "killstreak",
                         "entity_model", "model", "courier", "particle_create"):
                    sig.add((t, str(v["asset"]).lower()))
    return sig


def merge_asset_modifiers(item: dict, src_visuals: dict, types: Optional[Set[str]] = None) -> int:
    """Append every asset_modifier of `src_visuals` (optionally only `types`) to `item["visuals"]`. Returns count."""
    n = 0
    if not isinstance(src_visuals, dict):
        return 0
    vis = item.get("visuals")
    if not isinstance(vis, dict):
        vis = item["visuals"] = {}
    for k, v in src_visuals.items():
        if not is_modifier_key(k) or not isinstance(v, dict):
            continue
        if types and str(v.get("type", "")).lower() not in types:
            continue
        clean = copy.deepcopy(v)
        clean.pop("style", None)
        for g in GATING_KEYS:
            clean.pop(g, None)
        kv_set_unique(vis, "asset_modifier", clean)
        n += 1
    return n


# ------------------------------------------------------------------ resource paths
RESOURCE_ROOTS = ("particles/", "models/", "materials/", "sounds/", "soundevents/", "scripts/", "panorama/",
                  "resource/", "maps/", "shaders/", "textures/")


def looks_like_resource(s) -> bool:
    if not isinstance(s, str) or "/" not in s:
        return False
    low = s.lower().replace("\\", "/").lstrip("/")
    return low.startswith(RESOURCE_ROOTS) and any(ext in low for ext in RESOURCE_EXTS)


def normalise_path(p: str) -> str:
    p = p.replace("\\", "/").strip().lower()
    for pre in ("s2r://", "resource:"):
        if p.startswith(pre):
            p = p[len(pre):]
    return p.lstrip("/")


def collect_paths(node, out: Optional[Set[str]] = None) -> Set[str]:
    """Every resource-looking string anywhere in an item block (no key-name guessing)."""
    out = set() if out is None else out
    if isinstance(node, dict):
        for v in node.values():
            collect_paths(v, out)
    elif looks_like_resource(node):
        out.add(normalise_path(node))
    return out


def particle_replacements(visuals: dict, only_hero: Optional[str] = None) -> List[Tuple[str, str]]:
    """
    (old_path, new_path) for every `particle` modifier - the community 'rename the file' technique.
    With `only_hero` ("sniper") a swap is kept only when the OLD particle belongs to that hero, so choosing an item
    for one hero can never change another hero's (or a shared) particle.
    """
    pairs = []
    if not isinstance(visuals, dict):
        return pairs
    for k, v in visuals.items():
        if not is_modifier_key(k) or not isinstance(v, dict):
            continue
        if str(v.get("type", "")).lower() != "particle":
            continue
        a, m = v.get("asset", ""), v.get("modifier", "")
        if isinstance(a, str) and isinstance(m, str) and ".vpcf" in a.lower() and ".vpcf" in m.lower():
            old = normalise_path(a)
            if only_hero and f"hero_{only_hero.lower()}" not in old and f"/{only_hero.lower()}/" not in old:
                continue
            pairs.append((old, normalise_path(m)))
    return pairs


def modifiers_by_type(visuals: dict) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    if isinstance(visuals, dict):
        for k, v in visuals.items():
            if is_modifier_key(k) and isinstance(v, dict):
                t = str(v.get("type", "?"))
                counts[t] = counts.get(t, 0) + 1
    return counts


def entity_model(visuals: dict, hero_name: str) -> str:
    """The `entity_model` modifier (asset = hero, modifier = replacement model)."""
    fallback = ""
    if isinstance(visuals, dict):
        for k, v in visuals.items():
            if not is_modifier_key(k) or not isinstance(v, dict):
                continue
            if str(v.get("type", "")).lower() != "entity_model":
                continue
            mod = v.get("modifier", "") or v.get("model", "")
            if not isinstance(mod, str) or not mod:
                continue
            if v.get("asset") == hero_name:
                return mod
            fallback = fallback or mod
    return fallback


# ------------------------------------------------------------------ adding effects to a default item
def add_particle_modifier(item: dict, particle_path: str, extra: Optional[dict] = None) -> None:
    """Attach a particle to an item the way the game expects: a repeated `asset_modifier` in `visuals`
    (the old code wrote an `attached_particle_effects` key that the game never reads)."""
    vis = item.get("visuals")
    if not isinstance(vis, dict):
        vis = item["visuals"] = {}
    mod = {"type": "particle_create", "modifier": normalise_path(particle_path)}
    if extra:
        mod.update(extra)
    kv_set_unique(vis, "asset_modifier", mod)


def copy_particle_modifiers(src_visuals: dict, item: dict) -> int:
    """Copy every `particle_create` modifier from a source `visuals` block onto `item`. Returns the count."""
    n = 0
    if not isinstance(src_visuals, dict):
        return 0
    for k, v in src_visuals.items():
        if is_modifier_key(k) and isinstance(v, dict) and str(v.get("type", "")).lower() == "particle_create":
            vis = item.get("visuals")
            if not isinstance(vis, dict):
                vis = item["visuals"] = {}
            clean = copy.deepcopy(v)
            clean.pop("style", None)
            for g in GATING_KEYS:
                clean.pop(g, None)
            kv_set_unique(vis, "asset_modifier", clean)
            n += 1
    return n
