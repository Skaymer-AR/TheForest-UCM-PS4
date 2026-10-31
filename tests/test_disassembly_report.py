import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_disassembly_report as report_analysis
from analyze_ps4_il2cpp_candidates import parse_evidence


class DisassemblyReportTests(unittest.TestCase):
    def setUp(self):
        self.candidates = parse_evidence(report_analysis.DEFAULT_EVIDENCE)

    def test_parser_keeps_machine_bytes_and_method_windows(self):
        text = """\
Example — RVA 0x1000 — ventana 0x10 bytes
  1000: 55 48 89 e5                   push rbp
  1004: c3                            ret
"""
        windows = report_analysis.parse_windows(text)
        self.assertEqual(windows[0].name, "Example")
        self.assertEqual(windows[0].rva, 0x1000)
        self.assertEqual(windows[0].instructions[0].raw_bytes,
                         bytes.fromhex("55 48 89 e5"))

    def test_supplied_hardware_anchors_are_compared_when_present(self):
        ongui = "55 48 89 E5 41 57 41 56 41 55 41 54 53 48 83 E4"
        text = f"""\
DebugConsole.OnGUI — RVA 0x005C37B0 — ventana 0x10 bytes
  5c37b0: {ongui}                      push rbp
DebugConsole.ToggleConsole — RVA 0x005CB6D0 — ventana 0x10 bytes
  5cb6d0: 31 f6                         xor esi, esi
  5cb6d2: 80 7f 5a 00                   cmp byte ptr [rdi + 0x5a], 0
  5cb6d6: 40 0f 94 c6                   sete sil
  5cb6da: e9 21 f1 ff ff                jmp 0x5ca800
  5cb6df: 90                            nop
"""
        windows = report_analysis.parse_windows(text)
        status = report_analysis.verify_included_anchors(windows, self.candidates)
        self.assertEqual(len(status), 2)
        self.assertTrue(all("coincide" in value for value in status.values()))

    def test_update_directly_calls_and_tail_jumps_to_process_gamepads(self):
        text = """\
PS4Controller.Update — RVA 0x00476080 — ventana 0x180 bytes
  476080: 55                            push rbp
  476179: e8 22 00 00 00                call 0x4761a0
  47618b: e9 10 00 00 00                jmp 0x4761a0
  476194: c3                            ret
PS4Controller.ProcessGamePads — RVA 0x004761A0 — ventana 0x10 bytes
  4761a0: 55                            push rbp
  4761a1: c3                            ret
"""
        windows = report_analysis.parse_windows(text)
        edges = report_analysis.build_edges(windows, self.candidates)
        update_edges = [edge for edge in edges
                        if edge.source_name == "PS4Controller.Update"]
        self.assertEqual([(edge.mnemonic, edge.target_name) for edge in update_edges],
                         [("call", "PS4Controller.ProcessGamePads"),
                          ("jmp", "PS4Controller.ProcessGamePads")])

    def test_loader_awake_directly_calls_load_dll_mod(self):
        text = """\
TheForest.Tools.DllModLoader.Awake — RVA 0x022CEF10 — ventana 0x150 bytes
  22cef10: 55                            push rbp
  22cf01d: e8 2e 00 00 00                call 0x22cf050
  22cf041: c3                            ret
TheForest.Tools.DllModLoader.LoadDllMod — RVA 0x022CF050 — ventana 0x10 bytes
  22cf050: 55                            push rbp
  22cf051: c3                            ret
"""
        windows = report_analysis.parse_windows(text)
        edges = report_analysis.build_edges(windows, self.candidates)
        self.assertTrue(any(edge.source_name == "TheForest.Tools.DllModLoader.Awake"
                            and edge.site_rva == 0x022CF01D
                            and edge.mnemonic == "call"
                            and edge.target_name == "TheForest.Tools.DllModLoader.LoadDllMod"
                            for edge in edges))

    def test_modlist_onenable_and_refresh_are_empty_entries(self):
        text = """\
TheForest.Modding.UI.ModList.OnEnable — RVA 0x017D5390 — ventana 0x20 bytes
  17d5390: c3                            ret
  17d5391: 90                            nop
TheForest.Modding.UI.ModList.Refresh — RVA 0x017D53A0 — ventana 0x20 bytes
  17d53a0: c3                            ret
  17d53a1: 90                            nop
"""
        windows = report_analysis.parse_windows(text)
        candidate_rvas = sorted(candidate.rva for candidate in self.candidates)
        self.assertEqual([report_analysis._entry_behavior(window, candidate_rvas)
                          for window in windows],
                         ["ret inmediato; sin cuerpo de método en este build"] * 2)

    def test_mismatched_confirmed_prefix_fails_closed(self):
        text = """\
DebugConsole.OnGUI — RVA 0x005C37B0 — ventana 0x10 bytes
  5c37b0: cc cc cc cc cc cc cc cc cc cc cc cc cc cc cc cc int3
"""
        windows = report_analysis.parse_windows(text)
        with self.assertRaisesRegex(ValueError, "no coincide"):
            report_analysis.verify_included_anchors(windows, self.candidates)


if __name__ == "__main__":
    unittest.main()
