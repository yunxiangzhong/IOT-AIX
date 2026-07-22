from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from PySide6 import QtCore


@dataclass(frozen=True)
class SerialPortOption:
    device: str
    description: str
    vid: int | None = None
    pid: int | None = None
    serial_number: str = ""

    @property
    def label(self) -> str:
        if self.description and self.description != "n/a":
            return f"{self.device}  {self.description}"
        return self.device

    @property
    def identity(self) -> str:
        if self.vid is None or self.pid is None:
            return ""
        return f"{self.vid:04X}:{self.pid:04X}:{self.serial_number}"


def preferred_serial_port(options: list[SerialPortOption], remembered_identity: str = "") -> SerialPortOption | None:
    """Return an unambiguous ESP32 serial candidate without opening other ports.

    Port names are only a convenience signal.  A remembered hardware identity is
    preferred, and a name/USB-ID candidate is used only when it is the sole
    likely development-board adapter.  Otherwise the caller must leave the
    choice to the operator.
    """
    if remembered_identity:
        for option in options:
            if option.identity == remembered_identity:
                return option
        # Windows can temporarily omit serial_number during USB re-enumeration.
        # Keep a unique adapter with the same VID/PID selected, but never guess
        # when two adapters of that type are present.
        remembered_usb_id = _usb_id_from_identity(remembered_identity)
        if remembered_usb_id is not None:
            same_adapter = [
                option for option in options
                if (option.vid, option.pid) == remembered_usb_id
            ]
            if len(same_adapter) == 1:
                return same_adapter[0]
        # Some Windows driver enumerations expose only the adapter name.  With
        # exactly one known ESP32 adapter name, it is still safe to open the
        # port and wait for real AIX telemetry before treating it as connected.
        named_candidates = [
            option for option in options
            if _looks_like_remembered_adapter(option, remembered_usb_id)
        ]
        if len(named_candidates) == 1:
            return named_candidates[0]
        # 有目标身份但未找到匹配端口，禁止回退到其他设备
        return None

    candidates = [option for option in options if _looks_like_esp32_adapter(option)]
    if len(candidates) == 1:
        return candidates[0]

    # A single non-Bluetooth port is still safe to preselect.  It remains a
    # user-confirmed manual connection until valid AIX telemetry is received.
    non_bluetooth = [option for option in options if not _looks_like_bluetooth(option)]
    return non_bluetooth[0] if len(non_bluetooth) == 1 else None


def _looks_like_esp32_adapter(option: SerialPortOption) -> bool:
    """Recognize common ESP32 development-board USB/UART adapters by ID/name."""
    if option.vid == 0x303A:  # Espressif native USB / USB-JTAG-Serial
        return True
    if option.vid == 0x10C4 and option.pid == 0xEA60:  # Silicon Labs CP210x
        return True

    name = f"{option.description} {option.device}".casefold()
    return any(marker in name for marker in (
        "esp32", "espressif", "cp210", "silicon labs",
    ))


def _usb_id_from_identity(identity: str) -> tuple[int, int] | None:
    parts = identity.split(":", 2)
    if len(parts) != 3:
        return None
    try:
        return int(parts[0], 16), int(parts[1], 16)
    except ValueError:
        return None


def _looks_like_remembered_adapter(
    option: SerialPortOption,
    remembered_usb_id: tuple[int, int] | None,
) -> bool:
    """Use a name-only fallback only for the same saved adapter family."""
    if remembered_usb_id == (0x10C4, 0xEA60):
        name = option.description.casefold()
        return "cp210" in name or "silicon labs" in name
    if remembered_usb_id is not None and remembered_usb_id[0] == 0x303A:
        name = option.description.casefold()
        return "esp32" in name or "espressif" in name
    return False


def _looks_like_bluetooth(option: SerialPortOption) -> bool:
    return "bluetooth" in option.description.casefold() or "蓝牙" in option.description


def has_matching_port(options: list[SerialPortOption], remembered_identity: str = "") -> bool:
    """检查是否有端口与保存的目标身份匹配，供 UI 层显示提示。"""
    if not remembered_identity:
        return False
    return any(option.identity == remembered_identity for option in options)


def list_serial_ports() -> list[SerialPortOption]:
    try:
        from serial.tools import list_ports
    except Exception:
        return []

    options: list[SerialPortOption] = []
    for port in list_ports.comports():
        options.append(SerialPortOption(
            device=port.device,
            description=port.description or "n/a",
            vid=port.vid,
            pid=port.pid,
            serial_number=port.serial_number or "",
        ))
    return options


class SerialLineReader(QtCore.QThread):
    line_received = QtCore.Signal(str)
    error_changed = QtCore.Signal(str)
    state_changed = QtCore.Signal(str)

    def __init__(self, port: str, baudrate: int, parent=None) -> None:
        super().__init__(parent)
        self._port = port
        self._baudrate = baudrate
        self._stop_requested = False
        self._serial = None
        self._write_lock = Lock()

    def stop(self) -> None:
        self._stop_requested = True
        serial_obj = self._serial
        if serial_obj is not None:
            try:
                serial_obj.close()
            except Exception:
                pass

    def write_line(self, line: str) -> bool:
        serial_obj = self._serial
        if serial_obj is None:
            return False
        text = line.rstrip("\r\n") + "\n"
        try:
            with self._write_lock:
                serial_obj.write(text.encode("utf-8"))
            return True
        except Exception as exc:
            self.error_changed.emit(f"串口写入失败：{exc}")
            return False

    def run(self) -> None:
        try:
            import serial
        except Exception as exc:
            self.error_changed.emit(f"缺少 pyserial，无法打开串口：{exc}")
            self.state_changed.emit("disconnected")
            return

        try:
            self._serial = serial.Serial(self._port, self._baudrate, timeout=0.2)
            self.state_changed.emit("connected")
            while not self._stop_requested:
                raw = self._serial.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    self.line_received.emit(line)
        except Exception as exc:
            if not self._stop_requested:
                self.error_changed.emit(f"串口断开或读取失败：{exc}")
        finally:
            if self._serial is not None:
                try:
                    self._serial.close()
                except Exception:
                    pass
                self._serial = None
            self.state_changed.emit("disconnected")
