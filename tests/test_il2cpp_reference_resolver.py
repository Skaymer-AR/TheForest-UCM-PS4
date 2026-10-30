import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import resolve_il2cpp_references as resolver


class Il2CppReferenceResolverTests(unittest.TestCase):
    def test_loads_known_debugconsole_and_rewired_method_symbols(self):
        symbols, provenance = resolver.load_symbols()
        self.assertIn("TheForest.DebugConsole.Awake", symbols[0x005C1C30])
        self.assertIn("TheForest.DebugConsole.GetInstance", symbols[0x005CB690])
        self.assertIn("TheForest.DebugConsole.ShowConsole", symbols[0x005CA800])
        self.assertIn("Rewired.ReInput.get_players", symbols[0x00934F40])
        self.assertIn("prior PS4 evidence", provenance[0x005C1C30])

    def test_custom_method_map_is_local_and_resolved_by_rva(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "private-method-map.tsv"
            path.write_text("0x12345678 Example.Namespace.Method\n", encoding="utf-8")
            symbols, provenance = resolver.load_symbols(extra=path)
        self.assertIn("Example.Namespace.Method", symbols[0x12345678])
        self.assertTrue(any("user-supplied local" in item
                            for item in provenance[0x12345678]))

    def test_direct_call_is_resolved_against_method_map(self):
        text = """\
DebugConsole.OnGUI — RVA 0x005C37B0 — ventana 0x20 bytes
  5c37b0: e8 4b 56 00 00                call 0x5c8e00
  5c37b5: c3                            ret
"""
        windows = resolver.parse_windows(text)
        symbols, provenance = resolver.load_symbols()
        refs = resolver.resolve_references(windows, symbols)
        calls = [item for item in refs if item.kind == "direct call/jump"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].target_rva, 0x005C8E00)
        self.assertIn("TheForest.DebugConsole.HandleInput", calls[0].target_names)

    def test_virtual_dispatch_is_reported_without_guessing_its_target(self):
        text = """\
PS4Controller.ProcessGamePads — RVA 0x004761A0 — ventana 0x20 bytes
  4761a0: e8 9b ed 4b 00                call 0x934f40
  4761a5: ff 11                         call qword ptr [rcx]
  4761a7: ff 11                         call qword ptr [rcx]
"""
        windows = resolver.parse_windows(text)
        symbols, _ = resolver.load_symbols()
        refs = resolver.resolve_references(windows, symbols)
        indirect = [item for item in refs if item.kind == "indirect call/jump"]
        self.assertEqual([item.site_rva for item in indirect], [0x004761A5, 0x004761A7])
        self.assertTrue(all(item.target_rva is None and not item.target_names
                            for item in indirect))
        self.assertFalse(any("ScePad" in name for item in refs
                             for name in item.target_names))

    def test_full_image_scan_finds_incoming_method_xrefs_without_fabricating_caller(self):
        text = """\
  1000: e8 2b 0c 5c 00                call 0x5c1c30 <PT_LOAD#0+0x5c1c30>
  1005: e9 86 b6 5c 00                jmp 0x5cb690 <PT_LOAD#0+0x5cb690>
  100a: ff 11                         call qword ptr [rcx]
"""
        instructions = resolver.parse_full_image_disassembly(text)
        symbols, _ = resolver.load_symbols()
        refs = resolver.resolve_full_image_xrefs(instructions, symbols)
        self.assertEqual([(item.site_rva, item.target_rva, item.detail)
                          for item in refs],
                         [(0x1000, 0x005C1C30, "call"),
                          (0x1005, 0x005CB690, "jmp")])
        self.assertTrue(all(item.source_name == "caller unresolved in symbol map"
                            for item in refs))

    def test_collects_conditional_branch_and_rip_relative_field_access(self):
        text = """\
DebugConsole.Awake — RVA 0x005C1C30 — ventana 0x20 bytes
  5c1c30: 74 05                         je 0x5c1c37
  5c1c32: 48 89 1d 10 00 00 00          mov qword ptr [rip + 0x10], rbx # 0x5c1c49
  5c1c39: 48 8b 05 10 00 00 00          mov rax, qword ptr [rip + 0x10] # 0x5c1c50
"""
        windows = resolver.parse_windows(text)
        symbols, _ = resolver.load_symbols()
        refs = resolver.resolve_references(windows, symbols)
        branches = [item for item in refs if item.kind == "branch"]
        data = [item for item in refs if item.kind == "rip-relative data"]
        self.assertEqual([(item.site_rva, item.target_rva) for item in branches],
                         [(0x005C1C30, 0x005C1C37)])
        self.assertEqual([item.target_rva for item in data], [0x005C1C49, 0x005C1C50])
        self.assertIn("write", data[0].detail)
        self.assertIn("read", data[1].detail)

    def test_report_marks_absent_method_windows_as_unobserved_not_absent(self):
        text = """\
DebugConsole.OnGUI — RVA 0x005C37B0 — ventana 0x10 bytes
  5c37b0: c3                            ret
"""
        windows = resolver.parse_windows(text)
        symbols, provenance = resolver.load_symbols()
        report = resolver.render_report(Path("private.txt"), windows,
                                        symbols, provenance)
        row = next(line for line in report.splitlines()
                   if "TheForest.DebugConsole.Awake" in line)
        self.assertIn("0x005C1C30", row)
        self.assertIn("| no |", row)
        self.assertIn("not ‘no reference exists’", report)

    def test_malformed_extra_symbol_map_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "invalid.tsv"
            path.write_text("DebugConsole.Awake 0x1234\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "expected '0xRVA Name'"):
                resolver.load_symbols(extra=path)


if __name__ == "__main__":
    unittest.main()
