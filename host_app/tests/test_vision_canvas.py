import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets

from aix_host_app.widgets.vision_canvas import VisionCanvas


class VisionCanvasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_snapshot_does_not_change_layout_size_hint(self):
        canvas = VisionCanvas()
        before = canvas.sizeHint()
        image = QtGui.QImage(320, 240, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtGui.QColor("#234567"))
        buffer = QtCore.QBuffer()
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        self.assertTrue(image.save(buffer, "JPG"))

        self.assertTrue(canvas.set_snapshot(
            bytes(buffer.data()),
            [{"class_name": "car", "score": 0.93, "bbox_norm": [0.1, 0.2, 0.7, 0.8], "risk_score": 68}],
        ))

        self.assertEqual(canvas.sizeHint(), before)
        self.assertEqual(canvas.sizeHint(), QtCore.QSize(640, 360))
        self.assertEqual(canvas.sizePolicy().horizontalPolicy(), QtWidgets.QSizePolicy.Policy.Ignored)
        self.assertEqual(canvas.detections[0]["class_name"], "car")

    def test_rejects_invalid_image_without_replacing_snapshot(self):
        canvas = VisionCanvas()

        self.assertFalse(canvas.set_snapshot(b"broken", []))
        self.assertEqual(canvas.detections, ())

    def test_accepts_png_static_snapshot(self):
        canvas = VisionCanvas()
        image = QtGui.QImage(16, 12, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtGui.QColor("#234567"))
        buffer = QtCore.QBuffer()
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        self.assertTrue(image.save(buffer, "PNG"))

        self.assertTrue(canvas.set_snapshot(bytes(buffer.data()), []))


if __name__ == "__main__":
    unittest.main()
