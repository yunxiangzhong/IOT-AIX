import json
import unittest

from aix_host_app.vision import VisionEventBridge, VisionFeatureEvent


class FakeWriter:
    def __init__(self):
        self.lines = []

    def write_line(self, line: str) -> bool:
        self.lines.append(line)
        return True


class VisionEventBridgeTests(unittest.TestCase):
    def test_sends_first_event_with_sequence_one(self):
        writer = FakeWriter()
        bridge = VisionEventBridge(min_interval_ms=100)
        event = VisionFeatureEvent(
            ts_ms=1000,
            looming=0.7,
            area_rate=0.5,
            center_motion=0.2,
            confidence=0.8,
            valid=True,
        )

        self.assertTrue(bridge.maybe_send(event, writer, now_ms=1000))

        payload = json.loads(writer.lines[0])
        self.assertEqual(payload["seq"], 1)
        self.assertEqual(payload["type"], "vision")

    def test_throttles_events_inside_interval(self):
        writer = FakeWriter()
        bridge = VisionEventBridge(min_interval_ms=100)
        event = VisionFeatureEvent(1000, 0.7, 0.5, 0.2, 0.8, True)

        self.assertTrue(bridge.maybe_send(event, writer, now_ms=1000))
        self.assertFalse(bridge.maybe_send(event, writer, now_ms=1050))
        self.assertTrue(bridge.maybe_send(event, writer, now_ms=1100))

        self.assertEqual(len(writer.lines), 2)
        self.assertEqual(json.loads(writer.lines[1])["seq"], 2)

    def test_tracks_send_status_and_failures(self):
        writer = FakeWriter()
        bridge = VisionEventBridge(min_interval_ms=100)
        event = VisionFeatureEvent(1000, 0.7, 0.5, 0.2, 0.8, True)

        self.assertTrue(bridge.maybe_send(event, writer, now_ms=1000))
        self.assertEqual(bridge.status.last_seq, 1)
        self.assertEqual(bridge.status.last_sent_ms, 1000)
        self.assertEqual(bridge.status.failure_count, 0)

        writer.write_line = lambda line: False
        self.assertFalse(bridge.maybe_send(event, writer, now_ms=1100))
        self.assertEqual(bridge.status.last_seq, 1)
        self.assertEqual(bridge.status.failure_count, 1)

if __name__ == "__main__":
    unittest.main()

