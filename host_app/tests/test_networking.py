from __future__ import annotations

import unittest

from PySide6 import QtCore

from aix_host_app.networking import build_get_request


class NetworkingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])

    def test_preview_request_has_transfer_timeout(self):
        request = build_get_request("http://192.168.137.111:8080/capture.jpg", timeout_ms=4000)

        self.assertEqual(request.transferTimeout(), 4000)


if __name__ == "__main__":
    unittest.main()
