import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_ps4_il2cpp_candidates as analysis


def make_synthetic_elf(path: Path) -> None:
    """Tiny public-domain-shaped ELF fixture with one load segment."""
    image = bytearray(0x500)
    image[:16] = b"\x7fELF" + bytes([2, 1, 1]) + bytes(9)
    struct.pack_into(
        "<HHIQQQIHHHHHH", image, 16,
        3, 62, 1, 0, 64, 0, 0, 64, 56, 1, 64, 0, 0,
    )
    struct.pack_into("<IIQQQQQQ", image, 64,
                     1, 5, 0x100, 0x1000, 0, 0x300, 0x300, 0x1000)
    image[0x130] = 0xA5
    path.write_bytes(image)


class RecoveredPs4EvidenceTests(unittest.TestCase):
    def test_evidence_has_42_rows_and_two_byte_confirmations(self):
        candidates = analysis.parse_evidence(analysis.DEFAULT_EVIDENCE)
        self.assertEqual(len(candidates), 42)
        by_name = {candidate.name: candidate for candidate in candidates}
        self.assertEqual(by_name["TheForest.DebugConsole.OnGUI"].rva, 0x005C37B0)
        self.assertEqual(by_name["TheForest.DebugConsole.ToggleConsole"].rva, 0x005CB6D0)
        self.assertEqual(len(by_name["TheForest.DebugConsole.OnGUI"].confirmed_bytes), 16)
        self.assertEqual(len(by_name["TheForest.DebugConsole.ToggleConsole"].confirmed_bytes), 16)
        self.assertIn("offline PRX prefix match reported",
                      by_name["PS4Controller.Update"].status)
        self.assertIsNone(by_name["PS4Controller.Update"].confirmed_bytes)
        self.assertIsNone(by_name["TheForest.UI.VirtualCursor.LateUpdate"].confirmed_bytes)
        self.assertIsNone(by_name["TheForest.Tools.DllModLoader.Awake"].confirmed_bytes)
        self.assertIsNone(by_name["TheForest.Modding.UI.ModList.OnEnable"].confirmed_bytes)

    def test_toggle_console_branch_target_from_confirmed_bytes(self):
        candidates = analysis.parse_evidence(analysis.DEFAULT_EVIDENCE)
        toggle = next(c for c in candidates
                      if c.name == "TheForest.DebugConsole.ToggleConsole")
        self.assertEqual(
            analysis.toggle_console_tailcall_target(toggle.confirmed_bytes, toggle.rva),
            0x005CA800,
        )

    def test_two_confirmed_byte_anchors_are_required_and_checked(self):
        candidates = analysis.parse_evidence(analysis.DEFAULT_EVIDENCE)

        class AnchorImage:
            def __init__(self, wrong_name=None):
                self.wrong_name = wrong_name

            def read_rva(self, rva, length):
                candidate = next(c for c in candidates if c.rva == rva)
                if candidate.name == self.wrong_name:
                    return bytes([0xCC]) * length
                return candidate.confirmed_bytes[:length]

        self.assertEqual(len(analysis.verify_confirmed_anchors(
            candidates, AnchorImage())), 2)
        with self.assertRaisesRegex(ValueError, "does not match"):
            analysis.verify_confirmed_anchors(
                candidates, AnchorImage("TheForest.DebugConsole.OnGUI"))

    def test_local_imgui_detour_preflight_is_scoped_and_fails_closed_for_installation(self):
        candidates = analysis.parse_evidence(analysis.DEFAULT_EVIDENCE)
        ongui = next(c for c in candidates
                     if c.name == "TheForest.DebugConsole.OnGUI")
        preflight = analysis.assess_local_imgui_detour(ongui)
        self.assertTrue(preflight["anchor_match"])
        self.assertTrue(preflight["method_scope_only"])
        self.assertEqual(preflight["rel32_transfer_bytes"], 5)
        self.assertEqual(preflight["rel32_stolen_bytes"], 6)
        self.assertEqual(preflight["rel32_stolen_prefix"],
                         bytes.fromhex("55 48 89 E5 41 57"))
        self.assertEqual(preflight["recovery_original_bytes"],
                         preflight["rel32_stolen_prefix"])
        self.assertEqual(preflight["target_rva"], 0x005C37B0)
        self.assertEqual(preflight["resume_rva"], 0x005C37B6)
        self.assertTrue(preflight["rel32_near_relay_required"])
        self.assertFalse(preflight["absolute_stolen_window_verified"])
        self.assertIn("unverified", preflight["runtime_callback_active"])
        self.assertEqual(len(preflight["blockers"]), 4)
        self.assertFalse(preflight["patch_write_performed"])
        self.assertIn("require platform quiescence", preflight["release_policy"])
        self.assertIn("otherwise retain executable resources",
                      preflight["release_policy"])
        self.assertFalse(preflight["install_go"])

        report = analysis.render_report(candidates)
        self.assertIn("Localized IMGUI callback preflight", report)
        self.assertIn("preserve the PKG", report)
        self.assertIn("runtime invocation is **unverified**", report)
        self.assertIn("retain original bytes `55 48 89 E5 41 57`", report)
        self.assertIn("resume at RVA `0x005C37B6`", report)
        self.assertIn("Installation verdict: **NO-GO**", report)

    def test_local_imgui_detour_preflight_rejects_a_changed_anchor(self):
        bad = analysis.Candidate(
            "TheForest.DebugConsole.OnGUI", 0x005C37B0,
            "tampered evidence", bytes.fromhex("CC 48 89 E5 41 57 41 56"))
        preflight = analysis.assess_local_imgui_detour(bad)
        self.assertFalse(preflight["anchor_match"])
        self.assertFalse(preflight["install_go"])

    def test_elf64_rva_maps_through_link_image_base_not_runtime_base(self):
        with tempfile.TemporaryDirectory() as temp:
            binary = Path(temp) / "synthetic.prx.elf"
            make_synthetic_elf(binary)
            image = analysis.Elf64Image(binary)
            self.assertEqual(image.image_base, 0x1000)
            self.assertEqual(image.file_offset(0x30), 0x130)
            self.assertEqual(image.read_rva(0x30, 1), b"\xA5")

    def test_objdump_parser_reads_direct_call_and_jump_edges(self):
        lines = """\
  5cb6d0: 31 f6                   xor    esi,esi
  5cb6da: e9 21 f1 ff ff          jmp    5ca800 <target>
  5ca7f0: e8 0b 00 00 00          call   5ca800 <target>
  5ca7f5: ff d0                   call   rax
"""
        instructions = analysis.parse_disassembly(lines)
        branches = [(ins.address, analysis.direct_branch_target(ins))
                    for ins in instructions
                    if ins.mnemonic in {"call", "callq", "jmp", "jmpq"}]
        self.assertEqual(branches, [(0x5CB6DA, 0x5CA800), (0x5CA7F0, 0x5CA800),
                                    (0x5CA7F5, None)])

    def test_direct_branch_parser_handles_objdump_prefixed_target(self):
        instruction = analysis.Instruction(0x1000, "jmp", "0x0000000000000800 <target>")
        self.assertEqual(analysis.direct_branch_target(instruction), 0x800)

    def test_bad_machine_or_rva_outside_load_segment_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            binary = Path(temp) / "synthetic.elf"
            make_synthetic_elf(binary)
            image = analysis.Elf64Image(binary)
            self.assertIsNone(image.file_offset(0x8000))
            data = bytearray(binary.read_bytes())
            struct.pack_into("<H", data, 18, 183)  # AArch64, not PS4 x86-64.
            binary.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "x86-64"):
                analysis.Elf64Image(binary)


if __name__ == "__main__":
    unittest.main()
