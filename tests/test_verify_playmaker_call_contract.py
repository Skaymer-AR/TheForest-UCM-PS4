"""Synthetic-only tests for the exact-title native call-contract gate."""
import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from verify_playmaker_call_contract import (
    DIRECT_TARGETS, METHODS, SITES, inspect, verify_sites,
)


class PlayMakerCallContractTests(unittest.TestCase):
    def test_all_synthetic_instructions_match(self):
        data = {site: bytes.fromhex(pattern) for site, pattern in SITES.values()}
        self.assertEqual(len(verify_sites(lambda va, size: data[va][:size])),
                         len(SITES))

    def test_modification_fails_closed(self):
        data = {site: bytes.fromhex(pattern) for site, pattern in SITES.values()}
        site = SITES["virtual_methodinfo"][0]
        data[site] = bytes(len(data[site]))
        with self.assertRaisesRegex(ValueError, "virtual_methodinfo"):
            verify_sites(lambda va, size: data[va][:size])

    def test_no_fake_direct_call_target_accepted(self):
        data = {site: bytes.fromhex(pattern) for site, pattern in SITES.values()}
        with self.assertRaisesRegex(ValueError, "call target mismatch"):
            verify_sites(lambda va, size: data[va][:size], SITES,
                         {**DIRECT_TARGETS, "gui_button_call": 0})

    def test_compiled_abi_sites_are_pinned(self):
        self.assertEqual(SITES["virtual_call"][0], 0x0114139E)
        self.assertEqual(SITES["virtual_methodinfo"][0], 0x01141397)
        self.assertEqual(DIRECT_TARGETS["gui_button_call"], 0x019BE750)
        self.assertEqual(DIRECT_TARGETS["rewired_getbuttondown_call"], 0x00A25720)

    def test_rewired_and_gui_signatures_are_not_conflated(self):
        gui = next(m for m in METHODS if m[1:3] == ("UnityEngine.GUI", "Button"))
        rewired = next(m for m in METHODS if m[1:3] == ("Rewired.Player", "GetButtonDown"))
        self.assertEqual(gui[5], 3)
        self.assertEqual(rewired[5], 1)

    def test_invalid_elf_rejected_before_parser(self):
        with self.assertRaisesRegex(ValueError, "wrong IL2CPP ELF"):
            inspect(b"bogus", b"bogus metadata")


if __name__ == "__main__":
    unittest.main()
