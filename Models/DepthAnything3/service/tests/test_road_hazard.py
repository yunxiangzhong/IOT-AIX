import sys
import json
import threading
import urllib.error
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
        return ManualFuture()

    def run_all(self):
        while self.jobs:
            callback, args, kwargs = self.jobs.pop(0)
            callback(*args, **kwargs)

    def shutdown(self, wait=True):
        return None


class ManualFuture:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True
        return True


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

    def test_requires_exact_fields_and_string_enums(self):
        from road_hazard import RoadHazardValidationError, RoadHazardEvent
        for invalid in (
            event_payload(unexpected="no"),
            {key: value for key, value in event_payload().items() if key != "camera_id"},
            event_payload(direction=[]),
            event_payload(severity={"high"}),
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(RoadHazardValidationError):
                    RoadHazardEvent.from_payload(invalid)


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
        now, monotonic, executor, sent = [10_500], [10.0], ManualExecutor(), []
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
        sender = RoadHazardSender(store, states, token="t", transport=transport, clock=lambda: now[0], monotonic_clock=lambda: monotonic[0], executor=executor)
        sender.accept(RoadHazardEvent.from_payload(event_payload()))
        now[0] = 11_000
        monotonic[0] = 10.5
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
        current, monotonic = [10_500], [10.0]
        def clock(): return current[0]
        def sleep(delay):
            sleeps.append(delay)
            current[0] += int(delay * 1000)
            monotonic[0] += delay
        def transport(*_args):
            attempts.append(1)
            raise OSError("offline")
        from frame_pipeline import ChainStateRepository, LatestFrameStore
        from road_hazard import RoadHazardSender
        store, states = LatestFrameStore(), ChainStateRepository()
        store.put(frame()); states.record_frame(frame())
        sender = RoadHazardSender(store, states, token="t", transport=transport, clock=clock, monotonic_clock=lambda: monotonic[0], sleep=sleep, executor=ManualExecutor())
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
                self.assertEqual(state["delivery"]["state"], "failed")
                self.assertEqual(state["ack"]["state"], "failed")
                self.assertEqual(state["attempts"], 1)

    def test_rejects_boolean_ack_version(self):
        from road_hazard import RoadHazardDeliveryError, RoadHazardEvent, RoadHazardSender
        event = RoadHazardEvent.from_payload(event_payload())
        ack = {
            "type": "road_hazard_ack", "version": True, "device_id": event.device_id,
            "boot_id": "0123456789abcdef", "event_id": event.event_id,
            "accepted": True, "duplicate": False, "expires_in_ms": 1,
            "severity": event.severity, "effective_rgb_pattern": "x",
            "voice_state": "not_configured", "error": "",
        }
        with self.assertRaises(RoadHazardDeliveryError):
            RoadHazardSender._validate_ack(ack, event, "0123456789abcdef")

    def test_monotonic_ttl_never_increases_when_wall_clock_rolls_back(self):
        from frame_pipeline import ChainStateRepository, LatestFrameStore
        from road_hazard import RoadHazardSender, RoadHazardEvent
        executor, sent, monotonic, wall = ManualExecutor(), [], [10.0], [10_500]
        store, states = LatestFrameStore(), ChainStateRepository()
        store.put(frame()); states.record_frame(frame())
        def transport(_url, _token, payload, _timeout):
            sent.append(payload["ttl_ms"])
            if len(sent) == 1:
                raise OSError("retry")
            return {
                "type": "road_hazard_ack", "version": 1, "device_id": payload["device_id"],
                "boot_id": payload["boot_id"], "event_id": payload["event_id"], "accepted": True,
                "duplicate": False, "expires_in_ms": 1, "severity": payload["severity"],
                "effective_rgb_pattern": "x", "voice_state": "not_configured", "error": "",
            }
        def sleep(delay):
            if delay == 0.2:
                monotonic[0] = 10.2
                wall[0] = 9_500
        sender = RoadHazardSender(store, states, token="t", transport=transport, clock=lambda: wall[0], monotonic_clock=lambda: monotonic[0], sleep=sleep, executor=executor)
        sender.process(RoadHazardEvent.from_payload(event_payload()))
        self.assertEqual(sent, [10000, 9800])

    def test_stop_rejects_new_events_cancels_pending_work_and_can_restart(self):
        from frame_pipeline import ChainStateRepository, LatestFrameStore
        from road_hazard import RoadHazardSender, RoadHazardEvent, RoadHazardUnavailableError
        executor = ManualExecutor()
        store, states = LatestFrameStore(), ChainStateRepository()
        store.put(frame()); states.record_frame(frame())
        sender = RoadHazardSender(store, states, token="t", executor=executor, max_pending=1)
        sender.accept(RoadHazardEvent.from_payload(event_payload()))
        with self.assertRaises(RoadHazardUnavailableError):
            sender.accept(RoadHazardEvent.from_payload(event_payload(event_id="road-event-002")))
        sender.stop()
        self.assertEqual(states.latest("aix-helmet-01")["road_hazard"]["delivery"]["state"], "failed")
        with self.assertRaises(RoadHazardUnavailableError):
            sender.accept(RoadHazardEvent.from_payload(event_payload(event_id="road-event-003")))
        sender.start()
        self.assertTrue(sender.accept(RoadHazardEvent.from_payload(event_payload(event_id="road-event-003"))))

    def test_exhausted_5xx_records_specific_error(self):
        from frame_pipeline import ChainStateRepository, LatestFrameStore
        from road_hazard import RoadHazardSender
        store, states = LatestFrameStore(), ChainStateRepository()
        store.put(frame()); states.record_frame(frame())
        def transport(*_args):
            raise urllib.error.HTTPError("http://device", 503, "unavailable", {}, None)
        sender = RoadHazardSender(store, states, token="t", transport=transport, clock=lambda: 10_500, sleep=lambda _: None, executor=ManualExecutor())
        sender.process(event_payload())
        self.assertEqual(states.latest("aix-helmet-01")["road_hazard"]["error"], "device HTTP 503")

    def test_stop_during_running_transport_cannot_complete_event(self):
        from frame_pipeline import ChainStateRepository, LatestFrameStore
        from road_hazard import RoadHazardSender, RoadHazardEvent
        store, states, executor = LatestFrameStore(), ChainStateRepository(), ManualExecutor()
        store.put(frame()); states.record_frame(frame())
        sender = None
        def transport(_url, _token, payload, _timeout):
            sender.stop()
            return {
                "type": "road_hazard_ack", "version": 1, "device_id": payload["device_id"],
                "boot_id": payload["boot_id"], "event_id": payload["event_id"], "accepted": True,
                "duplicate": False, "expires_in_ms": 1, "severity": payload["severity"],
                "effective_rgb_pattern": "x", "voice_state": "not_configured", "error": "",
            }
        sender = RoadHazardSender(store, states, token="t", transport=transport, clock=lambda: 10_500, executor=executor)
        sender.accept(RoadHazardEvent.from_payload(event_payload()))
        executor.run_all()
        state = states.latest("aix-helmet-01")["road_hazard"]
        self.assertEqual(state["delivery"]["state"], "failed")
        self.assertEqual(state["ack"]["state"], "failed")

    def test_accept_stop_race_only_returns_mapped_outcomes(self):
        from frame_pipeline import ChainStateRepository, LatestFrameStore
        from road_hazard import RoadHazardSender, RoadHazardEvent, RoadHazardUnavailableError
        store, states, executor = LatestFrameStore(), ChainStateRepository(), ManualExecutor()
        store.put(frame()); states.record_frame(frame())
        sender = RoadHazardSender(store, states, token="t", executor=executor, max_pending=32)
        barrier, outcomes = threading.Barrier(2), []
        def accept():
            barrier.wait()
            try:
                outcomes.append(sender.accept(RoadHazardEvent.from_payload(event_payload(event_id="race-event"))))
            except RoadHazardUnavailableError:
                outcomes.append("unavailable")
        thread = threading.Thread(target=accept)
        thread.start(); barrier.wait(); sender.stop(); thread.join()
        self.assertEqual(len(outcomes), 1)
        self.assertIn(outcomes[0], (True, "unavailable"))
        if outcomes[0] is True:
            self.assertEqual(states.latest("aix-helmet-01")["road_hazard"]["delivery"]["state"], "failed")


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
        self.headers = {"X-AIX-Token": "unit-secret"}

    def test_returns_202_before_background_delivery_then_advances_state(self):
        response = self.client.post("/v1/road-hazards", json=event_payload(), headers=self.headers)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["event_id"], "road-event-001")
        self.assertEqual(len(self.executor.jobs), 1)
        self.executor.run_all()
        state = self.client.get("/v1/state/latest?device_id=aix-helmet-01").json()
        self.assertEqual(state["road_hazard"]["ack"]["state"], "completed")

    def test_is_idempotent_for_same_event_and_conflicts_for_changed_content(self):
        self.assertEqual(self.client.post("/v1/road-hazards", json=event_payload(), headers=self.headers).status_code, 202)
        self.assertEqual(self.client.post("/v1/road-hazards", json=event_payload(), headers=self.headers).status_code, 202)
        self.assertEqual(len(self.executor.jobs), 1)
        self.assertEqual(self.client.post("/v1/road-hazards", json=event_payload(severity="critical"), headers=self.headers).status_code, 409)

    def test_rejects_invalid_schema_with_422(self):
        response = self.client.post("/v1/road-hazards", json=event_payload(direction="up"), headers=self.headers)
        self.assertEqual(response.status_code, 422)

    def test_rejects_malformed_json_and_missing_link_token(self):
        self.assertEqual(self.client.post("/v1/road-hazards", content=b"{", headers={"content-type": "application/json", "X-AIX-Token": "unit-secret"}).status_code, 422)
        self.assertEqual(self.client.post("/v1/road-hazards", json=event_payload()).status_code, 401)

    def test_maps_bounded_queue_to_503_before_creating_event(self):
        from app import create_app
        from road_hazard import RoadHazardSender
        from frame_pipeline import ChainStateRepository, LatestFrameStore
        store, states, executor = LatestFrameStore(), ChainStateRepository(), ManualExecutor()
        store.put(frame()); states.record_frame(frame())
        sender = RoadHazardSender(store, states, token="unit-secret", executor=executor, max_pending=1)
        with TestClient(create_app(None, token="unit-secret", start_worker=False, road_hazard_sender=sender)) as client:
            self.assertEqual(client.post("/v1/road-hazards", json=event_payload(), headers=self.headers).status_code, 202)
            self.assertEqual(client.post("/v1/road-hazards", json=event_payload(event_id="road-event-004"), headers=self.headers).status_code, 503)
        self.assertEqual(states.latest("aix-helmet-01")["road_hazard"]["event_id"], "road-event-001")
