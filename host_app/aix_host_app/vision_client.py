from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6 import QtCore, QtNetwork


class InferenceRateLimiter:
    def __init__(self, interval_s: float = 1.0) -> None:
        self.interval_s = interval_s
        self._last: float | None = None

    def reset(self) -> None:
        self._last = None

    def accept(self, now: float) -> bool:
        if self._last is not None and now - self._last < self.interval_s:
            return False
        self._last = now
        return True


class ModelServiceManager(QtCore.QObject):
    ready_changed = QtCore.Signal(bool, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.ready = False
        self._started_by_us = False
        self._process = QtCore.QProcess(self)
        self._network = QtNetwork.QNetworkAccessManager(self)
        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._poll_health)
        self._process.finished.connect(self._process_finished)
        self._polling = False
        self._message = ""

    def start(self) -> None:
        self._polling = True
        self._poll_timer.start()
        self._poll_health()

    def stop(self) -> None:
        self._polling = False
        self._poll_timer.stop()
        if self._started_by_us and self._process.state() != QtCore.QProcess.ProcessState.NotRunning:
            self._process.terminate()
            if not self._process.waitForFinished(1500):
                self._process.kill()
        self._started_by_us = False
        self._set_ready(False, "模型服务已停止")

    def _poll_health(self) -> None:
        if not self._polling:
            return
        reply = self._network.get(QtNetwork.QNetworkRequest(QtCore.QUrl("http://127.0.0.1:8008/healthz")))
        reply.finished.connect(lambda reply=reply: self._handle_health(reply))

    def _handle_health(self, reply: QtNetwork.QNetworkReply) -> None:
        ok = reply.error() == QtNetwork.QNetworkReply.NetworkError.NoError and reply.attribute(QtNetwork.QNetworkRequest.Attribute.HttpStatusCodeAttribute) == 200
        reply.deleteLater()
        if ok:
            self._set_ready(True, "DA3 + SSDLite 已就绪")
            return
        if self._process.state() == QtCore.QProcess.ProcessState.NotRunning and not self._started_by_us:
            root = Path(__file__).resolve().parents[2] / "Models" / "DepthAnything3"
            script = root / "run_service.ps1"
            self._process.start("powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Port", "8008"])
            self._started_by_us = True
            self._set_ready(False, "正在启动 DA3 + SSDLite…")

    def _process_finished(self) -> None:
        if self._polling:
            self._set_ready(False, "模型服务启动失败或已退出")

    def _set_ready(self, ready: bool, message: str) -> None:
        if self.ready != ready or self._message != message:
            self.ready = ready
            self._message = message
            self.ready_changed.emit(ready, message)


class VisionInferenceClient(QtCore.QObject):
    frame_selected = QtCore.Signal(bytes, int, int)
    risk_received = QtCore.Signal(dict, bytes)
    analysis_error = QtCore.Signal(str)
    esp_sync_finished = QtCore.Signal(bool, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._network = QtNetwork.QNetworkAccessManager(self)
        self._reply: QtNetwork.QNetworkReply | None = None
        self._current_frame = b""
        self._ready = False
        self._session_id = ""
        self._limiter = InferenceRateLimiter()

    def set_service_ready(self, ready: bool) -> None:
        self._ready = ready

    def set_session_id(self, session_id: str) -> None:
        self._session_id = session_id
        self._limiter.reset()

    def submit_frame(self, data: bytes, frame_seq: int, capture_ts_ms: int) -> None:
        now = time.monotonic()
        if self._reply is not None or not self._limiter.accept(now):
            return
        self.frame_selected.emit(data, frame_seq, capture_ts_ms)
        if not self._ready or not self._session_id:
            self.analysis_error.emit("模型服务未就绪，已保存帧但未生成风险")
            return
        request = QtNetwork.QNetworkRequest(QtCore.QUrl("http://127.0.0.1:8008/v1/analyze"))
        request.setHeader(QtNetwork.QNetworkRequest.KnownHeaders.ContentTypeHeader, "image/jpeg")
        request.setRawHeader(b"X-Frame-Seq", str(frame_seq).encode())
        request.setRawHeader(b"X-Capture-Ts-Ms", str(capture_ts_ms).encode())
        request.setRawHeader(b"X-Session-Id", self._session_id.encode())
        self._current_frame = data
        self._reply = self._network.post(request, data)
        self._reply.finished.connect(self._handle_analysis)

    def send_risk_to_esp(self, endpoint: str, payload: dict) -> None:
        if not endpoint:
            return
        request = QtNetwork.QNetworkRequest(QtCore.QUrl(endpoint))
        request.setHeader(QtNetwork.QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        reply = self._network.post(request, json.dumps(payload, separators=(",", ":")).encode())
        reply.finished.connect(lambda reply=reply: self._handle_sync(reply))

    def _handle_analysis(self) -> None:
        reply = self._reply
        self._reply = None
        if reply is None:
            return
        if reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError:
            message = reply.errorString()
            reply.deleteLater()
            self.analysis_error.emit(f"视觉服务请求失败：{message}")
            return
        try:
            payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            reply.deleteLater()
            self.analysis_error.emit(f"视觉服务响应无效：{exc}")
            return
        reply.deleteLater()
        if payload.get("type") != "vision_risk":
            self.analysis_error.emit("视觉服务返回类型错误")
            return
        self.risk_received.emit(payload, self._current_frame)

    def _handle_sync(self, reply: QtNetwork.QNetworkReply) -> None:
        ok = reply.error() == QtNetwork.QNetworkReply.NetworkError.NoError and reply.attribute(QtNetwork.QNetworkRequest.Attribute.HttpStatusCodeAttribute) == 200
        message = "ESP 风险已确认" if ok else f"ESP 风险同步失败：{reply.errorString()}"
        reply.deleteLater()
        self.esp_sync_finished.emit(ok, message)
