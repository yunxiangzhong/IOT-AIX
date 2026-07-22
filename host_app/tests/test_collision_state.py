import unittest

from aix_host_app.collision_state import CollisionEventTracker, protection_readiness
from aix_host_app.models import MotionEvent, PneumaticStatusEvent


def motion_event(
    *, seq: int, impact: bool = False, impact_event: bool = False,
    impact_count: int | None = None
) -> MotionEvent:
    return MotionEvent(
        seq=seq,
        ts_ms=seq * 10,
        speed_mps=0.0,
        accel_mps2=0.0,
        speed_valid=False,
        accel_valid=True,
        impact=impact,
        impact_event=impact_event,
        impact_count=impact_count,
    )


def pneumatic_event(**overrides: object) -> PneumaticStatusEvent:
    values = {
        "ts_ms": 1000,
        "state": "vented",
        "fault": "none",
        "trigger": "none",
        "operation": 0,
        "pump_on": False,
        "valve_on": False,
        "pressure_kpa": 0.0,
        "pressure_valid": True,
        "pressure_age_ms": 20,
        "vision_state": "safe",
        "vision_fresh": True,
        "mpu_available": True,
        "mpu_calibrated": True,
        "impact": False,
        "rapid_tilt": False,
        "pump_verified": True,
        "valve_verified": True,
        "self_test_failed": False,
        "automatic_enabled": True,
    }
    values.update(overrides)
    return PneumaticStatusEvent(**values)


class CollisionEventTrackerTests(unittest.TestCase):
    def test_new_firmware_deduplicates_and_reports_counter_delta(self):
        tracker = CollisionEventTracker()

        self.assertEqual(tracker.observe(motion_event(seq=1, impact_event=True, impact_count=1)), 1)
        self.assertEqual(tracker.observe(motion_event(seq=2, impact_event=False, impact_count=1)), 0)
        self.assertEqual(tracker.observe(motion_event(seq=3, impact_event=True, impact_count=3)), 2)

    def test_old_firmware_uses_impact_rising_edge(self):
        tracker = CollisionEventTracker()

        self.assertEqual(tracker.observe(motion_event(seq=1, impact=False)), 0)
        self.assertEqual(tracker.observe(motion_event(seq=2, impact=True)), 1)
        self.assertEqual(tracker.observe(motion_event(seq=3, impact=True)), 0)

    def test_new_firmware_restarts_without_replaying_counter(self):
        tracker = CollisionEventTracker()
        tracker.observe(motion_event(seq=10, impact_event=False, impact_count=8))

        self.assertEqual(tracker.observe(motion_event(seq=9, impact_event=False, impact_count=2)), 0)
        self.assertEqual(tracker.observe(motion_event(seq=10, impact_event=True, impact_count=3)), 1)

    def test_new_firmware_counter_supports_uint32_wrap(self):
        tracker = CollisionEventTracker()
        tracker.observe(motion_event(seq=1, impact_event=False, impact_count=0xFFFFFFFF))

        self.assertEqual(tracker.observe(motion_event(seq=2, impact_event=True, impact_count=1)), 2)


class ProtectionReadinessTests(unittest.TestCase):
    def test_mpu_collision_does_not_require_fresh_vision(self):
        readiness = protection_readiness(
            pneumatic_event(vision_fresh=False), require_vision=False
        )

        self.assertTrue(readiness.allowed)
        self.assertEqual(readiness.reason, "安全条件有效")

    def test_rejects_unverified_pump(self):
        readiness = protection_readiness(
            pneumatic_event(pump_verified=False), require_vision=False
        )

        self.assertFalse(readiness.allowed)
        self.assertIn("泵自检", readiness.reason)

    def test_pressure_age_boundary_is_200_ms(self):
        self.assertTrue(
            protection_readiness(pneumatic_event(pressure_age_ms=200), False).allowed
        )
        readiness = protection_readiness(pneumatic_event(pressure_age_ms=201), False)
        self.assertFalse(readiness.allowed)
        self.assertIn("压力", readiness.reason)

    def test_failures_follow_safety_priority(self):
        cases = (
            ({"automatic_enabled": False, "pressure_valid": False}, "自动模式关闭"),
            ({"pressure_valid": False, "pump_verified": False}, "压力"),
            ({"pump_verified": False, "valve_verified": False}, "泵自检"),
            ({"valve_verified": False, "self_test_failed": True}, "阀自检"),
            ({"self_test_failed": True, "vision_fresh": False}, "气动自检失败"),
        )
        for overrides, reason in cases:
            with self.subTest(reason=reason):
                readiness = protection_readiness(pneumatic_event(**overrides), True)
                self.assertFalse(readiness.allowed)
                self.assertIn(reason, readiness.reason)

    def test_requires_fresh_vision_when_requested(self):
        readiness = protection_readiness(
            pneumatic_event(vision_fresh=False), require_vision=True
        )

        self.assertFalse(readiness.allowed)
        self.assertEqual(readiness.reason, "视觉结果过期")


if __name__ == "__main__":
    unittest.main()
