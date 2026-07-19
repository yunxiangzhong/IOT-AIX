import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets

from aix_host_app.widgets.active_dashboard import ActiveVisionDashboard
from aix_host_app.models import HardwareHealthEvent, PressureSample
from aix_host_app.widgets.status_card import ClickableStatusCard
from aix_host_app.widgets.trend_dialog import TrendStore


class DashboardTrendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_trend_store_keeps_latest_60_seconds_and_reports_stats(self):
        store = TrendStore()
        store.add("pressure_kpa", 0, 1.0)
        store.add("pressure_kpa", 30_000, 4.0)
        store.add("pressure_kpa", 60_001, 3.0)
        samples = store.samples("pressure_kpa")
        self.assertEqual([sample.value for sample in samples], [4.0, 3.0])
        self.assertEqual(store.stats("pressure_kpa"), (3.0, 3.0, 4.0))

    def test_clickable_status_card_emits_metric_key_for_keyboard_activation(self):
        card = ClickableStatusCard("pressure_kpa", "压力")
        card.set_trend_enabled(True)
        received = []
        card.clicked.connect(received.append)
        QtWidgets.QApplication.sendEvent(card, QtGui.QKeyEvent(
            QtCore.QEvent.Type.KeyPress,
            QtCore.Qt.Key.Key_Enter,
            QtCore.Qt.KeyboardModifier.NoModifier,
        ))
        self.assertEqual(received, ["pressure_kpa"])

    def test_status_card_keeps_static_line_separate_when_numeric_line_changes(self):
        card = ClickableStatusCard("pressure_kpa", "压力")
        card.set_value("5.58 kPa\n有效")
        static_line = card.secondary_label
        card.set_value("5.60 kPa\n有效")
        self.assertIs(card.secondary_label, static_line)
        self.assertEqual(card.secondary_label.text(), "有效")
        self.assertEqual(card.value_label.text(), "5.60 kPa")

    def test_overview_pressure_value_has_no_diagnostic_milliseconds(self):
        dashboard = ActiveVisionDashboard()
        dashboard.apply_pressure(type("Pressure", (), {
            "valid": True, "seq": 1, "filtered_kpa": 5.4, "ts_ms": 1000,
        })())
        self.assertIn("5.40 kPa", dashboard.realtime_values["pressure"].text())
        self.assertNotIn("ms", dashboard.realtime_values["pressure"].text())
        dashboard.close()

    def test_pressure_status_is_stable_across_sensor_and_health_events(self):
        dashboard = ActiveVisionDashboard()
        dashboard.apply_pressure(type("Pressure", (), {
            "valid": True, "seq": 1, "filtered_kpa": 5.4, "ts_ms": 1000,
        })())
        dashboard.apply_hardware_health(type("Health", (), {
            "modules": {
                "ov5640": "healthy", "mpu6050": "healthy", "pressure": "healthy",
                "dfplayer": "healthy", "rgb": "healthy", "pump": "healthy", "valve": "healthy",
            },
            "automatic_ready": True, "overall": "healthy", "reason": "硬件正常",
        })())
        self.assertEqual(dashboard.peripheral_values["pressure"].text(), "正常")
        self.assertNotIn("Hz", dashboard.peripheral_values["pressure"].text())
        self.assertNotIn("心跳", dashboard.peripheral_values["pressure"].text())
        dashboard.close()

    def test_pressure_sample_cannot_overwrite_hardware_health_card(self):
        dashboard = ActiveVisionDashboard()
        dashboard.apply_hardware_health(HardwareHealthEvent(
            ts_ms=1_000,
            overall="fault",
            automatic_ready=False,
            modules={
                "ov5640": "healthy", "mpu6050": "healthy", "pressure": "fault",
                "dfplayer": "healthy", "rgb": "healthy", "pump": "healthy", "valve": "healthy",
            },
            reason="压力传感器故障",
        ))
        dashboard.apply_pressure(PressureSample(
            seq=2,
            ts_ms=1_100,
            raw=100,
            mv=900,
            kpa=5.4,
            filtered_kpa=5.4,
            over_pressure=False,
            valid=True,
        ))
        dashboard._flush_display_updates()

        self.assertEqual(dashboard.peripheral_values["pressure"].text(), "故障")
        self.assertEqual(dashboard.peripheral_panel.rows["pressure"].property("statusTone"), "fault")
        self.assertEqual(dashboard.realtime_values["pressure"].text(), "5.40 kPa")
        dashboard.close()

    def test_every_mapping_card_has_one_declared_owner(self):
        expected = {
            (panel, key)
            for panel in ("peripheralPanel", "realtimePanel", "decisionPanel")
            for key, _ in ActiveVisionDashboard.ROWS
        }
        self.assertEqual(set(ActiveVisionDashboard.DISPLAY_OWNERS), expected)
        self.assertTrue(all(ActiveVisionDashboard.DISPLAY_OWNERS.values()))

    def test_non_owner_cannot_write_any_mapping_card(self):
        dashboard = ActiveVisionDashboard()
        panels = {
            "peripheralPanel": dashboard.peripheral_panel,
            "realtimePanel": dashboard.realtime_panel,
            "decisionPanel": dashboard.decision_panel,
        }
        for (panel_name, key), owner in dashboard.DISPLAY_OWNERS.items():
            panel = panels[panel_name]
            self.assertTrue(dashboard._queue_mapping_value(
                panel, key, f"{owner}-value", source=owner, immediate=True, tone="ok",
            ))
            self.assertFalse(dashboard._queue_mapping_value(
                panel, key, "foreign-value", source="foreign_event", immediate=True, tone="fault",
            ))
            self.assertEqual(panel.rows[key]._raw_value, f"{owner}-value")
            self.assertEqual(panel.rows[key].property("statusTone"), "ok")
        dashboard.close()

    def test_identical_display_state_never_enters_refresh_queue(self):
        dashboard = ActiveVisionDashboard()
        self.assertTrue(dashboard._queue_mapping_value(
            dashboard.realtime_panel, "pressure", "5.40 kPa\n有效",
            source="pressure", immediate=True, tone="ok",
        ))
        self.assertFalse(dashboard._queue_mapping_value(
            dashboard.realtime_panel, "pressure", "5.40 kPa\n有效",
            source="pressure", tone="ok",
        ))
        self.assertEqual(dashboard._pending_display_updates, {})
        dashboard.close()


if __name__ == "__main__":
    unittest.main()
