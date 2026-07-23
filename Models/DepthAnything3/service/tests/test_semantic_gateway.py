from __future__ import annotations

import json
import time
import unittest

from frame_pipeline import FrameEnvelope
from semantic_gateway import (
    SemanticGatewayClient,
    SemanticAnalysisWorker,
    SemanticResultCache,
    SemanticWindowScheduler,
)


def frame(seq: int, received_ts_ms: int) -> FrameEnvelope:
    return FrameEnvelope(
        device_id="aix-helmet-01",
        boot_id="0123456789abcdef",
        frame_seq=seq,
        capture_ts_ms=received_ts_ms - 20,
        received_ts_ms=received_ts_ms,
        source_ip="192.168.137.2",
        jpeg=b"\xff\xd8" + bytes([seq]) + b"\xff\xd9",
    )


class SemanticWindowSchedulerTests(unittest.TestCase):
    def test_selects_three_real_frames_across_six_second_window(self) -> None:
        scheduler = SemanticWindowScheduler(interval_ms=6_000)

        self.assertIsNone(scheduler.offer(frame(1, 1_000)))
        self.assertIsNone(scheduler.offer(frame(2, 4_000)))
        selected = scheduler.offer(frame(3, 7_000))

        self.assertIsNotNone(selected)
        self.assertEqual([item.frame_seq for item in selected or ()], [1, 2, 3])
        self.assertIsNone(scheduler.offer(frame(4, 8_000)))

    def test_keeps_latest_frames_without_building_request_backlog(self) -> None:
        scheduler = SemanticWindowScheduler(interval_ms=6_000)
        scheduler.offer(frame(1, 1_000))
        scheduler.offer(frame(2, 4_000))
        scheduler.offer(frame(3, 7_000))

        for seq, timestamp in enumerate(range(8_000, 13_001, 1_000), start=4):
            self.assertIsNone(scheduler.offer(frame(seq, timestamp)))
        selected = scheduler.offer(frame(10, 13_100))

        self.assertIsNotNone(selected)
        self.assertEqual((selected or ())[-1].frame_seq, 10)
        self.assertLessEqual(scheduler.buffered_count, 8)

    def test_never_mixes_frames_across_boot_sessions(self) -> None:
        scheduler = SemanticWindowScheduler(interval_ms=6_000)
        scheduler.offer(frame(1, 1_000))
        scheduler.offer(frame(2, 4_000))
        rebooted = frame(1, 7_000)
        rebooted = FrameEnvelope(
            **{**rebooted.__dict__, "boot_id": "fedcba9876543210"}
        )

        self.assertIsNone(scheduler.offer(rebooted))
        self.assertEqual(scheduler.buffered_count, 1)


class SemanticGatewayClientTests(unittest.TestCase):
    def test_parses_controlled_semantic_result_without_risk_fields(self) -> None:
        payload = {
            "scene_type": "road",
            "summary": "道路前方存在施工围挡，车辆缓慢通行。",
            "road_environment": "construction_or_blockage",
            "traffic_flow": "slow",
            "visibility": "clear",
            "changes": ["围挡在三帧中持续可见"],
            "confidence": 0.86,
            "uncertainty": "无法确认围挡后的车道数量",
        }
        calls: list[dict] = []

        def completion(request: dict) -> str:
            calls.append(request)
            return f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"

        client = SemanticGatewayClient(api_key="sk-test", completion=completion)
        result = client.analyze((frame(1, 1_000), frame(2, 4_000), frame(3, 7_000)))

        self.assertEqual(result["summary"], payload["summary"])
        self.assertNotIn("risk_score", result)
        self.assertNotIn("risk_band", result)
        self.assertEqual(len(calls[0]["images"]), 3)
        self.assertNotIn("sk-test", json.dumps(calls[0]))

    def test_rejects_model_output_that_contains_execution_or_risk_fields(self) -> None:
        payload = {
            "scene_type": "road",
            "summary": "测试",
            "road_environment": "normal",
            "traffic_flow": "smooth",
            "visibility": "clear",
            "changes": [],
            "confidence": 0.8,
            "uncertainty": "",
            "risk_score": 90,
        }
        client = SemanticGatewayClient(
            api_key="sk-test",
            completion=lambda _request: json.dumps(payload),
        )

        with self.assertRaisesRegex(ValueError, "forbidden"):
            client.analyze((frame(1, 1_000), frame(2, 4_000), frame(3, 7_000)))

    def test_rejects_boolean_confidence(self) -> None:
        payload = {
            "scene_type": "road",
            "summary": "测试",
            "road_environment": "normal",
            "traffic_flow": "smooth",
            "visibility": "clear",
            "changes": [],
            "confidence": True,
            "uncertainty": "",
        }
        client = SemanticGatewayClient(
            api_key="sk-test",
            completion=lambda _request: json.dumps(payload),
        )
        with self.assertRaisesRegex(ValueError, "confidence"):
            client.analyze((frame(1, 1_000), frame(2, 4_000), frame(3, 7_000)))


