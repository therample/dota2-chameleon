# For developers

This page is for people who want to look inside Chameleon, run the tests or add something. Normal users do not need it.

## How it works

1. **Read** – `items_game.txt`, hero files and the language files are read from the game's VPK archives.
2. **Choose** – every choice is stored as an override: `hero::<hero>::<slot>`, `taunt::<hero>`, `gem::<hero>::socket`,
   `cat::<category>::<prefab>`.
3. **Build** – the game equips *default* items, so a default item keeps its identity (id, name, slot, hero) and takes everything
   else from the chosen item. Effects live in repeated `asset_modifier` blocks (the parser keeps every one). Style and
   ability-slot gating keys are flattened so the effects work on the default item.
4. **Write** – one `pak01_dir.vpk` in the mod folder (`items_game.txt`, hero files, replaced particles / river / menu files).
5. **Register** – the folder is added to `gameinfo_branchspecific.gi`; one line is added to `dota.signatures` (switch in Settings).
   Restore removes both and the folder.

Effects and units without a default item: by default a **base item is created in the equipped slot** (this is what shows in the Dota
loadout and what worked for emblems and map effects). Setting `effect_mode`: `slot` (default), `hero` (attach the effect to the main
default item of every hero – works with other players but can look attached) or `both`. Map units (Roshan, ancients, tormentors, statues)
get an extra base item. `default_mode`: `auto`, `replace`, `create`.

Personas are chosen in their own slot (`persona_selector`); when a hero has no persona default, one is created for that hero only.
Music packs are recognised by the folders under `soundevents/music` that exist in the game files (`Database.music_ids`).

## Files

| Path | Responsibility |
|---|---|
| `run.py` | entry point |
| `chameleon/common.py` | constants, paths, logging, default settings |
| `chameleon/qt.py` | the only PySide6 import of the core (the core runs without Qt) |
| `chameleon/vpk_io.py` | VPK reader / writer |
| `chameleon/kv.py` | KeyValues parser that keeps repeated keys |
| `chameleon/itemdef.py` | prefab merge, style flatten, override building, default discovery |
| `chameleon/slots.py` | a hero's real slots |
| `chameleon/database.py` | items, heroes (`#base` files), names, category rules, gems |
| `chameleon/deps.py` | follows references of compiled resources |
| `chameleon/applier.py` | builds the mod (`commit` / `restore`), progress stages, report |
| `chameleon/extras.py` | river, menu background (ffmpeg) |
| `chameleon/gameinfo.py`, `signatures.py` | reversible registration |
| `chameleon/vtex.py`, `iconsrc.py`, `icons.py` | texture decoder, icon lookup, icon manager |
| `chameleon/bridge.py`, `window.py` | Qt ⇄ page bridge, window |
| `chameleon/ui/index.html` | the whole interface |
| `chameleon/diagnose.py` | command line inspector |
| `tests/` | tests on a synthetic Dota install, plus the real page in jsdom |

## Tests

```
pip install -r requirements.txt
cd tests/ui && npm install && cd ../..
python -W ignore -m unittest discover -s tests -v
```

No Dota 2 install is needed: the tests build a small fake one. The UI test loads the real `index.html` in jsdom against data
from the real Python bridge.

## Inspecting your own game

```
python -m chameleon.diagnose "<dota path>" "<item name>"      # what the data holds for an item (+ icon format)
python -m chameleon.diagnose "<dota path>" --categories       # which prefab / slot names go to which category
python -m chameleon.diagnose "<dota path>" --find music       # every item that mentions a word, and what became of it
```

If a category looks empty, send the output of `--categories` (lines marked `UNMAPPED`) or `--find <word>` in an issue: the real
names are exactly what a new rule needs.

## What is checked and what is not

Checked by tests: parsing and writing of repeated keys, every modifier reaching the pack, slots of heroes with many extra slots,
`#base` hero files, VPK files read back by the reference `vpk` library, the texture decoder (288 real compiled textures and a
Pillow cross-check), fonts renamed to the target family, ffmpeg conversion of videos and pictures, the signature line, the real
page in jsdom.

Not checked (needs a real Dota 2): how every category looks in game, announcer and music sound, online matchmaking with the
signature line, Roshan / ancient / tormentor models.

## Install methods, stock paths, Panorama

- `install_method`: `language` (`game/dota_<lang>/pakNN_dir.vpk`, tracked in a manifest so Valve's own paks are never touched) or `custom`
  (own folder + `gameinfo_branchspecific.gi` + one `dota.signatures` line).
- Stock paths (`stock_models`): `Applier._override_item` / `_prune_model_swaps` write the chosen model under the stock model path and drop
  the model modifier; `_swap_pairs` is flushed into the pak by `_stock_files`. If nothing else changes, `items_game` is not written.
- `panorama.py`: a compiled `.vxml_c` / `.vcss_c` is a container whose DATA block holds the source text (`crc32 | u16 0 | text`), so layouts
  are read from the game, patched as text and written back. The menu background points `DOTADashboardBackgroundManager`'s
  `override-background` at our layout.
- `rpc.py`: optional Discord Rich Presence on a worker thread (latest state wins, at most one update per 15 s).
