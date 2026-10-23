from .common import *
from .itemdef import resolve_prefabs, family_fallback, looks_like_loadout_slot

# ==============================================================================
# SLOT RESOLVER
#
# A hero's loadout slots are exactly the `item_slot` values of its DEFAULT items in items_game.
# Heroes differ a lot (Invoker, Lone Druid, Lycan, Meepo, Io ... have many extra slots such as
# "weapon_alt", "head_accessory", "back_accessory", "misc", "shapeshift" ...), so slots are never
# merged or renamed: an item belongs to the slot named in its own `item_slot`, and that slot exists for
# the hero if (and only if) the hero has a default item for it.
# ==============================================================================

# slots that are not part of a hero's visible loadout
NON_LOADOUT_SLOTS = {"taunt", "courier", "ward", "weather", "terrain", "music", "tower_skin", "announcer",
                     "kill_streak", "mega_kills", "loading_screen", "emoticon", "hud_skin", "cursor_pack",
                     "persona_selector", "ability_effects", "bundle"}

SLOT_ORDER = ["weapon", "offhand_weapon", "head", "shoulder", "back", "arms", "armor", "belt", "neck",
              "gloves", "legs", "misc"]

# only used when an item names a slot the hero has no default item for (data quirks, old items)
_FALLBACK = {"offhand": "offhand_weapon", "shoulders": "shoulder", "hands": "gloves", "waist": "belt",
             "boots": "legs", "feet": "legs", "helmet": "head", "hat": "head", "mask": "head",
             "cape": "back", "cloak": "back", "chest": "armor"}


def slot_title(slot: str) -> str:
    return slot.replace("_", " ").strip().capitalize()


def slot_sort_key(slot: str):
    base = slot
    return (SLOT_ORDER.index(base) if base in SLOT_ORDER else len(SLOT_ORDER), slot)


class DynamicSlotResolver:
    def __init__(self):
        self.hero_slots: Dict[str, Dict[str, List[str]]] = {}

    def build_from_items_game(self, items_data: dict):
        self.hero_slots.clear()
        root = items_data.get("items_game", items_data)
        items = root.get("items", {})
        prefabs = root.get("prefabs", {})
        if not isinstance(items, dict):
            return
        for item_id, d in items.items():
            if not isinstance(d, dict):
                continue
            is_default = ("default_item" in str(d.get("prefab", "")).split()
                          or str(d.get("baseitem", "")) == "1")
            if not is_default:
                continue
            full = d if d.get("item_slot") and d.get("used_by_heroes") else resolve_prefabs(d, prefabs)
            slot = str(full.get("item_slot", "")).strip()
            ub = full.get("used_by_heroes", {})
            if not slot or not isinstance(ub, dict):
                continue
            for hero in ub:
                self.hero_slots.setdefault(hero, {}).setdefault(slot, []).append(item_id)
        log.info("Slot map: %d heroes, %d distinct slots", len(self.hero_slots),
                 len({s for h in self.hero_slots.values() for s in h}))

    # slot name -> first default item id (kept for older callers)
    def get_hero_slots(self, hero_name: str) -> Dict[str, str]:
        return {s: ids[0] for s, ids in self.hero_slots.get(hero_name, {}).items() if ids}

    def get_default_ids(self, hero_name: str, slot: str) -> List[str]:
        return list(self.hero_slots.get(hero_name, {}).get(slot, []))

    def loadout_slots(self, hero_name: str) -> List[str]:
        slots = [s for s in self.hero_slots.get(hero_name, {}) if s not in NON_LOADOUT_SLOTS]
        return sorted(slots, key=slot_sort_key)

    def resolve_slot(self, hero_name: str, requested_slot: str) -> Optional[str]:
        """
        Slot an item of this hero belongs to. A slot the hero has no default item for is still accepted when it is
        a real loadout slot (weapon, head, misc ...): the build step then falls back to a related default
        (see targets_for) or reports clearly that there is no target. Non-loadout names (hud_skin_slot ...) -> None.
        """
        have = self.hero_slots.get(hero_name)
        if not have:
            return requested_slot
        if requested_slot in have:
            return requested_slot
        alt = _FALLBACK.get(requested_slot.lower().strip())
        if alt and alt in have:
            return alt
        if requested_slot not in NON_LOADOUT_SLOTS and looks_like_loadout_slot(requested_slot):
            return requested_slot
        return None

    def targets_for(self, hero_name: str, slot: str):
        """(default item ids, slot actually used). Exact slot first, then the same family, else ([], slot)."""
        have = self.hero_slots.get(hero_name, {})
        if have.get(slot):
            return list(have[slot]), slot
        loadout = [s for s in have if s not in NON_LOADOUT_SLOTS]
        alt = family_fallback(slot, loadout)
        if alt and have.get(alt):
            return list(have[alt]), alt
        return [], slot

    def all_loadout_ids(self, hero_name: str) -> List[str]:
        out: List[str] = []
        for s in self.loadout_slots(hero_name):
            out += self.hero_slots[hero_name][s]
        return out

    def get_arcana_base_slot(self, hero_name: str, item_data: dict = None) -> str:
        if item_data and item_data.get("item_slot"):
            return str(item_data["item_slot"])
        slots = self.loadout_slots(hero_name)
        for preferred in ("weapon", "head", "armor", "offhand_weapon"):
            if preferred in slots:
                return preferred
        return slots[0] if slots else "weapon"
