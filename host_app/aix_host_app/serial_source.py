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
    if remembered_identity:
        for option in options:
            if option.identity == remembered_identity:
                return option
    cp210x = [option for option in options if option.vid == 0x10C4 and option.pid == 0xEA60]
    if len(cp210x) == 1:
        return cp210x[0]
    return options[0] if len(options) == 1 else None


def list_serial_ports() -> list[SerialPortOption]:
    try:
        from serial.tools import list_ports
    except Exception:
        return []

    options: list[SerialPortOption] = []
    for port in list_ports.comports():
        if port.vid is None or port.pid is None:
            continue
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
