import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from aix_host_app.widgets.collision_alert_dialog import CollisionAlertDialog
from aix_host_app.collision_state import ProtectionReadiness
from aix_host_app.models import MotionEvent


def collision_event() -> MotionEvent:
    return MotionEvent(
        seq=201,
        ts_ms=4200,
        speed_mps=0.0,
        accel_mps2=0.0,
        speed_valid=False,
        accel_valid=True,
        accel_x_g=0.0,
        accel_y_g=0.0,
        accel_z_g=2.31,
        accel_norm_g=2.31,
        accel_delta_g=1.31,
        sample_interval_ms=10,
        tilt_deg=3.0,
        impact=True,
        impact_event=True,
        impact_count=1,
    )


class CollisionAlertDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.dialog = CollisionAlertDialog()

    def tearDown(self):
        self.dialog.shutdown()

    def test_shows_non_modal_red_alert_with_blocked_protection_reason(self):
        self.dialog.show_collision(
            collision_event(), 1, ProtectionReadiness(False, "压力无效或过期")
        )

        self.assertTrue(self.dialog.isVisible())
        self.assertFalse(self.dialog.isModal())
        self.assertIn("#", self.dialog.title_label.styleSheet())
        self.assertIn("压力无效或过期", self.dialog.readiness_label.text())

    def test_window_close_cannot_dismiss_alert_but_acknowledge_can(self):
        acknowledged = []
        self.dialog.acknowledged.connect(lambda: acknowledged.append(True))
        self.dialog.show_collision(collision_event(), 1, None)

        self.dialog.close()
        self.app.processEvents()
        self.assertTrue(self.dialog.isVisible())

        self.dialog.ack_button.click()
        self.app.processEvents()
        self.assertFalse(self.dialog.isVisible())
        self.assertEqual(acknowledged, [True])

    def test_shutdown_allows_application_exit(self):
        self.dialog.show_collision(collision_event(), 1, None)

        self.dialog.shutdown()
        self.app.processEvents()

        self.assertFalse(self.dialog.isVisible())


if __name__ == "__main__":
    unittest.main()
