from __future__ import annotations

import json

from PySide6 import QtCore, QtNetwork

from .networking import build_get_request


def normalize_service_url(url: str) -> str:
    return url.strip().rstrip("/")


def frame_identity_from_state(state: dict) -> tuple[str, int] | None:
    try:
        boot_id = str(state["boot_id"])
        frame_seq = int(state["upload"]["last_frame_seq"])
    except (KeyError, TypeError, ValueError):
        return None
    if len(boot_id) != 16 or frame_seq < 0:
        return None
    return boot_id, frame_seq


class PcChainClient(QtCore.QObject):
    health_received = QtCore.Signal(dict)
    state_received = QtCore.Signal(dict)
    frame_received = QtCore.Signal(bytes, int, int)
    error_changed = QtCore.Signal(str)

    def __init__(self, service_url: str, device_id: str, parent=None) -> None:
        super().__init__(parent)
        self.service_url = normalize_service_url(service_url)
        self.device_id = device_id
        self._network = QtNetwork.QNetworkAccessManager(self)
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._poll)
        self._state_reply: QtNetwork.QNetworkReply | None = None
        self._frame_reply: QtNetwork.QNetworkReply | None = None
        self._last_frame_identity: tuple[str, int] | None = None
        self._poll_count = 0

    def configure(self, service_url: str, device_id: str) -> None:
        self.service_url = normalize_service_url(service_url)
        self.device_id = device_id
        self._last_frame_identity = None

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
        self._poll()

    def stop(self) -> None:
        self._timer.stop()
        for reply in (self._state_reply, self._frame_reply):
            if reply is not None:
                reply.abort()
        self._state_reply = self._frame_reply = None

    def _poll(self) -> None:
        if not self.service_url or not self.device_id or self._state_reply is not None:
            return
        self._poll_count += 1
        if self._poll_count == 1 or self._poll_count % 10 == 0:
            health_reply = self._network.get(build_get_request(f"{self.service_url}/healthz", timeout_ms=1000))
            health_reply.finished.connect(lambda reply=health_reply: self._handle_health(reply))
        url = QtCore.QUrl(f"{self.service_url}/v1/state/latest")
        query = QtCore.QUrlQuery()
        query.addQueryItem("device_id", self.device_id)
        url.setQuery(query)
        self._state_reply = self._network.get(build_get_request(url.toString(), timeout_ms=1200))
        self._state_reply.finished.connect(self._handle_state)

    def _handle_health(self, reply: QtNetwork.QNetworkReply) -> None:
        try:
            if reply.error() == QtNetwork.QNetworkReply.NetworkError.NoError:
                payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
                if isinstance(payload, dict):
                    self.health_received.emit(payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        finally:
            reply.deleteLater()

    def _handle_state(self) -> None:
        reply = self._state_reply
        self._state_reply = None
        if reply is None:
            return
        if reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError:
            if reply.attribute(QtNetwork.QNetworkRequest.Attribute.HttpStatusCodeAttribute) != 404:
                self.error_changed.emit(f"PC 链路状态读取失败：{reply.errorString()}")
            reply.deleteLater()
            return
        try:
            payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.error_changed.emit(f"PC 链路状态无效：{exc}")
            reply.deleteLater()
            return
        reply.deleteLater()
        if not isinstance(payload, dict) or payload.get("type") != "chain_state":
            self.error_changed.emit("PC 链路状态协议不匹配")
            return
        self.state_received.emit(payload)
        identity = frame_identity_from_state(payload)
        if identity is not None and identity != self._last_frame_identity and self._frame_reply is None:
            self._request_frame(identity)

    def _request_frame(self, identity: tuple[str, int]) -> None:
        url = QtCore.QUrl(f"{self.service_url}/v1/frame/latest.jpg")
        query = QtCore.QUrlQuery()
        query.addQueryItem("device_id", self.device_id)
        url.setQuery(query)
        self._frame_reply = self._network.get(build_get_request(url.toString(), timeout_ms=1200))
        self._frame_reply.setProperty("boot_id", identity[0])
        self._frame_reply.setProperty("expected_seq", identity[1])
        self._frame_reply.finished.connect(self._handle_frame)

    def _handle_frame(self) -> None:
        reply = self._frame_reply
        self._frame_reply = None
        if reply is None:
            return
        if reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError:
            self.error_changed.emit(f"PC 最新帧读取失败：{reply.errorString()}")
            reply.deleteLater()
            return
        try:
            frame_seq = int(bytes(reply.rawHeader("X-Frame-Seq")).decode("ascii"))
            capture_ts_ms = int(bytes(reply.rawHeader("X-Capture-Ts-Ms")).decode("ascii"))
            boot_id = bytes(reply.rawHeader("X-Boot-Id")).decode("ascii")
        except (UnicodeDecodeError, ValueError):
            self.error_changed.emit("PC 最新帧响应头无效")
            reply.deleteLater()
            return
        expected = (str(reply.property("boot_id")), int(reply.property("expected_seq")))
        if (boot_id, frame_seq) != expected:
            self.error_changed.emit("PC 最新帧与链路状态不一致，已丢弃")
            reply.deleteLater()
            return
        data = bytes(reply.readAll())
        reply.deleteLater()
        if len(data) < 4 or data[:2] != b"\xff\xd8" or data[-2:] != b"\xff\xd9":
            self.error_changed.emit("PC 最新帧不是合法 JPEG")
            return
        self._last_frame_identity = expected
        self.frame_received.emit(data, frame_seq, capture_ts_ms)
