"""Takeoff/landing fly with a run log, so the session's live brain page shows it.

    python -m flight_simulator.takeoff_live takeoff --brain connectome --backend flightgear

Same arguments as `python -m flight_simulator.takeoff_landing`. This only wraps it:
it opens a RunLog (sim-logs `runs/<time>_<who>_<backend>-<brain>/`), and while the
fly flies it writes
    fly_activity.csv   one row per brain decision: sensory inputs + descending-neuron rates
    fly_spikes.jsonl   connectome: every neuron that fired in that trial (the brain map)
    airplane.csv       every sim step the controller logged
The FlightGear session logger tails those files, so http://127.0.0.1:8765/brain shows
the fly live. Nothing about how the fly flies changes (takeoff_landing.py is untouched).
`launch_fg --phase takeoff --fly` starts this automatically.
"""
import argparse
import csv
import json
import os
import socket
import sys
import time

from . import takeoff_landing as tl
from .runlog import RunLog


def parking_brake(telnet_port, on):
    """Hold the 737 still while the brain calibrates (minutes for the connectome).

    The takeoff start has the engines already running and the parking brake off, so
    without this the airplane creeps off the runway at idle before the fly ever gets
    the controls (2026-11-14: 30 m off the centerline, heading 195 instead of 284, at
    handover). Released right before the fly takes over. Not an autopilot."""
    from .flightgear import telnet_get
    try:
        with socket.create_connection(('127.0.0.1', telnet_port), timeout=3) as s:
            s.sendall(f'data\r\nset /controls/gear/brake-parking {int(on)}\r\nquit\r\n'.encode())
    except OSError:
        return False
    return telnet_get(telnet_port, '/controls/gear/brake-parking') in (str(int(on)), str(bool(on)).lower())


CALIBRATION_TRIALS = 20  # flies.PhaseFly.calibrate() default


class Stage:
    """stage.json in the run folder: what the fly brain is doing right now.

    The session logger passes it to the brain page, so the page can say
    "loading", "calibrating: trial 7 of 20" or "flying" instead of looking idle
    during the minutes before the handover. Written atomically (replace)."""
    def __init__(self, runlog):
        self.path, self.runlog = runlog.dir / 'stage.json', runlog
        self.state = {}

    def set(self, stage, **info):
        self.state = {'stage': stage, 'since': time.time(), **info}
        self._write()

    def update(self, **info):
        self.state.update(info)
        self._write()

    def _write(self):
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.state), encoding='utf-8')
        os.replace(tmp, self.path)


def watch_calibration(brain, stage, runlog):
    """Count the brain's calibration trials (read-only wrapper around brain.run)."""
    run = brain.run

    def counted(*a, **k):
        out = run(*a, **k)
        if stage.state.get('stage') == 'calibrating':
            done = stage.state.get('done', 0) + 1
            stage.update(done=done, last_trial_s=round(time.time() - stage.state['trial_started'], 1),
                         trial_started=time.time())
            counts = getattr(brain, 'last_counts', None)
            if counts is not None and hasattr(counts, 'nonzero'):
                runlog._spike_row(None, counts, getattr(brain, 'ms', None))
        return out
    brain.run = counted


def fly_row(entry):
    """Brain-page row: time, phase, inputs as in_<x>_hz, readouts as <DN>_hz."""
    row = {'time': entry.get('time'), 'phase': entry.get('phase')}
    for k, v in entry.items():
        if k.startswith('in_'):
            row[f'{k}_hz'] = v
        elif k.startswith('dn_'):
            row[f'{k[3:]}_hz'] = v
    return row


class LiveLog(list):
    """The list takeoff_landing appends each sim step to, mirrored into the run log."""
    def __init__(self, runlog, fly):
        super().__init__()
        self.runlog, self.fly = runlog, fly
        self._air = self._air_writer = None
        self._last_counts = None
        self._last_dn = None

    def append(self, entry):
        super().append(entry)
        if self._air is None:
            self._air = open(self.runlog.dir / 'airplane.csv', 'w', newline='', encoding='utf-8')
            self._air_writer = csv.DictWriter(self._air, list(entry), extrasaction='ignore')
            self._air_writer.writeheader()
        self._air_writer.writerow(entry)
        self._air.flush()
        brain = getattr(self.fly, 'brain', None)
        counts = getattr(brain, 'last_counts', None)
        dn = tuple(v for k, v in entry.items() if k.startswith('dn_'))
        # One fly row per brain decision: a new trial publishes a new counts array
        # (connectome) or new readout rates (stand-in).
        if counts is not None and counts is not self._last_counts:
            self._last_counts = counts
        elif not dn or dn == self._last_dn:
            return
        self._last_dn = dn
        self.runlog.fly(fly_row(entry))
        if counts is not None and hasattr(counts, 'nonzero'):
            self.runlog._spike_row(entry.get('time'), counts, getattr(brain, 'ms', None))

    def close(self):
        if self._air:
            self._air.close()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument('phase', nargs='?', default='takeoff')
    p.add_argument('--brain', default='standin')
    p.add_argument('--backend', default='demo')
    p.add_argument('--telemetry-port', type=int, default=5501)
    ns, _ = p.parse_known_args(argv)
    telnet = ns.telemetry_port - 1
    hold = ns.backend == 'flightgear' and ns.phase == 'takeoff'
    if hold:
        print('Parking brake ' + ('SET' if parking_brake(telnet, True) else 'could NOT be set')
              + ' while the fly brain calibrates.', flush=True)
    runlog = RunLog(ns, ['takeoff_live', *argv])
    stage = Stage(runlog)
    stage.set('loading', note=f'loading the {ns.brain} brain')
    calibrate = '--no-calibrate' not in argv
    make_brain = tl.make_brain

    def made(args):
        brain = make_brain(args)
        if calibrate:
            stage.set('calibrating', done=0, total=CALIBRATION_TRIALS, trial_started=time.time(),
                      note='measuring the resting steering level (neutral stimulus); '
                           'the airplane is held on the parking brake' if hold else
                           'measuring the resting steering level (neutral stimulus)')
            watch_calibration(brain, stage, runlog)
        return brain
    tl.make_brain = made
    live = {}
    real = {'demo': tl.run_demo, 'flightgear': tl.run_flightgear}

    def wrap(name):
        def run(args, fly, log):
            live['log'] = LiveLog(runlog, fly)
            if hold and name == 'flightgear':
                if not parking_brake(telnet, False):
                    raise RuntimeError('Could not release the parking brake for the takeoff roll')
                print('Parking brake released: the fly has the airplane.', flush=True)
            stage.set('flying', note='the fly brain has the controls')
            result = real[name](args, fly, live['log'])
            log.extend(live['log'])
            runlog.result = {**result, 'phase': ns.phase}
            return result
        return run

    tl.run_demo, tl.run_flightgear = wrap('demo'), wrap('flightgear')
    code = 1
    try:
        code = tl.main(argv)
    finally:
        if 'log' in live:
            live['log'].close()
        stage.set('finished', exit_code=code)
        runlog.finish(code)
    return code


if __name__ == '__main__':
    sys.exit(main())
