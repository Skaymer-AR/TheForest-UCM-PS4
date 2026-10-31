"""Registration checks on generated synthetic ELF/v23 metadata fixtures."""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from inspect_aot_registration import inspect_registration
from test_analyze_ps4_il2cpp_pipeline import metadata_fixture


def fixture():
    data = bytearray(0x4000)
    ident = b"\x7fELF\x02\x01\x01\x09"+bytes(8)
    struct.pack_into("<16sHHIQQQIHHHHHH", data, 0,
                     ident, 0xFE18, 62, 1, 0, 64, 0, 0, 64, 56, 2, 0, 0, 0)
    struct.pack_into("<II6Q", data, 64, 1, 5, 0x1000, 0x1000, 0, 0x1000, 0x1000, 0x1000)
    struct.pack_into("<II6Q", data, 120, 0x61000010, 4, 0x2000, 0x3000, 0, 0x2000, 0x2000, 0x1000)
    for off, opcode, target in ((0, b"\x48\x8d\x3d", 0x3100),
                                (7, b"\x48\x8d\x35", 0x3200),
                                (14, b"\x48\x8d\x15", 0x3300)):
        data[0x1100+off:0x1100+off+3] = opcode
        struct.pack_into("<i", data, 0x1100+off+3, target-(0x1100+off+7))
    data[0x1115] = 0xE9
    struct.pack_into("<i", data, 0x1116, 0x1200-0x111A)
    struct.pack_into("<QQ", data, 0x2100, 2, 0x3400)
    struct.pack_into("<QQ", data, 0x2400, 0x1200, 0x1300)
    # Native typesCount is not the number of metadata TypeDefinitions.
    struct.pack_into("<QQ", data, 0x2200+3*16, 128, 0x3500)
    struct.pack_into("<QQ", data, 0x2200+5*16, 5, 0x3900)
    struct.pack_into("<QQ", data, 0x2200+6*16, 5, 0x3940)
    return data


class AotRegistrationTests(unittest.TestCase):
    def inspect(self, data=None, metadata=None, **kwargs):
        return inspect_registration(fixture() if data is None else data,
                                    metadata_fixture() if metadata is None else metadata,
                                    0x1100, 0x2400, **kwargs)

    def test_relro_registration_is_coherent_and_absent_host_is_reported(self):
        report = self.inspect()
        self.assertEqual(report["code_registration"]["methods"]["count"], 2)
        self.assertEqual(report["metadata_registration"]["types"]["count"], 128)
        self.assertFalse(report["host_native_presence_passed"])
        self.assertFalse(report["runtime_component_creation_or_invocation_checked"])

    def test_native_method_presence_requires_real_executable_bodies(self):
        kwargs = {"host_type":"TheForest.DebugConsole", "required_methods":("OnDestroy",)}
        self.assertTrue(self.inspect(**kwargs)["host_native_presence_passed"])
        data = fixture()
        struct.pack_into("<Q", data, 0x2400, 0x3500)
        self.assertFalse(self.inspect(data, **kwargs)["host_native_presence_passed"])

    def test_supplied_method_table_must_belong_to_this_registration(self):
        data = fixture()
        struct.pack_into("<Q", data, 0x2108, 0x3410)
        with self.assertRaisesRegex(ValueError, "supplied method table"):
            self.inspect(data)

    def test_type_index_is_bounded_against_native_types_not_typedefinitions(self):
        metadata = bytearray(metadata_fixture())
        offset = struct.unpack_from("<I", metadata, 8+19*8)[0]
        struct.pack_into("<i", metadata, offset+5*4, 100)
        self.inspect(metadata=metadata)
        struct.pack_into("<i", metadata, offset+5*4, 128)
        with self.assertRaisesRegex(ValueError, "native TypeIndex"):
            self.inspect(metadata=metadata)

    def test_inconsistent_native_counts_and_pointer_ranges_fail(self):
        for at, value, error in ((0x2100, 1, "methodIndex"),
                                 (0x2250, 4, "field_offsets"),
                                 (0x2238, 0xFFFFFFFFFFFF, "file-backed")):
            data = fixture()
            struct.pack_into("<Q", data, at, value)
            with self.assertRaisesRegex(ValueError, error):
                self.inspect(data)

    def test_unrecognized_initializer_is_not_guessed(self):
        data = fixture()
        data[0x1100] = 0x90
        with self.assertRaisesRegex(ValueError, "supported"):
            self.inspect(data)


if __name__ == "__main__":
    unittest.main()
