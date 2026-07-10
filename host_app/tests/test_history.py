
import unittest

from aix_host_app.history import PressureHistory
from aix_host_app.models import PressureSample


def sample(seq: int, filtered: float) -> PressureSample:
    return PressureSample(
        seq=seq,
        ts_ms=seq * 500,
        raw=2000 + seq,
        mv=1400 + seq,
        kpa=filtered + 2.0,
        filtered_kpa=filtered,
        over_pressure=False,
        valid=True,
    )


class PressureHistoryTests(unittest.TestCase):
    def test_keeps_only_latest_samples(self):
        history = PressureHistory(max_points=3)

        for seq in range(5):
            history.add(sample(seq, 80.0 + seq))

        self.assertEqual(history.seq_values(), [2, 3, 4])
        self.assertEqual(history.filtered_values(), [82.0, 83.0, 84.0])

    def test_tracks_raw_and_filtered_kpa_separately(self):
        history = PressureHistory(max_points=5)

        history.add(sample(1, 91.5))

        self.assertEqual(history.kpa_values(), [93.5])
        self.assertEqual(history.filtered_values(), [91.5])


if __name__ == "__main__":
    unittest.main()
