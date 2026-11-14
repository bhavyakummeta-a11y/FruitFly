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
        return r['completed'] and not r['rejected'] and r['phase'].startswith('HANDOVER')
    if r['go_around']:
        return False
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
    """Live FlightGear, in real time: the sim stays at 1x and is never paused or slowed for
    a brain trial. Trials run in a background worker; the plane flies on the last decision
    until the next one is ready. If the brain is too slow and the plane crashes, that is data."""
    from dataclasses import replace
    from .flightgear import RunwayFlightGear, SpeedLock, engine_asymmetry
    runway = tuple(args.runway) if args.runway else None
    # Without --runway, landing assumes the launch_fg --phase landing start:
    # on the extended centerline, --final-nm before the threshold.
    ahead = args.final_nm * 1852.0 if args.phase == 'landing' else 0.0
    bridge = RunwayFlightGear(args.telemetry_port, args.control_port, runway=runway, ahead_m=ahead)
    pilot = None
    ap_guard = None
    speed_lock = None
    worker = fly.run_in_background()
    body = None
    reason = "time_limit"
    try:
        print('Waiting for FlightGear runway telemetry on localhost...', flush=True)
        s = bridge.read()
        bridge.send(bridge.last_controls)  # idle + brakes until the fly's first decision
        # 1x rule (gh #3): raises if FlightGear can't be put and kept at 1x sim speed.
        speed_lock = SpeedLock(args.telemetry_port - 1)
        print('Real time: FlightGear at 1x, no pause during brain trials.', flush=True)
        if args.phase == 'takeoff' and not s.on_ground:
            raise ValueError('Start FlightGear on the runway (main gear on the ground) for takeoff')
        if args.phase == 'landing' and (s.on_ground or s.agl < 300 * FT):
            raise ValueError('Start FlightGear on a stabilised approach above 300 ft for landing')
        if args.phase == 'landing':
            fly.trim_throttle = fly.throttle = args.approach_throttle
        # No-autopilot rule: the fly never flies with the airplane autopilot on. In an in-air
        # 737 start the overlay's autopilot holds the plane until the handover switches it off.
        from .flightgear import AutopilotGuard, hand_over
        ap_guard = AutopilotGuard(args.telemetry_port - 1)  # raises if it can't be verified (no telnet)
        if not hand_over(args.telemetry_port - 1):
            raise RuntimeError('FlightGear did not acknowledge the handover; the fly does not take the '
                               'controls without it (no-autopilot rule).')
        ap_guard.wait_off()
        print('Handover: airplane autopilot confirmed OFF; the fly flies.', flush=True)
        previous = start = s.time
        max_y, touchdown, liftoff, tail_strike = 0.0, None, None, False
        asym_since = None
        body = None
        if not args.no_cockpit_fly:
            # The fly pilot in the 737's captain seat, animated by this brain (display only).
            from .flightgear import CockpitFly
            try:
                pilot = CockpitFly(args.telemetry_port - 1)
            except OSError as exc:
                print(f'Cockpit fly not animated (telnet: {exc}).', flush=True)
        if not args.no_fly_body:
            # Live 3D fly window (python -m flight_simulator.fly_body); display only.
            from .fly_body import BodyLink
            body = BodyLink(args.body_port)
        while True:
            # Keep flying after airborne phase completion until the run time limit.
            # Cleanup requests an acknowledged pause so surfaces are not left latched.
            if fly.status.done and s.on_ground:
                reason='phase_completed';break
            if s.time-start >= args.seconds:
                reason='time_limit';break
            if fly.status.done and not fly.hold:
                fly.hold = True
                print(f'{fly.status.phase} reached in the air. No Cruise fly yet, so the {fly.name} keeps '
                      f'flying: wings level, {HOLD_PITCH:.0f} deg climb, climb power. '
                      'Press Ctrl-C to pause FlightGear and exit.', flush=True)
            applied = len(worker.records)
            controls = fly.step(s, max(s.time - previous, 1e-3))  # never waits for the brain
            if len(worker.records) > applied and args.brain == 'connectome':
                rec = worker.records[-1]
                print(f'  decision {fly.last_decision_status} {rec["latency_s"]:.1f}s after its state  {fly.status.phase:14s} '
                      f'ias={s.speed / KT:5.1f}kt agl={s.agl / FT:5.0f}ft pitch={math.degrees(s.pitch):4.1f}deg '
                      f'thr={controls.throttle:.2f}', flush=True)
            if isinstance(fly, TakeoffFly) and not s.on_ground and s.climb > 1 and s.agl > 10:
                bridge.gear_down = False  # scripted checklist: gear up at positive climb
            entry = row(fly, s, controls)
            if worker.records:
                entry['decision_started'] = round(worker.records[-1]['started'], 3)
                entry['decision_latency_s'] = round(worker.records[-1]['latency_s'], 3)
                entry['decision_accepted'] = worker.records[-1].get('accepted',True)
            entry['decisions_skipped'] = worker.skipped
            log.append(entry)
            ap_guard.check()  # no-autopilot rule; raises if it can't be forced off
            speed_lock.check()  # 1x rule; resets and records any change
            if body:
                last = fly.decisions[-1] if fly.decisions else None
                rates = {f'{k}_hz': v for k, v in last.rates.items()} if last else None
                body.send(s, fly.status.phase, args.brain, (rates or {}).get('DNp01_hz', 0.0), rates)
            if pilot:
                last = fly.decisions[-1] if fly.decisions else None
                rates = {f'{k}_hz': v for k, v in last.rates.items()} if last else None
                pilot.update((rates or {}).get('DNp01_hz', 0.0), rates)
            bridge.send(controls)
            previous = s.time
            was_ground = s.on_ground
            try:
                s = bridge.read()
            except KeyboardInterrupt:
                print('\nCtrl-C: pausing FlightGear.', flush=True)
                reason='interrupted'
                break
            if s.on_ground or s.agl < 100 * FT:
                max_y = max(max_y, abs(s.y))
            if was_ground and not s.on_ground and liftoff is None:
                liftoff = s.x
            if not was_ground and s.on_ground and touchdown is None:
                touchdown = (s.x, -log[-1]['climb_fpm'], log[-1]['pitch_deg'])
            warning = engine_asymmetry(s, controls.throttle)
            asym_since = (asym_since or s.time) if warning else None
            if warning and s.time - asym_since >= 2.0:
                print(warning, flush=True)
                bridge.send(replace(controls, throttle=0.0, brake=1.0))
                reason="engine_asymmetry"
                break
            if s.on_ground and math.degrees(s.pitch) > 11:
                tail_strike = True
                reason="tail_strike"
                break
            if s.on_ground and (abs(s.y) > 30 or s.x > RUNWAY_LENGTH):
                reason="runway_departure"
                break
        sim_like = type('FGResult', (), {})()
        sim_like.state = s
        sim_like.events = type('Ev', (), dict(
            liftoff_x=liftoff, tail_strike=tail_strike, stall=False,
            left_runway=s.on_ground and (abs(s.y) > 30 or s.x > RUNWAY_LENGTH),
            touchdown_x=touchdown and touchdown[0],
            touchdown_sink_fpm=touchdown and touchdown[1],
            touchdown_pitch_deg=touchdown and touchdown[2]))()
        result = summarize(fly, sim_like, max_y)
        result['termination_reason'] = reason
        if reason in ('engine_asymmetry','interrupted','time_limit') and not fly.status.done:
            result['outcome'] = reason
        result['decision_timing'] = worker.summary()
        result['speed_up_resets'] = len(speed_lock.events)
        return result
    finally:
        if body: body.close()
        worker.close(wait=0)
        if pilot:
            pilot.close()
        if ap_guard:
            if ap_guard.violations:
                print(f'NO-AUTOPILOT RULE: {len(ap_guard.violations)} autopilot engagement(s) were forced off '
                      'during this run.', flush=True)
            ap_guard.close()
        if speed_lock:
            speed_lock.close()
        fly.worker = None
        paused = bridge.close()  # end of run only: stops a pilotless 737
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
    p.add_argument('--no-calibrate', action='store_true',
                   help='Skip the pre-flight adaptation trials that measure the zero points')
    p.add_argument('--noise-seed', type=int,
                   help='standin only: add the connectome\'s spike-count noise (1-4 neurons per readout)')
    p.add_argument('--silence', nargs='+', default=[], choices=list(INPUTS) + list(READOUTS),
                   help='Lesion control: cut the outgoing synapses of these groups')
    p.add_argument('--period', type=float, default=0.25, help='Seconds of sim time between brain trials')
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
    p.add_argument('--vision-port',type=int,default=5601,help='Synthetic fly-view UDP port; 0 disables display stream')
    p.add_argument('--vision-obstacles',help='Known obstacles JSON in runway coordinates: east=right, north=along; heights above runway')
    p.add_argument('--log', help='CSV of every sim step, incl. sensory inputs and DN rates')
    p.add_argument('--body-port', type=int, default=5600, help='UDP port of the live 3D fly window')
    p.add_argument('--no-fly-body', action='store_true', help='Do not stream to the 3D fly window')
    p.add_argument('--smooth', action='store_true',
                   help='Accepted for old commands, no effect: FlightGear runs are always real time '
                        '(1x, no pause per brain trial)')
    p.add_argument('--no-cockpit-fly', action='store_true', help='Do not animate the fly pilot in the 737 cockpit')
    p.add_argument('--plot', help='PNG of sugar input, brain activity, altitude and airspeed (needs matplotlib)')
    args = p.parse_args(argv)
    if not math.isfinite(args.seconds) or args.seconds <= 0 or args.period <= 0:
        p.error('--seconds and --period must be positive')
    vision = None
    try:
        brain = make_brain(args)
        print(brain.name, flush=True)
        if args.phase == 'takeoff':
            fly = TakeoffFly(brain, args.period, fault_at_kt=args.fault_at_kt)
        else:
            fly = LandingFly(brain, args.period)
        from .vision import VisionPublisher
        vision = VisionPublisher(args.vision_port)
        fly.vision_sink = vision
        if args.vision_obstacles:
            from .__main__ import load_obstacles
            fly.vision_obstacles = load_obstacles(args.vision_obstacles)
        if not args.no_calibrate:
            print('Adapting: measuring zero points with the neutral stimulus mix (20 brain trials)...', flush=True)
            cal = fly.calibrate()
            print('  zero points: ' + ', '.join(f'{k}={v:.1f}' for k, v in cal.items()), flush=True)
        print(f'{fly.name}: ' + ('standing fly, looming stimulus presented at Vr -> jump = rotation' if args.phase == 'takeoff'
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
    finally:
        if vision:
            vision.close()


if __name__ == '__main__':
    sys.exit(main())
