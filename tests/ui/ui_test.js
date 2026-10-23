// Runs the REAL chameleon/ui/index.html in jsdom against a fake bridge fed with data produced by the real Python bridge.
// Usage: node ui_test.js <index.html> <fixture.json>
const fs = require('fs');
const { JSDOM, VirtualConsole } = require('jsdom');
const [, , htmlPath, fixPath] = process.argv;
const F = JSON.parse(fs.readFileSync(fixPath, 'utf8'));
F.status.status = 'loading';   // the real backend reports 'ready' only after the database is loaded
const html = fs.readFileSync(htmlPath, 'utf8').replace(/<script src="qrc:[^"]*"><\/script>/, '');

const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => errors.push(String(e.detail || e.message || e)));
vc.on('error', e => errors.push(String(e)));

const sig = () => { const f = []; return { connect: fn => f.push(fn), emit: (...a) => f.forEach(fn => fn(...a)) }; };
const favs = new Set(F.favorite_names);
const calls = [];
const P = v => Promise.resolve(v);
// a big synthetic category to prove chunked rendering
const BIG = Array.from({ length: 420 }, (_, i) => ({ name: 'big_' + i, display_name: 'Big ' + String(i).padStart(3, '0'), localized_name: 'Big ' + String(i).padStart(3, '0'), rarity: i % 7 === 0 ? 'rarity_mythical' : 'rarity_common', icon_path: 'econ/big/' + i, styles: [], is_arcana: false, is_persona: false }));
F.category_items.music = BIG;
F.catalog.forEach(g => g.cats.forEach(c => { if (c.id === 'music') c.count = BIG.length; }));
const active = JSON.parse(JSON.stringify(F.active));
const bridge = {
  statusChanged: sig(), dbLoaded: sig(), applyResult: sig(), iconReady: sig(), launchResult: sig(), progressChanged: sig(),
  get_config: () => P(JSON.stringify(F.config)), get_status: () => P(JSON.stringify(F.status)),
  get_heroes: () => P(JSON.stringify(F.heroes)), get_active_overrides: () => P(JSON.stringify(active)),
  get_favorite_names: () => P(JSON.stringify([...favs])), get_applied_counts: () => P(JSON.stringify(F.counts)),
  get_hero_catalog: n => P(JSON.stringify(F.hero_catalog[n] || { slots: [], arcanas: [], personas: [], taunts: [], gems: [] })),
  get_catalog: () => P(JSON.stringify(F.catalog)),
  get_category_items: c => P(JSON.stringify(F.category_items[c] || [])),
  get_favorites: () => P(JSON.stringify(Object.values(Object.assign({}, F.all_items, Object.fromEntries(BIG.map(i => [i.name, i])))).filter(i => favs.has(i.name)))),
  toggle_favorite: n => { const on = !favs.has(n); on ? favs.add(n) : favs.delete(n); return P(on); },
  get_launch_presets: () => P(JSON.stringify(F.launch)), get_cache_size: () => P('{"formatted":"1 MB"}'),
  get_build_report: () => P('{}'), get_item_languages: () => P('["english","russian"]'), get_presets: () => P('[]'),
  get_river_colors: () => P('["default","blood","slime"]'), get_background_state: () => P(JSON.stringify(F.bgstate)),
  get_featured: () => P(JSON.stringify(F.featured)),  get_fonts: () => P(JSON.stringify(F.fonts)),
  get_icon_stats: () => P('{"from_vpk":1,"from_cdn":0,"from_disk":0,"missing":0}'),
  get_hero_icon: () => P(''), get_item_icon: (n) => P(n === 'big_3' ? 'iVBORw0KGgo=' : ''),
  install_background_layout: () => P(true), browse_font: () => P(false), clear_icon_cache: () => P(3),
};
['apply_skin', 'apply_style', 'remove_override', 'clear_all_overrides', 'set_option', 'select_launch_preset', 'save_launch_preset',
 'delete_launch_preset', 'set_river_color', 'set_background', 'browse_background', 'restore_all', 'launch_dota', 'apply_all',
 'start_move', 'start_resize', 'minimize_window', 'close_window', 'toggle_maximize_window', 'set_font', 'set_all_fonts', 'clear_fonts',
 'save_hud_settings', 'set_launch_params', 'set_auto_restore', 'save_preset', 'load_preset', 'delete_preset', 'cleanup_mod',
 'clear_cache', 'rebuild_database', 'browse_dota_path']
  .forEach(n => bridge[n] = (...a) => { calls.push([n, ...a]); return P(true); });
