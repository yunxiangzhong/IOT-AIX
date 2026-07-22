import sys
import types
import unittest
from unittest.mock import patch

from aix_host_app.serial_source import SerialLineReader, SerialPortOption, has_matching_port, list_serial_ports, preferred_serial_port


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


class PreferredSerialPortTests(unittest.TestCase):
    def test_prefers_matching_cp210x_and_ignores_bluetooth_ports(self):
        selected = preferred_serial_port([
            SerialPortOption("COM8", "Bluetooth", None, None, ""),
            SerialPortOption("COM21", "Silicon Labs CP210x", 0x10C4, 0xEA60, "AIX-BOARD"),
        ])

        self.assertIsNotNone(selected)
        self.assertEqual(selected.device, "COM21")

    def test_prefers_cp210x_named_port_when_pyserial_does_not_supply_usb_id(self):
        selected = preferred_serial_port([
            SerialPortOption("COM8", "蓝牙链接上的标准串行", None, None, ""),
            SerialPortOption("COM21", "Silicon Labs CP210x USB to UART Bridge", None, None, ""),
        ])

        self.assertIsNotNone(selected)
        self.assertEqual(selected.device, "COM21")

    def test_does_not_guess_between_two_usb_uart_candidates(self):
        selected = preferred_serial_port([
            SerialPortOption("COM20", "Silicon Labs CP210x USB to UART Bridge", None, None, ""),
            SerialPortOption("COM21", "ESP32-S3 USB JTAG/serial debug unit", None, None, ""),
        ])

        self.assertIsNone(selected)

    def test_returns_none_when_remembered_identity_not_present(self):
        """有 remembered_identity 但无匹配端口时返回 None，禁止回退。"""
        options = [
            SerialPortOption("COM13", "ESP32-S3 USB", 0x303A, 0x1001, ""),
            SerialPortOption("COM9", "Other Device", 0x1234, 0x5678, ""),
        ]
        result = preferred_serial_port(options, "10C4:EA60:TARGET-BOARD")
        self.assertIsNone(result)
        # has_matching_port 也应返回 False
        self.assertFalse(has_matching_port(options, "10C4:EA60:TARGET-BOARD"))

    def test_keeps_unique_saved_adapter_selected_when_serial_number_is_missing(self):
        options = [
            SerialPortOption("COM12", "蓝牙链接上的标准串行", None, None, ""),
            SerialPortOption("COM21", "Silicon Labs CP210x USB to UART Bridge", 0x10C4, 0xEA60, ""),
        ]

        result = preferred_serial_port(options, "10C4:EA60:TARGET-BOARD")

        self.assertIsNotNone(result)
        self.assertEqual(result.device, "COM21")

    def test_keeps_unique_cp210x_name_selected_when_driver_omits_usb_fields(self):
        options = [
            SerialPortOption("COM12", "蓝牙链接上的标准串行", None, None, ""),
            SerialPortOption("COM21", "Silicon Labs CP210x USB to UART Bridge", None, None, ""),
        ]

        result = preferred_serial_port(options, "10C4:EA60:TARGET-BOARD")

        self.assertIsNotNone(result)
        self.assertEqual(result.device, "COM21")

    def test_does_not_fallback_when_two_saved_adapter_types_are_present(self):
        options = [
            SerialPortOption("COM20", "Silicon Labs CP210x", 0x10C4, 0xEA60, ""),
            SerialPortOption("COM21", "Silicon Labs CP210x", 0x10C4, 0xEA60, ""),
        ]

        self.assertIsNone(preferred_serial_port(options, "10C4:EA60:TARGET-BOARD"))

    def test_returns_none_when_no_usb_ports_available(self):
        """无 USB 端口时返回 None。"""
        result = preferred_serial_port([], "10C4:EA60:TARGET-BOARD")
        self.assertIsNone(result)
        # 无 remembered_identity 且空列表也应返回 None
        result_no_id = preferred_serial_port([])
        self.assertIsNone(result_no_id)

    def test_has_matching_port_returns_true_when_match_exists(self):
        """has_matching_port 在有匹配端口时返回 True。"""
        options = [
            SerialPortOption("COM13", "ESP32-S3", 0x303A, 0x1001, ""),
            SerialPortOption("COM21", "CP210x", 0x10C4, 0xEA60, "AIX-BOARD"),
        ]
        self.assertTrue(has_matching_port(options, "10C4:EA60:AIX-BOARD"))
        self.assertFalse(has_matching_port(options, ""))
        self.assertFalse(has_matching_port(options, "10C4:EA60:WRONG-BOARD"))


class SerialPortEnumerationTests(unittest.TestCase):
    def test_includes_manual_ports_without_usb_identity(self):
        anonymous_port = types.SimpleNamespace(
            device="COM7", description="USB-SERIAL CH340", vid=None, pid=None, serial_number=None,
        )
        identified_port = types.SimpleNamespace(
            device="COM21", description="CP210x", vid=0x10C4, pid=0xEA60, serial_number="AIX",
        )
        serial_module = types.ModuleType("serial")
        tools_module = types.ModuleType("serial.tools")
        list_ports_module = types.ModuleType("serial.tools.list_ports")
        list_ports_module.comports = lambda: [anonymous_port, identified_port]
        tools_module.list_ports = list_ports_module
        serial_module.tools = tools_module

        with patch.dict(sys.modules, {
            "serial": serial_module,
            "serial.tools": tools_module,
            "serial.tools.list_ports": list_ports_module,
        }):
            options = list_serial_ports()

        self.assertEqual([option.device for option in options], ["COM7", "COM21"])
        self.assertEqual(options[0].identity, "")


if __name__ == "__main__":
    unittest.main()
