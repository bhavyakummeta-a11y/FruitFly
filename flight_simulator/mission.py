"""Full flight in one go: Takeoff fly -> Circuit fly -> Landing fly.

    python -m flight_simulator.mission --brain standin
    python -m flight_simulator.mission --brain connectome --log runs/mission.csv --plot runs/mission.png
    python -m flight_simulator.mission --brain connectome --backend flightgear --log runs/fg-mission.csv

One connectome, three behavioural configurations, handed over in flight:

| Fly | State | Flies | Looming means |
|---|---|---|---|
| Takeoff fly | standing | runway -> 1,000 ft | jump (DNp02/04/11) = rotation |
| Circuit fly | cruising | right-hand traffic circuit back to the same runway | nothing yet: the obstacle-avoidance slot |
| Landing fly | flying | 3 nm final -> touchdown -> rollout | leg extension (DNp07) = flare |

At every handover the new fly adapts (calibrate()), and the haltere-reflex
integrator and throttle carry over so the controls don't jump.

The Circuit fly is a thin transit configuration, not the cruise/obstacle work:
obstacle avoidance belongs to its own experiment (flight_simulator/__main__.py)
and is NOT used here. `CircuitFly.obstacle_slot` is where it can plug in.
"""
import argparse
import csv
from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
import sys
import time

from .core import clip, wrap
from .flies import (PhaseFly, TakeoffFly, LandingFly, StandInBrain, steer_index, row,
                    TONIC, HS_GAIN, MN9_APPROACH, MAX_AILERON)
from .runway import (RunwaySim, FLAPS5, FLAPS5_GEAR_UP, FLAPS30, KT, FT, AIM_POINT, GLIDESLOPE,
                     takeoff_start)

# One airplane, one mass for the whole flight (flaps/gear are scripted config changes).
MISSION_MASS = 60000.0
CFG_TAKEOFF = replace(FLAPS5, mass=MISSION_MASS)
CFG_CIRCUIT = replace(FLAPS5_GEAR_UP, mass=MISSION_MASS)
CFG_LANDING = replace(FLAPS30, mass=MISSION_MASS)
FG_FLAPS = {CFG_TAKEOFF.name: 0.375, CFG_CIRCUIT.name: 0.375, CFG_LANDING.name: 0.875}  # 737 detents 5, 30

BANK_PER_HZ = 0.22     # deg of bank target per Hz of steering index (25 deg when HS saturates)
MAX_BANK = 25.0
STEER_FULL = 114.0     # Hz of steering index that asks for full bank (HS saturated)
BANK_SHAPE = 1.5       # 1 = linear; >1 = gentler for small track errors
LOOKAHEAD = 1500.0     # m, cross-track look-ahead on circuit legs
HANDOVER_X = -5556.0   # 3 nm before the threshold
YAW_DAMPING = 1.0      # s: turn-rate term in the HS track error
TRIM_RATE = 0.0002     # slow throttle trim per decision per Hz of MN9 error
THROTTLE_GAIN = 0.004  # throttle per Hz of MN9 error


@dataclass(frozen=True)
class Leg:
    """Straight leg in the runway frame (x along the runway from the threshold, y right)."""
    name: str
    x0: float
    y0: float
    x1: float
    y1: float
    alt_ft: float
    speed_kt: float
    glideslope: bool = False   # altitude target = min(alt_ft, 3 deg glideslope)

    @property
    def course(self):
        return math.atan2(self.y1 - self.y0, self.x1 - self.x0)

    @property
    def length(self):
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)

    def track(self, s):
        """(along, cross-track right-positive, remaining) for state s."""
        c, sn = math.cos(self.course), math.sin(self.course)
        dx, dy = s.x - self.x0, s.y - self.y0
        along = dx * c + dy * sn
        return along, -dx * sn + dy * c, self.length - along

    def altitude_target(self, s):
        alt = self.alt_ft * FT
        if self.glideslope:
            alt = min(alt, max(0.0, (AIM_POINT - s.x) * math.tan(GLIDESLOPE)))
        return alt


