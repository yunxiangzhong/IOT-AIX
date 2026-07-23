from __future__ import annotations

import json
import uuid
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


def build_scenario_request(url: str, link_token: str) -> QtNetwork.QNetworkRequest:
    request = build_get_request(url, timeout_ms=2500)
    request.setHeader(QtNetwork.QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
    request.setRawHeader(b"X-AIX-Token", link_token.encode("utf-8"))
    return request


def build_demo_reset_payload(device_id: str, session_id: str) -> dict:
    return {"device_id": device_id, "session_id": session_id}


def build_collision_ack_payload(
    device_id: str, boot_id: str, impact_count: int
) -> dict:
    if len(boot_id) != 16 or any(ch not in "0123456789abcdefABCDEF" for ch in boot_id):
        raise ValueError("invalid collision boot_id")
    if isinstance(impact_count, bool) or impact_count < 0:
        raise ValueError("invalid collision impact_count")
    return {
        "device_id": device_id,
        "boot_id": boot_id.lower(),
        "impact_count": impact_count,
    }


class PcChainClient(QtCore.QObject):
    health_received = QtCore.Signal(dict)
    state_received = QtCore.Signal(dict)
    snapshot_received = QtCore.Signal(bytes, int, int, dict)
    pneumatic_config_received = QtCore.Signal(dict)
    pneumatic_command_finished = QtCore.Signal(dict)
    pneumatic_error = QtCore.Signal(str)
    error_changed = QtCore.Signal(str)
    scenario_dispatched = QtCore.Signal(dict)
    scenario_dispatch_error = QtCore.Signal(str)
    demo_mode_received = QtCore.Signal(dict)
    demo_mode_error = QtCore.Signal(str)
    demo_action_dispatched = QtCore.Signal(dict)
    demo_action_error = QtCore.Signal(str)
    demo_reset_finished = QtCore.Signal(dict)
    demo_reset_error = QtCore.Signal(str)
    semantic_record_received = QtCore.Signal(dict, object)
    semantic_record_error = QtCore.Signal(str)
    collision_ack_finished = QtCore.Signal(dict)
    collision_ack_error = QtCore.Signal(str)

    def __init__(self, service_url: str, device_id: str, *, link_token: str = "", parent=None) -> None:
        super().__init__(parent)
        self.service_url = normalize_service_url(service_url)
        self.device_id = device_id
        self.link_token = link_token.strip()
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
        self._demo_session_id = ""
        self._demo_heartbeat_timer = QtCore.QTimer(self)
        self._demo_heartbeat_timer.setInterval(5000)
        self._demo_heartbeat_timer.timeout.connect(self.send_demo_session_heartbeat)
        self._semantic_pending: dict[str, dict] = {}
        self._semantic_completed: set[str] = set()

    def configure(self, service_url: str, device_id: str) -> None:
        self.service_url = normalize_service_url(service_url)
        self.device_id = device_id
        self._last_frame_identity = None
        self._requested_identity = None
        self._requested_state = None
        self._queued_snapshot = None
        self._demo_session_id = ""
        self._demo_heartbeat_timer.stop()
        self._semantic_pending.clear()
        self._semantic_completed.clear()

    def is_link_ready(self) -> bool:
        """True when the client has a service URL, device ID, and link token configured."""
        return bool(self.service_url and self.device_id and self.link_token)

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
        for pending in list(self._semantic_pending.values()):
            for reply in pending.get("replies", []):
                reply.abort()
        self._semantic_pending.clear()

    def request_pneumatic_config(self) -> None:
        if not self.service_url or not self.device_id or self._pneumatic_config_reply is not None:
            return
        url = QtCore.QUrl(f"{self.service_url}/v1/pneumatic/config")
        query = QtCore.QUrlQuery()
        query.addQueryItem("device_id", self.device_id)
        url.setQuery(query)
        self._pneumatic_config_reply = self._network.get(build_get_request(url.toString(), timeout_ms=1500))
        self._pneumatic_config_reply.finished.connect(self._handle_pneumatic_config)

    def send_scenario_risk(self, scene_id: int) -> None:
        """POST /v1/scenario-risk to PC backend for real ESP32 dispatch."""
        if not self.service_url or not self.device_id:
            self.scenario_dispatch_error.emit("未配置 PC 服务地址或设备标识")
            return
        if not self.link_token:
            self.scenario_dispatch_error.emit("未配置 AIX 链路令牌，已阻止场景下发")
            return
        if self._last_frame_identity is None:
            self.scenario_dispatch_error.emit("链路未就绪：未收到 ESP32 帧数据，无法路由场景事件")
            return
        url = QtCore.QUrl(f"{self.service_url}/v1/scenario-risk")
        request = build_scenario_request(url.toString(), self.link_token)
        body = json.dumps({"scene_id": scene_id, "device_id": self.device_id},
                          separators=(",", ":")).encode("utf-8")
        reply = self._network.post(request, body)
        reply.finished.connect(lambda r=reply: self._handle_scenario_risk(r))

    def _post_json(self, endpoint: str, payload: dict, finished) -> None:
        request = build_scenario_request(f"{self.service_url}{endpoint}", self.link_token)
        reply = self._network.post(request, json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        reply.finished.connect(lambda r=reply: finished(r))

    def send_collision_ack(self, boot_id: str, impact_count: int) -> None:
        if not self.is_link_ready():
            self.collision_ack_error.emit("真实链路未就绪，无法清除模拟 Airbag 白灯")
            return
        try:
            payload = build_collision_ack_payload(
                self.device_id, boot_id, impact_count
            )
        except ValueError as exc:
            self.collision_ack_error.emit(str(exc))
            return
        self._post_json(
            "/v1/collision-indicator/ack", payload, self._handle_collision_ack
        )

    def _handle_collision_ack(self, reply: QtNetwork.QNetworkReply) -> None:
        try:
            payload = self._read_json_reply(reply)
            if (
                reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError
                or payload.get("accepted") is not True
            ):
                self.collision_ack_error.emit(
                    str(payload.get("detail") or reply.errorString())
                )
                return
            self.collision_ack_finished.emit(payload)
        finally:
            reply.deleteLater()

    def send_demo_session_start(self) -> None:
        if not self.is_link_ready() or self._last_frame_identity is None:
            self.demo_mode_error.emit("真实链路未就绪：没有可用头盔最新帧，无法建立模拟通道")
            return
        self._demo_session_id = f"demo-{uuid.uuid4().hex[:12]}"
        self._post_json("/v1/demo/session/start", {
            "device_id": self.device_id, "session_id": self._demo_session_id, "lease_ms": 15_000,
        }, self._handle_demo_session_start)

    def _handle_demo_session_start(self, reply: QtNetwork.QNetworkReply) -> None:
        self._handle_demo_mode_reply(reply, starting=True)

    def send_demo_session_heartbeat(self) -> None:
        if not self._demo_session_id:
            return
        self._post_json("/v1/demo/session/heartbeat", {
            "device_id": self.device_id, "session_id": self._demo_session_id, "lease_ms": 15_000,
        }, lambda reply: self._handle_demo_mode_reply(reply, starting=False, heartbeat=True))

    def restore_real_link(self) -> None:
        if not self._demo_session_id:
            self.demo_mode_received.emit({"mode": "real", "session_id": "", "lease_remaining_ms": 0})
            return
        self._post_json("/v1/demo/session/end", {
            "device_id": self.device_id, "session_id": self._demo_session_id,
        }, self._handle_demo_session_end)

    def _handle_demo_session_end(self, reply: QtNetwork.QNetworkReply) -> None:
        try:
            payload = self._read_json_reply(reply)
            if reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError or not payload.get("accepted"):
                self.demo_mode_error.emit(self._map_demo_error(reply, payload))
                return
            self._demo_heartbeat_timer.stop()
            self._demo_session_id = ""
            self.demo_mode_received.emit(payload)
        finally:
            reply.deleteLater()

    def _handle_demo_mode_reply(self, reply: QtNetwork.QNetworkReply, *, starting: bool, heartbeat: bool = False) -> None:
        try:
            payload = self._read_json_reply(reply)
            if reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError or not payload.get("accepted"):
                self.demo_mode_error.emit(self._map_demo_error(reply, payload))
                if starting:
                    self._demo_session_id = ""
                return
            if starting:
                self._demo_heartbeat_timer.start()
            self.demo_mode_received.emit(payload)
        finally:
            reply.deleteLater()

    @staticmethod
    def _read_json_reply(reply: QtNetwork.QNetworkReply) -> dict:
        raw = bytes(reply.readAll())
        try:
            payload = json.loads(raw.decode("utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _map_demo_error(reply: QtNetwork.QNetworkReply, payload: dict) -> str:
        detail = str(payload.get("detail", ""))
        status = reply.attribute(QtNetwork.QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status == 401:
            return "PC 鉴权失败：链路令牌无效"
        if status == 503:
            return f"模拟通道不可达：{detail or reply.errorString()}"
        if status == 409:
            return f"模拟通道状态冲突：{detail or reply.errorString()}"
        return f"模拟通道请求失败：{detail or reply.errorString()}"

    def send_demo_action(self, scene_id: int) -> None:
        if not self._demo_session_id:
            self.demo_action_error.emit("模拟通道未启用，请先进入模拟模式")
            return
        if self._last_frame_identity is None:
            self.demo_action_error.emit("未收到头盔最新帧，无法下发模拟动作")
            return
        self._post_json("/v1/demo/action", {
            "device_id": self.device_id, "session_id": self._demo_session_id, "scene_id": scene_id,
        }, self._handle_demo_action)

    def send_demo_action_reset(self) -> None:
        if not self._demo_session_id or self._last_frame_identity is None:
            return
        self._post_json(
            "/v1/demo/action/reset",
            build_demo_reset_payload(self.device_id, self._demo_session_id),
            self._handle_demo_action_reset,
        )

    def _handle_demo_action(self, reply: QtNetwork.QNetworkReply) -> None:
        try:
            payload = self._read_json_reply(reply)
            if reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError or not payload.get("accepted"):
                self.demo_action_error.emit(self._map_demo_error(reply, payload))
                return
            self.demo_action_dispatched.emit(payload)
        finally:
            reply.deleteLater()

    def _handle_demo_action_reset(self, reply: QtNetwork.QNetworkReply) -> None:
        try:
            payload = self._read_json_reply(reply)
            if reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError or not payload.get("accepted"):
                self.demo_reset_error.emit(self._map_demo_error(reply, payload))
                return
            self.demo_reset_finished.emit(payload)
        finally:
            reply.deleteLater()

    def _handle_scenario_risk(self, reply: QtNetwork.QNetworkReply) -> None:
        try:
            http_status = reply.attribute(QtNetwork.QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            raw = bytes(reply.readAll())
            if reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError:
                detail = ""
                try:
                    body = json.loads(raw.decode("utf-8"))
                    detail = str(body.get("detail", ""))
                except Exception:
                    pass
                message = self._map_scenario_error(http_status, detail, reply.errorString())
                self.scenario_dispatch_error.emit(message)
                return
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict) or not payload.get("accepted"):
                self.scenario_dispatch_error.emit("场景下发被 PC 服务拒绝")
                return
            self.scenario_dispatched.emit(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.scenario_dispatch_error.emit(f"场景下发响应无效：{exc}")
        finally:
            reply.deleteLater()

    @staticmethod
    def _map_scenario_error(http_status: int | None, detail: str, fallback: str) -> str:
        """Map PC backend HTTP response to user-facing Chinese error messages."""
        if http_status == 401:
            return "PC 鉴权失败：链路令牌无效"
        if http_status == 503:
            if "no recent frame" in detail.lower():
                return "未收到头盔最新帧：ESP32 尚未上传检测画面"
            if "health endpoint" in detail.lower() or "unreachable" in detail.lower():
                return f"ESP32:8080 不可达：{detail}"
            return f"ESP32 服务不可用：{detail or fallback}"
        if http_status == 502:
            if "身份不匹配" in detail or "identity mismatch" in detail.lower():
                return f"ESP32 身份不匹配：{detail}"
            if "拒绝" in detail or "rejected" in detail.lower():
                return f"ESP32 拒绝风险事件：{detail}"
            if "不可达" in detail or "call failed" in detail.lower():
                return f"ESP32:8080 不可达：{detail}"
            return f"ESP32 通信失败：{detail or fallback}"
        if http_status in (422, 400):
            return f"场景请求参数无效：{detail or fallback}"
        return fallback

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
        self._consider_semantic(payload)
        identity = frame_identity_from_state(payload)
        if identity is None or identity == self._last_frame_identity:
            self.state_received.emit(payload)
        elif self._frame_reply is None:
            self._request_frame(identity, payload)
        elif identity == self._requested_identity:
            self._requested_state = deepcopy(payload)
        else:
            self._queued_snapshot = (identity, deepcopy(payload))

    def _consider_semantic(self, state: dict) -> None:
        semantic = state.get("semantic")
        if not isinstance(semantic, dict):
            return
        recent = semantic.get("recent", [])
        records = [item for item in recent if isinstance(item, dict)]
        records.append(semantic)
        for record in records:
            self._consider_semantic_record(record)

    def _consider_semantic_record(self, semantic: dict) -> None:
        analysis_id = str(semantic.get("analysis_id", ""))
        if (
            not analysis_id
            or analysis_id in self._semantic_completed
            or analysis_id in self._semantic_pending
        ):
            return
        pending = {"record": deepcopy(semantic), "frames": {}, "replies": []}
        self._semantic_pending[analysis_id] = pending
        for index in (1, 2, 3):
            url = (
                f"{self.service_url}/v1/semantic/{analysis_id}/keyframes/{index}.jpg"
            )
            reply = self._network.get(build_get_request(url, timeout_ms=1800))
            pending["replies"].append(reply)
            reply.finished.connect(
                lambda current=reply, aid=analysis_id, idx=index:
                self._handle_semantic_keyframe(current, aid, idx)
            )

    def _handle_semantic_keyframe(
        self, reply: QtNetwork.QNetworkReply, analysis_id: str, index: int
    ) -> None:
        pending = self._semantic_pending.get(analysis_id)
        if pending is None:
            reply.deleteLater()
            return
        try:
            if reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError:
                self._semantic_pending.pop(analysis_id, None)
                self.semantic_record_error.emit(
                    f"语义关键帧 {index} 下载失败：{reply.errorString()}"
                )
                return
            data = bytes(reply.readAll())
            if len(data) < 4 or data[:2] != b"\xff\xd8" or data[-2:] != b"\xff\xd9":
                self._semantic_pending.pop(analysis_id, None)
                self.semantic_record_error.emit(f"语义关键帧 {index} 不是合法 JPEG")
                return
            pending["frames"][index] = data
            if len(pending["frames"]) == 3:
                self._semantic_pending.pop(analysis_id, None)
                self._semantic_completed.add(analysis_id)
                frames = tuple(pending["frames"][i] for i in (1, 2, 3))
                self.semantic_record_received.emit(pending["record"], frames)
        finally:
            reply.deleteLater()

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
            # Frame identity doesn't match what was requested — the state has
            # advanced since we asked.  Discard silently and try the next one.
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
