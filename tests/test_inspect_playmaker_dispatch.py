"""Synthetic disassembly only; no proprietary ELF bytes."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from inspect_playmaker_dispatch import parse_calls, inspect

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

    def test_wrong_elf_rejected_before_disassembler(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "wrong.elf"
            path.write_bytes(b"not a valid native module")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                inspect(path)


if __name__ == "__main__":
    unittest.main()