def circuit(upwind=10000.0, offset=5000.0, final=12000.0, alt_ft=3000.0):
    """Right-hand traffic circuit back to the same runway (at KSFO 28R it stays over the bay)."""
    return [
        Leg('upwind', 0, 0, upwind, 0, alt_ft, 180),
        Leg('crosswind', upwind, 0, upwind, offset, alt_ft, 180),
        Leg('downwind', upwind, offset, -final, offset, 2000, 170),
        Leg('base', -final, offset, -final, 0, 2000, 160),
        Leg('final', -final, 0, AIM_POINT, 0, 2000, 145, glideslope=True),
    ]


class CircuitFly(PhaseFly):
    """A CRUISING fly that flies the circuit legs.

    Same senses as the other flies: HS cells get the track error (heading error
    plus cross-track look-ahead), VS cells the climb-angle error and the bank
    error, sugar the speed error. The steering readout sets the bank target
    (nerve-cord layer), and the VS roll channel flies the bank.
    """
    name = 'Circuit fly'
    neutral_sugar = TONIC
    obstacle_slot = None  # hook for obstacle avoidance: callable(state, rates) -> bank override or None

    def __init__(self, brain, period=0.5, legs=None):
        super().__init__(brain, period)
        self.legs = legs or circuit()
        self.leg_index = 0
        self.bank_target = 0.0
        self.throttle_trim = 0.6
        self.status.phase = 'CIRCUIT: ' + self.leg.name

    @property
    def leg(self):
        return self.legs[self.leg_index]

    def advance_leg(self, s):
        _, _, remaining = self.leg.track(s)
        if self.leg_index < len(self.legs) - 1:
            nxt = self.legs[self.leg_index + 1]
            turn = abs(wrap(nxt.course - self.leg.course))
            radius = s.speed ** 2 / (9.81 * math.tan(math.radians(MAX_BANK)))
            if remaining < radius * math.tan(turn / 2) + 300:
                self.leg_index += 1
                return True
        return False

    def encode(self, s):
        leg = self.leg
        _, xtrack, _ = leg.track(s)
        # HS cells sense rotation: the turn rate is part of what they see (and damps the loop).
        drift = math.degrees(wrap(s.psi - leg.course) + math.atan2(xtrack, LOOKAHEAD)
                             + YAW_DAMPING * s.yaw_rate)
        climb = clip(0.1 * (leg.altitude_target(s) - s.agl), -7.6, 7.6)
        gamma_target = math.asin(clip(climb / max(s.speed, 30.0), -0.3, 0.3))
        pitch_target = math.degrees(s.pitch) + 1.5 * math.degrees(gamma_target - s.gamma)
        inputs = {'sugar': clip(TONIC + 4.0 * (leg.speed_kt * KT - s.speed) / KT, 80, 200),
                  'bitter': 0.0, 'looming': 0.0}  # looming: reserved for obstacle avoidance
        inputs.update(self.vs_inputs(s, pitch_target, self.bank_target))
        inputs.update(self.hs_inputs(s, drift, HS_GAIN))
        return inputs

    def decode(self, r, s):
        steer = steer_index(r, self.zero['steer'])    # positive = steer left
        # Gentle near zero (where the 1-neuron steering noise lives), full bank for big errors.
        x = clip(-steer / STEER_FULL, -1.0, 1.0)
        self.bank_target = MAX_BANK * math.copysign(abs(x) ** BANK_SHAPE, x)
        if self.obstacle_slot:
            override = self.obstacle_slot(s, r)
            if override is not None:
                self.bank_target = clip(override, -MAX_BANK, MAX_BANK)
        self.aileron = clip(self.aileron_from_vs(r), -MAX_AILERON, MAX_AILERON)
        self.rudder = 0.0
        self.q_cmd = math.radians(clip(self.pitch_rate_from_vs(r), -3.0, 3.0))
        # Throttle: MN9 around its zero, plus a slow trim (a fixed reflex, like a trim wheel).
        self.throttle_trim = clip(self.throttle_trim + TRIM_RATE * (r['MN9'] - MN9_APPROACH), 0.05, 1.0)
        self.throttle = clip(self.throttle_trim + THROTTLE_GAIN * (r['MN9'] - MN9_APPROACH), 0.0, 1.0)
        self.brake = 0.0
        return ''

    def check(self, s):
        if self.advance_leg(s):
            print(f'{s.time:6.1f}s   leg -> {self.leg.name}', flush=True)
        self.status.phase = 'CIRCUIT: ' + self.leg.name
        if self.leg.name == 'final' and s.x >= HANDOVER_X:
            _, xtrack, _ = self.leg.track(s)
            established = (abs(xtrack) < 30 and abs(math.degrees(s.psi)) < 5
                           and abs(math.degrees(s.roll)) < 5 and abs(s.glideslope_error()) < 0.6)
            if established or s.x >= HANDOVER_X + 1500:  # hand over anyway; the Landing fly can go around
                self.status.done = True