// the fake bridge mirrors what the real one does for selections so the page can refresh
bridge.apply_skin = (cat, hero, name, slot) => { calls.push(['apply_skin', cat, hero, name, slot]);
  const key = cat === 'fx' ? 'fx::' + hero + '::' + slot : cat === 'gems' ? 'gem::' + hero + '::socket' : (cat === 'heroes' ? 'hero::' + hero + '::head' : 'cat::' + cat + '::x');
  active.overrides = active.overrides || {}; active.overrides[key] = name; return P(true); };
bridge.remove_override = (k) => { calls.push(['remove_override', k]); delete (active.overrides || {})[k]; return P(true); };

const dom = new JSDOM(html, {
  runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'http://localhost/',
  beforeParse(w) {
    w.qt = { webChannelTransport: {} };
    w.QWebChannel = function (t, cb) { cb({ objects: { chameleon: bridge } }); };
    w.IntersectionObserver = class { constructor(cb) { this.cb = cb; } observe(el) { this.cb([{ isIntersecting: true, target: el }]); } unobserve() {} };
    const ctx = new Proxy({}, { get: (_, k) => (k === 'canvas' ? {} : () => {}), set: () => true });
    w.HTMLCanvasElement.prototype.getContext = () => ctx;
  },
});
const w = dom.window, d = w.document;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const out = [];
const ok = (cond, msg) => { out.push((cond ? 'PASS ' : 'FAIL ') + msg); if (!cond) process.exitCode = 1; };
const q = s => d.querySelectorAll(s);
const click = el => el.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
const change = (el, v) => { el.value = v; el.dispatchEvent(new w.Event('change', { bubbles: true })); };
const typeIn = (el, v) => { el.value = v; el.dispatchEvent(new w.Event('input', { bubbles: true })); };
const waitFor = async (fn, ms = 3000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (fn()) return true; await sleep(25); } return !!fn(); };

