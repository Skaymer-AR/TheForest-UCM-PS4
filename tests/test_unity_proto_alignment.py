import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UnityPrototypeAlignmentTests(unittest.TestCase):
    def test_mirrored_menu_ids_match_existing_c_core_in_order(self):
        c = (ROOT / "src/overlay.c").read_text()
        cs = (ROOT / "prototype/Unity56/Assets/UCM/UcmMenuModel.cs").read_text()
        ids_c = re.findall(r'\(MenuItem\)\{"([^"]+)"', c)
        ids_cs = re.findall(r'new UcmItem\("([^"]+)"', cs)
        self.assertEqual(len(ids_c), 13)
        self.assertEqual(ids_cs, ids_c)

    def test_build_does_not_modify_game_or_use_rewired_ids(self):
        cs = (ROOT / "prototype/Unity56/Assets/UCM/UltimateMenuHost.cs").read_text()
        self.assertIn("RuntimeInitializeOnLoadMethod", cs)
        self.assertIn("OnGUI()", cs)
        self.assertIn("DontDestroyOnLoad", cs)
        self.assertNotIn("scePad", cs)
        self.assertNotIn("GetButton(", cs)
        self.assertNotIn("GoldHEN", cs)


if __name__ == "__main__":
    unittest.main()
