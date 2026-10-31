"""Synthetic fixtures only; no commercial asset bytes are present."""
import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import inspect_ds4_hardware_elements as scanner


def fixture(mutate=None, omit=None):
    result = bytearray(100)
    for label, element_id in scanner.EXPECTED_IDS.items():
        if label == omit:
            continue
        raw = label.encode("ascii")
        if label == mutate:
            element_id += 1
        result += struct.pack("<II", element_id, len(raw)) + raw
        result += bytes(-len(result) % 4)
    result += b"Wireless Controller\0"
    return bytes(result)


class SonyDs4ElementTests(unittest.TestCase):
    def test_24_hardware_ids(self):
        self.assertEqual(scanner.extract_elements(fixture()), scanner.EXPECTED_IDS)
        self.assertEqual(set(scanner.EXPECTED_IDS.values()), set(range(24)))

    def test_missing_or_changed_element_rejected(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            scanner.extract_elements(fixture(omit="L1"))
        with self.assertRaisesRegex(ValueError, "differs"):
            scanner.extract_elements(fixture(mutate="Cross"))

    def test_missing_table_rejected(self):
        with self.assertRaisesRegex(ValueError, "not identified"):
            scanner.extract_elements(bytes(512))


if __name__ == "__main__":
    unittest.main()
