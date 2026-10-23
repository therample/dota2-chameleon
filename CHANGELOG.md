# Changelog

## 15.3

### Removed
- **Fonts** (the font changer), the **Item effects** tab and the **Kill effects** tab.

### Fixed
- **Music**: music packs are now recognised by the music folders that really exist in your game files (for example `valve_ti7_01`):
  any item that points at one of them is a music pack, whatever its name or slot says. Treasure chests and bundles stay out.
- **Icons**: when an item lists an old or slightly different picture name, Chameleon now looks inside that item's own folder and
  takes the only picture there, or the closest name. Pictures from other folders are never used, which is what showed strange icons.
- **Settings** page: the panels now flow in two columns, so there is no half-empty space next to a tall block.
- **Loading screen**: bigger and nicer – a large animated logo, a wide progress bar, the step name and a percentage.

## 15.2

### Fixed
- **Emblems, map effects (shaders) and other effects** are back in the equipped slots of Dota, as before. Attaching them to hero items
  (it looked attached, came with a delay and sank under the map) is now only an option: Settings → *Emblems and effects on heroes*.
- **Personas**: more personas are found (by slot, name or persona modifier), and a persona is now chosen as the hero's persona itself,
  not as a gear slot. If the hero has no persona slot yet, one is added for that hero only.
- **Music**: every text of an item is checked (for example an icon path with "music" in it), so packs whose type says nothing are
  found. Treasure chests and bundles stay out. Two items with the same name no longer replace each other, which could hide
  a lot of a category.
- **Settings** page is laid out evenly in two equal columns with aligned controls.

### Added
- **Item effects** (new tab on every hero page): put Frostbloom, unusual-style effects, gem glows and similar particles on any item
  slot of a hero. One effect per slot, explicit choice, easy to remove.
- Counters (heroes, items, selected) are back on the Home page.
- Livelier look again: particles, soft glow, zoom on hover over cards, an animated logo (it draws itself, glows and wiggles on hover).
  The loading screen stays quiet and shows the animated logo.
- A clearer progress window again, with "Step 3 of 6".

### Removed
- The "Item names language" setting.

## 15.1

### Fixed
- **Hero pictures** now come from Steam first (always the right picture) and from the game as a backup. Item pictures come only from the
  game (the Steam source never had them). Items are no longer hidden by the colour filter.
- **Music** no longer includes treasure chests, bundles and keys. Music packs are also found when their name and slot say nothing
  but their sound points to a music track.
- **Gems**: only gems that really change something are offered (stat-only gems were clutter). They are matched to a hero by id,
  by name or by the hero's effect files; a hero with an arcana but no match gets all effect gems.
- **Blink, kill, teleport, head, death and courier effects** are found with wider matching.
- **Emblems and hero effects in online matches**: they are attached to the heroes' own items (a base item created only for you
  never reached online matches). Roshan, ancients, tormentors and statues get an extra base item. Settings → *Special items*.

### Changed
- A calmer, simpler look: no particles, no glow, no counters; a quiet loading screen; a compact progress window with
  "Step 3 of 6". All texts are written for everyday users.
- README and troubleshooting are written for users; developer notes moved to `docs/DEVELOPERS.md`.

## 15.0

### New UI
- **Cinematic loading screen**: shield drawn stroke by stroke, orbiting rings, converging star field, letter-by-letter title,
  real progress that follows what the backend is doing (files → names → items → heroes → catalog → cache) and a burst when ready.
- **Apply progress card**: progress ring + bar, six-step timeline (Prepare → Rewrite → Resources → Extras → Write → Register) with
  check marks, live detail ("12/40 files"), elapsed time, success and error states.
- **No lag**: big tabs are filled in small frames (a 420-card category paints its first cards instantly), selecting an item patches
  the card in place instead of rebuilding the page, searches are debounced, the page-wide MutationObserver is gone.
- Toolbar on every hero tab and catalog tab: **search, sort (A–Z / rarity / selected first), card size S/M/L, selected only**.
- Apply button shows how many things are selected; Ctrl+Enter applies; `/` focuses search; Esc goes back.

### Gems (Terrorblade, Techies …)
- Heroes whose arcana has gems get a **Gems** tab (by the gem's hero, by the hero's particle paths in the gem, or by an arcana that
  mentions sockets). One gem per hero; its modifiers are attached to the hero's main item and its particle swap is written under
  the hero's own particle path.

### New categories (from real `diagnose --categories` output)
Head / teleport / blink / death / kill effects, courier effects, heroic statues, map effects (= map shaders), emblems.
New **Effects** group in the catalog.

