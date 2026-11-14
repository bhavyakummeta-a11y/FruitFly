"""The fast LIF kernel must be the same model as the notebook loop: identical spike counts."""
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import numpy as np
    import scipy.sparse as sp
except ImportError:  # the brain needs requirements-brain.txt
    np = None

from flight_simulator import brain as B  # noqa: E402

DATA = ROOT / 'data' / 'brain'


def random_brain(n, seed, density=0.02, integer=True):
    """Small random network, strong enough to cascade, with excitation and inhibition."""
    rng = np.random.default_rng(seed)
    m = sp.random(n, n, density=density, random_state=rng, format='csr')
    m.data = rng.integers(-12, 30, len(m.data)).astype(np.int64 if integer else float)
    if not integer:
        m.data += rng.random(len(m.data))
    return m


@unittest.skipIf(np is None, 'numpy/scipy not installed')
class KernelEquivalence(unittest.TestCase):
    def both(self, w, active, seed, ms=60):
        ref = B.lif_trial_reference(w, active, np.random.default_rng(seed), ms)
        fast = B.lif_trial(w, active, np.random.default_rng(seed), ms)
        return ref, fast

    def test_identical_counts_on_random_networks(self):
        total = 0
        for seed in range(6):
            w = random_brain(1500, seed, integer=seed % 2 == 0)
            rng = np.random.default_rng(100 + seed)
            a = np.sort(rng.choice(1500, 40, replace=False))
            b = np.sort(rng.choice(1500, 25, replace=False))   # may overlap a: two drives on one neuron
            ref, fast = self.both(w, [(a, 150.0), (b, 60.0)], seed)
            self.assertTrue(np.array_equal(ref, fast), f'seed {seed}: spike counts differ')
            total += int(ref.sum())
            self.assertGreater(np.count_nonzero(ref), 65, 'network did not cascade; test is too weak')
        self.assertGreater(total, 2000)

    def test_refractory_and_repeat_firing_covered(self):
        w = random_brain(800, 7, density=0.05)
        a = np.arange(30)
        ref, fast = self.both(w, [(a, 200.0)], 3, ms=120)
        self.assertTrue(np.array_equal(ref, fast))
        undriven = np.ones(800, bool)
        undriven[a] = False
        self.assertGreater(ref[undriven].max(), 3, 'no undriven neuron fired repeatedly')

    def test_no_synapses_and_single_spiker(self):
        w = sp.csr_matrix((50, 50), dtype=np.int64)
        ref, fast = self.both(w, [(np.array([4]), 200.0)], 1)
        self.assertTrue(np.array_equal(ref, fast))
        self.assertGreater(ref[4], 0)

    def test_connectome_brain_uses_the_fast_kernel(self):
        self.assertIs(B.ConnectomeBrain.trial, B.lif_trial)


@unittest.skipIf(np is None or not (DATA / 'Connectivity_783.parquet').is_file(),
                 'connectome data not downloaded (python -m flight_simulator.download_data)')
class RealConnectome(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.brain = B.ConnectomeBrain(DATA)
        except (RuntimeError, ImportError) as exc:
            raise unittest.SkipTest(str(exc))

    def test_identical_counts_and_faster_on_the_real_brain(self):
        inputs = {'sugar': 150.0, 'looming': 60.0, 'vs_left': 100.0, 'vs_right': 110.0,
                  'hs_left': 100.0, 'hs_right': 90.0}
        active = [(self.brain.groups[k], hz) for k, hz in inputs.items()]
        t = time.monotonic()
        fast = B.lif_trial(self.brain.w, active, np.random.default_rng(5), 200)
        fast_s = time.monotonic() - t
        t = time.monotonic()
        ref = B.lif_trial_reference(self.brain.w, active, np.random.default_rng(5), 200)
        ref_s = time.monotonic() - t
        self.assertTrue(np.array_equal(ref, fast), 'fast kernel changed the brain\'s spikes')
        self.assertGreater(int(ref.sum()), 1000)
        self.assertLess(fast_s, ref_s / 2, f'fast kernel {fast_s:.2f}s vs reference {ref_s:.2f}s')


if __name__ == '__main__':
    unittest.main()
