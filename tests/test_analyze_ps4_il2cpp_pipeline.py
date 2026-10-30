import contextlib
import hashlib
import io
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import analyze_ps4_il2cpp_pipeline as pipeline
from analyze_disassembly_report import parse_windows
from resolve_il2cpp_references import load_symbols, resolve_references


def metadata_fixture():
    strings = bytearray(b"\0")
    string_indices = {"": 0}

    def add_string(value):
        if value not in string_indices:
            string_indices[value] = len(strings)
            strings.extend(value.encode("utf-8") + b"\0")
        return string_indices[value]

    type_specs = [
        ("DebugConsole", "TheForest", 0, 0, 1, 0, 1),
        ("PS4Controller", "", 0, 2, 0, 1, 1),
        ("ReInput", "Rewired", 0, 2, 0, 2, 0),
        ("IPlayer", "Rewired", pipeline.TYPE_ATTRIBUTE_INTERFACE, 2, 0, 2, 0),
        ("CoopPeerStarter", "", 0, 1, 1, 2, 0),
    ]
    type_rows = []
    for name, namespace, flags, field_start, field_count, method_start, method_count in type_specs:
        # v23: name/namespace; 9 legacy indices; flags; 8 starts; 8 counts;
        # bitfield and token. Keep absent indexes at -1.
        type_rows.append(pipeline.TYPE_RECORD.pack(
            add_string(name), add_string(namespace),
            *([-1] * 9), flags,
            field_start, method_start, 0, 0, 0, 0, 0, 0,
            method_count, 0, field_count, 0, 0, 0, 0, 0,
            0, 0x02000001,
        ))

    method_rows = [
        pipeline.METHOD_RECORD.pack(
            add_string("OnDestroy"), 0, -1, 0, -1, -1, 0, -1, -1, -1, 0,
            0x06000001, 0, 0, 0, 0,
        ),
        pipeline.METHOD_RECORD.pack(
            add_string("ProcessGamePads"), 1, -1, 0, -1, -1, 1, -1, -1, -1, 0,
            0x06000002, 0, 0, 0, 0,
        ),
    ]
    field_rows = [
        pipeline.FIELD_RECORD.pack(add_string("Instance"), -1, -1, 0x04000001),
        pipeline.FIELD_RECORD.pack(add_string("DedicatedHost"), -1, -1, 0x04000002),
    ]

    blob = bytearray(pipeline.HEADER_SIZE_V23)
    struct.pack_into("<Ii", blob, 0, pipeline.METADATA_MAGIC, pipeline.METADATA_VERSION)
    sections = {
        "strings": bytes(strings),
        "methods": b"".join(method_rows),
        "fields": b"".join(field_rows),
        "type_definitions": b"".join(type_rows),
    }
    for name in ("strings", "methods", "fields", "type_definitions"):
        offset = len(blob)
        section_data = sections[name]
        blob.extend(section_data)
        pair_index = pipeline.HEADER_PAIR_INDEX[name]
        struct.pack_into("<Ii", blob, 8 + pair_index * 8, offset, len(section_data))
    return bytes(blob)


def elf_fixture():
    blob = bytearray(0xB000)
    blob[:16] = b"\x7fELF\x02\x01\x01" + b"\0" * 9
    struct.pack_into("<HHIQQQIHHHHHH", blob, 16,
                     3, 62, 1, 0, 64, 0, 0, 64, 56, 3, 0, 0, 0)
    segments = [
        (0x1000, 0x00000000, 0x2000, 5),
        (0x3000, 0x033EB000, 0x6000, 6),
        (0x9000, 0x00476000, 0x2000, 5),
    ]
    for index, (file_offset, vaddr, size, flags) in enumerate(segments):
        struct.pack_into("<IIQQQQQQ", blob, 64 + index * 56,
                         1, flags, file_offset, vaddr, vaddr, size, size, 0x1000)
    struct.pack_into("<QQQ", blob, 0x200, 0x120, 0x004761A0, 0x033EB300)
    # Native data-slot bytes are present in the ELF image but are not treated
    # as runtime values or as a mapping to any managed TypeDef.
    for slot in (0x033EB300, 0x033EF3E8):
        file_offset = 0x3000 + slot - 0x033EB000
        struct.pack_into("<Q", blob, file_offset, 0)
    return bytes(blob)


