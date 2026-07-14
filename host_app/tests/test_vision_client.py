import unittest

from aix_host_app.vision_client import InferenceRateLimiter


class InferenceRateLimiterTests(unittest.TestCase):
    def test_allows_first_frame_then_at_most_one_per_second(self):
        limiter = InferenceRateLimiter(interval_s=1.0)

        self.assertTrue(limiter.accept(0.0))
        self.assertFalse(limiter.accept(0.4))
        self.assertTrue(limiter.accept(1.0))


if __name__ == "__main__":
    unittest.main()
