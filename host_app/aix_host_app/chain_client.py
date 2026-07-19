from __future__ import annotations

import json
from copy import deepcopy

from PySide6 import QtCore, QtNetwork

from .networking import build_get_request


SNAPSHOT_POLL_INTERVAL_MS = 500


def normalize_service_url(url: str) -> str:
    return url.strip().rstrip("/")


def frame_identity_from_state(state: dict) -> tuple[str, int] | None:
    try:
        display = state["display"]
        if display.get("ready") is not True:
            return None
        boot_id = str(display["boot_id"])
        frame_seq = int(display["frame_seq"])
    except (KeyError, TypeError, ValueError):
        return None
    if len(boot_id) != 16 or frame_seq < 0:
        return None
    return boot_id, frame_seq


class PcChainClient(QtCore.QObject):
    health_received = QtCore.Signal(dict)
    state_received = QtCore.Signal(dict)
    snapshot_received = QtCore.Signal(bytes, int, int, dict)
    pneumatic_config_received = QtCore.Signal(dict)
    pneumatic_command_finished = QtCore.Signal(dict)
    pneumatic_error = QtCore.Signal(str)
    road_hazard_finished = QtCore.Signal(dict)
    road_hazard_error = QtCore.Signal(str)
    error_changed = QtCore.Signal(str)

    def __init__(self, service_url: str, device_id: str, *, token: str = "", parent=None) -> None:
        super().__init__(parent)
        self.service_url = normalize_service_url(service_url)
        self.device_id = device_id
        self.token = token
        self._network = QtNetwork.QNetworkAccessManager(self)
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(SNAPSHOT_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        self._state_reply: QtNetwork.QNetworkReply | None = None
        self._frame_reply: QtNetwork.QNetworkReply | None = None
        self._last_frame_identity: tuple[str, int] | None = None
        self._requested_identity: tuple[str, int] | None = None
        self._requested_state: dict | None = None
        self._queued_snapshot: tuple[tuple[str, int], dict] | None = None
        self._pneumatic_config_reply: QtNetwork.QNetworkReply | None = None
        self._poll_count = 0

    def configure(self, service_url: str, device_id: str) -> None:
        self.service_url = normalize_service_url(service_url)
        self.device_id = device_id
        self._last_frame_identity = None
        self._requested_identity = None
        self._requested_state = None
        self._queued_snapshot = None

    def send_road_hazard(self, payload: dict) -> None:
        if not self.service_url:
            self.road_hazard_error.emit("未配置 PC 服务地址")
            return
        if not self.token:
            self.road_hazard_error.emit("未配置路侧协同 Token；演示未下发")
            return
        request = build_get_request(f"{self.service_url}/v1/road-hazards", timeout_ms=1800)
        request.setHeader(QtNetwork.QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        request.setRawHeader(b"X-AIX-Token", self.token.encode("utf-8"))
        reply = self._network.post(request, json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        reply.finished.connect(lambda current=reply: self._handle_road_hazard(current))

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
        self._requested_identity = None
        self._requested_state = None
        self._queued_snapshot = None
        if self._pneumatic_config_reply is not None:
            self._pneumatic_config_reply.abort()
            self._pneumatic_config_reply = None

    def request_pneumatic_config(self) -> None:
        if not self.service_url or not self.device_id or self._pneumatic_config_reply is not None:
            return
        url = QtCore.QUrl(f"{self.service_url}/v1/pneumatic/config")
        query = QtCore.QUrlQuery()
        query.addQueryItem("device_id", self.device_id)
        url.setQuery(query)
        self._pneumatic_config_reply = self._network.get(build_get_request(url.toString(), timeout_ms=1500))
        self._pneumatic_config_reply.finished.connect(self._handle_pneumatic_config)

    def send_pneumatic_command(self, payload: dict) -> None:
        if not self.service_url or not self.device_id:
            self.pneumatic_error.emit("未配置 PC 服务地址或设备标识")
            return
        url = QtCore.QUrl(f"{self.service_url}/v1/pneumatic/command")
        query = QtCore.QUrlQuery()
        query.addQueryItem("device_id", self.device_id)
        url.setQuery(query)
        request = build_get_request(url.toString(), timeout_ms=1800)
        request.setHeader(QtNetwork.QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        reply = self._network.post(request, json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        reply.finished.connect(lambda current=reply: self._handle_pneumatic_command(current))

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
        identity = frame_identity_from_state(payload)
        if identity is None or identity == self._last_frame_identity:
            self.state_received.emit(payload)
        elif self._frame_reply is None:
            self._request_frame(identity, payload)
        elif identity == self._requested_identity:
            self._requested_state = deepcopy(payload)
        else:
            self._queued_snapshot = (identity, deepcopy(payload))

    def _handle_pneumatic_config(self) -> None:
        reply = self._pneumatic_config_reply
        self._pneumatic_config_reply = None
        if reply is None:
            return
        try:
            if reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError:
                self.pneumatic_error.emit(f"读取气动阈值失败：{reply.errorString()}")
                return
            payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
            if not isinstance(payload, dict) or payload.get("type") != "pneumatic_config":
                self.pneumatic_error.emit("气动阈值协议不匹配")
                return
            self.pneumatic_config_received.emit(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.pneumatic_error.emit(f"气动阈值响应无效：{exc}")
        finally:
            reply.deleteLater()

    def _handle_pneumatic_command(self, reply: QtNetwork.QNetworkReply) -> None:
        try:
            if reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError:
                self.pneumatic_error.emit(f"气动命令失败：{reply.errorString()}")
                return
            payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
            if not isinstance(payload, dict) or payload.get("type") != "pneumatic_ack":
                self.pneumatic_error.emit("气动命令响应协议不匹配")
                return
            self.pneumatic_command_finished.emit(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.pneumatic_error.emit(f"气动命令响应无效：{exc}")
        finally:
            reply.deleteLater()

    def _handle_road_hazard(self, reply: QtNetwork.QNetworkReply) -> None:
        try:
            if reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError:
                self.road_hazard_error.emit(f"协同事件提交失败：{reply.errorString()}")
                return
            payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
            if not isinstance(payload, dict) or payload.get("accepted") is not True or not payload.get("event_id"):
                self.road_hazard_error.emit("协同事件响应协议不匹配")
                return
            self.road_hazard_finished.emit(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.road_hazard_error.emit(f"协同事件响应无效：{exc}")
        finally:
            reply.deleteLater()

    def _request_frame(self, identity: tuple[str, int], state: dict) -> None:
        url = QtCore.QUrl(f"{self.service_url}/v1/frame/processed.jpg")
        query = QtCore.QUrlQuery()
        query.addQueryItem("device_id", self.device_id)
        url.setQuery(query)
        self._frame_reply = self._network.get(build_get_request(url.toString(), timeout_ms=1200))
        self._requested_identity = identity
        self._requested_state = deepcopy(state)
        self._frame_reply.finished.connect(self._handle_frame)

    def _start_queued_snapshot(self) -> None:
        queued = self._queued_snapshot
        self._queued_snapshot = None
        if queued is not None and queued[0] != self._last_frame_identity:
            self._request_frame(*queued)

    def _handle_frame(self) -> None:
        reply = self._frame_reply
        self._frame_reply = None
        expected = self._requested_identity
        state = self._requested_state
        self._requested_identity = None
        self._requested_state = None
        if reply is None:
            return
        if reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError:
            self.error_changed.emit(f"PC 最新帧读取失败：{reply.errorString()}")
            reply.deleteLater()
            self._start_queued_snapshot()
            return
        try:
            frame_seq = int(bytes(reply.rawHeader("X-Frame-Seq")).decode("ascii"))
            capture_ts_ms = int(bytes(reply.rawHeader("X-Capture-Ts-Ms")).decode("ascii"))
            boot_id = bytes(reply.rawHeader("X-Boot-Id")).decode("ascii")
        except (UnicodeDecodeError, ValueError):
            self.error_changed.emit("PC 最新帧响应头无效")
            reply.deleteLater()
            self._start_queued_snapshot()
            return
        if expected is None or (boot_id, frame_seq) != expected:
            self.error_changed.emit("PC 最新帧与链路状态不一致，已丢弃")
            reply.deleteLater()
            self._start_queued_snapshot()
            return
        data = bytes(reply.readAll())
        reply.deleteLater()
        if len(data) < 4 or data[:2] != b"\xff\xd8" or data[-2:] != b"\xff\xd9":
            self.error_changed.emit("PC 最新帧不是合法 JPEG")
            self._start_queued_snapshot()
            return
        self._last_frame_identity = expected
        self.snapshot_received.emit(data, frame_seq, capture_ts_ms, state or {})
        self._start_queued_snapshot()