def on_destroy_mapping_elf_fixture():
    # A sparse-sized synthetic executable PT_LOAD is enough to exercise the
    # exact pinned methodIndex -> RVA lookup without any game binary.
    blob = bytearray(0x5C8000)
    blob[:16] = b"\x7fELF\x02\x01\x01" + b"\0" * 9
    struct.pack_into("<HHIQQQIHHHHHH", blob, 16,
                     3, 62, 1, 0, 64, 0, 0, 64, 56, 1, 0, 0, 0)
    struct.pack_into("<IIQQQQQQ", blob, 64,
                     1, 5, 0x1000, 0, 0, 0x5C7000, 0x5C7000, 0x1000)
    struct.pack_into("<Q", blob, 0x200 + 75393 * 8, 0x005C3340)
    return bytes(blob)


PROCESS_GAMEPADS = """\
PS4Controller.ProcessGamePads — RVA 0x004761A0 — ventana 0x180 bytes
  4761a0: 55                            push rbp
  476279: 48 8b 35 68 91 f7 02          mov rsi, qword ptr [rip + 0x2f79168] # 0x33ef3e8
  4762c7: 48 8d 8c 08 10 01 00 00       lea rcx, [rax + rcx + 0x110]
  4762cf: 48 8b 71 08                   mov rsi, qword ptr [rcx + 0x8]
  4762d3: 48 89 df                      mov rdi, rbx
  4762d6: ff 11                         call qword ptr [rcx]
  476300: 8b 0a                         mov ecx, dword ptr [rdx]
  476306: 48 8d 8c 08 10 01 00 00       lea rcx, [rax + rcx + 0x110]
  47630e: 48 8b 71 08                   mov rsi, qword ptr [rcx + 0x8]
  476312: 4c 89 ff                      mov rdi, r15
  476315: ff 11                         call qword ptr [rcx]
"""


