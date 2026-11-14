"""Fly the 737-800 through takeoff or landing with a fly brain.

    python -m flight_simulator.takeoff_landing takeoff --brain connectome
    python -m flight_simulator.takeoff_landing landing --brain connectome
    python -m flight_simulator.takeoff_landing takeoff --brain standin --fault-at-kt 100   # rejected takeoff
    python -m flight_simulator.takeoff_landing landing --brain connectome --silence looming  # lesion control

Two configured brains on one connectome (docs/TAKEOFF_LANDING_PLAN.md):
the Takeoff fly is a *standing* fly (looming -> jump = rotation), the Landing
fly is a *flying* fly (looming -> DNp07 leg extension = flare).

--brain connectome runs the real FlyWire 783 LIF model (needs requirements-brain.txt
and `python -m flight_simulator.download_data`). --brain standin is a
deterministic lookup of the measured probe table, labelled as NOT a fly brain,
for fast offline runs and tests.

Exit status: 0 = success criteria met, 2 = failed (crash, tail strike, hard
landing, off the runway), 1 = configuration/runtime error.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import sys
import time

from .brain import INPUTS, READOUTS
from .flies import TakeoffFly, LandingFly, StandInBrain, run_phase, row, summarize, HOLD_PITCH
from .runway import (RunwaySim, FLAPS5, FLAPS30, FT, KT, RUNWAY_LENGTH,
                     takeoff_start, trimmed_approach, trim_elevator)

TOUCHDOWN_ZONE = (0.0, 900.0)  # m past the threshold
MAX_SINK_FPM = 500.0


def make_brain(args):
    if args.brain == 'standin':
        return StandInBrain(args.silence, noise_seed=args.noise_seed)
    from .brain import ConnectomeBrain
    return ConnectomeBrain(args.data, seed=args.seed, silence=args.silence)


def judge(phase, r):
    """Did the fly meet the plan's 'done when' criteria? (reduced sim / FG alike)"""
    if r['tail_strike'] or r['stall'] or r['left_runway']:
        return False
    if phase == 'takeoff':
        return r['completed'] and (r['rejected'] or r['phase'].startswith('HANDOVER'))
    if r['go_around']:
        return r['completed']
    x, sink = r['touchdown_x_m'], r['touchdown_sink_fpm']
    return (x is not None and TOUCHDOWN_ZONE[0] <= x <= TOUCHDOWN_ZONE[1]
            and sink is not None and sink < MAX_SINK_FPM)


def run_demo(args, fly, log):
    if args.phase == 'takeoff':
        sim = RunwaySim(takeoff_start(y=args.offset_m), FLAPS5, yaw_disturbance=args.yaw_drift)
    else:
        state = trimmed_approach(speed_kt=args.start_speed_kt or 145.0, y=args.offset_m)
        state.agl += args.high_ft * FT
        sim = RunwaySim(state, FLAPS30)
        fly.trim_throttle = fly.throttle = state.spool
        fly.elevator_i = trim_elevator(state)
    last_print = [-10.0]

    def progress(f, s, c):
        if s.time - last_print[0] >= 5:
            last_print[0] = s.time
            d = f.decisions[-1] if f.decisions else None
            dn = '' if not d else ' '.join(f'{k}={d.rates[k]:.0f}' for k in
                                           ('MN9', 'DNp07', 'DNp04', 'DNp20_L', 'DNp15_R') if d.rates.get(k))
            print(f'{s.time:6.1f}s {f.status.phase:20s} x={s.x:7.0f}m agl={s.agl / FT:6.0f}ft '
                  f'ias={s.speed / KT:5.1f}kt pitch={math.degrees(s.pitch):5.1f}° '
                  f'thr={c.throttle:.2f} | {dn}', flush=True)
    return run_phase(fly, sim, args.seconds, log=log, on_tick=progress)


