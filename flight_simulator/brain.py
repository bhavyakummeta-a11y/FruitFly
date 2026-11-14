"""Notebook LIF model exposed as a reusable neural backend.

No authentication, notebook execution, or data download happens on import.

``ConnectomeBrain.run(inputs, readouts)`` stimulates any named sensory groups
with Poisson input (0-200 Hz) and returns the mean firing rate of any named
readout groups, using the starter notebook's equations and Shiu et al. 2024
parameters unchanged. ``escape()`` is the original single-channel API used by
the obstacle-avoidance experiment.
"""
from pathlib import Path
import math
import time

MN9_ROOT_ID = 720575940660219265  # not in the label file; ID from Shiu et al. 2024

VS = [f'VS{i}' for i in range(1, 9)]
HS = ['HSE', 'HSN', 'HSS']

# Sensory groups we can stimulate: name -> (annotation column, values, side or None).
INPUTS = {
    'sugar': ('cell_type', ['LB3c'], None),
    'bitter': ('cell_sub_class', ['bitter'], None),
    'looming': ('cell_type', ['LC4', 'LPLC2'], None),
    'hs_left': ('cell_type', HS, 'left'),
    'hs_right': ('cell_type', HS, 'right'),
    'vs_left': ('cell_type', VS, 'left'),
    'vs_right': ('cell_type', VS, 'right'),
    'translational_flow': ('cell_type', ['LPC1', 'LLPC1'], None),
}

# Descending / motor neurons we can read: name -> (column, values, side or None).
# A value ending in '*' matches by prefix (DNg02_a ... DNg02_h).
READOUTS = {
    'DNp01': ('cell_type', ['DNp01'], None),          # Giant Fibre: fast escape takeoff
    'DNp02': ('cell_type', ['DNp02'], None),          # non-GF looming escape
    'DNp04': ('cell_type', ['DNp04'], None),
    'DNp06': ('cell_type', ['DNp06'], None),
    'DNp11': ('cell_type', ['DNp11'], None),
    'DNp07': ('cell_type', ['DNp07'], None),          # landing (Ache et al. 2019)
    'DNp10': ('cell_type', ['DNp10'], None),          # landing
    'DNp09': ('cell_type', ['DNp09'], None),          # walk forward
    'MDN': ('cell_type', ['MDN'], None),              # walk backward
    'DNg02': ('cell_type', ['DNg02*'], None),         # wingbeat amplitude (flight power)
    'DNa01_L': ('cell_type', ['DNa01'], 'left'),      # steering
    'DNa01_R': ('cell_type', ['DNa01'], 'right'),
    'DNa02_L': ('cell_type', ['DNa02'], 'left'),
    'DNa02_R': ('cell_type', ['DNa02'], 'right'),
    'DNp15_L': ('cell_type', ['DNp15'], 'left'),      # DNHS1, HS-coupled neck DN
    'DNp15_R': ('cell_type', ['DNp15'], 'right'),
    'DNp20_L': ('cell_type', ['DNp20'], 'left'),      # VS-coupled DN candidates
    'DNp20_R': ('cell_type', ['DNp20'], 'right'),
    'DNp22_L': ('cell_type', ['DNp22'], 'left'),
    'DNp22_R': ('cell_type', ['DNp22'], 'right'),
    'MN9': ('root_id', [MN9_ROOT_ID], None),          # proboscis extension (feeding)
}