class Ps4Il2CppPipelineTests(unittest.TestCase):
    def test_v23_metadata_and_method_index_map_to_executable_rva(self):
        metadata = pipeline.parse_metadata_v23(metadata_fixture())
        with tempfile.TemporaryDirectory() as temp_dir:
            module_path = Path(temp_dir) / "private-module.elf"
            module_path.write_bytes(elf_fixture())
            image = pipeline.Elf64Image(module_path)
            on_destroy = metadata.methods_named(metadata.find_types("TheForest.DebugConsole")[0],
                                                "OnDestroy")[0]
            process = metadata.methods_named(metadata.find_types("PS4Controller")[0],
                                             "ProcessGamePads")[0]
            self.assertEqual(on_destroy.definition_index, 0)
            self.assertEqual(on_destroy.method_index, 0)
            self.assertEqual(pipeline.resolve_method_rva(module_path, image, on_destroy, 0x200),
                             (0x120, True))
            self.assertEqual(process.definition_index, 1)
            self.assertEqual(process.method_index, 1)
            self.assertEqual(pipeline.resolve_method_rva(module_path, image, process, 0x200),
                             (0x004761A0, True))
            data_pointer_method = pipeline.MethodDefinition(2, "NotCode", 0, 2, 0, 0)
            self.assertEqual(pipeline.resolve_method_rva(
                module_path, image, data_pointer_method, 0x200), (0x033EB300, False))

    def test_end_to_end_report_keeps_type_slots_unresolved_without_registration(self):
        metadata_bytes = metadata_fixture()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            metadata_path = root / "global-metadata.dat"
            module_path = root / "module.elf"
            disassembly_path = root / "bounded.txt"
            report_path = root / "report.md"
            windows_text = (
                "DebugConsole.OnDestroy — RVA 0x00000120 — ventana 0x10 bytes\n"
                "  120: c3                            ret\n\n" + PROCESS_GAMEPADS)
            windows = parse_windows(windows_text)
            module_data = bytearray(elf_fixture())
            module_path.write_bytes(module_data)
            image = pipeline.Elf64Image(module_path)
            for window in windows:
                for instruction in window.instructions:
                    offset = image.file_offset(instruction.address)
                    self.assertIsNotNone(offset)
                    module_data[offset:offset + len(instruction.raw_bytes)] = instruction.raw_bytes
            metadata_path.write_bytes(metadata_bytes)
            module_bytes = bytes(module_data)
            module_path.write_bytes(module_bytes)
            disassembly_path.write_text(windows_text, encoding="utf-8")
            status = pipeline.main([
                "--metadata", str(metadata_path), "--module", str(module_path),
                "--method-pointer-table-offset", "0x200",
                "--expected-metadata-sha256", hashlib.sha256(metadata_bytes).hexdigest(),
                "--expected-module-sha256", hashlib.sha256(module_bytes).hexdigest(),
                "--disassembly", str(disassembly_path), "--output", str(report_path),
            ])
            report = report_path.read_text(encoding="utf-8")
        self.assertEqual(status, 0)
        self.assertIn("`TheForest.DebugConsole.OnDestroy` | `0` | `0`", report)
        self.assertIn("`0x00000120`", report)
        self.assertIn("`0x004762D6`", report)
        self.assertIn("`0x00476315`", report)
        self.assertIn("Instruction byte sequences matched against the pinned ELF: `12`", report)
        self.assertIn("unresolved metadata type", report)
        self.assertIn("native slot binding unresolved", report)
        self.assertIn("possible DedicatedHost owner | `CoopPeerStarter`", report)
        self.assertIn("Rewired interface candidate pool | `Rewired.IPlayer`", report)
        self.assertNotIn("| `0x033EB300` | `CoopPeerStarter`", report)
        self.assertNotIn("| `0x033EF3E8` | `Rewired.IPlayer`", report)
        self.assertIn("contains no analyst-annotated direct store", report)

    def test_on_destroy_assessment_requires_complete_body_and_explicit_field_mapping(self):
        methods = [{"method": "OnDestroy", "type": "TheForest.DebugConsole",
                    "status": "resolved", "rva": 0x2000, "method_index": 0}]
        symbols, _ = load_symbols()
        complete = parse_windows("""\
TheForest.DebugConsole.OnDestroy — RVA 0x00002000 — ventana 0x10 bytes
  2000: 48 c7 05 10 00 00 00 00 00 00  mov qword ptr [rip + 0x10], 0
  200a: c3                            ret
""")[0]
        no_annotation = pipeline._on_destroy_assessment(methods, [complete], symbols, {}, {})
        self.assertIn("no analyst-annotated direct store", no_annotation)
        clear = pipeline._on_destroy_assessment(
            methods, [complete], symbols,
            {0x2000: "TheForest.DebugConsole.Instance"}, {})
        self.assertIn("supports a clear on that visible path", clear)

        incomplete = parse_windows("""\
TheForest.DebugConsole.OnDestroy — RVA 0x00002000 — ventana 0x20 bytes
  2000: 75 20                         jne 0x2022
  2002: 48 c7 05 10 00 00 00 00 00 00  mov qword ptr [rip + 0x10], 0
  200c: c3                            ret
""")[0]
        uncertain = pipeline._on_destroy_assessment(
            methods, [incomplete], symbols,
            {0x2002: "TheForest.DebugConsole.Instance"}, {})
        self.assertIn("CFG window has gaps, an external branch, or an open end", uncertain)

    def test_pinned_on_destroy_identity_matches_definition_method_index_token_and_rva(self):
        expected = json.loads((ROOT / "docs/PS4_ONDESTROY_EXPECTATIONS.json")
                              .read_text(encoding="utf-8"))
        method = expected["method"]
        row = {"type": method["type"], "method": method["name"],
               "definition_index": method["definition_index"],
               "method_index": method["method_index"],
               "token": int(method["token"], 16),
               "rva": int(method["rva"], 16), "status": "resolved"}
        pipeline.validate_pinned_on_destroy_identity(
            [row], expected["metadata_sha256"], expected["module_sha256"])
        row["rva"] += 1
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            pipeline.validate_pinned_on_destroy_identity(
                [row], expected["metadata_sha256"], expected["module_sha256"])

    def test_pinned_on_destroy_method_index_maps_to_the_recorded_executable_rva(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module_path = Path(temp_dir) / "synthetic-module.elf"
            module_path.write_bytes(on_destroy_mapping_elf_fixture())
            image = pipeline.Elf64Image(module_path)
            method = pipeline.MethodDefinition(82470, "OnDestroy", 0, 75393,
                                               0x0600777D, 0)
            self.assertEqual(pipeline.resolve_method_rva(
                module_path, image, method, 0x200), (0x005C3340, True))

    def test_on_destroy_counters_clear_is_distinct_from_instance_this_store(self):
        expected = json.loads((ROOT / "docs/PS4_ONDESTROY_EXPECTATIONS.json")
                              .read_text(encoding="utf-8"))
        method = expected["method"]
        row = {"method": method["name"], "type": method["type"],
               "definition_index": method["definition_index"],
               "method_index": method["method_index"],
               "token": int(method["token"], 16), "rva": int(method["rva"], 16),
               "status": "resolved"}
        window = parse_windows("""\
TheForest.DebugConsole.OnDestroy — RVA 0x005C3340 — ventana 0x240 bytes
  5c3340: 55                            push rbp
  5c3351: 4c 89 f7                      mov r14, rdi
  5c3384: 48 c7 40 08 00 00 00 00       mov qword ptr [rax + 0x8], 0
  5c356c: 4c 89 70 10                   mov qword ptr [rax + 0x10], r14
  5c3578: c3                            ret
""")[0]
        symbols, _ = load_symbols()
        report = pipeline._on_destroy_assessment(
            [row], [window], symbols, {}, {}, pinned_input=True)
        self.assertIn("DebugConsole.Counters", report)
        self.assertIn("matches `mov [rax + 0x8], 0`", report)
        self.assertIn("DebugConsole.Instance", report)
        self.assertIn("matches `mov [rax + 0x10], r14`", report)
        self.assertIn("source resolves to `this`", report)
        self.assertIn("not an Instance clear", report)
        self.assertNotIn("supports a clear", report)
        unpinned = pipeline._on_destroy_assessment(
            [row], [window], symbols, {}, {}, pinned_input=False)
        self.assertNotIn("Pinned PS4 instruction expectations", unpinned)
        self.assertIn("no analyst-annotated direct store", unpinned)

    def test_on_destroy_instance_zero_is_not_misread_as_the_recorded_this_store(self):
        expected = json.loads((ROOT / "docs/PS4_ONDESTROY_EXPECTATIONS.json")
                              .read_text(encoding="utf-8"))
        method = expected["method"]
        row = {"method": method["name"], "type": method["type"],
               "definition_index": method["definition_index"],
               "method_index": method["method_index"],
               "token": int(method["token"], 16), "rva": int(method["rva"], 16),
               "status": "resolved"}
        window = parse_windows("""\
TheForest.DebugConsole.OnDestroy — RVA 0x005C3340 — ventana 0x240 bytes
  5c3340: 55                            push rbp
  5c3351: 4c 89 f7                      mov r14, rdi
  5c3384: 48 c7 40 08 00 00 00 00       mov qword ptr [rax + 0x8], 0
  5c356c: 48 c7 40 10 00 00 00 00       mov qword ptr [rax + 0x10], 0
  5c3578: c3                            ret
""")[0]
        symbols, _ = load_symbols()
        report = pipeline._on_destroy_assessment(
            [row], [window], symbols, {}, {}, pinned_input=True)
        self.assertIn("Counters", report)
        self.assertIn("Instance` at `0x005C356C` (0x10) does not match", report)
        self.assertIn("Do not infer Instance cleanup", report)

    def test_rewired_vtable_callsites_are_indirect_and_do_not_acquire_names(self):
        window = parse_windows(PROCESS_GAMEPADS)[0]
        references = resolve_references([window], load_symbols()[0])
        calls = {ref.site_rva: ref for ref in references
                 if ref.site_rva in {0x004762D6, 0x00476315}}
        self.assertEqual(set(calls), {0x004762D6, 0x00476315})
        for call in calls.values():
            self.assertEqual(call.kind, "indirect call/jump")
            self.assertIsNone(call.target_rva)
            self.assertFalse(call.target_names)
            self.assertIn("0x033EF3E8", call.detail)
            self.assertIn("unresolved metadata type", call.detail)

    def test_disassembly_bytes_and_rip_comment_must_match_the_pinned_module(self):
        text = """\
Example — RVA 0x00476279 — ventana 0x10 bytes
  476279: 48 8b 35 68 91 f7 02          mov rsi, qword ptr [rip + 0x2f79168] # 0x33ef3e9
"""
        window = parse_windows(text)[0]
        with tempfile.TemporaryDirectory() as temp_dir:
            module_path = Path(temp_dir) / "module.elf"
            module = bytearray(elf_fixture())
            module[0x9000 + 0x279:0x9000 + 0x279 + 7] = bytes.fromhex(
                "48 8b 35 68 91 f7 02")
            module_path.write_bytes(module)
            image = pipeline.Elf64Image(module_path)
            with self.assertRaisesRegex(ValueError, "RIP-relative comment disagrees"):
                pipeline.verify_window_bytes(image, [window])

    def test_static_field_evidence_keeps_guard_read_separate_from_instance_write(self):
        expected = json.loads((ROOT / "docs/PS4_STATIC_FIELD_EXPECTATIONS.json")
                              .read_text(encoding="utf-8"))
        guard = next(item for item in expected["fields"]
                     if item["type_suffix"] == "Cheats")
        instance = next(item for item in expected["fields"]
                        if item["type_suffix"] == "DebugConsole")
        self.assertIn("reads Cheats.static_fields+0x10", guard["native_evidence"])
        self.assertNotIn("writes this", guard["native_evidence"])
        self.assertIn("writes this pointer to DebugConsole.static_fields+0x10", 
                      instance["native_evidence"])
        self.assertNotIn("Cheats.static_fields", instance["native_evidence"])

    def test_metadata_hash_and_version_gate_fail_closed(self):
        blob = bytearray(metadata_fixture())
        struct.pack_into("<i", blob, 4, 24)
        with self.assertRaisesRegex(ValueError, "expected IL2CPP metadata v23"):
            pipeline.parse_metadata_v23(bytes(blob))

    def test_cli_hash_mismatch_fails_before_creating_a_report(self):
        metadata_bytes = metadata_fixture()
        module_bytes = elf_fixture()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            metadata_path = root / "metadata.dat"
            module_path = root / "module.elf"
            report_path = root / "report.md"
            metadata_path.write_bytes(metadata_bytes)
            module_path.write_bytes(module_bytes)
            status = pipeline.main([
                "--metadata", str(metadata_path), "--module", str(module_path),
                "--method-pointer-table-offset", "0x200",
                "--expected-metadata-sha256", "00" * 32,
                "--expected-module-sha256", hashlib.sha256(module_bytes).hexdigest(),
                "--output", str(report_path),
            ])
        self.assertEqual(status, 2)
        self.assertFalse(report_path.exists())

    def test_cli_rejects_sce_self_container_before_rva_or_hash_analysis(self):
        metadata_bytes = metadata_fixture()
        module_bytes = b"SCE/SELF container fixture"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            metadata_path = root / "metadata.dat"
            module_path = root / "module.prx"
            report_path = root / "report.md"
            metadata_path.write_bytes(metadata_bytes)
            module_path.write_bytes(module_bytes)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                status = pipeline.main([
                    "--metadata", str(metadata_path), "--module", str(module_path),
                    "--expected-metadata-sha256", hashlib.sha256(metadata_bytes).hexdigest(),
                    "--expected-module-sha256", hashlib.sha256(module_bytes).hexdigest(),
                    "--output", str(report_path),
                ])
        self.assertEqual(status, 2)
        self.assertIn("RVA mapping is unavailable", stderr.getvalue())
        self.assertFalse(report_path.exists())

    def test_static_field_hash_failure_is_reported_and_returns_nonzero(self):
        metadata_bytes = metadata_fixture()
        module_bytes = elf_fixture()
        dump = """\
// Namespace: TheForest
public class DebugConsole
{
    private static DebugConsole Instance;
}
public class Cheats
{
    public static bool DebugConsole;
}
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            metadata_path = root / "metadata.dat"
            module_path = root / "module.elf"
            dump_path = root / "dump.cs"
            report_path = root / "report.md"
            metadata_path.write_bytes(metadata_bytes)
            module_path.write_bytes(module_bytes)
            dump_path.write_text(dump, encoding="utf-8")
            status = pipeline.main([
                "--metadata", str(metadata_path), "--module", str(module_path),
                "--method-pointer-table-offset", "0x200",
                "--expected-metadata-sha256", hashlib.sha256(metadata_bytes).hexdigest(),
                "--expected-module-sha256", hashlib.sha256(module_bytes).hexdigest(),
                "--dump-cs", str(dump_path), "--output", str(report_path),
            ])
            report = report_path.read_text(encoding="utf-8")
        self.assertEqual(status, 1)
        self.assertIn("FAIL", report)
        self.assertIn("metadata SHA-256", report)


if __name__ == "__main__":
    unittest.main()