STATES = {'Takeoff fly': 'standing', 'Circuit fly': 'cruising', 'Landing fly': 'flying'}


class Mission:
    """Runs the three flies in sequence on one brain and records the handovers."""

    def __init__(self, brain, period=0.5, calibrate=True, legs=None, log=print):
        self.brain, self.period, self.calibrate, self.say = brain, period, calibrate, log
        self.legs = legs or circuit()
        self.handovers = []
        self.config = CFG_TAKEOFF
        self.gear_down = True
        self.fly = None
        self.start_fly(TakeoffFly(brain, period), None)

    @property
    def phase(self):
        return f'{self.fly.name}: {self.fly.status.phase}'

    def start_fly(self, fly, s):
        old = self.fly
        if old is not None:
            fly.elevator_i = old.elevator_i     # haltere reflex: no elevator jump
            fly.throttle = old.throttle
        self.say(f'\n=== {"START" if old is None else "HANDOVER"}: '
                 f'{"" if old is None else old.name + " (" + STATES[old.name] + ") -> "}'
                 f'{fly.name} ({STATES[fly.name]}) '
                 + ('' if s is None else f'at {s.agl / FT:.0f} ft, {s.speed / KT:.0f} kt') + ' ===')
        zero = fly.calibrate() if self.calibrate else {}
        if zero:
            self.say('    adapted: ' + ', '.join(f'{k} zero {v:.1f} Hz' for k, v in zero.items()))
        self.handovers.append({'time': 0.0 if s is None else round(s.time, 1), 'to': fly.name,
                               'state': STATES[fly.name], 'agl_ft': 0 if s is None else round(s.agl / FT),
                               'ias_kt': 0 if s is None else round(s.speed / KT), **{f'zero_{k}': v for k, v in zero.items()}})
        self.fly = fly

    def step(self, s, dt):
        """One sim step: handovers, scripted checklist, then the active fly."""
        fly = self.fly
        if isinstance(fly, TakeoffFly) and fly.status.done and not fly.rejected:
            self.start_fly(CircuitFly(self.brain, self.period, self.legs), s)
        elif isinstance(fly, CircuitFly) and fly.status.done:
            landing = LandingFly(self.brain, self.period, trim_throttle=fly.throttle_trim)  # averaged power, not the last sample
            # Reference attitude = the one that flies the 3 deg glideslope at the current angle of attack
            # (not whatever pitch the circuit had at handover: the P-only glideslope loop keeps that error).
            landing.trim_pitch_deg = math.degrees(s.alpha - GLIDESLOPE)
            self.start_fly(landing, s)
        # Scripted checklist (never the fly): gear up after liftoff, flaps 30 + gear down on final.
        if isinstance(self.fly, TakeoffFly) and not s.on_ground and s.climb > 1 and s.agl > 10:
            self.gear_down, self.config = False, CFG_CIRCUIT
        if isinstance(self.fly, CircuitFly) and self.fly.leg.name == 'final' and self.config is not CFG_LANDING:
            self.gear_down, self.config = True, CFG_LANDING
            self.fly.throttle_trim = clip(self.fly.throttle_trim + 0.15, 0, 1)  # power for the extra drag
            self.say(f'{s.time:6.1f}s   checklist: flaps 30, gear down, +power')
        return self.fly.step(s, dt)

    @property
    def done(self):
        f = self.fly
        return f.status.done and (isinstance(f, LandingFly) or (isinstance(f, TakeoffFly) and f.rejected))


