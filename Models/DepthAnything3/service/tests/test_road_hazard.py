import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))


class ManualExecutor:
    def __init__(self):
        self.jobs = []

    def submit(self, callback, *args, **kwargs):
        self.jobs.append((callback, args, kwargs))

    def run_all(self):
        while self.jobs:
            callback, args, kwargs = self.jobs.pop(0)
            callback(*args, **kwargs)

    def shutdown(self, wait=True):
        return None


def event_payload(**overrides):
    payload = {
        "event_id": "road-event-001",
        "device_id": "aix-helmet-01",
        "camera_id": "cam-right-01",
        "intersection_id": "intersection-a",
        "direction": "right",
        "object_type": "truck",
        "eta_ms": 5000,
        "severity": "high",
        "ttl_ms": 10000,
        "simulated": True,
        "message_code": "truck_right_eta_5s",
    }
    payload.update(overrides)
    return payload


def frame(device_id="aix-helmet-01", received_ts_ms=10_000, source_ip="192.168.137.20"):
    from frame_pipeline import FrameEnvelope
    return FrameEnvelope(
        device_id=device_id, boot_id="0123456789abcdef", frame_seq=7,
        capture_ts_ms=9000, source_ip=source_ip, jpeg=b"jpeg", received_ts_ms=received_ts_ms,
    )


class RoadHazardSchemaTests(unittest.TestCase):
    def test_accepts_demonstration_payload(self):
        from road_hazard import RoadHazardEvent
        event = RoadHazardEvent.from_payload(event_payload())
        self.assertEqual(event.direction, "right")
        self.assertEqual(event.eta_ms, 5000)

    def test_rejects_boolean_and_invalid_identifier_values(self):
        from road_hazard import RoadHazardValidationError, RoadHazardEvent
        with self.assertRaises(RoadHazardValidationError):
            RoadHazardEvent.from_payload(event_payload(eta_ms=True))
        with self.assertRaises(RoadHazardValidationError):
            RoadHazardEvent.from_payload(event_payload(event_id="not valid"))


class RoadHazardSenderTests(unittest.TestCase):
    def _sender(self, transport, *, now=10_500, sleep=lambda _: None):
        from frame_pipeline import ChainStateRepository, LatestFrameStore
        from road_hazard import RoadHazardSender
        self.store = LatestFrameStore()
        self.states = ChainStateRepository()
        self.store.put(frame())
        self.states.record_frame(frame())
        return RoadHazardSender(
            self.store, self.states, token="unit-secret", transport=transport,
            clock=lambda: now, sleep=sleep, executor=ManualExecutor(),
        )

    def test_sends_fresh_frame_context_with_remaining_ttl_and_strict_ack(self):
        sent = []
        def transport(url, token, payload, timeout_s):
            sent.append((url, token, payload, timeout_s))
            return {
                "type": "road_hazard_ack", "version": 1, "device_id": payload["device_id"],
                "boot_id": payload["boot_id"], "event_id": payload["event_id"],
                "accepted": True, "duplicate": False, "expires_in_ms": 9000,
                "severity": payload["severity"], "effective_rgb_pattern": "orange_blink_2hz",
                "voice_state": "not_configured", "error": "",
            }
        sender = self._sender(transport)
        sender.process(event_payload())
        self.assertEqual(sent[0][0], "http://192.168.137.20:8080/road-hazard")
        self.assertEqual(sent[0][1], "unit-secret")
        self.assertEqual(sent[0][2]["ttl_ms"], 10000)
        self.assertEqual(sent[0][2]["boot_id"], "0123456789abcdef")
        state = self.states.latest("aix-helmet-01")
        self.assertEqual(state["road_hazard"]["delivery"]["state"], "completed")
        self.assertEqual(state["road_hazard"]["ack"]["state"], "completed")
        self.assertEqual(state["road_hazard"]["effective_rgb_pattern"], "orange_blink_2hz")

    def test_delivery_ttl_counts_down_from_service_acceptance_not_worker_start(self):
        from frame_pipeline import ChainStateRepository, LatestFrameStore
        from road_hazard import RoadHazardSender, RoadHazardEvent
        now, executor, sent = [10_500], ManualExecutor(), []
        store, states = LatestFrameStore(), ChainStateRepository()
        store.put(frame()); states.record_frame(frame())
        def transport(_url, _token, payload, _timeout):
            sent.append(payload)
            return {
                "type": "road_hazard_ack", "version": 1, "device_id": payload["device_id"],
                "boot_id": payload["boot_id"], "event_id": payload["event_id"],
                "accepted": True, "duplicate": False, "expires_in_ms": 9000,
                "severity": payload["severity"], "effective_rgb_pattern": "x",
                "voice_state": "not_configured", "error": "",
            }
        sender = RoadHazardSender(store, states, token="t", transport=transport, clock=lambda: now[0], executor=executor)
        sender.accept(RoadHazardEvent.from_payload(event_payload()))
        now[0] = 11_000
        executor.run_all()
        self.assertEqual(sent[0]["ttl_ms"], 9500)

    def test_fails_when_frame_is_missing_stale_or_has_no_address(self):
        from frame_pipeline import ChainStateRepository, LatestFrameStore
        from road_hazard import RoadHazardSender
        for item in (None, frame(received_ts_ms=7_499), frame(source_ip="")):
            with self.subTest(item=item):
                store, states = LatestFrameStore(), ChainStateRepository()
                states.record_frame(frame())
                if item:
                    store.put(item)
                sender = RoadHazardSender(store, states, token="t", clock=lambda: 10_500, executor=ManualExecutor())
                sender.process(event_payload())
                state = states.latest("aix-helmet-01")
                self.assertEqual(state["road_hazard"]["delivery"]["state"], "failed")
                self.assertEqual(state["road_hazard"]["ack"]["state"], "failed")

    def test_retries_temporary_errors_and_stops_if_ttl_expires(self):
        attempts, sleeps = [], []
        current = [10_500]
        def clock(): return current[0]
        def sleep(delay):
            sleeps.append(delay)
            current[0] += int(delay * 1000)
        def transport(*_args):
            attempts.append(1)
            raise OSError("offline")
        from frame_pipeline import ChainStateRepository, LatestFrameStore
        from road_hazard import RoadHazardSender
        store, states = LatestFrameStore(), ChainStateRepository()
        store.put(frame()); states.record_frame(frame())
        sender = RoadHazardSender(store, states, token="t", transport=transport, clock=clock, sleep=sleep, executor=ManualExecutor())
        sender.process(event_payload(ttl_ms=600))
        self.assertEqual(len(attempts), 2)
        self.assertEqual(sleeps, [0, 0.2, 0.5])
        self.assertIn("TTL", states.latest("aix-helmet-01")["road_hazard"]["error"])

    def test_ack_identity_mismatch_and_rejection_are_terminal_failures(self):
        for ack_update in ({"boot_id": "wrong"}, {"event_id": "wrong"}, {"accepted": False, "error": "rejected"}):
            with self.subTest(ack_update=ack_update):
                def transport(_url, _token, payload, _timeout):
                    ack = {
                        "type": "road_hazard_ack", "version": 1, "device_id": payload["device_id"],
                        "boot_id": payload["boot_id"], "event_id": payload["event_id"],
                        "accepted": True, "duplicate": False, "expires_in_ms": 100,
                        "severity": payload["severity"], "effective_rgb_pattern": "x",
                        "voice_state": "not_configured", "error": "",
                    }
                    ack.update(ack_update)
                    return ack
                sender = self._sender(transport)
                sender.process(event_payload())
                state = self.states.latest("aix-helmet-01")["road_hazard"]
                self.assertEqual(state["ack"]["state"], "failed")
                self.assertEqual(state["attempts"], 1)


