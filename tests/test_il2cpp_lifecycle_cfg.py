import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_il2cpp_lifecycle as lifecycle
import resolve_il2cpp_references as references


class Il2CppLifecycleCfgTests(unittest.TestCase):
    def setUp(self):
        self.symbols, _ = references.load_symbols()
        self.symbols.setdefault(lifecycle.DESTROY_RVA, set()).add(
            "UnityEngine.Object.Destroy")

    def test_cfg_separates_disabled_guard_destroy_from_instance_store(self):
        text = """\
TheForest.DebugConsole.Awake — RVA 0x00001000 — ventana 0x20 bytes
  1000: 80 3d 00 00 00 00 00          cmp byte ptr [rip + 0x0], 0
  1007: 74 0b                         je 0x1014
  1009: 48 89 70 10                   mov qword ptr [rax + 0x10], rsi
  100d: c3                            ret
  1014: e8 17 69 21 02                call 0x2176930
  1019: c3                            ret
"""
        window = lifecycle.parse_windows(text)[0]
        cfg, sinks, guards = lifecycle.analyze_window(
            window, self.symbols,
            {0x1009: "TheForest.DebugConsole.Instance"},
            {0x1007: "Cheats.DebugConsole == false"})
        self.assertEqual({sink.name for sink in sinks}, {
            "UnityEngine.Object.Destroy", "TheForest.DebugConsole.Instance"})
        route_by_sink = {guard.sink_name: guard.route for guard in guards}
        self.assertEqual(route_by_sink["UnityEngine.Object.Destroy"], "taken")
        self.assertEqual(route_by_sink["TheForest.DebugConsole.Instance"], "fallthrough")
        self.assertEqual(len(cfg.edges), 5)

    def test_external_branch_target_is_kept_unresolved(self):
        text = """\
TheForest.DebugConsole.OnDestroy — RVA 0x00002000 — ventana 0x10 bytes
  2000: 75 20                         jne 0x2022
  2002: c3                            ret
"""
        cfg = lifecycle.build_cfg(lifecycle.parse_windows(text)[0])
        self.assertEqual(cfg.external_branches,
                         ((0x2000, 0x2022, "taken jne"),))
        self.assertEqual(cfg.edges[0].kind, "fallthrough jne")

    def test_missing_fallthrough_bytes_suppress_destroy_guard_claim(self):
        text = """\
Example — RVA 0x00002500 — ventana 0x20 bytes
  2500: 75 06                         jne 0x2508
  2508: e8 23 44 21 02                call 0x2176930
  250d: c3                            ret
"""
        window = lifecycle.parse_windows(text)[0]
        cfg, _sinks, guards = lifecycle.analyze_window(
            window, self.symbols, annotations={0x2500: "example guard"})
        self.assertEqual(cfg.fallthrough_gaps, ((0x2500, 0x2508),))
        self.assertEqual(guards, [])
        report = lifecycle.render_report(Path("gapped.txt"), window,
                                         self.symbols, {}, {})
        self.assertIn("incomplete CFG", report)

    def test_open_window_end_suppresses_unique_destroy_route(self):
        text = """\
Example — RVA 0x00002600 — ventana 0x20 bytes
  2600: 75 05                         jne 0x2607
  2602: e8 29 43 21 02                call 0x2176930
  2607: 89 c0                         mov eax, eax
"""
        window = lifecycle.parse_windows(text)[0]
        cfg, _sinks, guards = lifecycle.analyze_window(window, self.symbols)
        self.assertTrue(cfg.open_end)
        self.assertEqual(guards, [])

    def test_indirect_jump_is_recorded_as_unknown_edge(self):
        text = """\
Example — RVA 0x00002700 — ventana 0x10 bytes
  2700: ff e0                         jmp rax
"""
        cfg = lifecycle.build_cfg(lifecycle.parse_windows(text)[0])
        self.assertEqual(cfg.external_branches,
                         ((0x2700, None, "indirect jump; target unresolved"),))

    def test_cycles_terminate_when_computing_reachability(self):
        text = """\
Example — RVA 0x00003000 — ventana 0x20 bytes
  3000: 75 fe                         jne 0x3000
  3002: c3                            ret
  3003: e8 28 39 21 02                call 0x2176930
  3008: c3                            ret
"""
        window = lifecycle.parse_windows(text)[0]
        _cfg, sinks, guards = lifecycle.analyze_window(window, self.symbols)
        self.assertEqual(len(sinks), 1)
        self.assertEqual(guards, [])

    def test_store_annotation_must_point_to_memory_destination_mov(self):
        text = """\
Example — RVA 0x00004000 — ventana 0x10 bytes
  4000: 48 89 c0                      mov rax, rax
  4003: c3                            ret
"""
        window = lifecycle.parse_windows(text)[0]
        with self.assertRaisesRegex(ValueError, "not a recognizable"):
            lifecycle.analyze_window(window, self.symbols,
                                     {0x4000: "Instance"})

    def test_store_annotation_outside_window_fails_closed(self):
        text = """\
Example — RVA 0x00005000 — ventana 0x10 bytes
  5000: c3                            ret
"""
        window = lifecycle.parse_windows(text)[0]
        with self.assertRaisesRegex(ValueError, "outside the selected method window"):
            lifecycle.analyze_window(window, self.symbols,
                                     {0x5008: "Instance"})

    def test_report_labels_windowed_cfg_and_no_runtime_claim(self):
        text = """\
Example — RVA 0x00006000 — ventana 0x10 bytes
  6000: 74 03                         je 0x6005
  6002: c3                            ret
  6005: c3                            ret
"""
        window = lifecycle.parse_windows(text)[0]
        report = lifecycle.render_report(
            Path("private-disasm.txt"), window, self.symbols, {}, {})
        self.assertIn("instruction-level CFG", report)
        self.assertIn("No code, flags, objects, or game memory", report)
        self.assertIn("in-window direct edges", report)

    def test_cli_accepts_raw_objdump_with_explicit_window_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "awake.raw.txt"
            output = Path(temp_dir) / "cfg.md"
            source.write_text("""\
  1000: 74 05                         je 0x1007
  1002: c3                            ret
  1007: e8 24 69 21 02                call 0x2176930
  100c: c3                            ret
""", encoding="utf-8")
            status = lifecycle.main([
                str(source), "--method-rva", "0x1000", "--raw-size", "0x20",
                "--output", str(output),
            ])
            report = output.read_text(encoding="utf-8")
        self.assertEqual(status, 0)
        self.assertIn("UnityEngine.Object.Destroy", report)


if __name__ == "__main__":
    unittest.main()