def mission_row(mission, s, c):
    r = row(mission.fly, s, c)
    r['fly'] = mission.fly.name
    r['brain_state'] = STATES[mission.fly.name]
    r['leg'] = mission.fly.leg.name if isinstance(mission.fly, CircuitFly) else ''
    return r


def run_local(mission, seconds=1500.0, dt=0.05, log=None, progress=True):
    sim = RunwaySim(takeoff_start(), CFG_TAKEOFF)
    next_print = 0.0
    while sim.state.time < seconds and not mission.done:
        s = sim.state
        controls = mission.step(s, dt)
        sim.config = mission.config
        if log is not None:
            log.append(mission_row(mission, s, controls))
        if progress and s.time >= next_print:
            next_print = s.time + 10
            print(f'{s.time:6.1f}s {mission.phase:34s} x={s.x:7.0f} y={s.y:6.0f}m '
                  f'agl={s.agl / FT:5.0f}ft ias={s.speed / KT:4.0f}kt bank={math.degrees(s.roll):5.1f} '
                  f'thr={controls.throttle:.2f}', flush=True)
        sim.step(controls, dt)
        ev = sim.events
        if ev.tail_strike or ev.stall or ev.left_runway:
            break
        if ev.touchdown_x is not None and not isinstance(mission.fly, LandingFly):
            break  # hit the ground outside the landing phase
    return summarize(mission, sim)


def summarize(mission, sim):
    s, ev = sim.state, sim.events
    landed = isinstance(mission.fly, LandingFly) and ev.touchdown_x is not None
    r = {'brain': getattr(mission.brain, 'name', '?'), 'ended_in': mission.phase,
         'time_s': round(s.time, 1), 'handovers': mission.handovers,
         'liftoff_x_m': None if ev.liftoff_x is None else round(ev.liftoff_x),
         'touchdown_x_m': round(ev.touchdown_x) if landed else None,
         'touchdown_sink_fpm': round(ev.touchdown_sink_fpm) if landed else None,
         'touchdown_y_m': round(s.y, 1) if landed else None,
         'go_around': getattr(mission.fly, 'go_around', False),
         'tail_strike': ev.tail_strike, 'stall': ev.stall, 'left_runway': ev.left_runway}
    r['success'] = bool(landed and not (ev.tail_strike or ev.stall or ev.left_runway)
                        and 0 <= ev.touchdown_x <= 900 and ev.touchdown_sink_fpm < 500)
    return r


