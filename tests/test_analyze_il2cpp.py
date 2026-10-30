import io
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import analyze_il2cpp


METADATA_MAGIC = 0xFAB11BAF

DUMP = """// Namespace: TheForest.Tools
public class DllModLoader : MonoBehaviour
{
    // Methods
    // RVA: 0x1010 Offset: 0x1000 VA: 0x2010
    private void Awake() { }
    // RVA: 0x1120 Offset: 0x1110 VA: 0x2120
    private void LoadDllMod(string filename) { }
}

// Namespace: TheForest.Modding.UI
public class ModList : MonoBehaviour
{
    // RVA: 0x2200 Offset: 0x21F0 VA: 0x3200
    private void OnEnable() { }
}

// Namespace:
public class Cheats
{
    public class CheatsBridge
    {
        // RVA: 0x3300 Offset: 0x32F0 VA: 0x4300
        public void SetGodMode(bool onoff) { }
    }
}

// Namespace: TheForest.UI
public class VirtualCursor : MonoBehaviour
{
    // RVA: 0x4400 Offset: 0x43F0 VA: 0x5400
    private void LateUpdate() { }
}

// Namespace: TheForest
public class DebugConsole : MonoBehaviour
{
    // RVA: 0x5500 Offset: 0x54F0 VA: 0x6500
    private void OnGUI() { }
    // RVA: 0x5560 Offset: 0x5550 VA: 0x6560
    private void OnDestroy() { }
}
"""


def write_metadata(path: Path, version: int = 29) -> None:
    header = bytearray(64)
    struct.pack_into("<Ii", header, 0, METADATA_MAGIC, version)
    path.write_bytes(header)


class AnalyzerTests(unittest.TestCase):
    def test_metadata_prefix_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            metadata = Path(temp) / "metadata.dat"
            write_metadata(metadata, 29)
            info = analyze_il2cpp.read_metadata_info(metadata)
            self.assertEqual(info.version, 29)
            self.assertEqual(info.size, 64)

            metadata.write_bytes(b"too short")
            with self.assertRaisesRegex(ValueError, "magic mismatch"):
                analyze_il2cpp.read_metadata_info(metadata)

            metadata.write_bytes(b"\x00\x01\x02")
            with self.assertRaisesRegex(ValueError, "shorter than"):
                analyze_il2cpp.read_metadata_info(metadata)

    def test_extracts_candidates_rvas_and_managed_signatures(self):
        with tempfile.TemporaryDirectory() as temp:
            dump = Path(temp) / "dump.cs"
            dump.write_text(DUMP, encoding="utf-8")
            classes, methods = analyze_il2cpp.parse_dump_cs(dump)

        self.assertEqual(set(classes), set(analyze_il2cpp.TARGET_CLASSES))
        found = {(m.class_name, m.managed_signature, m.rva) for m in methods}
        self.assertIn(("TheForest.Tools.DllModLoader", "private void Awake()", 0x1010), found)
        self.assertIn(("Cheats.CheatsBridge", "public void SetGodMode(bool onoff)", 0x3300), found)
        self.assertIn(("TheForest.DebugConsole", "private void OnGUI()", 0x5500), found)
        self.assertIn(("TheForest.DebugConsole", "private void OnDestroy()", 0x5560), found)

    def test_report_marks_missing_ps4_candidates_and_omits_input_path(self):
        with tempfile.TemporaryDirectory(prefix="private-game-path-") as temp:
            metadata_path = Path(temp) / "global-metadata.dat"
            dump_path = Path(temp) / "dump.cs"
            write_metadata(metadata_path)
            dump_path.write_text(DUMP, encoding="utf-8")
            info = analyze_il2cpp.read_metadata_info(metadata_path)
            classes, methods = analyze_il2cpp.parse_dump_cs(dump_path)
            report = analyze_il2cpp.render_report(info, classes, methods)

        self.assertIn("`0x1010`", report)
        self.assertIn("private void LateUpdate()", report)
        self.assertNotIn("private-game-path", report)
        self.assertIn("not native x86-64 ABI prototypes", report)

    def test_local_dumper_wrapper_uses_private_temporary_output(self):
        with tempfile.TemporaryDirectory(prefix="analyzer-test-") as temp:
            root = Path(temp)
            metadata = root / "metadata.dat"
            binary = root / "local-eboot.elf"
            dumper = root / "fake-dumper"
            write_metadata(metadata)
            binary.write_bytes(b"synthetic ELF placeholder")
            dumper.write_text(
                "#!/usr/bin/env python3\n"
                "import pathlib, sys\n"
                "pathlib.Path(sys.argv[3], 'dump.cs').write_text("
                + repr(DUMP) + ", encoding='utf-8')\n",
                encoding="utf-8",
            )
            dumper.chmod(0o755)
            classes, methods = analyze_il2cpp.invoke_dumper(dumper, binary, metadata)

        self.assertIn("TheForest.DebugConsole", classes)
        self.assertTrue(any(m.managed_signature == "private void OnGUI()" for m in methods))

    def test_cli_writes_only_the_requested_markdown_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            metadata = root / "metadata.dat"
            dump = root / "dump.cs"
            output = root / "report.md"
            write_metadata(metadata)
            dump.write_text(DUMP, encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = analyze_il2cpp.main([
                    "--metadata", str(metadata), "--dump-cs", str(dump),
                    "--output", str(output),
                ])
            output_exists = output.is_file()
            report_text = output.read_text(encoding="utf-8") if output_exists else ""

        self.assertEqual(status, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertTrue(output_exists)
        self.assertIn("TheForest.Modding.UI.ModList", report_text)


if __name__ == "__main__":
    unittest.main()
