"""Synthetic container fixtures only; never imports or executes game code."""
import contextlib
import io
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from unwrap_plain_self import main, unpack_plain_self


def fixture(props=0x804, trailer=True):
    phnum = 2 if trailer else 1
    headers = bytearray(64 + 56 * phnum)
    ident = b"\x7fELF\x02\x01\x01\x09" + bytes(8)
    struct.pack_into("<16sHHIQQQIHHHHHH", headers, 0,
                     ident, 0xFE18, 62, 1, 0, 64, 0, 0, 64, 56, phnum, 0, 0, 0)
    struct.pack_into("<II6Q", headers, 64, 1, 5, 0x200, 0, 0, 16, 32, 0x100)
    if trailer:
        struct.pack_into("<II6Q", headers, 120, 0x6FFFFF01, 0, 0x220, 0, 0, 4, 0, 1)
    data = bytearray(0x210)
    struct.pack_into("<I4BIHHQHHI", data, 0,
                     0x1D3D154F, 0, 1, 1, 0x12, 0x101, 0x100, 0x100, 0x210, 1, 0x22, 0)
    struct.pack_into("<4Q", data, 32, props, 0x200, 16, 16)
    data[64:64+len(headers)] = headers
    data[0x200:0x210] = b"0123456789ABCDEF"
    expected = bytearray(0x224 if trailer else 0x210)
    expected[:len(headers)] = headers
    expected[0x200:0x210] = data[0x200:0x210]
    if trailer:
        data += b"VERS"
        expected[0x220:0x224] = b"VERS"
    return data, bytes(expected)


class PlainSelfTests(unittest.TestCase):
    def test_recovers_exact_file_ranges_and_known_version_trailer(self):
        data, expected = fixture()
        result, report = unpack_plain_self(data)
        self.assertEqual(result, expected)
        self.assertEqual(report["version_trailer_bytes"], 4)
        self.assertFalse(report["cryptographic_signature_verified"])
        self.assertEqual(report["zero_filled_gaps"], [[176, 512], [528, 544]])

    def test_encryption_and_compression_are_not_mistaken_for_plaintext(self):
        for bit, word in ((2, "encrypted"), (8, "compressed"), (1 << 17, "unsupported")):
            with self.subTest(bit=bit):
                data, _ = fixture(props=0x804 | bit)
                with self.assertRaisesRegex(ValueError, word):
                    unpack_plain_self(data)

    def test_untrusted_ranges_are_rejected_before_allocation(self):
        for offset, size in ((1 << 63, 16), (0x200, 1 << 63)):
            data, _ = fixture()
            struct.pack_into("<Q", data, 64+64+8, offset)
            struct.pack_into("<Q", data, 64+64+32, size)
            with self.assertRaisesRegex(ValueError, "outside"):
                unpack_plain_self(data)

    def test_invalid_payload_size_and_index(self):
        for at, value, error in ((48, 15, "size differs"), (32, 0x804 | (7 << 20), "index")):
            data, _ = fixture()
            struct.pack_into("<Q", data, at, value)
            with self.assertRaisesRegex(ValueError, error):
                unpack_plain_self(data)

    def test_missing_aliased_segment_bytes_are_rejected(self):
        data, _ = fixture()
        struct.pack_into("<I", data, 64+120, 2)
        data = data[:0x210]
        with self.assertRaisesRegex(ValueError, "missing"):
            unpack_plain_self(data)

    def test_duplicate_targets_and_conflicting_overlaps_are_ambiguous(self):
        original, _ = fixture()
        headers = bytearray(original[64:64+176])
        struct.pack_into("<II6Q", headers, 120, 1, 5, 0x208, 0x100, 0, 16, 16, 1)
        for second_props, error in ((0x804, "duplicate"), (0x100804, "conflicting")):
            data = bytearray(0x230)
            struct.pack_into("<I4BIHHQHHI", data, 0,
                             0x1D3D154F, 0, 1, 1, 0x12, 0x101, 0x180, 0x80, 0x230, 2, 0x22, 0)
            struct.pack_into("<4Q", data, 32, 0x804, 0x200, 16, 16)
            struct.pack_into("<4Q", data, 64, second_props, 0x220, 16, 16)
            data[96:96+176] = headers
            data[0x200:0x210] = b"0123456789ABCDEF"
            data[0x220:0x230] = b"Z"*16
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                unpack_plain_self(data)

    def test_bad_or_unexplained_trailers_are_rejected(self):
        data, _ = fixture()
        for value in (data[:-1], data + b"X"):
            with self.assertRaisesRegex(ValueError, "trailer"):
                unpack_plain_self(value)
        data, _ = fixture(trailer=False)
        with self.assertRaisesRegex(ValueError, "unexplained"):
            unpack_plain_self(data+b"X")

    def test_wrong_elf_abi_and_section_tables_are_not_rewritten(self):
        for offset, fmt, value, error in ((64+18, "<H", 183, "x86-64"),
                                         (64+40, "<Q", 0x200, "section tables"),
                                         (64+32, "<Q", 0, "overlap")):
            data, _ = fixture()
            struct.pack_into(fmt, data, offset, value)
            with self.assertRaisesRegex(ValueError, error):
                unpack_plain_self(data)

    def test_stale_fields_of_an_absent_section_table_are_disclosed(self):
        data, expected = fixture()
        struct.pack_into("<H", data, 64+0x3A, 64)
        struct.pack_into("<H", data, 64+0x3E, 33)
        result, report = unpack_plain_self(data)
        self.assertEqual(result, expected)
        self.assertEqual(report["absent_section_table_source_fields"],
                         {"e_shentsize": 64, "e_shstrndx": 33})

    def test_truncation_is_rejected(self):
        data, _ = fixture()
        for length in (0, 16, 40, 80, 0x208):
            with self.subTest(length=length), self.assertRaises(ValueError):
                unpack_plain_self(data[:length])

    def test_cli_never_overwrites_inputs_or_existing_output(self):
        data, expected = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/"module.self"
            reference = Path(tmp)/"old.elf"
            source.write_bytes(data)
            reference.write_bytes(expected)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--self", str(source), "--output-elf", str(source)]), 2)
                self.assertEqual(main(["--self", str(source), "--output-elf", str(reference)]), 2)
            self.assertEqual(source.read_bytes(), data)
            self.assertEqual(reference.read_bytes(), expected)

    def test_rejected_input_creates_no_partial_output(self):
        data, _ = fixture(props=0x806)
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp)/"source", Path(tmp)/"output"
            source.write_bytes(data)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--self", str(source), "--output-elf", str(output)]), 2)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
