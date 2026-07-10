import unittest

from aix_host_app.serial_source import SerialLineReader


class FakeSerial:
    def __init__(self):
        self.writes = []

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)


class SerialLineReaderWriteTests(unittest.TestCase):
    def test_write_line_appends_newline_and_encodes_utf8(self):
        reader = SerialLineReader("COM_TEST", 115200)
        fake = FakeSerial()
        reader._serial = fake

        ok = reader.write_line('{"type":"vision"}')

        self.assertTrue(ok)
        self.assertEqual(fake.writes, [b'{"type":"vision"}\n'])

    def test_write_line_returns_false_when_disconnected(self):
        reader = SerialLineReader("COM_TEST", 115200)

        self.assertFalse(reader.write_line('{"type":"vision"}'))


if __name__ == "__main__":
    unittest.main()