class RoadHazardApiTests(unittest.TestCase):
    def setUp(self):
        from app import create_app
        from road_hazard import RoadHazardSender
        from frame_pipeline import ChainStateRepository, LatestFrameStore
        self.executor = ManualExecutor()
        self.store, self.states = LatestFrameStore(), ChainStateRepository()
        self.store.put(frame()); self.states.record_frame(frame())
        self.sender = RoadHazardSender(
            self.store, self.states, token="unit-secret", executor=self.executor,
            clock=lambda: 10_500,
            transport=lambda *_: {
                "type": "road_hazard_ack", "version": 1, "device_id": "aix-helmet-01",
                "boot_id": "0123456789abcdef", "event_id": "road-event-001",
                "accepted": True, "duplicate": False, "expires_in_ms": 9500,
                "severity": "high", "effective_rgb_pattern": "orange_blink_2hz",
                "voice_state": "not_configured", "error": "",
            },
        )
        self.client = TestClient(create_app(None, token="unit-secret", start_worker=False, road_hazard_sender=self.sender))

    def test_returns_202_before_background_delivery_then_advances_state(self):
        response = self.client.post("/v1/road-hazards", json=event_payload())
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["event_id"], "road-event-001")
        self.assertEqual(len(self.executor.jobs), 1)
        self.executor.run_all()
        state = self.client.get("/v1/state/latest?device_id=aix-helmet-01").json()
        self.assertEqual(state["road_hazard"]["ack"]["state"], "completed")

    def test_is_idempotent_for_same_event_and_conflicts_for_changed_content(self):
        self.assertEqual(self.client.post("/v1/road-hazards", json=event_payload()).status_code, 202)
        self.assertEqual(self.client.post("/v1/road-hazards", json=event_payload()).status_code, 202)
        self.assertEqual(len(self.executor.jobs), 1)
        self.assertEqual(self.client.post("/v1/road-hazards", json=event_payload(severity="critical")).status_code, 409)

    def test_rejects_invalid_schema_with_422(self):
        response = self.client.post("/v1/road-hazards", json=event_payload(direction="up"))
        self.assertEqual(response.status_code, 422)