def run_flightgear(args, fly, log):
    """Live FlightGear. The sim is frozen during every brain trial."""
    from .flightgear import RunwayFlightGear
    runway = tuple(args.runway) if args.runway else None
    # Without --runway, landing assumes the launch_fg --phase landing start:
    # on the extended centerline, --final-nm before the threshold.
    ahead = args.final_nm * 1852.0 if args.phase == 'landing' else 0.0
    bridge = RunwayFlightGear(args.telemetry_port, args.control_port, runway=runway, ahead_m=ahead)
    try:
        print('Waiting for FlightGear runway telemetry on localhost...', flush=True)
        s = bridge.read()
        if args.phase == 'takeoff' and not s.on_ground:
            raise ValueError('Start FlightGear on the runway (main gear on the ground) for takeoff')
        if args.phase == 'landing' and (s.on_ground or s.agl < 300 * FT):
            raise ValueError('Start FlightGear on a stabilised approach above 300 ft for landing')
        if args.phase == 'landing':
            fly.trim_throttle = fly.throttle = args.approach_throttle
            # In-air 737 start: the overlay's autopilot holds the plane until we say we're here.
            from .flightgear import hand_over
            if not hand_over(args.telemetry_port - 1):
                print('WARNING: no telnet handover; the 737 autopilot stays on (start FlightGear with --telnet).',
                      flush=True)
        previous = s.time
        max_y, touchdown, liftoff, tail_strike = 0.0, None, None, False
        body = None
        if not args.no_fly_body:
            # Live 3D fly window (python -m flight_simulator.fly_body); display only.
            from .fly_body import BodyLink
            body = BodyLink(args.body_port)
        while True:
            # Never stop sending while airborne: FlightGear keeps the last controls
            # it received, so an exit mid-air flies the plane on frozen surfaces.
            # (2026-11-14 FG test: handover at 1,000 ft, controller exited, rudder
            # -0.2 stayed latched, spiral dive into the ground.)
            if (fly.status.done or s.time >= args.seconds) and s.on_ground:
                break
            if fly.status.done and not fly.hold:
                fly.hold = True
                print(f'{fly.status.phase} reached in the air. No Cruise fly yet, so the {fly.name} keeps '
                      f'flying: wings level, {HOLD_PITCH:.0f} deg climb, climb power. '
                      'Press Ctrl-C to pause FlightGear and exit.', flush=True)
            if fly.decision_due(s):
                s = bridge.freeze(True)
                t0 = time.monotonic()
                controls = fly.step(s, max(s.time - previous, 1e-3))
                if args.brain == 'connectome':
                    print(f'  brain trial {time.monotonic() - t0:.1f}s', flush=True)
                s = bridge.freeze(False)
            else:
                controls = fly.step(s, max(s.time - previous, 1e-3))
            if isinstance(fly, TakeoffFly) and not s.on_ground and s.climb > 1 and s.agl > 10:
                bridge.gear_down = False  # scripted checklist: gear up at positive climb
            log.append(row(fly, s, controls))
            if body:
                last = fly.decisions[-1] if fly.decisions else None
                rates = {f'{k}_hz': v for k, v in last.rates.items()} if last else None
                body.send(s, fly.status.phase, args.brain, (rates or {}).get('DNp01_hz', 0.0), rates)
            bridge.send(controls)
            previous = s.time
            was_ground = s.on_ground
            try:
                s = bridge.read()
            except KeyboardInterrupt:
                print('\nCtrl-C: pausing FlightGear.', flush=True)
                break
            if s.on_ground or s.agl < 100 * FT:
                max_y = max(max_y, abs(s.y))
            if was_ground and not s.on_ground and liftoff is None:
                liftoff = s.x
            if not was_ground and s.on_ground and touchdown is None:
                touchdown = (s.x, -log[-1]['climb_fpm'], log[-1]['pitch_deg'])
            if s.on_ground and math.degrees(s.pitch) > 11:
                tail_strike = True
                break
            if s.on_ground and (abs(s.y) > 30 or s.x > RUNWAY_LENGTH):
                break
        sim_like = type('FGResult', (), {})()
        sim_like.state = s
        sim_like.events = type('Ev', (), dict(
            liftoff_x=liftoff, tail_strike=tail_strike, stall=False,
            left_runway=s.on_ground and abs(s.y) > 30,
            touchdown_x=touchdown and touchdown[0],
            touchdown_sink_fpm=touchdown and touchdown[1],
            touchdown_pitch_deg=touchdown and touchdown[2]))()
        return summarize(fly, sim_like, max_y)
    finally:
        paused = bridge.close()
        print('FlightGear paused (acknowledged), ailerons and rudder centred.' if paused else
              'WARNING: FlightGear did not acknowledge the pause. Pause it by hand (p) NOW: '
              'it keeps the last controls it received.', flush=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('phase', choices=['takeoff', 'landing'])
    p.add_argument('--brain', choices=['connectome', 'standin'], required=True)
    p.add_argument('--backend', choices=['demo', 'flightgear'], default='demo')
    p.add_argument('--data', default='data/brain')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--noise-seed', type=int,
                   help='standin only: add the connectome\'s spike-count noise (1-4 neurons per readout)')
    p.add_argument('--silence', nargs='+', default=[], choices=list(INPUTS) + list(READOUTS),
                   help='Lesion control: cut the outgoing synapses of these groups')
    p.add_argument('--period', type=float, default=0.5, help='Seconds of sim time between brain trials')
    p.add_argument('--seconds', type=float, default=200)
    p.add_argument('--fault-at-kt', type=float, help='Takeoff: inject a reject condition at this speed')
    p.add_argument('--offset-m', type=float, default=0.0, help='Initial centerline offset (demo)')
    p.add_argument('--yaw-drift', type=float, default=0.0, help='Takeoff ground yaw disturbance, rad/s (demo)')
    p.add_argument('--start-speed-kt', type=float, help='Landing: initial approach speed (demo)')
    p.add_argument('--high-ft', type=float, default=0.0, help='Landing: start this far above the glideslope (demo)')
    p.add_argument('--runway', type=float, nargs=3, metavar=('LAT', 'LON', 'HDG'),
                   help='FlightGear: runway threshold/brake-release point and true heading')
    p.add_argument('--final-nm', type=float, default=3.0,
                   help='FlightGear landing without --runway: start distance before the threshold, nm')
    p.add_argument('--approach-throttle', type=float, default=0.55, help='FlightGear landing: approach power')
    p.add_argument('--telemetry-port', type=int, default=5501)
    p.add_argument('--control-port', type=int, default=5502)
    p.add_argument('--log', help='CSV of every sim step, incl. sensory inputs and DN rates')
    p.add_argument('--body-port', type=int, default=5600, help='UDP port of the live 3D fly window')
    p.add_argument('--no-fly-body', action='store_true', help='Do not stream to the 3D fly window')
    p.add_argument('--plot', help='PNG of sugar input, brain activity, altitude and airspeed (needs matplotlib)')
    args = p.parse_args(argv)
    if not math.isfinite(args.seconds) or args.seconds <= 0 or args.period <= 0:
        p.error('--seconds and --period must be positive')
    try:
        brain = make_brain(args)
        print(brain.name, flush=True)
        if args.phase == 'takeoff':
            fly = TakeoffFly(brain, args.period, fault_at_kt=args.fault_at_kt)
        else:
            fly = LandingFly(brain, args.period)
        print(f'{fly.name}: ' + ('standing fly, looming -> jump = rotation' if args.phase == 'takeoff'
                                 else 'flying fly, looming -> DNp07 = flare'), flush=True)
        log = []
        start = time.monotonic()
        result = (run_demo if args.backend == 'demo' else run_flightgear)(args, fly, log)
        result['backend'] = args.backend
        result['wall_s'] = round(time.monotonic() - start, 1)
        result['success'] = judge(args.phase, result)
        if args.log and log:
            Path(args.log).parent.mkdir(parents=True, exist_ok=True)
            fields = sorted({k for r in log for k in r}, key=lambda k: (k.startswith(('in_', 'dn_')), k))
            with open(args.log, 'w', newline='') as f:
                w = csv.DictWriter(f, fields)
                w.writeheader()
                w.writerows(log)
        if args.plot and log:
            from .plot_run import plot
            title = f'{fly.name}, {brain.name} ({args.backend}): ' + ('success' if result['success'] else 'FAILED')
            # The CSV round-trip keeps the plot identical to plot_run on the saved log.
            rows = [{k: ('' if v is None else str(v)) for k, v in r.items()} for r in log]
            print(f'Plot written to {plot(rows, args.plot, title)}', flush=True)
        print(json.dumps(result, indent=2))
        return 0 if result['success'] else 2
    except KeyboardInterrupt:
        print('\nStopped.')
        return 0
    except (OSError, ValueError, RuntimeError, ImportError, KeyError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
