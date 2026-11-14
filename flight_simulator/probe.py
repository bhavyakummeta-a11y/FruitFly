"""Step 0, open-loop probe: stimulate each sensory group alone, record every readout.

    python -m flight_simulator.probe --rates 50 100 200 --out runs/probe.json

The resulting table is what the Takeoff and Landing flies' decoder channels are
chosen from (see docs/TAKEOFF_LANDING.md). Nothing here is fitted or trained.
"""
import argparse
import json
from pathlib import Path
import sys
import time

from .brain import INPUTS, READOUTS, ConnectomeBrain


def probe(brain, rates, seeds, groups=None, extra=()):
    """Return {condition: {readout: mean Hz over seeds}}."""
    conditions = {f'{g}@{hz:g}': {g: hz} for g in (groups or INPUTS) for hz in rates}
    conditions.update({label: inputs for label, inputs in extra})
    table = {}
    for label, inputs in conditions.items():
        totals = {name: 0.0 for name in READOUTS}
        for seed in range(seeds):
            brain.seed, brain.calls = seed, 0
            for name, hz in brain.run(inputs).items():
                totals[name] += hz / seeds
        table[label] = totals
        print(f'{label:28s} {brain.last_seconds:5.1f}s  ' + ' '.join(
            f'{k}={v:.0f}' for k, v in totals.items() if v > 0), flush=True)
    return table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', default='data/brain')
    parser.add_argument('--rates', type=float, nargs='+', default=[50, 100, 200])
    parser.add_argument('--seeds', type=int, default=1)
    parser.add_argument('--groups', nargs='+', choices=list(INPUTS))
    parser.add_argument('--out', default='runs/probe.json')
    args = parser.parse_args()
    brain = ConnectomeBrain(args.data)
    print('Group sizes: ' + ', '.join(f'{k}={len(v)}' for k, v in brain.groups.items()), flush=True)
    start = time.monotonic()
    table = probe(brain, args.rates, args.seeds, args.groups)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({'rates': args.rates, 'seeds': args.seeds,
                                          'table': table}, indent=1) + '\n')
    print(f'Wrote {args.out} in {time.monotonic() - start:.0f}s')
    return 0


if __name__ == '__main__':
    sys.exit(main())
