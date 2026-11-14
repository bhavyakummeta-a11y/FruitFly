import struct
import unittest

from flight_simulator.fg_crashes import parse_minidump


def minidump(code, address, access=0, target=0x10, base=0x140000000, size=0x1000000, name='fgfs.exe'):
    """Smallest minidump the parser reads: a module list and an exception record."""
    name_bytes = ('C:\\FG\\bin\\' + name).encode('utf-16-le')
    header = 32
    dir_rva = header
    mod_rva = dir_rva + 2 * 12
    mod_list = struct.pack('<I', 1)
    name_rva = mod_rva + 4 + 108
    module = struct.pack('<QIIII', base, size, 0, 0, name_rva) + bytes(108 - 24)
    names = struct.pack('<I', len(name_bytes)) + name_bytes
    exc_rva = name_rva + len(names)
    exc = struct.pack('<II', 1, 0) + struct.pack('<IIQQI', code, 0, 0, address, 2) + bytes(4) + struct.pack('<QQ', access, target)
    data = struct.pack('<4sIII', b'MDMP', 0xA793, 2, dir_rva) + bytes(header - 16)
    data += struct.pack('<III', 4, len(mod_list) + 108, mod_rva) + struct.pack('<III', 6, len(exc), exc_rva)
    data += mod_list + module + names + exc
    return data


class FgCrashTests(unittest.TestCase):
    def test_access_violation_site_and_access(self):
        info = parse_minidump(minidump(0xC0000005, 0x140000000 + 0x5adea5, access=0, target=0x7ff700000001))
        self.assertEqual(info['site'], 'fgfs.exe+0x5adea5')
        self.assertEqual(info['access'], 'read')
        self.assertEqual(info['target'], 0x7ff700000001)

    def test_address_outside_modules(self):
        info = parse_minidump(minidump(0xC0000374, 0x10))
        self.assertEqual(info['site'], '0x10 (no module)')
        self.assertEqual(info['access'], '')

    def test_rejects_non_minidump(self):
        with self.assertRaises(ValueError):
            parse_minidump(b'PK\x03\x04 not a dump')


if __name__ == '__main__':
    unittest.main()
