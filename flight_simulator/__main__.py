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


class EnvelopeMonitor:
    """Crashes are data (gh #5): leaving the test envelope is logged, never aborts the run.

    update() returns the limits newly broken this step. The run goes on until
    collision/ground contact or the time limit."""

    def __init__(self):
        self.active = set()
        self.events = []
        self.worst = {'bank_deg': 0.0, 'pitch_deg': 0.0, 'altitude_error_m': 0.0,
                      'heading_error_deg': 0.0, 'speed_fraction': 1.0}

    def update(self, state, controller):
        heading = math.degrees(abs(wrap(state.heading - controller.heading)))
        bank, pitch = math.degrees(state.roll), math.degrees(state.pitch)
        alt = state.altitude - controller.altitude
        fraction = state.speed / max(controller.speed, 1e-6)
        w = self.worst
        w['bank_deg'] = max(w['bank_deg'], abs(bank))
        w['pitch_deg'] = max(w['pitch_deg'], abs(pitch))
        w['altitude_error_m'] = max(w['altitude_error_m'], abs(alt))
        w['heading_error_deg'] = max(w['heading_error_deg'], heading)
        w['speed_fraction'] = min(w['speed_fraction'], fraction)
        limits = {
            'heading': (heading > 90, f'heading off by {heading:.0f} deg (>90)'),
            'bank': (abs(bank) > 50, f'bank {bank:+.0f} deg (>50)'),
            'pitch': (abs(pitch) > 25, f'pitch {pitch:+.0f} deg (>25)'),
            'speed': (fraction < .70, f'speed {state.speed:.0f} m/s (<70% of {controller.speed:.0f})'),
            'altitude': (abs(alt) > 40, f'altitude {alt:+.0f} m from target (>40)'),
        }
        hit = {kind for kind, (broken, _) in limits.items() if broken}
        new = [{'time_s': round(state.time, 2), 'kind': kind, 'detail': limits[kind][1]}
               for kind in limits if kind in hit and kind not in self.active]
        self.events += new
        self.active = hit
        return new

    def result(self):
        return {'breaches': len(self.events), 'first_breach': self.events[0] if self.events else None,
                **{f'worst_{k}': round(v, 2) for k, v in self.worst.items()},
                'events': self.events[:100]}