### Settings
- **Icons**: item icon source (own icon / auto / preview), where icons come from (game files / Steam CDN / auto), yellow-green cast
  fix, clear icon cache, statistics. The default is *own icon only* - it never shows a hero preview in place of an item.
- **Base items** (Roshan, ancients, tormentors, emblems, effects …): *Auto* replaces Valve's default AND creates a base item
  (what worked in game), *Replace* or *Create only*.
- **Background method**: Layout (BackgroundChanger) or replacing the game's own menu videos.

### Fixed
- Yellow **and yellow-green** cast detection (pure green and orange pictures are not flagged); the CDN replaces rejected pictures.
- Icons: the disk cache name contains the settings profile, so a setting change never shows icons made under another one.
- **Background**: any video or a **still picture** (PNG/JPG/WebP) - converted to VP9 / yuv420p / no audio / even size / ≤1080p / ≤30 fps
  with ffmpeg (a picture becomes a looping clip). Without ffmpeg only a VP9 WebM is accepted.
- **Roshan / ancients / tormentors / emblems**: base item is created next to (or instead of) the default.
- **Couriers**: the default is also found by its model modifier when its slot/prefab names differ.
- **Music**: found by prefab, slot, type, modifier type, and (last resort) by its own name; `diagnose --find music` shows what
  happened to every music-like item.
- Catalog items (effects, statues, emblems …) no longer also appear as hero cosmetics.

### Tools
- `python -m chameleon.diagnose "<dota>" --find <word>`: every item mentioning a word and what became of it.

## 14.5

### Fixed
- **Yellow hero icons**: a decoded hero picture with a yellow/olive cast is rejected and the CDN portrait is used instead
  (item icons are never filtered - real gold items stay gold). Icon cache bumped (`v4_`).
- **Fonts did nothing**: Panorama asks for a font *family name*. The replacement is now renamed (name IDs 1/2/4/6/16/17 and
  `fsType`) to the target's own names, like dota2-minify's Custom Fonts. Works for game fonts and your own `.ttf/.otf`.
- **Background = black screen**: Panorama only plays VP9 / yuv420p / no audio. With ffmpeg installed any video
  (`.mp4 .webm .mov .mkv .avi .gif`) is converted that way (cached); without ffmpeg only a VP9 WebM is accepted and every
  other file is refused with an explanation instead of silently producing a black screen.
- **River not always applied**: every non-vial water material under `materials/water/` is now replaced, not only
  `water_generic_*`.
- **Music "almost empty"**: music is detected by prefab/slot/type/modifier type (`music`, `soundtrack`), and catalog items are
  no longer hidden just because their name is missing in the localization (they get a readable name instead).
- **Screen shaders**: found by prefab/slot/type keywords, modifier type, `.vpost` files and any string pointing at
  post-processing / `/correction/` data.
- **Build report: "no default baseitem" for effigy / emblem, ancient, tormentor**: when Valve's data has no default for a
  slot/prefab, Chameleon creates a base item for it (noted in the report) instead of failing.

### Changed
- Attribute icons and the attribute filter are gone.
- Less dependent on game patches: prefab resolution is memoised (12k items parse in well under a second of Python work),
  the game's signature is stored at Apply time and a banner appears when Dota was updated ("click here to Apply again").
- UI: card spotlight, tilt on featured skins, count-up stats, drifting banner shine, update banner.

## 14.4

### Fixed
- **Icons**: the "file name only" fallback could resolve many different items to one unrelated (gold) texture. It now
  requires the same folder + name. A CDN fallback (Steam) fills what the game files don't have. Texture layout was
  verified on 288 real compiled textures (all decode, mip layout exact); BC1/BC3 cross-checked with Pillow.
- **Catalog page did not load** (a missing `S.regCat` state variable threw inside the card renderer).
- **White blob bottom-left**: the resize handle shared the `.sw` class with the settings switch.
- Star / tick / tag overlays now live inside the image box (star top-right, tick bottom-right).
- **River colour**: uses the game's own water materials (`water_dota_*` / `water_econ_dota_*`) over the default river
  (`water_generic_*`). No more byte-patching.
- **Custom main-menu background**: done like BackgroundChanger / dota2-minify (layout files + your `.webm` at
  `panorama/videos/zxc/zxc.webm`); layout files are downloaded on request.
- **Slots**: a hero's loadout is any non-system slot - nothing is hidden because of an unexpected name.
- Emblems and effigies are one category and the search is wider; shaders are found by keyword, modifier type and `.vpost`.

