# Catalog categories

Rules live in `database.py::CATEGORY_RULES` and match the prefab-resolved item (prefab tokens, `item_slot`, `item_type_name`).
## TESTMD
| Category | Rule | Status |
|---|---|---|
| weather | prefab/slot `weather` (default item **555**) | confirmed |
| terrain | prefab/slot `terrain` | confirmed |
| shaders | slot/prefab `map_effect`; keywords (`shader`, `color_filter`, `postprocess`…), modifier type, `.vpost` file | confirmed + keyword |
| head / teleport / blink / death / etc. | slot/prefab `head_effect`, `teleport_effect`, `blink_effect`, `death_effect` | confirmed |
| courier_effects, statues | `courier_effect`, `heroic_statue` | confirmed |
| gems | prefab `socket_gem` (shown on the hero page, not in the catalog) | confirmed |
| towers | prefab ends with `towers` (`diretowers`, `radianttowers`) or slot `tower_skin` | confirmed |
| creeps | prefab ends with `creeps` (`direcreeps`) | confirmed |
| ancients / roshan / tormentor | keyword in prefab/slot/type | keyword |
| emblems | `emblem`, `effigy`, `ambient_effect`… (effigies are the same thing) | keyword |
| wards / couriers | prefab / slot | confirmed |
| hud / cursors | prefab `hud_skin` / `cursor_pack` | confirmed |
| loadings / versus | `loading_screen` / keyword `versus` | mixed |
| streak | prefab `streak_effect` | confirmed |
| music / mega_kills / announcers | slot/prefab + `(type, asset)` modifier match for the default | mixed |

A category is empty because the game names it differently → run `python -m chameleon.diagnose "<dota path>" --categories`.
Lines marked `UNMAPPED` show the real names; add a rule + a test and open a PR.

## Base items
Some categories (Roshan, ancients, tormentors, emblems, effects) only worked in game when a **new base item** was created. Settings → *Base items*: Auto (replace Valve's default and create one), Replace, or Create only.