def run(args, runlog=None):
    obstacles = load_obstacles(args.obstacles)
    course = json.loads(Path(args.obstacles).read_text())
    course_origin = None
    if 'origin' in course:
        from .scenery import validate_origin
        course_origin = validate_origin(course['origin'])
    brain = {'reflex': ReflexBrain, 'silent': SilentBrain}.get(args.brain)
    if args.learn or args.load_learning:
        from .learning import LearningBrain
        brain = LearningBrain(args.data, seed=args.seed)
        if args.load_learning:
            brain.plasticity.load(args.load_learning)
        brain.name += ' (UPDATES ENABLED)' if args.learn else ' (FROZEN CHECKPOINT)'
    else:
        brain = brain() if brain else ConnectomeBrain(args.data, seed=args.seed)
    print(brain.name, flush=True)
    # Real-time rule (gh #4): in FlightGear the connectome decides in a background worker and
    # the sim is never paused for it. Fly training (--learn / --load-learning) is owned by a
    # teammate and keeps its synchronous pause per trial.
    training = bool(args.learn or args.load_learning)
    realtime = args.backend == 'flightgear' and args.brain == 'connectome' and not training
    if realtime:
        print('Real time: FlightGear stays at 1x and is not paused for brain trials; the plane flies on '
              'the last decision while the connectome works. A crash is data.', flush=True)
    elif args.brain == 'connectome' and args.backend == 'flightgear':
        print('Training run: connectome decisions run synchronously; FlightGear pauses during each trial.',
              flush=True)
    worker = None
    speed_lock = None
    envelope = EnvelopeMonitor()
    view = None
    bridge = None
    body = None
    pilot = None
    scene = None
    ap_guard = None
    log_file = None
    from .vision import scene as visual_scene, visual_escape, VisionPublisher
    vision = VisionPublisher(args.vision_port)
    applied_inputs, applied_time = {}, None
    try:
        if args.backend == 'flightgear':
            from .flightgear import FlightGear
            bridge = FlightGear(args.telemetry_port, args.control_port, engines=args.engines)
            if course_origin is not None:
                bridge.origin = course_origin
            print('Waiting for airborne FlightGear telemetry on localhost...', flush=True)
            state = bridge.read()
            from .flightgear import SpeedLock, telnet_get, wait_until_steady
            # 1x rule (gh #3): raises if FlightGear can't be put and kept at 1x sim speed.
            speed_lock = SpeedLock(args.telnet_port or args.telemetry_port - 1)
            aircraft =telnet_get(args.telnet_port or args.telemetry_port - 1, '/sim/aircraft') or ''
            if aircraft.startswith('738'):
                # The 737 overlay keeps its autopilot on until hand_over(); let it settle first.
                state = wait_until_steady(bridge, state)
            if state.speed < 35 or abs(state.roll) > .35:
                raise ValueError('Start FlightGear in stable flight, at least 35 m/s and wings near level.')
            if course_origin is not None and math.hypot(state.east, state.north) > 20000:
                raise ValueError('Aircraft is over 20 km from the scenery course. Use the course launch position.')
            # Pause before scenery/display setup; the autopilot still holds trim.
            state = bridge.freeze(True)
            clock_paused = telnet_get(args.telnet_port or args.telemetry_port - 1, "/sim/freeze/clock")
            if clock_paused is not None and clock_paused.lower() in ("false", "0"):
                raise RuntimeError("Outdated cruise pause protocol: reinstall flybrain-state and flybrain-controls "
                                   "from flight_simulator/protocols and restart FlightGear.")
            controller = FlightController(state.altitude, state.heading, state.speed, state.pitch)
            print('FlightGear connected. Initial altitude/heading/speed are the hold targets.', flush=True)
        else:
            sim = DemoSimulator()
            state = sim.state
            controller = FlightController()
        if bridge and not args.no_cockpit_fly:
            # The fly pilot in the 737's captain seat, animated by this brain (display only).
            from .flightgear import CockpitFly
            try:
                pilot = CockpitFly(args.telnet_port or args.telemetry_port - 1)
            except OSError as exc:
                print(f'Cockpit fly not animated (telnet: {exc}).', flush=True)
        if not args.no_fly_body:
            # Live 3D fly (python -m flight_simulator.fly_body); fire-and-forget UDP, display only.
            from .fly_body import BodyLink
            body = BodyLink(args.body_port)
        if bridge and Path(args.obstacles).resolve() == (ROOT / 'scenarios/obstacles.json').resolve():
            # Keep the default course ahead of any spawn heading. Faster aircraft
            # need more space to turn; custom obstacle files remain local ENU.
            scale = max(1.0, (state.speed / 50.0)**2)
            sn, cs = math.sin(state.heading), math.cos(state.heading)
            obstacles = [replace(o, east=state.east + o.east*cs + o.north*scale*sn,
                                 north=state.north - o.east*sn + o.north*scale*cs,
                                 top=max(o.top, state.altitude+500)) for o in obstacles]
        controller.configure_course(obstacles, origin=(state.east, state.north))
        if bridge and not args.no_scene and not course.get('scenery'):
            # Show the virtual cylinders as live towers inside FlightGear. A fixed
            # scenery course (flightgear/SCENERY.md) already has its own towers.
            try:
                from .fg_scene import ObstacleScene
                scene = ObstacleScene(args.telnet_port or args.telemetry_port - 1)
                n = scene.publish(obstacles, bridge.origin)
                print(f'Placed {n} obstacle towers in FlightGear (telnet {scene.sock.getpeername()[1]}).', flush=True)
            except OSError as exc:
                scene = None
                print(f'Obstacles not shown in FlightGear (telnet: {exc}); start it with --telnet=5500.', flush=True)
        if args.plot or (args.backend == 'flightgear' and not args.no_plot):
            from .companion import Companion
            view = Companion(obstacles, scenery=bool(course.get('scenery')))
        if args.log:
            Path(args.log).parent.mkdir(parents=True, exist_ok=True)
            log_file = open(args.log, 'w', newline='')
            fields = list(asdict(state)) + ['phase', 'brain', 'looming_hz', 'escape_hz',
                      'clearance', 'aileron', 'elevator', 'rudder', 'throttle',
                      'reward', 'dan_hz', 'plastic_edges_changed', 'altitude_target', 'altitude_error',
                      'vertical_speed_target', 'pitch_target', 'bank_target', 'heading_target',
                      'cross_track', 'predicted_clearance', 'decision_source',
                      'decision_latency_s', 'decisions_skipped', 'envelope_breached']
            writer = csv.DictWriter(log_file, fields)
            writer.writeheader()
        if bridge:
            # No-autopilot rule: the fly never flies with the airplane autopilot on.
            from .flightgear import AutopilotGuard, hand_over
            telnet = args.telnet_port or args.telemetry_port - 1
            ap_guard = AutopilotGuard(telnet)  # raises if the autopilot can't be verified (no telnet)
            if not hand_over(telnet):
                raise RuntimeError('FlightGear did not acknowledge the handover; the fly does not take the '
                                   'controls without it (no-autopilot rule).')
            ap_guard.wait_off()
            print('Handover: airplane autopilot confirmed OFF; the controller flies.', flush=True)
            state = bridge.freeze(False)
        if realtime:
            from .flightgear import DecisionWorker
            worker = DecisionWorker(lambda cues: (cues, visual_escape(brain,cues), dict(getattr(brain, 'last_activity', {}))))
        next_brain, next_display, next_print = state.time, 0.0, 0.0
        latency = None
        escape, controls = 0.0, Controls()
        minimum = math.inf
        min_altitude = state.altitude
        collision = False
        start = state.time
        previous_decision = None
        learning_event = {'reward': 0.0, 'dan_hz': 0.0, 'changed_edges': 0}
        while args.seconds == 0 or state.time - start < args.seconds:
            tick = time.monotonic()
            stimulus = sense(state, obstacles, horizon=max(25.0, state.speed / 2))
            visual = visual_scene(state, obstacles, controller.heading, controller.guidance.origin, controller.altitude)
            cues = visual['inputs'] if args.brain=='connectome' and not training else {'looming':stimulus.looming_hz}
            visual['inputs'] = cues
            visual['input_time'] = state.time
            terminal = state.altitude <= 0 or any(o.clearance(state) <= 0 for o in obstacles)
            if worker:
                # Real time: collect a finished decision, start the next one, never wait.
                done = worker.poll(state.time)
                if done:
                    (applied_inputs, escape, activity), record = done
                    applied_time = record["started"]
                    looming = applied_inputs["looming"]
                    latency = record['latency_s']
                    if runlog:
                        runlog.fly({'time': round(state.time, 3), 'brain': args.brain,
                                    'looming_hz': looming, 'escape_hz': escape,
                                    'decision_started': round(record['started'], 3),
                                    'decision_latency_s': round(latency, 3),
                                    'brain_wall_s': round(record['brain_wall_s'], 3), **activity})
                if state.time >= next_brain and not terminal and not worker.busy:
                    worker.submit(state.time, cues, missed=(state.time - next_brain) / .5)
                    next_brain = state.time + .5
            elif state.time >= next_brain and not terminal:
                if bridge and args.brain == 'connectome':  # training runs only (see `realtime`)
                    state = bridge.freeze(True)
                    stimulus = sense(state, obstacles, horizon=max(25.0, state.speed / 2))
                if args.learn and previous_decision is not None:
                    from .learning import flight_reward
                    distance = min((o.clearance(state) for o in obstacles), default=math.inf)
                    reward = flight_reward(previous_decision, state, controller.heading, distance,
                                           collision=distance <= 0 or state.altitude <= 0)
                    learning_event = brain.reinforce(reward)
                escape = brain.escape(stimulus.looming_hz) if training else visual_escape(brain,cues)
                applied_inputs, applied_time = dict(cues), state.time
                previous_decision = replace(state)
                if runlog:
                    runlog.fly({'time': round(state.time, 3), 'brain': args.brain,
                                'looming_hz': stimulus.looming_hz, 'escape_hz': escape,
                                **getattr(brain, 'last_activity', {})})
                next_brain = state.time + .5
                if bridge and args.brain == 'connectome':
                    state = bridge.freeze(False)
            if bridge:
                # Crashes are data (gh #5): log the breach and keep flying.
                for breach in envelope.update(state, controller):
                    print(f'{state.time:6.1f}s ENVELOPE BREACH (logged, run continues): {breach["detail"]}',
                          flush=True)
            controls = controller.update(state, stimulus, escape)
            visual["phase"] = controller.phase
            visual["planned_route"] = controller.guidance.path
            vision.send(visual, applied_inputs, applied_time, brain.name)
            clearance = min((o.clearance(state) for o in obstacles), default=math.inf)
            minimum = min(minimum, clearance)
            min_altitude = min(min_altitude, state.altitude)
            collision = collision or clearance <= 0 or state.altitude <= 0
            if log_file:
                writer.writerow({**asdict(state), **asdict(controls), 'phase': controller.phase,
                                 'brain': args.brain, 'looming_hz': stimulus.looming_hz,
                                 'escape_hz': escape, 'clearance': clearance,
                                 'reward': learning_event['reward'], 'dan_hz': learning_event['dan_hz'],
                                 'plastic_edges_changed': learning_event['changed_edges'],
                                 'altitude_target': controller.altitude,
                                 'altitude_error': controller.altitude-state.altitude,
                                 'vertical_speed_target': controller.desired_climb,
                                 'pitch_target': controller.target_pitch,
                                 'bank_target': controller.target_bank,
                                 'heading_target': controller.target_heading,
                                 'cross_track': controller.guidance.cross_track,
                                 'predicted_clearance': controller.guidance.clearance,
                                 'decision_source': controller.decision_source,
                                 'decision_latency_s': '' if latency is None else round(latency, 3),
                                 'decisions_skipped': worker.skipped if worker else '',
                                 'envelope_breached': ' '.join(sorted(envelope.active))})
            if state.time >= next_print:
                print(f'{state.time:6.1f}s {controller.phase:6} altitude={state.altitude:7.1f}m '
                      f'speed={state.speed:5.1f}m/s escape={escape:5.1f}Hz clearance={clearance:7.1f}m', flush=True)
                next_print = state.time + 10
            if body:
                body.send(state, controller.phase, args.brain, escape,
                          getattr(brain, 'last_activity', None))
            if pilot:
                pilot.update(escape, getattr(brain, 'last_activity', None))
            if state.time >= next_display:
                if scene:
                    scene.threat(stimulus.obstacle, stimulus.looming_hz / 200)
                if view:
                    view.update(state, controller.phase, brain.name, stimulus, escape, controller.target_heading, controller=controller)
                next_display = state.time + .2
            if collision:
                if args.learn:
                    if bridge:
                        bridge.freeze(True)
                    learning_event = brain.reinforce(-1.0)
                print('STOP: collision with a configured obstacle or ground.', flush=True)
                break
            if bridge:
                ap_guard.check()  # no-autopilot rule; raises if it can't be forced off
                speed_lock.check()  # 1x rule; resets and records any change
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
        if ap_guard:
            result['autopilot_violations'] = len(ap_guard.violations)
        if bridge:
            result['envelope'] = envelope.result()
            result['speed_up_resets'] = len(speed_lock.events)
        if worker:
            result['decisions'] = worker.summary()
        if hasattr(brain, 'plasticity'):
            result['learning'] = brain.plasticity.summary()
            result['learning_enabled'] = args.learn
        if runlog:
            runlog.result = result
        print(json.dumps(result, indent=2))
        return 2 if collision else 0
    finally:
        vision.close()
        if log_file:
            log_file.close()
        try:
            if scene:
                scene.close()
        finally:
            try:
                if body:
                    body.close()
                if pilot:
                    pilot.close()
                if ap_guard:
                    ap_guard.close()
                if speed_lock:
                    speed_lock.close()
                if bridge:
                    bridge.close()
                    print('Sent FlightGear pause request on exit. Verify pause in the simulator.', flush=True)
            finally:
                if view:
                    view.close()
                if args.learn:
                    brain.plasticity.save(args.save_learning)
                    print(f'Learning checkpoint saved locally: {args.save_learning}', flush=True)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=['demo', 'flightgear'], default='demo')
    parser.add_argument('--brain', choices=['reflex', 'connectome', 'silent'], required=True,
                        help='Explicit selection: reflex is a non-neural baseline; connectome needs data.')
    parser.add_argument('--data', default='data/brain')
    parser.add_argument('--learn', action='store_true', help='Experimental KC->MBON reward updates (connectome only)')
    parser.add_argument('--load-learning', help='Load a matching checkpoint; frozen unless --learn is given')
    parser.add_argument('--save-learning', default='runs/learning-checkpoint.npz', help='Checkpoint output when --learn is enabled')
    parser.add_argument('--vision-port',type=int,default=5601,help='Synthetic fly-view UDP port; 0 disables display stream')
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
    parser.add_argument('--telnet-port', type=int, help='FlightGear telnet port for in-sim obstacle towers (default: telemetry port - 1)')
    parser.add_argument('--body-port', type=int, default=5600, help='UDP port of the live 3D fly window (python -m flight_simulator.fly_body)')
    parser.add_argument('--no-fly-body', action='store_true', help='Do not stream to the 3D fly window')
    parser.add_argument('--no-cockpit-fly', action='store_true', help='Do not animate the fly pilot in the 737 cockpit')
    parser.add_argument('--no-scene', action='store_true', help='Do not place obstacle towers in FlightGear')
    parser.add_argument('--note', help='Feedback note saved with this run log')
    parser.add_argument('--no-push', action='store_true', help='Log this run locally, do not push')
    parser.add_argument('--no-runlog', action='store_true', help='Skip the run log entirely')
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds < 0:
        parser.error('--seconds must be finite and nonnegative')
    if any(not 1 <= p <= 65535 for p in [args.telemetry_port, args.control_port]):
        parser.error('Ports must be between 1 and 65535')
    if (args.learn or args.load_learning) and args.brain != 'connectome':
        parser.error('Learning requires --brain connectome')
    runlog = None
    if not args.no_runlog:
        from .runlog import RunLog
        runlog = RunLog(args, sys.argv[1:], auto_push=not args.no_push)
        if not args.log:
            args.log = str(runlog.dir / 'airplane.csv')
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