class SemanticResultCacheTests(unittest.TestCase):
    def test_keeps_bounded_results_and_returns_exact_keyframe(self) -> None:
        cache = SemanticResultCache(capacity=2)
        frames = (frame(1, 1_000), frame(2, 4_000), frame(3, 7_000))
        cache.put("analysis-1", {"status": "ready"}, frames)
        cache.put("analysis-2", {"status": "error"}, frames)
        cache.put("analysis-3", {"status": "ready"}, frames)

        self.assertIsNone(cache.get("analysis-1"))
        self.assertEqual(cache.get("analysis-3")["status"], "ready")
        self.assertEqual(cache.keyframe("analysis-3", 2), frames[1].jpeg)
        with self.assertRaises(KeyError):
            cache.keyframe("../analysis-3", 1)


class SemanticAnalysisWorkerTests(unittest.TestCase):
    def test_success_is_recorded_cached_and_indicated_once(self) -> None:
        result = {
            "scene_type": "road",
            "summary": "道路畅通",
            "road_environment": "normal",
            "traffic_flow": "smooth",
            "visibility": "clear",
            "changes": [],
            "confidence": 0.9,
            "uncertainty": "",
        }
        records: list[dict] = []
        indicators: list[dict] = []
        worker = SemanticAnalysisWorker(
            client=SemanticGatewayClient(
                api_key="sk-test",
                completion=lambda _request: json.dumps(result),
            ),
            cache=SemanticResultCache(capacity=2),
            record=lambda _device_id, record: records.append(record),
            indicator=lambda _frame, payload: indicators.append(payload)
            or {
                "accepted": True,
                "flashed": True,
                "effective_rgb_pattern": "cyan_result_pulse",
            },
            interval_ms=6_000,
        )
        worker.start()
        try:
            worker.offer(frame(1, 1_000))
            worker.offer(frame(2, 4_000))
            worker.offer(frame(3, 7_000))
            deadline = time.time() + 1
            while not records and time.time() < deadline:
                time.sleep(0.01)
        finally:
            worker.stop()

        self.assertEqual(records[0]["status"], "ready")
        self.assertEqual(records[0]["frame_seqs"], [1, 2, 3])
        self.assertTrue(records[0]["rgb_delivery"]["flashed"])
        self.assertEqual(len(indicators), 1)
        self.assertNotIn("risk_score", json.dumps(records[0]))

    def test_failure_is_recorded_but_never_indicated(self) -> None:
        records: list[dict] = []
        indicators: list[dict] = []
        worker = SemanticAnalysisWorker(
            client=SemanticGatewayClient(
                api_key="sk-test",
                completion=lambda _request: "not-json",
            ),
            cache=SemanticResultCache(capacity=2),
            record=lambda _device_id, record: records.append(record),
            indicator=lambda _frame, payload: indicators.append(payload),
            interval_ms=6_000,
        )
        worker.start()
        try:
            worker.offer(frame(1, 1_000))
            worker.offer(frame(2, 4_000))
            worker.offer(frame(3, 7_000))
            deadline = time.time() + 1
            while not records and time.time() < deadline:
                time.sleep(0.01)
        finally:
            worker.stop()

        self.assertEqual(records[0]["status"], "error")
        self.assertTrue(records[0]["error"])
        self.assertEqual(indicators, [])


if __name__ == "__main__":
    unittest.main()
