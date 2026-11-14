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


def validate_inputs(inputs, specifications=None):
    specifications = INPUTS if specifications is None else specifications
    for name, hz in inputs.items():
        if name not in specifications:
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


# Notebook LIF equations and Shiu et al. 2024 parameters. Shared by both kernels below.
DT, V0, VTH, TM, TS, REF = 0.1, -52.0, -45.0, 20.0, 5.0, 2.2
WSYN, KICK, DELAY = 0.275, 250 * 0.275, int(1.8 / 0.1)


def lif_trial_reference(w, active, rng, ms):
    """The starter notebook's loop, unchanged: every neuron is updated every 0.1 ms.

    Kept as the definition of the model. lif_trial() must return the same spike
    counts (tests/test_brain_speed.py). w: CSR weights (row = presynaptic);
    active: [(neuron indices, Hz)]; returns spike counts per neuron."""
    import numpy as np
    n = w.shape[0]
    v, g = np.full(n, V0), np.zeros(n)
    last, counts = np.full(n, -1e9), np.zeros(n, int)
    driven = np.zeros(n, bool)
    for idx, _ in active:
        driven[idx] = True
    ring = np.zeros((DELAY, n))
    decay = np.exp(-DT / TS)
    for k in range(int(ms / DT)):
        t, slot = k * DT, k % DELAY
        g += ring[slot]
        ring[slot] = 0
        free = ((t - last) > REF) | driven
        v[free] += DT * (V0 - v[free] + g[free]) / TM
        g[free] *= decay
        for idx, hz in active:
            v[idx[rng.random(len(idx)) < hz * DT / 1000]] += KICK
        spikes = np.flatnonzero(v > VTH)
        v[spikes], g[spikes], last[spikes] = V0, 0.0, t
        counts[spikes] += 1
        if len(spikes):
            ring[slot] += np.asarray(w[spikes].sum(0)).ravel() * WSYN
    return counts


def lif_trial(w, active, rng, ms):
    """Same model, same arithmetic, same random stream as lif_trial_reference(), about
    6-8x faster. It is not an approximation: spike counts are identical.

    What it skips is work that cannot change anything:
    - A neuron that has never received input sits exactly at rest (v = V0, g = 0) and its
      update is exactly zero. Only neurons that have been stimulated or have received a
      synaptic input are simulated ("touched"; about half the brain by the end of a trial).
      They are kept in compact arrays in the order they were first touched.
    - Refractory neurons are a handful per step. Everything is updated in one pass and
      the refractory ones are put back, instead of masking every array every step.
    - Synaptic input is summed straight from the CSR rows of the spiking neurons
      (same order as the reference) instead of building a sparse sub-matrix per step.
    """
    import numpy as np
    n = w.shape[0]
    indptr, indices, data = w.indptr, w.indices, w.data
    local = np.full(n, -1, np.int64)      # neuron index -> slot in the compact arrays
    glob = np.empty(n, np.int64)          # slot -> neuron index
    v, g, last = np.full(n, V0), np.zeros(n), np.full(n, -1e9)
    driven = np.zeros(n, bool)
    counts = np.zeros(n, int)
    tmp = np.empty(n)
    size = 0

    def touch(idx):
        nonlocal size
        new = np.unique(idx[local[idx] < 0])
        local[new] = np.arange(size, size + len(new))
        glob[size:size + len(new)] = new
        size += len(new)

    groups = []
    for idx, hz in active:
        touch(idx)
        driven[local[idx]] = True
        groups.append((local[idx], hz * DT / 1000))
    decay = np.exp(-DT / TS)
    ring = [None] * DELAY                 # per delay slot: summed input for the first len() slots
    recent = []                           # (step, slots) that spiked lately and are not driven
    hold = int(REF / DT) + 2
    frozen = ()
    for k in range(int(ms / DT)):
        t, slot = k * DT, k % DELAY
        arriving = ring[slot]
        if arriving is not None:
            g[:len(arriving)] += arriving
            ring[slot] = None
        while recent and k - recent[0][0] > hold:
            recent.pop(0)
        if recent:
            candidates = np.concatenate([s for _, s in recent]) if len(recent) > 1 else recent[0][1]
            frozen = candidates[~((t - last[candidates]) > REF)]
            keep_v, keep_g = v[frozen], g[frozen]
        va, ga, step = v[:size], g[:size], tmp[:size]
        np.subtract(V0, va, out=step)     # DT * (V0 - v + g) / TM, operation for operation
        step += ga
        step *= DT
        step /= TM
        va += step
        ga *= decay
        if recent and len(frozen):
            v[frozen], g[frozen] = keep_v, keep_g
        for idx, p in groups:
            v[idx[rng.random(len(idx)) < p]] += KICK
        spikes = np.flatnonzero(va > VTH)
        if not len(spikes):
            continue
        va[spikes], ga[spikes] = V0, 0.0
        last[spikes] = t
        quiet = spikes[~driven[spikes]]
        if len(quiet):
            recent.append((k, quiet))
        firing = np.sort(glob[spikes])    # the reference delivers in ascending neuron order
        counts[firing] += 1
        if len(firing) == 1:
            lo, hi = indptr[firing[0]], indptr[firing[0] + 1]
            targets, weights = indices[lo:hi], data[lo:hi]
        else:
            targets = np.concatenate([indices[indptr[s]:indptr[s + 1]] for s in firing])
            weights = np.concatenate([data[indptr[s]:indptr[s + 1]] for s in firing])
        if len(targets):
            slots = local[targets]
            if slots.min() < 0:
                touch(targets)
                slots = local[targets]
            ring[slot] = np.bincount(slots, weights=weights, minlength=size) * WSYN
    return counts


