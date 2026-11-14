"""Plot a takeoff/landing run: sugar input, brain activity, altitude, airspeed.

    python -m flight_simulator.takeoff_landing landing --brain standin --log runs/landing.csv --plot runs/landing.png
    python -m flight_simulator.plot_run runs/landing.csv                # -> runs/landing.png
    python -m flight_simulator.plot_run runs/landing.csv -o fig.png

Reads the CSV written by `takeoff_landing --log` (in_* = sensory inputs, dn_* =
descending-neuron firing rates, both in Hz). Panels share one time axis:

1. Sugar input to the brain (the speed reward channel, LB3c neurons).
2. Brain activity: one row per descending neuron, darker blue = firing harder.
3. Altitude above ground.  4. Airspeed.

Thin vertical lines mark phase changes (ROLL, ROTATE, FLARE, ...). Needs matplotlib.
"""
import argparse
import csv
from pathlib import Path
import sys

# Reference palette (light): chart surface, ink, recessive grid, one series hue.
SURFACE, INK, INK_2, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#e4e3df'
SUGAR = '#eb6834'
# Sequential blue ramp for firing rate, near-surface = silent.
RAMP = ['#fcfcfb', '#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b']


def load(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def series(rows, key):
    return [_num(r.get(key)) for r in rows]


def phase_changes(rows):
    """[(time, phase)] at the first row of every new phase."""
    out, last = [], None
    for r in rows:
        if r.get('phase') != last:
            last = r.get('phase')
            out.append((_num(r['time']), last))
    return out


def phase_strip(ax, changes, end):
    """Flight phases as alternating bands, names centred; narrow bands stagger onto a second row."""
    from matplotlib.patches import Rectangle
    ax.set_ylim(0, 1)
    ax.axis('off')
    span = max(end - changes[0][0], 1e-9)
    bounds = [w for w, _ in changes[1:]] + [end]
    row = 0
    for i, ((start, name), stop) in enumerate(zip(changes, bounds)):
        ax.add_patch(Rectangle((start, 0), max(stop - start, 0), 1, facecolor=GRID if i % 2 else '#efeeea',
                               edgecolor=SURFACE, linewidth=2))
        narrow = (stop - start) / span < 0.06 + 0.012 * len(name)
        row = (row + 1) % 2 if narrow else 0
        x = min(max((start + stop) / 2, changes[0][0] + 0.02 * span), end - 0.02 * span)
        ha = 'right' if x >= end - 0.02 * span else 'left' if x <= changes[0][0] + 0.02 * span else 'center'
        if narrow:
            x, ha = (end, 'right') if start > end - 0.2 * span else (start, 'left')
        ax.text(x, 0.72 - 0.44 * row if narrow else 0.5, name, ha=ha, va='center', fontsize=8,
                color=INK, clip_on=False)
    ax.set_title('Flight phase', loc='left', fontsize=10, color=INK)


def plot(rows, out, title=None):
    if not rows:
        raise ValueError('Empty run log: nothing to plot')
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.colors import LinearSegmentedColormap
    except ImportError as exc:
        raise ImportError('Plotting needs matplotlib: pip install matplotlib') from exc

    t = series(rows, 'time')
    neurons = sorted({k[3:] for r in rows for k in r if k.startswith('dn_')})
    if not neurons:
        raise ValueError('No dn_* columns in the log: was it written by takeoff_landing --log?')
    # Rows before the first brain decision have no rates yet: show them as silent.
    rates = [[_num(r.get(f'dn_{n}')) or 0.0 for r in rows] for n in neurons]
    vmax = max(1.0, max(max(row) for row in rates))

    plt.rcParams.update({'font.size': 9, 'text.color': INK, 'axes.labelcolor': INK_2,
                         'xtick.color': INK_2, 'ytick.color': INK_2, 'axes.edgecolor': GRID})
    fig, all_axes = plt.subplots(5, 1, sharex=True, figsize=(11, 9.5), facecolor=SURFACE,
                                 gridspec_kw={'height_ratios': [0.32, 1.1, 2.6, 0.9, 0.9], 'hspace': 0.3})
    ax_phase, ax_sugar, ax_brain, ax_alt, ax_speed = all_axes
    axes = all_axes[1:]
    phase_strip(ax_phase, phase_changes(rows), t[-1])
    for ax in axes:
        ax.set_facecolor(SURFACE)
        for side in ('top', 'right'):
            ax.spines[side].set_visible(False)

    def line(ax, key, label, color):
        ax.plot(t, series(rows, key), color=color, linewidth=2, solid_capstyle='round')
        ax.set_ylabel(label)
        ax.grid(axis='y', color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)

    line(ax_sugar, 'in_sugar', 'Hz', SUGAR)
    ax_sugar.set_title('Sugar input to the brain (speed reward, LB3c)', loc='left', fontsize=10, color=INK)
    ax_sugar.set_ylim(bottom=0)

    cmap = LinearSegmentedColormap.from_list('firing', RAMP)
    edges = t + [t[-1] + (t[-1] - t[-2] if len(t) > 1 else 1.0)]
    mesh = ax_brain.pcolormesh(edges, range(len(neurons) + 1), rates, cmap=cmap, vmin=0, vmax=vmax,
                               shading='flat', rasterized=True)
    ax_brain.set_yticks([i + 0.5 for i in range(len(neurons))], neurons)
    ax_brain.tick_params(axis='y', length=0)
    ax_brain.invert_yaxis()
    ax_brain.set_title('Brain activity: descending neuron firing rate (darker = firing harder)',
                       loc='left', fontsize=10, color=INK)
    bar = fig.colorbar(mesh, ax=all_axes, location='right', fraction=0.025, pad=0.015, aspect=40)
    bar.set_label('firing rate (Hz)', color=INK_2)
    bar.outline.set_visible(False)

    line(ax_alt, 'agl_ft', 'ft', INK_2)
    ax_alt.set_title('Altitude above ground', loc='left', fontsize=10, color=INK)
    line(ax_speed, 'ias_kt', 'kt', INK_2)
    ax_speed.set_title('Airspeed', loc='left', fontsize=10, color=INK)
    ax_speed.set_xlabel('time (s)')

    for when, _ in phase_changes(rows)[1:]:
        for ax in axes:
            ax.axvline(when, color=INK_2, linewidth=0.8, linestyle=(0, (3, 3)), alpha=0.7)

    fig.suptitle(title or 'Fly-brain run', x=0.125, ha='left', fontsize=13, color=INK, y=0.94)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140, facecolor=SURFACE)
    plt.close(fig)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('log', help='CSV from takeoff_landing --log')
    p.add_argument('-o', '--out', help='PNG to write (default: next to the CSV)')
    p.add_argument('--title')
    args = p.parse_args(argv)
    try:
        out = plot(load(args.log), args.out or Path(args.log).with_suffix('.png'),
                   args.title or Path(args.log).stem)
    except (OSError, ValueError, ImportError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    print(f'Plot written to {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
