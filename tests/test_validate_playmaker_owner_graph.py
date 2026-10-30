"""Synthetic data only. Never commits proprietary IL2CPP modules."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from validate_playmaker_owner_graph import SITES, verify_sites, inspect


class PlayMakerOwnershipTests(unittest.TestCase):
    def test_all_exact_native_sites(self):
        data = {va: bytes.fromhex(hexbytes) for va,hexbytes in SITES.values()}
        self.assertEqual(len(verify_sites(lambda va,n: data[va][:n])), 19)

    def test_distinguishes_enabled_active_and_raw_actions_setter(self):
        self.assertEqual(SITES['action_enabled_filter'][1], '807b1800')
        self.assertEqual(SITES['action_enabled_property_read'][1], '8a4718c3')
        self.assertEqual(SITES['action_active_check'][1], '807f1a00')
        self.assertEqual(SITES['action_active_property_read'][1], '8a471ac3')
        self.assertEqual(SITES['set_actions_raw_pointer'][1], '48897760c3')

    def test_bad_instruction_fails_closed(self):
        data = {va: bytes.fromhex(hexbytes) for va,hexbytes in SITES.values()}
        first = next(iter(data))
        data[first] = bytes(len(data[first]))
        with self.assertRaisesRegex(ValueError, 'native instruction mismatch'):
            verify_sites(lambda va,n: data[va][:n])

    def test_bad_elf_rejected_before_any_metadata_access(self):
        with self.assertRaisesRegex(ValueError, 'ELF identity'):
            inspect(b'invalid ELF', b'invalid metadata')

    def test_bad_metadata_rejected_before_parsing(self):
        import hashlib
        import validate_playmaker_owner_graph as gate
        old = gate.ELF_SHA
        try:
            gate.ELF_SHA = hashlib.sha256(b'fake ELF').hexdigest()
            with self.assertRaisesRegex(ValueError, 'metadata identity'):
                gate.inspect(b'fake ELF', b'invalid metadata')
        finally:
            gate.ELF_SHA = old


if __name__ == '__main__':
    unittest.main()