class ConnectomeBrain:
    """Shiu whole-brain LIF on FlyWire 783.

    ``silence`` lists input or readout group names whose outgoing synapses are
    cut (the notebook's lesion method: the neurons still fire, nobody hears
    them). It is for control experiments only.
    """
    def __init__(self, directory, seed=0, ms=200, silence=(), extra_inputs=None, extra_readouts=None):
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

        self.input_specs = {**INPUTS, **(extra_inputs or {})}
        self.readout_specs = {**READOUTS, **(extra_readouts or {})}
        self.groups = {name: group(spec) for name, spec in {**self.input_specs, **self.readout_specs}.items()}
        self.last_counts = np.zeros(self.n, dtype=int)
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

    # The LIF kernel. lif_trial is the fast, bit-identical one; set this to
    # lif_trial_reference to run the notebook loop as written.
    trial = staticmethod(lif_trial)

    def run(self, inputs, readouts=None):
        """Fresh 200 ms trial from rest. inputs: {group: Hz} -> {readout: Hz}."""
        import numpy as np
        validate_inputs(inputs, self.input_specs)
        readouts = list(self.readout_specs) if readouts is None else list(readouts)
        for name in readouts:
            if name not in self.groups:
                raise KeyError(f'Unknown readout group {name!r}')
        start = time.monotonic()
        active = [(self.groups[name], hz) for name, hz in inputs.items() if hz > 0]
        if not active:
            # Exact shortcut: reset voltages are below threshold, synaptic current
            # is zero, and there is no other drive or spontaneous noise.
            self.calls += 1
            self.last_counts.fill(0)
            self.last_seconds = time.monotonic() - start
            return self._record(inputs, {name: 0.0 for name in readouts})
        rng = np.random.default_rng(self.seed + self.calls)
        self.calls += 1
        counts = self.trial(self.w, active, rng, self.ms)
        self.last_counts = counts
        self.last_seconds = time.monotonic() - start
        seconds = self.ms / 1000
        return self._record(inputs, {name: float(counts[self.groups[name]].mean() / seconds)
                                     for name in readouts})

    def _record(self, inputs, rates):
        """Keep the last trial's inputs and readout rates for the fly-activity log."""
        self.last_activity = {**{f'in_{k}_hz': v for k, v in inputs.items()},
                              **{f'{k}_hz': v for k, v in rates.items()},
                              'trial_s': round(self.last_seconds, 3)}
        return rates

    def escape(self, looming_hz):
        """Original API: Giant Fibre rate for a looming input.

        Reads out every non-empty descending group (same cost: one trial) so the
        fly-activity log captures the whole DN population, not just DNp01."""
        if not math.isfinite(looming_hz) or not 0 <= looming_hz <= 200:
            raise ValueError('Input rate must be in 0–200 Hz')
        readouts = [n for n in READOUTS if len(self.groups[n])]
        if 'DNp01' not in readouts:
            readouts.append('DNp01')
        return self.run({'looming': looming_hz}, readouts)['DNp01']
