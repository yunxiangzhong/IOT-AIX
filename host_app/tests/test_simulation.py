import unittest

from aix_host_app.simulation import make_simulated_pressure_sample


class SimulationTests(unittest.TestCase):
    def test_generates_valid_pressure_sample(self):
        sample = make_simulated_pressure_sample(seq=12, elapsed_ms=6000)

        self.assertEqual(sample.seq, 12)
        self.assertEqual(sample.ts_ms, 6000)
        self.assertTrue(0 <= sample.kpa <= 200)
        self.assertTrue(0 <= sample.filtered_kpa <= 200)
        self.assertTrue(100 <= sample.mv <= 2900)
        self.assertEqual(sample.source, "simulated")


if __name__ == "__main__":
    unittest.main()
