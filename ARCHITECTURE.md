# Architecture

```
Game VPKs ──► database.py ──► picks (active_overrides) ──► applier.py ──► pak01_dir.vpk ──► gameinfo + dota.signatures
              (items, slots,    hero::<hero>::<slot>        itemdef.py     scripts/items/items_game.txt
               categories)      taunt::<hero>               extras.py      + replaced resources
                                cat::<category>::<prefab>
```

* **kv.py** keeps repeated keys (`"asset_modifier"` appears many times in `visuals`). A plain dict would keep only the last.
* **itemdef.py** is pure logic: prefab resolution, style flattening, `build_override`, default discovery
  (`find_default_ids`: slot → prefab → `(type, asset)` signature), particle swaps scoped per hero.
* **slots.py** – a hero's loadout is the union of its default-item slots and the real cosmetic slots of its items.
* **applier.py** – `commit()` reports progress as `@@<percent>|<stage>|<detail>`; the bridge turns it into a Qt signal.
* **extras.py** – river (game water materials), main-menu background (BackgroundChanger layout + your `.webm` at
  `panorama/videos/zxc/zxc.webm`), fonts (game fonts or your own file).
* **signatures.py** – appends/removes exactly one line in `dota.signatures`.
* **vtex.py** – `.vtex_c` decoder (DXT1/DXT5/RGBA/BGRA/I8/IA88/LZ4/embedded PNG-JPEG); mips are stored smallest-first.
