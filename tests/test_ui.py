"""
Loads the REAL interface (chameleon/ui/index.html) in jsdom against a fake bridge fed by data from the REAL Python bridge,
and checks what the user sees: hero grid, attribute filter, hero page, catalog groups/cards, favorites, launch presets,
settings, language switch and that no script error occurs. Skipped without node + jsdom + PySide6.
Setup: cd tests/ui && npm install jsdom   (or set NODE_PATH to a folder containing jsdom)
"""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE))
_TMP = tempfile.mkdtemp(prefix="cham_ui_")
os.environ["CHAMELEON_HOME"] = str(Path(_TMP) / "home")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

NODE = shutil.which("node")
env = dict(os.environ)
local = HERE / "ui" / "node_modules"
if local.exists():
    env["NODE_PATH"] = str(local) + os.pathsep + env.get("NODE_PATH", "")
HAVE_JSDOM = bool(NODE) and subprocess.run([NODE, "-e", "require('jsdom')"], env=env, capture_output=True).returncode == 0
try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except Exception:
    HAVE_QT = False


@unittest.skipUnless(HAVE_JSDOM and HAVE_QT, "needs node + jsdom + PySide6")
class RealUiTest(unittest.TestCase):
    def test_ui_against_real_bridge_data(self):
        import test_pipeline as tp
        from chameleon.database import SkinDatabase
        from chameleon.applier import SkinApplier
        from chameleon.bridge import ChameleonBridge
        app = QApplication.instance() or QApplication([])
        game = tp.build_fake_dota(Path(_TMP) / "g")
        db = SkinDatabase(game)
        self.assertTrue(db.initialize())
        ap = SkinApplier(game, db, {"pack_resources": True})
        br = ChameleonBridge()
        br.set_database(db); br.set_applier(ap)
        J = json.loads
        heroes = J(br.get_heroes())
        fx = {
            "config": J(br.get_config()) if hasattr(br, "get_config") else {},
            "status": {"status": "ready", "vpk": False, "items": len(db.items)},
            "heroes": heroes, "active": J(br.get_active_overrides()), "counts": J(br.get_applied_counts()),
            "favorite_names": [], "catalog": J(br.get_catalog()),
            "hero_catalog": {h["name"]: J(br.get_hero_catalog(h["name"])) for h in heroes},
            "category_items": {c["id"]: J(br.get_category_items(c["id"])) for g in J(br.get_catalog()) for c in g["cats"] if c["id"] != "fonts"},
            "launch": J(br.get_launch_presets()), "bgstate": J(br.get_background_state()), "fonts": J(br.get_fonts()), "featured": J(br.get_featured()), "effect_lib": J(br.get_effect_library()),
            "hero_with_items": tp.HERO,
        }
        fx["all_items"] = {i["name"]: i for lst in fx["category_items"].values() for i in lst}
        for hc in fx["hero_catalog"].values():
            for g in hc["slots"]:
                for i in g["items"]:
                    fx["all_items"][i["name"]] = i
        fx["config"].setdefault("language", "en")
        fix = Path(_TMP) / "fixture.json"
        fix.write_text(json.dumps(fx), encoding="utf-8")
        r = subprocess.run([NODE, str(HERE / "ui" / "ui_test.js"), str(HERE.parent / "chameleon" / "ui" / "index.html"), str(fix)],
                           env=env, capture_output=True, text=True, timeout=120)
        print(r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("FAIL", r.stdout)


if __name__ == "__main__":
    unittest.main()
