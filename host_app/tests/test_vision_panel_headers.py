from __future__ import annotations

import unittest

from aix_host_app.widgets.vision_panel import VisionPanel


class _StringHeaderReply:
    def rawHeader(self, name: str):
        if not isinstance(name, str):
            raise TypeError("rawHeader requires str")
        return b"42"


class VisionPanelHeaderTests(unittest.TestCase):
    def test_reads_header_when_caller_supplies_bytes_name(self):
        self.assertEqual(VisionPanel._read_header(_StringHeaderReply(), b"X-Frame-Seq", 0), 42)


if __name__ == "__main__":
    unittest.main()