def run_flightgear(mission, args, log):
    """Whole flight in FlightGear, started on the runway (launch_fg --phase takeoff)."""
    from .flightgear import RunwayFlightGear, engine_asymmetry
    bridge = RunwayFlightGear(args.telemetry_port, args.control_port)
    body = None
    try:
        if not args.no_fly_body:
            from .fly_body import BodyLink
            body = BodyLink(args.body_port)
        print('Waiting for FlightGear runway telemetry on localhost...', flush=True)
        s = bridge.read()
        bridge.send(bridge.last_controls)  # idle + brakes until the fly's first decision
        if not s.on_ground:
            raise ValueError('Start FlightGear on the runway: python -m flight_simulator.launch_fg --phase takeoff')
        previous, touchdown, asym_since = s.time, None, None
        while not mission.done:
            handing_over = (mission.fly.status.done and not isinstance(mission.fly, LandingFly)) \
                or mission.fly.decision_due(s)
            if handing_over:
                s = bridge.freeze(True)         # also covers the adaptation trials at a handover
            controls = mission.step(s, max(s.time - previous, 1e-3))
            if handing_over:
                s = bridge.freeze(False)
            bridge.gear_down = mission.gear_down
            bridge.flaps = FG_FLAPS[mission.config.name]
            log.append(mission_row(mission, s, controls))
            if body:
                d = mission.fly.decisions[-1] if mission.fly.decisions else None
                rates = {f'{k}_hz': v for k, v in (d.rates if d else {}).items()}
                body.send(s, mission.phase, args.brain, rates.get('DNp01_hz', 0.0), rates)
            bridge.send(controls)
            previous, was_ground = s.time, s.on_ground
            try:
                s = bridge.read()
            except KeyboardInterrupt:
                print('\nCtrl-C: pausing FlightGear.', flush=True)
                break
            warning = engine_asymmetry(s, controls.throttle)
            asym_since = (asym_since or s.time) if warning else None
            if warning and s.time - asym_since >= 2.0:
                print(warning, flush=True)
                bridge.send(replace(controls, throttle=0.0, brake=1.0))
                break
            if not was_ground and s.on_ground and touchdown is None and isinstance(mission.fly, LandingFly):
                touchdown = (round(s.x), round(-log[-1]['climb_fpm']))
        return {'brain': getattr(mission.brain, 'name', '?'), 'ended_in': mission.phase,
                'handovers': mission.handovers, 'touchdown_x_m': touchdown and touchdown[0],
                'touchdown_sink_fpm': touchdown and touchdown[1],
                'success': bool(touchdown and 0 <= touchdown[0] <= 900 and touchdown[1] < 500)}
    finally:
        if body:
            body.close()
        paused = bridge.close()
        print('FlightGear paused (acknowledged), ailerons and rudder centred.' if paused else
              'WARNING: FlightGear did not acknowledge the pause. Pause it by hand (p) NOW.', flush=True)


def save_log(log, args, brain):
    if args.log and log:
        Path(args.log).parent.mkdir(parents=True, exist_ok=True)
        fields = sorted({k for r in log for k in r}, key=lambda k: (k.startswith(('in_', 'dn_')), k))
        with open(args.log, 'w', newline='') as f:
            w = csv.DictWriter(f, fields)
            w.writeheader()
            w.writerows(log)
        print(f'Log written to {args.log} ({len(log)} rows)', flush=True)
    if args.plot and log:
        from .plot_run import plot
        print(f'Plot written to {plot(log, args.plot, "Full flight: " + brain.name)}', flush=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--brain', choices=['connectome', 'standin'], required=True)
    p.add_argument('--backend', choices=['demo', 'flightgear'], default='demo')
    p.add_argument('--data', default='data/brain')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--noise-seed', type=int, help='standin only: add the connectome\'s spike-count noise')
    p.add_argument('--period', type=float, default=0.5, help='Seconds of sim time between brain trials')
    p.add_argument('--no-calibrate', action='store_true')
    p.add_argument('--seconds', type=float, default=1500)
    p.add_argument('--log', help='CSV of every step: state, controls, active fly, inputs, DN rates')
    p.add_argument('--plot', help='PNG of the whole flight with the handovers marked (needs matplotlib)')
    p.add_argument('--telemetry-port', type=int, default=5501)
    p.add_argument('--control-port', type=int, default=5502)
    p.add_argument('--body-port', type=int, default=5600)
    p.add_argument('--no-fly-body', action='store_true')
    args = p.parse_args(argv)
    try:
        if args.brain == 'standin':
            brain = StandInBrain(noise_seed=args.noise_seed)
        else:
            from .brain import ConnectomeBrain
            brain = ConnectomeBrain(args.data, seed=args.seed)
        print(brain.name, flush=True)
        mission = Mission(brain, args.period, calibrate=not args.no_calibrate)
        log, start = [], time.monotonic()
        try:
            if args.backend == 'demo':
                result = run_local(mission, args.seconds, log=log)
            else:
                result = run_flightgear(mission, args, log)
        except KeyboardInterrupt:
            result = {'ended_in': mission.phase + ' (stopped)', 'handovers': mission.handovers,
                      'success': False}
            print('\nStopped: saving the log so far.', flush=True)
        finally:
            save_log(log, args, brain)  # always, even after Ctrl-C or an error mid-flight
        result['wall_s'] = round(time.monotonic() - start, 1)
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
