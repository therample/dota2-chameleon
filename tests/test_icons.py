import sys, struct, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from chameleon.iconsrc import IconSource, candidates_from_inventory_path, hero_candidates, _clean
from chameleon.vtex import encode_png
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_vtex import build


class FakeReader:
    def __init__(self, files): self.files = files
    def extract_to_bytes(self, p): return self.files[p]


class IconLookupTest(unittest.TestCase):
    def test_inventory_path_without_extension_finds_png_vtex(self):
        # exactly the case the old code missed
        self.assertIn("panorama/images/econ/items/ursa/claws/claws_png.vtex_c",
                      candidates_from_inventory_path("econ/items/ursa/claws/claws"))

    def test_clean_variants(self):
        for raw in ("econ/items/a/b", "s2r://panorama/images/econ/items/a/b_png.png", "panorama/images/econ/items/a/b.vtex_c",
                    "images/econ/items/a/b.png"):
            self.assertEqual(_clean(raw), "econ/items/a/b", raw)

    def test_item_icon_decoded_from_vpk(self):
        tex = build(4, 2, 2, bytes([200, 100, 50, 255]) * 4)
        src = IconSource([FakeReader({"panorama/images/econ/items/ursa/claws/claws_png.vtex_c": tex})])
        png = src.item_icon("econ/items/ursa/claws/claws")
        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_same_folder_and_name_in_another_root_is_found(self):
        tex = build(4, 1, 1, bytes([1, 2, 3, 255]))
        src = IconSource([FakeReader({"panorama/images/econ/items_v2/claws/claws_png.vtex_c": tex})])
        self.assertIsNotNone(src.item_icon("econ/items/ursa/claws/claws"))

    def test_generic_file_names_never_match_an_unrelated_texture(self):
        # a bare name like "icon" used to resolve many different items to ONE wrong (e.g. gold) image
        tex = build(4, 1, 1, bytes([230, 200, 20, 255]))
        src = IconSource([FakeReader({"panorama/images/misc/generic/icon_png.vtex_c": tex})])
        self.assertIsNone(src.item_icon("econ/items/ursa/claws/icon"))
        self.assertIsNone(src.item_icon("econ/items/axe/blade/icon"))

    def test_hero_icon(self):
        tex = build(4, 1, 1, bytes([9, 9, 9, 255]))
        src = IconSource([FakeReader({"panorama/images/heroes/antimage_png.vtex_c": tex})])
        self.assertIsNotNone(src.hero_icon("antimage"))
        self.assertEqual(hero_candidates("axe"), ["panorama/images/heroes/axe_png.vtex_c", "panorama/images/heroes/selection/npc_dota_hero_axe_png.vtex_c"])

    def test_missing_returns_none(self):
        self.assertIsNone(IconSource([FakeReader({})]).item_icon("econ/nothing/here"))


if __name__ == "__main__":
    unittest.main()
