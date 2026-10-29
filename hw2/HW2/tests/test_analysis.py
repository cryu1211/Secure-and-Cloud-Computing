import random
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from analyze import inversions
from workload import plan


class MeasurementTests(unittest.TestCase):
    def test_inversions_against_pairwise_oracle(self):
        rng = random.Random(71)
        for size in range(100):
            values = [rng.randrange(20) for _ in range(size)]
            expected = sum(values[i] > values[j]
                           for i in range(size) for j in range(i+1, size))
            self.assertEqual(inversions(values), expected)
        self.assertEqual(inversions(range(100)), 0)
        self.assertEqual(inversions(range(99, -1, -1)), 4950)

    def test_workload_has_distinct_five_tuples_and_mixed_sizes(self):
        flows = plan()
        keys = {(f['src'], f['dst'], f['protocol'], f['sport'], f['dport']) for f in flows}
        self.assertEqual(len(keys), len(flows))
        self.assertEqual(sum(f['packets'] for f in flows), 2080)
        self.assertEqual(sum(f['packets'] * f['frame_bytes'] for f in flows), 2393600)
        self.assertEqual({f['frame_bytes'] for f in flows}, {128, 512, 1400})
        self.assertEqual(plan(), flows)


if __name__ == '__main__':
    unittest.main()