### Added
- **Home** page with random featured skins; search inside a hero and in every catalog tab.
- **Staged progress overlay** (Prepare / Rewrite / Resources / Extras / Write / Register).
- **dota.signatures** support (one reversible line, switch in Settings, backup on first use).
- **Fonts**: game fonts or your own `.ttf/.otf`, validated.
- Icon statistics in Settings; real-UI test (jsdom) in CI.
- GitHub repo files: README (EN/RU), docs, issue/PR templates, CI, CONTRIBUTING, SECURITY, LICENSE.

### Removed
- Frostbloom, Terrorblade/Techies gems, kill banners, high fives, ranged attacks, creep deny, effect packs,
  river in the catalog, the built-in game video backgrounds (own background only), the HUD scale settings.

## 14.3

### New catalog (Catalog tab, grouped)
World (weather, terrain, river, screen shaders) / Units & buildings (towers, creeps, ancients, Roshan, tormentors) /
Items (wards, couriers, emblems, gems, effigies) / Interface (HUD skins, cursors, loading screens, versus screens,
fonts) / Kill effects (kill streak, kill banners, high fives, ranged attacks, creep deny, effect packs) /
Sound (music, mega-kills, announcers). Counts per category, search, sort-stable cards, **Favorites** (star on any card,
Favorites tab).
- Categories are detected from the game DATA by prefab/slot/type name. Names confirmed from real community data:
  `diretowers`/`radianttowers`, `direcreeps`, `cursor_pack`, `hud_skin`, `streak_effect`, `weather` (default id 555),
  `terrain`. The rest use keyword rules; `python -m chameleon.diagnose <dota> --categories` prints every name found and
  marks `UNMAPPED` ones so a rule can be added without guessing.
- One pick per (category, prefab): Dire and Radiant towers/creeps can both be set.
- Defaults (baseitem) are targets, never listed as choices.

### Fixed
- **Towers** (prefab was `diretowers`, not `tower`), creeps, cursors, HUD skins, kill streak effects.
- **Announcers / mega-kills**: the default entry is now also found by its `(type, asset)` modifiers, so unusual default
  names/prefabs no longer make the replacement silently miss.
- **Weather "only one / buggy"**: an old `cl_weather 1` autoexec line pinned snow. Removed; weather works through the
  default weather item (555) like the community patcher.
- **Taunts**: heroes have no default taunt item; the taunt's `activity` modifiers are now attached to the hero's main
  default item (reported in the build report).
- **Missing default weapon**: slots come from default items AND cosmetics, and an item for a slot without default is
  applied through the related default (weapon -> offhand) with a note in the report.
- **Arcanas that "did nothing"**: if the slot has no target, the arcana's effects/animations/model swap are attached to
  the hero's main item instead of being dropped.
- **Hero attributes / names**: newer Dota splits heroes into one file each (`#base` includes in npc_heroes.txt); those
  are now read, so attributes (and the filter), models and the arcana model swap work.
- **Particles changed on other heroes**: ability-particle swaps are now limited to the chosen hero's own particles
  (Settings: Hero only / All / Off); gems are bound to their own hero (no more global gem injection).
- **Style names**: tokens are shown as readable text (localized), raw internal names become "Style N".
- Backgrounds: builtin game backgrounds + your own `.webm`, validation, and the exact replaced files in the report.
- Frostbloom: effects come from the game data (items named Frostbloom), attached to a chosen hero slot.
- Icons: new decoder + correct VPK paths; cache bumped so wrongly decoded icons are never reused. BC1/BC3 decoding
  is checked against Pillow's independent decoder.

### UI
- Old black/white look and shield logo; tooltips fixed (sidebar above the page); attributes drawn as black/white shapes.
- Titlebar logo, stat tiles, page headers; EN/RU interface language and item-name language in Settings.
- **Staged progress bar**: Prepare > Rewrite > Resources > Extras > Write > Register with percent and detail.
- **Launch presets** page: built-in presets, quick flags, your own presets, used by the Launch button.
- **Fonts** (game fonts only): replace one game font with another, or use one for all.
- Removed the HUD / minimap scale settings and the `autoexec` writing (cosmetics only).
- Snappier: debounced search, `content-visibility` cards, no animation replay when picking items.

## 14.2
Language, frostbloom/background pages, icon fixes, tooltip/logo fixes.

## 14.1
Repeated `asset_modifier` keys preserved (root cause of missing effects), style flattening, slots, icons, report.

## 14.0
Modular rewrite, single `pak01_dir.vpk`, reversible gameinfo patch.
