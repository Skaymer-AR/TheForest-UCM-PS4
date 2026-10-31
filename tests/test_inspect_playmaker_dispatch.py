"""Synthetic disassembly only; no proprietary ELF bytes."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from inspect_playmaker_dispatch import parse_calls, inspect, action_slots_from_metadata, ACTION_SLOTS

EXAMPLE = """
 113fd5d: e8 8e c6 87 00 callq 0x19bc3f0 <UnityGUI>
 1140142: e8 d9 11 00 00 callq 0x1141320 <PlayMaker>
 114139e: ff 90 20 03 00 00 callq *0x320(%rax)
 11413a8: 48 ff c3 incq %rbx
"""


class PlayMakerDispatchTests(unittest.TestCase):
    def test_direct_and_indirect_are_distinct(self):
        direct, indirect = parse_calls(EXAMPLE)
        self.assertEqual(direct, [(0x113fd5d, 0x19bc3f0), (0x1140142, 0x1141320)])
        self.assertEqual(indirect, [(0x114139e, "0x320(%rax)")])

    def test_empty_or_non_call_text(self):
        self.assertEqual(parse_calls("  1234: nop\n"), ([], []))

    def test_virtual_slot_metadata_alignment(self):
        import struct
        count = max(entry[0] for entry in ACTION_SLOTS.values()) + 1
        off = 512
        fake = bytearray(off + 56 * count)
        struct.pack_into("<II", fake, 0, 0xFAB11BAF, 23)
        for i in range(32):
            struct.pack_into("<II", fake, 8 + 8*i, off, 0)
        struct.pack_into("<II", fake, 8 + 8*5, off, 56*count)
        for _, (idx, slot, _, _) in ACTION_SLOTS.items():
            struct.pack_into("<H", fake, off + 56*idx + 52, slot)
        self.assertEqual(action_slots_from_metadata(fake), {
            "OnEnter": 30, "OnUpdate": 32, "OnGUI": 33
        })
        struct.pack_into("<H", fake, off + 56*34075 + 52, 0)
        with self.assertRaisesRegex(ValueError, "unexpected virtual slot"):
            action_slots_from_metadata(fake)

    def test_wrong_inputs_rejected_before_disassembler(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "wrong.elf"
            path.write_bytes(b"not a valid native module")
            with self.assertRaisesRegex(ValueError, "metadata SHA-256"):
                inspect(path, path)


if __name__ == "__main__":
    unittest.main()