def validate_inputs(inputs):
    for name, hz in inputs.items():
        if name not in INPUTS:
            raise KeyError(f'Unknown input group {name!r}')
        if not math.isfinite(hz) or not 0 <= hz <= 200:
            raise ValueError(f'Input rate for {name} must be in 0-200 Hz, got {hz}')


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
    """Shiu whole-brain LIF on FlyWire 783.

    ``silence`` lists input or readout group names whose outgoing synapses are
    cut (the notebook's lesion method: the neurons still fire, nobody hears
    them). It is for control experiments only.
    """
    def __init__(self, directory, seed=0, ms=200, silence=()):
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

        def group(spec):
            column, values, side = spec
            col = labels[column]
            if column == 'root_id':
                mask = col.isin(values)
            else:
                col = col.astype(str)
                mask = col.isin([v for v in values if not v.endswith('*')])
                for v in values:
                    if v.endswith('*'):
                        mask |= col.str.startswith(v[:-1])
            if side:
                mask &= labels['side'] == side
            ids = [rows[int(r)] for r in labels.loc[mask, 'root_id'] if int(r) in rows]
            if column == 'root_id':  # MN9 is absent from the label file: look up directly
                ids = [rows[int(v)] for v in values if int(v) in rows]
            return np.array(sorted(set(ids)), dtype=int)

        self.groups = {name: group(spec) for name, spec in {**INPUTS, **READOUTS}.items()}
        empty = [name for name, idx in self.groups.items() if not len(idx)]
        if empty:
            raise ValueError('Empty neuron groups (check annotation IDs): ' + ', '.join(empty))
        self.looming = self.groups['looming']
        self.giant_fibre = self.groups['DNp01']
        self.silenced = tuple(silence)
        if self.silenced:
            keep = np.ones(self.n)
            for name in self.silenced:
                keep[self.groups[name]] = 0
            self.w = (sp.diags(keep) @ self.w).tocsr()
        if not math.isfinite(ms) or ms <= 0:
            raise ValueError('Brain simulation duration must be positive')
        self.seed, self.ms = seed, ms
        self.calls = 0
        self.last_seconds = 0.0
        self.name = 'CONNECTOME LIF (notebook model)' + (
            f' | silenced: {", ".join(self.silenced)}' if self.silenced else '')

    def run(self, inputs, readouts=None):
        """Fresh 200 ms trial from rest. inputs: {group: Hz} -> {readout: Hz}."""
        import numpy as np
        validate_inputs(inputs)
        readouts = list(READOUTS) if readouts is None else list(readouts)
        start = time.monotonic()
        active = [(self.groups[name], hz) for name, hz in inputs.items() if hz > 0]
        if not active:
            # Exact shortcut: reset voltages are below threshold, synaptic current
            # is zero, and there is no other drive or spontaneous noise.
            self.calls += 1
            self.last_seconds = time.monotonic() - start
            return {name: 0.0 for name in readouts}
        dt, v0, vth, tm, ts, ref = 0.1, -52.0, -45.0, 20.0, 5.0, 2.2
        wsyn, kick, delay = 0.275, 250 * 0.275, int(1.8 / 0.1)
        rng = np.random.default_rng(self.seed + self.calls)
        self.calls += 1
        v, g = np.full(self.n, v0), np.zeros(self.n)
        last, counts = np.full(self.n, -1e9), np.zeros(self.n, int)
        driven = np.zeros(self.n, bool)
        for idx, _ in active:
            driven[idx] = True
        ring = np.zeros((delay, self.n))
        decay = np.exp(-dt / ts)
        for k in range(int(self.ms / dt)):
            t, slot = k * dt, k % delay
            g += ring[slot]
            ring[slot] = 0
            free = ((t - last) > ref) | driven
            v[free] += dt * (v0 - v[free] + g[free]) / tm
            g[free] *= decay
            for idx, hz in active:
                v[idx[rng.random(len(idx)) < hz * dt / 1000]] += kick
            spikes = np.flatnonzero(v > vth)
            v[spikes], g[spikes], last[spikes] = v0, 0.0, t
            counts[spikes] += 1
            if len(spikes):
                ring[slot] += np.asarray(self.w[spikes].sum(0)).ravel() * wsyn
        self.last_seconds = time.monotonic() - start
        seconds = self.ms / 1000
        return {name: float(counts[self.groups[name]].mean() / seconds) for name in readouts}

    def escape(self, looming_hz):
        """Original API: Giant Fibre rate for a looming input."""
        if not math.isfinite(looming_hz) or not 0 <= looming_hz <= 200:
            raise ValueError('Input rate must be in 0–200 Hz')
        return self.run({'looming': looming_hz}, ['DNp01'])['DNp01']
