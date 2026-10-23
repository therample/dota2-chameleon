"""
Command-line inspector (no Qt, no changes to the game):

    python -m chameleon.diagnose "C:/Program Files (x86)/Steam/steamapps/common/dota 2 beta" "Item Name or part of it"
    python -m chameleon.diagnose "<dota path>" --categories      # which prefab/slot names map to which catalog category
    python -m chameleon.diagnose "<dota path>" --find music      # every item mentioning a word and what became of it

Prints what Chameleon would write for the item: slot, rarity, styles, every asset_modifier by type,
the particles it replaces, and which referenced files exist in the game. Send this output when an item
shows no effects - it shows exactly what the game data contains.
"""
import json
import sys
from pathlib import Path

from .common import *
from .database import SkinDatabase
from .applier import SkinApplier
from .itemdef import modifiers_by_type, particle_replacements, collect_paths, style_ids, resolve_prefabs, flatten_style
from .kv import kv_base
from .iconsrc import IconSource, candidates_from_inventory_path
from .vtex import describe_vtex_c


def find_items(dota: Path, word: str) -> int:
    """Every item mentioning `word` anywhere (name, prefab, slot, type, modifier strings) and what became of it."""
    db = SkinDatabase(dota)
    if not db.initialize():
        print("Could not load the game database")
        return 1
    w = word.lower()
    shown = 0
    print(f"{'name':38} {'prefab':22} {'slot':16} {'category':14} note")
    for it in db.items.values():
        raw = it.raw_item_data or {}
        hay = " ".join([it.name, it.localized_name or "", it.prefab, it.item_slot or "", str(raw.get("item_type_name", ""))] + db._all_strings(raw.get("visuals", {}))).lower()
        if w not in hay:
            continue
        cat = db.category_of(it) or "-"
        note = []
        if str(raw.get("baseitem", "")) == "1":
            note.append("BASEITEM(default: never listed)")
        if raw.get("used_by_heroes"):
            note.append("hero-bound")
        if db.is_system_item(it, strict=False):
            note.append("filtered as system item")
        if cat != "-" and cat in db.categories and it.name in db.categories[cat]:
            note.append("LISTED")
        print(f"{it.name[:38]:38} {it.prefab[:22]:22} {(it.item_slot or '-')[:16]:16} {cat:14} {', '.join(note)}")
        shown += 1
    print(f"\n{shown} item(s) mention '{word}'. Send this output if a category misses items.")
    return 0


def categories(dota: Path) -> int:
    """Every prefab / slot / type name used by non-hero items, with counts and the category each maps to."""
    from collections import Counter
    db = SkinDatabase(dota)
    if not db.initialize():
        print("Could not load the game database")
        return 1
    seen = Counter()
    for it in db.items.values():
        raw = it.raw_item_data or {}
        if raw.get("used_by_heroes"):
            continue
        typ = str(raw.get("item_type_name", "")).replace("#DOTA_WearableType_", "")
        seen[(it.prefab or "-", it.item_slot or "-", typ or "-", db.category_of(it) or "UNMAPPED")] += 1
    print(f"{'prefab':28} {'slot':18} {'type':22} {'category':14} count")
    for (pf, sl, ty, cat), n in sorted(seen.items(), key=lambda kv: (kv[0][3] != "UNMAPPED", -kv[1])):
        print(f"{pf[:28]:28} {sl[:18]:18} {ty[:22]:22} {cat:14} {n}")
    print("\nSend the UNMAPPED lines if a category is empty - they show the real names to add as rules.")
    return 0


def main(argv=None):
    argv = argv or sys.argv[1:]
    if len(argv) < 2:
        print(__doc__)
        return 2
    if argv[1] == "--categories":
        return categories(Path(argv[0]))
    if argv[1] == "--find" and len(argv) >= 3:
        return find_items(Path(argv[0]), argv[2])
    dota, query = Path(argv[0]), argv[1].lower()
    db = SkinDatabase(dota)
    if not db.initialize():
        print("Could not load the game database")
        return 1
    ap = SkinApplier(dota, db, {})
    loaded = ap._load_items_game()
    _, root, items, prefabs = loaded
    hits = [i for i in db.items.values() if query in i.name.lower() or query in (i.localized_name or "").lower()][:8]
    if not hits:
        print("No item matches", query)
        return 1
    index = ap._base_index()
    for it in hits:
        raw = items.get(str(it.item_id), {})
        src = flatten_style(resolve_prefabs(raw, prefabs), None)
        vis = src.get("visuals", {})
        print("=" * 72)
        print(f"{it.name}  (#{it.item_id})  '{it.localized_name}'")
        print(f"  prefab={it.prefab} slot={it.item_slot} rarity={it.rarity} hero={it.used_by_hero}")
        print(f"  styles: {style_ids(resolve_prefabs(raw, prefabs)) or 'none'}")
        print(f"  modifiers (style 0): {modifiers_by_type(vis) or 'NONE'}")
        for old, new in particle_replacements(vis):
            print(f"  replaces particle {old}  <-  {new}")
        if it.icon_path:
            src = IconSource(db.vpk_readers)
            found = [c for c in candidates_from_inventory_path(it.icon_path) if src._find(c)]
            if found:
                raw = src._find(found[0]).extract_to_bytes(found[0])
                print(f"  icon: {found[0]} -> {describe_vtex_c(raw)}")
                png = src.item_icon(it.icon_path)
                if png:
                    out = Path.cwd() / f"icon_{it.name}.png"
                    out.write_bytes(png)
                    print(f"  decoded icon written to {out}")
            else:
                print(f"  icon: no file for image_inventory '{it.icon_path}'")
        missing = [p for p in sorted(collect_paths(src)) if not p.endswith('.vmap') and index.resolve(p) is None]
        print(f"  referenced paths: {len(collect_paths(src))}, missing in game files: {len(missing)}")
        for m in missing[:10]:
            print("    missing:", m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