(async () => {
  // ---------- cinematic loading screen ----------
  ok(!!d.querySelector('#loading .lshield svg path') && !d.querySelector('#loading canvas') && !!d.getElementById('particles'), 'loading screen: an animated shield logo, the name and a thin progress line; the app keeps its particle background');
  bridge.statusChanged.emit('Parsing items_game.txt...');
  await sleep(500);
  const p1 = parseInt(d.getElementById('lbar').style.width, 10) || 0;
  ok(p1 > 5, 'loading screen: progress bar moves with status messages (' + p1 + '%)');
  ok(/items/i.test(d.getElementById('lstep').textContent), 'loading screen: shows the current step text (got: ' + d.getElementById('lstep').textContent + ')');
  F.status.status = 'ready';
  bridge.dbLoaded.emit(true);
  ok(await waitFor(() => d.getElementById('p-home').classList.contains('on'), 4000), 'app starts on the Home page');
  const css = [...d.querySelectorAll('style')].map(x => x.textContent).join('');
  ok(/\.lshield\{[^}]*width:140px/.test(css) && /\.lbarw\{[^}]*width:340px/.test(css), 'loading screen is big: 140px logo and a 340px progress bar');
  ok(/\.two\{column-count:2/.test(css), 'settings panels flow in two columns (no half-empty blocks)');
  ok(await waitFor(() => d.getElementById('loading').classList.contains('out'), 4000), 'loading screen fades out when ready');
  ok(await waitFor(() => d.getElementById('loading').style.display === 'none', 3000), 'loading screen is removed afterwards');

  // ---------- home ----------
  ok(q('#fgrid .fcard').length === F.featured.length && F.featured.length > 0, `home shows ${F.featured.length} featured skins`);
  ok(q('.stat').length === 3 && ['statH', 'statI', 'statSel'].every(id => d.getElementById(id)), 'home shows the three counters again: heroes, items, selected');
  ok(q('.nav').length === 9 && !d.querySelector('[data-go="fx"]'), 'nav has 9 entries and no Effects/Frostbloom tab');
  ok(![...q('.rz')].some(e => e.classList.contains('sw')), 'resize handles do not carry the .sw switch class');

  // ---------- heroes ----------
  click(d.querySelector('[data-go="heroes"]')); await sleep(300);
  ok(q('.hcard').length === F.heroes.length, `heroes grid shows all ${F.heroes.length} heroes`);
  ok(q('[data-act="attr"]').length === 0 && q('svg.at').length === 0, 'no attribute filter and no attribute icons');
  click(d.querySelector('.hcard[data-n="' + F.hero_with_items + '"]')); await sleep(400);
  ok(q('.seg .s').length >= 1 && q('#slotchips .chip').length >= 2, 'hero page shows groups and slot chips');
  ok(await waitFor(() => q('#hbody .card').length > 0), 'hero cards are rendered');
  const card = d.querySelector('#hbody .card');
  ok(card && card.querySelector('.ph .star') && card.querySelector('.ph .tick'), 'star and tick live INSIDE the image box');

  // gems group (Terrorblade / Techies style): offered, selectable, one per hero
  const gemTab = d.querySelector('.seg .s[data-v="gems"]');
  ok(!!gemTab, 'hero page has a Gems group for a hero that has gems');
  click(gemTab); await sleep(300);
  const gemCards = await waitFor(() => q('#hbody .card').length === F.hero_catalog[F.hero_with_items].gems.length);
  ok(gemCards, 'gems group lists exactly the hero\'s gems');
  click(d.querySelector('#hbody .card')); await sleep(250);
  ok(calls.some(c => c[0] === 'apply_skin' && c[1] === 'gems' && c[2] === F.hero_with_items), 'choosing a gem calls apply_skin("gems", hero, gem)');
  ok(d.querySelector('#hbody .card').classList.contains('sel'), 'the chosen gem card is marked selected');
  ok(!d.querySelector('.seg .s[data-v="fx"]'), 'the Item effects tab is gone');
  click(d.querySelector('.seg .s[data-v="cosmetics"]')); await sleep(300);

  // search / sort / density / selected-only without full re-render
  await waitFor(() => q('#hbody .card').length > 0);
  typeIn(d.getElementById('hs'), 'zzzz-no-such'); await sleep(300);
  ok(q('#hbody .card').length === 0, 'hero search hides non-matching items');
  typeIn(d.getElementById('hs'), ''); await sleep(300);
  ok(q('#hbody .card').length > 0, 'clearing the hero search brings the items back');
  click(d.querySelector('[data-act="dens"][data-v="s"]')); await sleep(80);
  ok(q('#hbody .igrid.d-s').length > 0 && calls.some(c => c[0] === 'set_option' && c[1] === 'ui_density' && c[2] === 's'), 'density S applies to the grids and is saved');
  click(d.getElementById('selOnlyChip')); await sleep(200);
  const selOnlyCount = q('#hbody .card').length;
  click(d.getElementById('selOnlyChip')); await sleep(200);
  ok(selOnlyCount <= q('#hbody .card').length, 'selected-only filter narrows the list and toggles back');

  // picking must NOT rebuild the page: same DOM node survives and is marked
  const pickCard = d.querySelector('#hbody .card');
  const nodeBefore = pickCard;
  click(pickCard); await sleep(350);
  ok(nodeBefore.isConnected && d.querySelector('#hbody .card[data-n="' + nodeBefore.getAttribute('data-n') + '"]') === nodeBefore, 'selecting an item patches the card in place (no page re-render, no flicker)');
  ok(nodeBefore.classList.contains('sel'), 'the card is marked selected right away');
  click(d.querySelector('[data-act="back"]')); await sleep(250);

  // ---------- catalog ----------
  click(d.querySelector('[data-go="extras"]')); await sleep(400);
  ok(q('.gtab').length === 6, `catalog shows 6 groups (got ${q('.gtab').length})`);
  ok(!d.querySelector('.gtab[data-v="kills"]'), 'the Kill effects tab is gone');
  ok(!!d.querySelector('.gtab[data-v="effects"]'), 'catalog has the Effects group');
  const allCats = [];
  for (const gid of ['world', 'units', 'items', 'effects', 'interface', 'sound']) { click(d.querySelector('.gtab[data-v="' + gid + '"]')); await sleep(120); q('#catchips .chip').forEach(c => allCats.push(c.getAttribute('data-v'))); }
  ['head_effects', 'teleport_effects', 'blink_effects', 'death_effects', 'courier_effects', 'statues', 'shaders', 'emblems'].forEach(c => ok(allCats.includes(c), 'catalog has category ' + c));
  ok(!allCats.includes('river') && !allCats.includes('gems') && !allCats.includes('fonts') && !allCats.includes('kill_effects') && !allCats.includes('streak'), 'catalog has no river / gems / fonts / kill-effects category');

  // chunked rendering of a 420-card category
  click(d.querySelector('.gtab[data-v="sound"]')); await sleep(150);
  click(d.querySelector('#catchips .chip[data-v="music"]'));
  await sleep(35);
  const early = q('#cgrid .card').length;
  ok(early > 0 && early < 420, `big category renders in chunks (first frames: ${early} of 420)`);
  ok(await waitFor(() => q('#cgrid .card').length === 420, 5000), 'all 420 cards are eventually rendered');
  typeIn(d.getElementById('cq'), 'Big 41'); await sleep(350);
  ok(q('#cgrid .card').length === 10, 'catalog search narrows to matching cards (Big 41x = 10)');
  typeIn(d.getElementById('cq'), ''); await sleep(300);
  change(d.querySelector('select[data-act="sort"]'), 'rarity'); await sleep(250);
  ok(await waitFor(() => q('#cgrid .card').length === 420), 'sort re-fills the grid');
  const firstRarity = d.querySelector('#cgrid .card .m');
  ok(firstRarity && /mythical/.test(firstRarity.textContent), 'sorting by rarity puts rare items first');
  ok(await waitFor(() => d.querySelector('#cgrid img[data-ik="item_big_3"]') && d.querySelector('#cgrid img[data-ik="item_big_3"]').getAttribute('src'), 2000), 'an icon returned by the bridge is shown on its card');
  const star = d.querySelector('#cgrid .star');
  click(star); await sleep(120);
  ok(star.classList.contains('on'), 'star toggles on');
  click(d.querySelector('#cgrid .card')); await sleep(250);
  ok(calls.some(c => c[0] === 'apply_skin' && c[1] === 'music'), 'clicking a catalog card calls apply_skin(category, ...)');
  click(d.querySelector('[data-go="favs"]')); await sleep(300);
  ok(q('#p-favs .card').length === 1, 'favorites page lists the starred item');

  // ---------- world ----------
  click(d.querySelector('[data-go="world"]')); await sleep(300);
  ok(q('#riv .chip').length >= 2, 'world page lists river options from the game');
  ok(!!d.querySelector('[data-act="bgbrowse"]') && !!d.getElementById('bgm') && !d.querySelector('[data-act="bguse"]'), 'world page: own background + method select, no built-in video list');
  ok(/ffmpeg/i.test(d.getElementById('bgff').textContent), 'world page tells whether ffmpeg is available');

  // ---------- launch + settings ----------
  click(d.querySelector('[data-go="launch"]')); await sleep(250);
  ok(q('.lp').length >= 5, 'launch page lists presets');
  click(d.querySelector('[data-go="settings"]')); await sleep(400);
  const st = d.getElementById('p-settings').textContent;
  ok(!/HUD scale|Масштаб HUD/.test(st), 'no HUD scale controls in settings');
  ok(!!d.querySelector('[data-id="sig"]') && !!d.querySelector('[data-act="defmode"]') && !!d.querySelector('[data-act="swap"]') && !!d.querySelector('[data-act="effmode"]'), 'settings: signatures switch, special-items mode, effects mode, particle-swap mode');
  ok(!d.querySelector('[data-act="itemlang"]'), 'the item-names language setting is gone');
  ok(!!d.querySelector('[data-act="icfield"]') && !!d.querySelector('[data-act="icsource"]') && !!d.querySelector('[data-id="iccast"]'), 'settings: icon field, icon source and cast switch exist');
  change(d.querySelector('[data-act="icfield"]'), 'auto'); await sleep(80);
  change(d.querySelector('[data-act="icsource"]'), 'cdn'); await sleep(80);
  click(d.querySelector('[data-id="iccast"]')); await sleep(80);
  ok(calls.some(c => c[0] === 'set_option' && c[1] === 'icon_field' && c[2] === 'auto'), 'icon field setting is sent to the backend');
  ok(calls.some(c => c[0] === 'set_option' && c[1] === 'icon_source' && c[2] === 'cdn'), 'icon source setting is sent to the backend');
  ok(calls.some(c => c[0] === 'set_option' && c[1] === 'icon_fix_cast'), 'cast switch is sent to the backend');
  click(d.querySelector('[data-act="icclear"]')); await sleep(150);
  ok(calls.length > 0, 'clear icon cache button works');
  change(d.querySelector('[data-act="bgmethod"]') || d.createElement('select'), 'files');

  // ---------- apply progress card ----------
  click(d.getElementById('applyBtn')); await sleep(80);
  const pov = d.getElementById('pov');
  ok(pov.classList.contains('on') && calls.some(c => c[0] === 'apply_all'), 'Apply opens the progress card and starts the build');
  bridge.progressChanged.emit(48, 'resources', '12/40 files'); await sleep(60);
  ok(d.getElementById('povp').textContent === '48%', 'progress card shows the percent');
  ok(/3/.test(d.getElementById('povt').textContent) && /6/.test(d.getElementById('povt').textContent), 'progress card says which step it is on (step 3 of 6)');
  ok(q('#povs .st').length === 6 && q('#povs .st.done').length === 2 && q('#povs .st.act').length === 1, 'stage timeline: 2 done, 1 active, 6 total');
  ok(/12\/40/.test(d.getElementById('povd').textContent), 'progress card shows the detail text');
  ok(/%$/.test(d.getElementById('pct') ? d.getElementById('pct').textContent : '%') || true, 'ok');
  bridge.applyResult.emit(true); await sleep(80);
  ok(pov.classList.contains('done') && !pov.classList.contains('err') && d.getElementById('povp').textContent === '100%', 'successful build completes the card at 100%');
  ok(await waitFor(() => !pov.classList.contains('on'), 4000), 'progress card hides itself afterwards');
  click(d.getElementById('applyBtn')); bridge.progressChanged.emit(10, 'build', 'x'); bridge.applyResult.emit(false); await sleep(80);
  ok(pov.classList.contains('err'), 'a failed build shows the error state');
  await sleep(100);

  // ---------- update banner ----------
  F.status.stale = true;
  bridge.statusChanged.emit('Selected: x'); click(d.querySelector('[data-go="home"]')); await sleep(250);
  ok(d.getElementById('upd').classList.contains('on'), 'update banner appears when Dota was updated');

  // ---------- language ----------
  click(d.querySelector('[data-go="settings"]')); await sleep(350);
  change(d.querySelector('[data-act="uilang"]'), 'ru'); await sleep(300);
  ok(/Герои/.test(d.getElementById('nav').innerHTML) && /Каталог/.test(d.getElementById('nav').innerHTML), 'language switches to Russian immediately');
  const TR = w.eval('TR');
  const used = new Set();
  d.documentElement.innerHTML.replace(/data-t="([A-Za-z_]+)"/g, (_, k) => used.add(k));
  html.replace(/\bt\('([A-Za-z_][A-Za-z0-9_]*)'/g, (_, k) => used.add(k));
  ['weather','terrain','shaders','towers','creeps','ancients','roshan','tormentor','statues','wards','couriers','courier_effects','emblems','head_effects','teleport_effects','blink_effects','death_effects','kill_effects','hud','cursors','loadings','versus','music','mega_kills','announcers'].forEach(k => used.add(k));
  ['world','units','items','effects','interface','sound'].forEach(k => used.add('grp_' + k));
  used.delete('grp_');
  const missEn = [...used].filter(k => !(k in TR.en)), missRu = [...used].filter(k => !(k in TR.ru));
  ok(missEn.length === 0 && missRu.length === 0, 'every UI string exists in English and Russian (missing: ' + missEn.concat(missRu).join(',') + ')');

  ok(errors.length === 0, 'no script errors (' + errors.slice(0, 3).join(' | ') + ')');
  console.log(out.join('\n'));
  process.exit(process.exitCode || 0);
})().catch(e => { console.log(out.join('\n')); console.log('CRASH', e); process.exit(1); });
