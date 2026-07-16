import unittest

from aix_host_app.chain_client import frame_identity_from_state, normalize_service_url


class ChainClientTests(unittest.TestCase):
    def test_normalizes_service_url_and_extracts_frame_identity(self):
        self.assertEqual(normalize_service_url("http://127.0.0.1:8008/"), "http://127.0.0.1:8008")
        self.assertEqual(
            frame_identity_from_state({
                "boot_id": "ffffffffffffffff",
                "upload": {"last_frame_seq": 19},
                "display": {"ready": True, "boot_id": "0123456789abcdef", "frame_seq": 17},
            }),
            ("0123456789abcdef", 17),
        )

    def test_rejects_invalid_state_identity(self):
        self.assertIsNone(frame_identity_from_state({"display": {"ready": False, "boot_id": "", "frame_seq": -1}}))


if __name__ == "__main__":
    unittest.main()
