# Contributing

Thanks for helping! The project is small on purpose: a Qt window + one HTML file, a pure-Python core that is testable
without Dota 2 and without Qt.

## Setup
```bash
pip install -r requirements.txt
cd tests/ui && npm install && cd ../..          # only for the UI test
python -W ignore -m unittest discover -s tests -v
```

## Ground rules
1. **Every fix needs a test.** The tests build a *synthetic* Dota install (`tests/test_pipeline.py::build_fake_dota`);
   add the item / file shape that exposed your bug and assert on the generated `pak01_dir.vpk`.
2. **Don't guess game data.** If a category or slot name is unknown, make it visible (build report,
   `diagnose --categories`) instead of inventing a path.
3. **Keep the core Qt-free.** Only `qt.py`, `icons.py`, `bridge.py`, `window.py` import PySide6.
4. **UI changes** go in `chameleon/ui/index.html` (single file). Run `tests/test_ui.py`; it loads the real page in jsdom.
5. One icon family: 24px grid, 1.75 stroke, round caps. No filled/mixed styles.

## Adding a catalog category
Add a rule in `database.py::CATEGORY_RULES` (and the id to `CATEGORY_GROUPS`), a translation in `index.html`
(`TR.en` / `TR.ru`, key = category id), and a test in `CategoryTest`.
