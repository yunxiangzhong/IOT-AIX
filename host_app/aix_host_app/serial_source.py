from __future__ import annotations

from dataclasses import dataclass

from PySide6 import QtCore


@dataclass(frozen=True)
class SerialPortOption:
    device: str
    description: str

    @property
    def label(self) -> str:
        if self.description and self.description != "n/a":
            return f"{self.device}  {self.description}"
        return self.device


def list_serial_ports() -> list[SerialPortOption]:
    try:
        from serial.tools import list_ports
    except Exception:
        return []

    options: list[SerialPortOption] = []
    for port in list_ports.comports():
        options.append(SerialPortOption(device=port.device, description=port.description or "n/a"))
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

    def stop(self) -> None:
        self._stop_requested = True
        serial_obj = self._serial
        if serial_obj is not None:
            try:
                serial_obj.close()
            except Exception:
                pass

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
