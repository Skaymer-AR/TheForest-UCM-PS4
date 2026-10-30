"""Synthetic data only. Never commits proprietary IL2CPP modules."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from validate_playmaker_owner_graph import SITES, verify_sites, inspect


class PlayMakerOwnershipTests(unittest.TestCase):
    def test_all_exact_native_sites(self):
        data = {va: bytes.fromhex(hexbytes) for va,hexbytes in SITES.values()}
        self.assertEqual(len(verify_sites(lambda va,n: data[va][:n])), 12)

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
