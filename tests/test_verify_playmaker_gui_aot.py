import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_playmaker_gui_aot import check_edges, inspect, SPEC


class PrecompiledGuiAotTests(unittest.TestCase):
    def test_synthetic_button_and_event_calls(self):
        edges={0x1234:0x2000,0x1300:0x3000}
        def read(at,size):
            return b'\xe8'+struct.pack('<i',edges[at]-at-5)
        self.assertEqual(len(check_edges(read,edges)),2)

    def test_bad_call_rejected(self):
        with self.assertRaisesRegex(ValueError,'unexpected native'):
            check_edges(lambda at,size: b'\x90'*size,{0x1234:0x2000})

    def test_wrong_target_rejected(self):
        with self.assertRaisesRegex(ValueError,'unexpected native'):
            check_edges(lambda at,size:b'\xe8'+struct.pack('<i',0),
                        {0x1234:0x2000})

    def test_bad_module_rejected(self):
        with self.assertRaisesRegex(ValueError,'wrong IL2CPP module'):
            inspect(b'bad ELF',b'bad metadata')

    def test_gui_action_coverage(self):
        self.assertEqual(len(SPEC),7)
        for name in ('GUIButton','GUIBox','GUILabel','GUILayoutButton'):
            self.assertIn(name,SPEC)


if __name__=='__main__':
    unittest.main()
