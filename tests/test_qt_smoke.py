"""Headless Qt smoke test: bridge slots + threaded icon pipeline. Skipped when PySide6 is not installed."""
import json, os, sys, tempfile, time, unittest
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cham_qt_")
os.environ["CHAMELEON_HOME"] = str(Path(_TMP) / "home")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
    HAVE_QT = True
except Exception:                                  # pragma: no cover
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class QtSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from chameleon.vpk_io import VPKBuilder
        import test_pipeline as tp
        from test_vtex import build as vtex
        cls.app = QApplication.instance() or QApplication([])
        game = tp.build_fake_dota(Path(_TMP) / "qt")
        # add an icon for cool_head + a hero icon to the game pak
        gd = game / "game" / "dota"
        b = VPKBuilder()
        for p, d in tp.GAME_FILES.items():
            b.add_data(d, p)
        b.add_data(vtex(4, 2, 2, bytes([120, 60, 30, 255]) * 4), "panorama/images/econ/items/sparrow/cool/cool_icon_png.vtex_c")
        b.add_data(vtex(4, 2, 2, bytes([30, 60, 120, 255]) * 4), "panorama/images/heroes/sparrow_png.vtex_c")
        b.build_standalone(gd / "pak01_dir.vpk")
        from chameleon.database import SkinDatabase
        from chameleon.applier import SkinApplier
        from chameleon.bridge import ChameleonBridge
        from chameleon.icons import IconManager
        cls.tp = tp
        cls.db = SkinDatabase(game)
        assert cls.db.initialize()
        cls.ap = SkinApplier(game, cls.db, {"pack_resources": True})
        cls.bridge = ChameleonBridge()
        IconManager._hub()
        cls.bridge._connect_icons()
        cls.bridge.set_database(cls.db)
        cls.bridge.set_applier(cls.ap)
        cls.IconManager = IconManager

    @classmethod
    def tearDownClass(cls):
        cls.IconManager.stop_worker()

    def _wait(self, cond, ms=4000):
        loop = QEventLoop()
        t0 = time.time()
        timer = QTimer()
        timer.setInterval(20)

        def poll():
            if cond() or (time.time() - t0) * 1000 > ms:
                loop.quit()
        timer.timeout.connect(poll)
        timer.start()
        loop.exec()
        timer.stop()
        return cond()

    def setUp(self):
        self.bridge.clear_all_overrides()

    def test_catalog_and_counts_through_bridge(self):
        H = self.tp.HERO
        cat = json.loads(self.bridge.get_hero_catalog(H))
        self.assertEqual([s["slot"] for s in cat["slots"]], ["head", "misc", "head_accessory", "weapon_alt"])
        self.assertEqual(len(cat["arcanas"]), 1)
        self.bridge.apply_skin("heroes", H, "cool_head", "")
        self.bridge.apply_skin("heroes", H, "alt_weapon", "")
        self.bridge.apply_skin("taunts", H, "funny_taunt", "")
        counts = json.loads(self.bridge.get_applied_counts())
        self.assertEqual(counts["heroes"][H], 3)
        self.assertEqual(counts["slots"][f"{H}::head"], 1)
        self.assertEqual(counts["slots"][f"{H}::weapon_alt"], 1)
        self.bridge.clear_all_overrides()
        self.assertEqual(json.loads(self.bridge.get_applied_counts())["heroes"], {})

    def test_item_icon_arrives_asynchronously_from_vpk(self):
        got = {}
        self.bridge.iconReady.connect(lambda k, b: got.__setitem__(k, b))
        self.IconManager.set_vpk_readers(self.db.vpk_readers)
        first = self.bridge.get_item_icon("cool_head@@@", "econ/items/sparrow/cool/cool_icon", 64)
        self.assertEqual(first, "")                                     # not cached yet -> async
        self.assertTrue(self._wait(lambda: "item_cool_head" in got), "icon never arrived")
        self.assertGreater(len(got["item_cool_head"]), 50)
        again = self.bridge.get_item_icon("cool_head@@@", "econ/items/sparrow/cool/cool_icon", 64)
        self.assertTrue(again)                                          # served from cache now

    def test_hero_icon_from_vpk(self):
        got = {}
        self.bridge.iconReady.connect(lambda k, b: got.__setitem__(k, b))
        self.IconManager.set_vpk_readers(self.db.vpk_readers)
        self.bridge.get_hero_icon(self.tp.HERO, 64)
        self.assertTrue(self._wait(lambda: "hero_sparrow" in got), "hero icon never arrived")

    def test_catalog_favorites_launch_presets_and_progress(self):
        cat = json.loads(self.bridge.get_catalog())
        ids = {c["id"]: c["count"] for g in cat for c in g["cats"]}
        self.assertEqual(ids["towers"], 2)
        self.assertEqual(ids["weather"], 2)
        self.assertNotIn("gems", ids)                                          # gems live on the hero page, not in the catalog
        self.assertEqual([g["id"] for g in cat], ["world", "units", "items", "effects", "interface", "kills", "sound"])
        items = json.loads(self.bridge.get_category_items("towers"))
        self.assertEqual(sorted(i["name"] for i in items), ["crow_towers", "sun_towers"])
        self.assertTrue(self.bridge.toggle_favorite("crow_towers"))
        self.assertEqual([i["name"] for i in json.loads(self.bridge.get_favorites())], ["crow_towers"])
        self.assertFalse(self.bridge.toggle_favorite("crow_towers"))
        lp = json.loads(self.bridge.get_launch_presets())
        self.assertEqual(lp["selected"], "Default")
        self.bridge.save_launch_preset("Mine", "-novid -console ; rm -rf /")      # unsafe characters are stripped
        lp = json.loads(self.bridge.get_launch_presets())
        mine = [p for p in lp["presets"] if p["name"] == "Mine"][0]
        self.assertEqual(mine["params"], "-novid -console  rm -rf /".replace("  ", "  "))
        self.assertNotIn(";", mine["params"])
        self.assertEqual(self.bridge.launch_params(), mine["params"])
        self.bridge.select_launch_preset("Performance")
        self.assertEqual(self.bridge.launch_params(), "-novid -high -nojoy")
        self.bridge.delete_launch_preset("Mine")
        # staged progress arrives as a structured signal
        got = []
        self.bridge.progressChanged.connect(lambda p, s, d: got.append((p, s)))
        self.bridge.apply_skin("heroes", self.tp.HERO, "cool_head", "")
        self.bridge.apply_all()
        self.assertTrue(self._wait(lambda: any(s == "register" for _, s in got), 6000))
        pcts = [p for p, _ in got]
        self.assertEqual(pcts, sorted(pcts))                                       # monotonic
        self.assertEqual({s for _, s in got}, {"scan", "build", "resources", "extras", "write", "register"})
        self.bridge.restore_all()

    def test_build_report_available_after_apply(self):
        H = self.tp.HERO
        self.bridge.apply_skin("heroes", H, "arcana_weapon", "")
        try:
            self.assertTrue(self.ap.commit())
            rep = json.loads(self.bridge.get_build_report())
            mods = rep["overrides"][0]["modifiers"]
            # default style (0): ambient + style-0 particle; the style-1 particle is dropped; 1 entity_model, 1 replacement
            self.assertEqual(mods.get("particle_create"), 2)
            self.assertEqual(mods.get("entity_model"), 1)
            self.assertEqual(mods.get("particle"), 1)
        finally:
            self.bridge.restore_all()


if __name__ == "__main__":
    unittest.main()
