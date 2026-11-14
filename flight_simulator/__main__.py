"""Run an airborne obstacle avoidance experiment."""
import argparse
import csv
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import sys
import time
from .brain import ReflexBrain, SilentBrain, ConnectomeBrain
from .core import Controls, DemoSimulator, FlightController, Obstacle, sense, wrap

ROOT = Path(__file__).resolve().parent.parent


def load_obstacles(path):
    items = json.loads(Path(path).read_text())['obstacles']
    obstacles = [Obstacle(**item) for item in items]
    for o in obstacles:
        if (not all(math.isfinite(v) for v in (o.east, o.north, o.radius, o.bottom, o.top))
                or o.radius <= 0 or o.top <= o.bottom):
            raise ValueError('Obstacle dimensions must be finite, radius > 0 and top > bottom')
    return obstacles


def run(args, runlog=None):
    obstacles = load_obstacles(args.obstacles)
    brain = {'reflex': ReflexBrain, 'silent': SilentBrain}.get(args.brain)
    brain = brain() if brain else ConnectomeBrain(args.data, seed=args.seed)
    print(brain.name, flush=True)
    if args.brain == 'connectome':
        print('Connectome decisions run synchronously; FlightGear pauses during each trial.', flush=True)
    view = None
    bridge = None
    log_file = None
    try:
        if args.backend == 'flightgear':
            from .flightgear import FlightGear
            bridge = FlightGear(args.telemetry_port, args.control_port, engines=args.engines)
            print('Waiting for airborne FlightGear telemetry on localhost...', flush=True)
            state = bridge.read()
            if state.speed < 35 or abs(state.roll) > .35:
                raise ValueError('Start FlightGear in stable flight, at least 35 m/s and wings near level.')
            controller = FlightController(state.altitude, state.heading, state.speed, state.pitch)
            print('FlightGear connected. Initial altitude/heading/speed are the hold targets.', flush=True)
        else:
            sim = DemoSimulator()
            state = sim.state
            controller = FlightController()
        if bridge and Path(args.obstacles).resolve() == (ROOT / 'scenarios/obstacles.json').resolve():
            # Keep the default course ahead of any spawn heading. Faster aircraft
            # need more space to turn; custom obstacle files remain local ENU.
            scale = max(1.0, (state.speed / 50.0)**2)
            sn, cs = math.sin(state.heading), math.cos(state.heading)
            obstacles = [replace(o, east=o.east*cs + o.north*scale*sn,
                                 north=-o.east*sn + o.north*scale*cs,
                                 top=max(o.top, state.altitude+500)) for o in obstacles]
        if args.plot or (args.backend == 'flightgear' and not args.no_plot):
            from .view import View
            view = View(obstacles)
        if args.log:
            Path(args.log).parent.mkdir(parents=True, exist_ok=True)
            log_file = open(args.log, 'w', newline='')
            fields = list(asdict(state)) + ['phase', 'brain', 'looming_hz', 'escape_hz',
                      'clearance', 'aileron', 'elevator', 'rudder', 'throttle']
            writer = csv.DictWriter(log_file, fields)
            writer.writeheader()
        next_brain, next_display, next_print = 0.0, 0.0, 0.0
        escape, controls = 0.0, Controls()
        minimum = math.inf
        min_altitude = state.altitude
        collision = False
        start = state.time
        while args.seconds == 0 or state.time - start < args.seconds:
            tick = time.monotonic()
            stimulus = sense(state, obstacles, horizon=max(25.0, state.speed / 2))
            if state.time >= next_brain:
                if bridge and args.brain == 'connectome':
                    state = bridge.freeze(True)
                    stimulus = sense(state, obstacles, horizon=max(25.0, state.speed / 2))
                escape = brain.escape(stimulus.looming_hz)
                next_brain = state.time + .5
                if bridge and args.brain == 'connectome':
                    state = bridge.freeze(False)
            if bridge and (abs(wrap(state.heading-controller.heading)) > math.radians(90)
                           or abs(state.roll) > math.radians(50)
                           or abs(state.pitch) > math.radians(25)
                           or state.speed < .70 * controller.speed
                           or state.altitude < controller.altitude - 150):
                raise RuntimeError('Flight departed the test envelope (heading, bank, pitch, speed or altitude); pausing. Check aircraft controls and trim.')
            controls = controller.update(state, stimulus, escape)
            clearance = min((o.clearance(state) for o in obstacles), default=math.inf)
            minimum = min(minimum, clearance)
            min_altitude = min(min_altitude, state.altitude)
            collision = collision or clearance <= 0 or state.altitude <= 0
            if log_file:
                writer.writerow({**asdict(state), **asdict(controls), 'phase': controller.phase,
                                 'brain': args.brain, 'looming_hz': stimulus.looming_hz,
                                 'escape_hz': escape, 'clearance': clearance})
            if state.time >= next_print:
                print(f'{state.time:6.1f}s {controller.phase:6} altitude={state.altitude:7.1f}m '
                      f'speed={state.speed:5.1f}m/s escape={escape:5.1f}Hz clearance={clearance:7.1f}m', flush=True)
                next_print = state.time + 10
            if view and state.time >= next_display:
                view.update(state, controller.phase, brain.name, stimulus, escape, controller.target_heading)
                next_display = state.time + .2
            if collision:
                print('STOP: collision with a configured obstacle or ground.', flush=True)
                break
            if bridge:
                bridge.send(controls)
                state = bridge.read()
            else:
                state = sim.step(controls, .05)
                if args.realtime:
                    time.sleep(max(0, .05 - (time.monotonic() - tick)))
        result = {'backend': args.backend, 'brain': args.brain,
                  'elapsed_s': round(state.time - start, 2), 'collision': collision,
                  'minimum_clearance_m': round(minimum, 2) if math.isfinite(minimum) else None,
                  'minimum_altitude_m': round(min_altitude, 2),
                  'avoidance_activations': controller.activations}
        if runlog:
            runlog.result = result
        print(json.dumps(result, indent=2))
        return 2 if collision else 0
    finally:
        if log_file:
            log_file.close()
        if bridge:
            bridge.close()
            print('Sent FlightGear pause request on exit. Verify pause in the simulator.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=['demo', 'flightgear'], default='demo')
    parser.add_argument('--brain', choices=['reflex', 'connectome', 'silent'], required=True,
                        help='Explicit selection: reflex is a non-neural baseline; connectome needs data.')
    parser.add_argument('--data', default='data/brain')
    parser.add_argument('--obstacles', default=str(ROOT / 'scenarios/obstacles.json'))
    parser.add_argument('--seconds', type=float, default=180, help='Active flight time; 0 runs until Ctrl-C')
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--plot', action='store_true', help='Show 3D obstacles and flight-path companion')
    parser.add_argument('--no-plot', action='store_true', help='Disable the default FlightGear companion')
    parser.add_argument('--engines', type=int, choices=[1, 2], default=1, help='2 requires flybrain-controls-twin.xml in FlightGear')
    parser.add_argument('--realtime', action='store_true', help='Pace the local demo at 20 Hz')
    parser.add_argument('--log', help='CSV telemetry output path')
    parser.add_argument('--telemetry-port', type=int, default=5501)
    parser.add_argument('--control-port', type=int, default=5502)
    parser.add_argument('--note', help='Feedback note saved with this run log')
    parser.add_argument('--no-push', action='store_true', help='Log this run locally, do not push')
    parser.add_argument('--no-runlog', action='store_true', help='Skip the run log entirely')
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds < 0:
        parser.error('--seconds must be finite and nonnegative')
    if any(not 1 <= p <= 65535 for p in [args.telemetry_port, args.control_port]):
        parser.error('Ports must be between 1 and 65535')
    runlog = None
    if not args.no_runlog:
        from .runlog import RunLog
        runlog = RunLog(args, sys.argv[1:], auto_push=not args.no_push)
        if not args.log:
            args.log = str(runlog.dir / 'telemetry.csv')
    code = 1
    try:
        code = run(args, runlog)
    except KeyboardInterrupt:
        print('\nStopped.')
        code = 130
    except (OSError, ValueError, RuntimeError, ImportError, KeyError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        code = 1
    finally:
        if runlog:
            runlog.finish(code)
    return 0 if code == 130 else code


if __name__ == '__main__':
    sys.exit(main())
