from __future__ import annotations

import sys
import time

from PySide6 import QtCore

from .camera import CameraFrame, CameraSourceConfig


class CameraReader(QtCore.QThread):
    frame_received = QtCore.Signal(object)
    error_changed = QtCore.Signal(str)
    state_changed = QtCore.Signal(str)

    def __init__(self, config: CameraSourceConfig, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._stop_requested = False
        self._capture = None

    def stop(self) -> None:
        self._stop_requested = True
        capture = self._capture
        if capture is not None:
            try:
                capture.release()
            except Exception:
                pass

    def run(self) -> None:
        try:
            import cv2
        except Exception as exc:
            self.error_changed.emit(f"缺少 opencv-python-headless，无法打开摄像头：{exc}")
            self.state_changed.emit("disconnected")
            return

        try:
            capture_input = self._config.capture_input()
            source_label = self._config.source_label()
        except ValueError as exc:
            self.error_changed.emit(str(exc))
            self.state_changed.emit("disconnected")
            return

        try:
            if self._config.kind == "local" and sys.platform.startswith("win"):
                self._capture = cv2.VideoCapture(capture_input, cv2.CAP_DSHOW)
            else:
                self._capture = cv2.VideoCapture(capture_input)

            if not self._capture.isOpened():
                self.error_changed.emit(f"摄像头打不开：{source_label}")
                self.state_changed.emit("disconnected")
                return

            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._config.width)
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._config.height)
            self._capture.set(cv2.CAP_PROP_FPS, self._config.fps)

            self.state_changed.emit("connected")
            frame_id = 0
            frame_interval = max(1.0 / float(self._config.fps), 0.01)
            next_emit = time.monotonic()

            while not self._stop_requested:
                ok, frame_bgr = self._capture.read()
                if self._stop_requested:
                    break
                if not ok or frame_bgr is None:
                    self.error_changed.emit("视频流中断或没有读取到画面")
                    break

                now = time.monotonic()
                if now < next_emit:
                    time.sleep(min(next_emit - now, 0.02))
                    continue
                next_emit = now + frame_interval

                if frame_bgr.shape[1] != self._config.width or frame_bgr.shape[0] != self._config.height:
                    frame_bgr = cv2.resize(frame_bgr, (self._config.width, self._config.height))

                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                height, width, channels = frame_rgb.shape
                frame_id += 1
                self.frame_received.emit(
                    CameraFrame(
                        frame_id=frame_id,
                        ts_ms=int(time.time() * 1000),
                        width=width,
                        height=height,
                        source=source_label,
                        rgb_data=frame_rgb.tobytes(),
                        bytes_per_line=width * channels,
                    )
                )
        except Exception as exc:
            if not self._stop_requested:
                self.error_changed.emit(f"摄像头读取失败：{exc}")
        finally:
            if self._capture is not None:
                try:
                    self._capture.release()
                except Exception:
                    pass
                self._capture = None
            self.state_changed.emit("disconnected")
