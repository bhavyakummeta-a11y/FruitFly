"""Notebook LIF model exposed as a reusable neural escape backend.

No authentication, notebook execution, or data download happens on import.
"""
from pathlib import Path
import math
import time


class ReflexBrain:
    """Explicit non-neural test baseline. Never presented as a fly brain."""
    name = 'REFLEX BASELINE (no connectome)'
    def escape(self, looming_hz):
        return 50.0 if looming_hz >= 40 else 0.0


class SilentBrain:
    """Ablation: no escape, even when geometry detects an obstacle."""
    name = 'SILENCED ESCAPE (control experiment)'
    def escape(self, looming_hz):
        return 0.0


class ConnectomeBrain:
    name = 'CONNECTOME LIF (notebook model)'
    def __init__(self, directory, seed=0, ms=200):
        import numpy as np
        import scipy.sparse as sp
        try:
            import pandas as pd
        except ImportError as exc:
            raise RuntimeError('Install requirements-brain.txt for connectome mode.') from exc
        directory = Path(directory)
        names = ['Completeness_783.csv', 'Connectivity_783.parquet', 'annotations.tsv']
        missing = [n for n in names if not (directory / n).is_file()]
        if missing:
            raise FileNotFoundError('Missing connectome data: ' + ', '.join(missing)
                                    + '. See docs/FLIGHT_SIMULATOR.md; no baseline substitution occurs.')
        neurons = pd.read_csv(directory / names[0], index_col=0)
        wiring = pd.read_parquet(directory / names[1])
        labels = pd.read_csv(directory / names[2], sep='\t', low_memory=False)
        self.n = len(neurons)
        self.w = sp.csr_matrix((wiring['Excitatory x Connectivity'],
                               (wiring['Presynaptic_Index'], wiring['Postsynaptic_Index'])),
                              shape=(self.n, self.n))
        if not np.isfinite(self.w.data).all():
            raise ValueError('Connectome contains non-finite weights')
        rows = {int(root): i for i, root in enumerate(neurons.index)}
        def group(types):
            return np.array([rows[int(r)] for r in labels.loc[labels.cell_type.isin(types), 'root_id']
                             if int(r) in rows], dtype=int)
        self.looming = group(['LC4', 'LPLC2'])
        self.giant_fibre = group(['DNp01'])
        if not len(self.looming) or not len(self.giant_fibre):
            raise ValueError('Looming or Giant Fibre neuron group is empty; check annotation IDs.')
        if not math.isfinite(ms) or ms <= 0:
            raise ValueError('Brain simulation duration must be positive')
        self.seed, self.ms = seed, ms
        self.calls = 0
        self.last_seconds = 0.0

    def escape(self, looming_hz):
        """Fresh 200 ms trial per call; preserve notebook equations/parameters."""
        import numpy as np
        if not math.isfinite(looming_hz) or not 0 <= looming_hz <= 200:
            raise ValueError('Input rate must be in 0–200 Hz')
        start = time.monotonic()
        if looming_hz == 0:
            # Exact shortcut: reset voltages are below threshold, synaptic current
            # is zero, and this backend has no other drive or spontaneous noise.
            self.calls += 1
            self.last_seconds = time.monotonic() - start
            return 0.0
        dt, v0, vth, tm, ts, ref = 0.1, -52.0, -45.0, 20.0, 5.0, 2.2
        wsyn, kick, delay = 0.275, 250 * 0.275, int(1.8 / 0.1)
        rng = np.random.default_rng(self.seed + self.calls)
        self.calls += 1
        v, g = np.full(self.n, v0), np.zeros(self.n)
        last, counts = np.full(self.n, -1e9), np.zeros(self.n, int)
        driven = np.zeros(self.n, bool)
        driven[self.looming] = True
        ring = np.zeros((delay, self.n))
        for k in range(int(self.ms / dt)):
            t, slot = k * dt, k % delay
            g += ring[slot]
            ring[slot] = 0
            free = ((t - last) > ref) | driven
            v[free] += dt * (v0 - v[free] + g[free]) / tm
            g[free] *= np.exp(-dt / ts)
            v[self.looming[rng.random(len(self.looming)) < looming_hz * dt / 1000]] += kick
            spikes = np.flatnonzero(v > vth)
            v[spikes], g[spikes], last[spikes] = v0, 0.0, t
            counts[spikes] += 1
            if len(spikes):
                ring[slot] += np.asarray(self.w[spikes].sum(0)).ravel() * wsyn
        self.last_seconds = time.monotonic() - start
        return float(counts[self.giant_fibre].mean() / (self.ms / 1000))
