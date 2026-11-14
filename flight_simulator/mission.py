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

Live runs calibrate all three configurations before flight and share one background
brain worker. The haltere-reflex integrator and controls carry over at handover.

The Circuit fly is a thin transit configuration, not the cruise/obstacle work:
the default circuit has no obstacle avoidance. With --route lax-burbank,
airport_route.py adds destination geometry and predictive known-obstacle guidance.
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
                     takeoff_start, RUNWAY_LENGTH)

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
        self.vision_sink = None
        self.vision_obstacles = []
        self.config = CFG_TAKEOFF
        self.gear_down = True
        self.fly = None
        self.worker = None
        self.precalibrated = {}
        self.start_fly(TakeoffFly(brain, period), None)

    @property
    def phase(self):
        return f'{self.fly.name}: {self.fly.status.phase}'

    def start_fly(self, fly, s):
        old = self.fly
        if old is not None:
            fly.elevator_i = old.elevator_i     # haltere reflex: no elevator jump
            fly.throttle = old.throttle
            fly.q_cmd, fly.aileron, fly.rudder = old.q_cmd, old.aileron, old.rudder
            fly.brake = old.brake
        self.say(f'\n=== {"START" if old is None else "HANDOVER"}: '
                 f'{"" if old is None else old.name + " (" + STATES[old.name] + ") -> "}'
                 f'{fly.name} ({STATES[fly.name]}) '
                 + ('' if s is None else f'at {s.agl / FT:.0f} ft, {s.speed / KT:.0f} kt') + ' ===')
        if self.worker is not None:
            fly.zero.update(self.precalibrated[fly.name])
            fly.worker = self.worker
            zero = fly.zero
        else:
            zero = fly.calibrate() if self.calibrate else {}
        if zero:
            self.say('    adapted: ' + ', '.join(f'{k} zero {v:.1f} Hz' for k, v in zero.items()))
        self.handovers.append({'time': 0.0 if s is None else round(s.time, 1), 'to': fly.name,
                               'state': STATES[fly.name], 'agl_ft': 0 if s is None else round(s.agl / FT),
                               'ias_kt': 0 if s is None else round(s.speed / KT), **{f'zero_{k}': v for k, v in zero.items()}})
        self.fly = fly

    def prepare_realtime(self):
        """Calibrate every phase before handover, then share a single background worker.

        The brain is never used concurrently and no in-flight phase switch calibrates it.
        """
        self.precalibrated[self.fly.name] = dict(self.fly.zero)
        for candidate in (CircuitFly(self.brain,self.period,self.legs),LandingFly(self.brain,self.period)):
            if self.calibrate: candidate.calibrate()
            self.precalibrated[candidate.name] = dict(candidate.zero)
        self.worker = self.fly.run_in_background()

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
        self.fly.vision_sink = self.vision_sink
        self.fly.vision_obstacles = self.vision_obstacles
        return self.fly.step(s, dt)

    @property
    def done(self):
        f = self.fly
        return f.status.done and (isinstance(f, LandingFly) or (isinstance(f, TakeoffFly) and f.rejected))


def mission_row(mission, s, c):
    world_state = s
    if hasattr(mission, 'control_state'): s = mission.control_state(s)
    r = row(mission.fly, s, c)
    if hasattr(mission, 'route'):
        r.update(mission.report(), world_x=world_state.x, world_y=world_state.y,
                 altitude_msl_ft=world_state.agl/FT+mission.route.departure.elevation_ft,
                 coordinate_frame=mission.runway.airport)
    r['fly'] = mission.fly.name
    r['brain_state'] = STATES[mission.fly.name]
    r['leg'] = mission.fly.leg.name if isinstance(mission.fly, CircuitFly) else ''
    return r


def run_local(mission, seconds=1500.0, dt=0.05, log=None, progress=True):
    if hasattr(mission, 'route'):
        from .airport_route import run_local as run_route
        return run_route(mission, seconds, dt, log, progress)
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
    r['success'] = bool(mission.done and landed and not (ev.tail_strike or ev.stall or ev.left_runway)
                        and 0 <= ev.touchdown_x <= 900 and ev.touchdown_sink_fpm < 500)
    r['safe_reject'] = bool(isinstance(mission.fly,TakeoffFly) and mission.fly.rejected and s.on_ground and s.speed<1 and not ev.left_runway)
    r['outcome'] = ('runway_departure' if ev.left_runway else 'tail_strike' if ev.tail_strike else
                    'stall' if ev.stall else 'takeoff_rejected' if r['safe_reject'] else
                    'go_around' if r['go_around'] else 'landing_completed' if r['success'] else 'incomplete')
    return r


def run_flightgear(mission, args, log):
    """Full mission at 1x. Calibration is on the ground; all flight trials are asynchronous."""
    from .flightgear import RunwayFlightGear, engine_asymmetry, AutopilotGuard, SpeedLock, hand_over
    route = getattr(mission, 'route', None)
    options = {} if route is None else dict(runway=(route.departure.lat,route.departure.lon,route.departure.heading),
                                           elevation_ft=route.departure.elevation_ft)
    bridge = RunwayFlightGear(args.telemetry_port, args.control_port, **options)
    body = ap_guard = speed_lock = obstacle_scene = None
    reason = 'time_limit'
    try:
        print('Waiting for FlightGear runway telemetry on localhost...', flush=True)
        s = bridge.read()
        if not s.on_ground:
            raise ValueError('Start FlightGear on the runway: launch_fg --phase takeoff')
        if route:
            route.check_start(s)
            from .takeoff_live import parking_brake
            if not parking_brake(args.telemetry_port-1,True):
                raise RuntimeError('Could not hold parking brake during route setup')
        bridge.send(bridge.last_controls)  # idle + brakes during setup only
        speed_lock = SpeedLock(args.telemetry_port-1)
        ap_guard = AutopilotGuard(args.telemetry_port-1)
        if route:
            from .fg_scene import ObstacleScene
            obstacle_scene = ObstacleScene(args.telemetry_port-1)
            obstacle_scene.publish(route.world_obstacles(mission.vision_obstacles),
                                   (route.departure.lat,route.departure.lon))
        mission.prepare_realtime()  # all phase calibration happens before releasing control
        if route:
            from .takeoff_live import parking_brake
            if not parking_brake(args.telemetry_port-1,False):
                raise RuntimeError('Could not release parking brake before route handover')
        if not hand_over(args.telemetry_port-1):
            raise RuntimeError('FlightGear did not acknowledge mission handover')
        ap_guard.wait_off()
        if not args.no_fly_body:
            from .fly_body import BodyLink
            body = BodyLink(args.body_port)
        s = bridge.read()  # discard setup-era telemetry
        start = previous = s.time
        touchdown = asym_since = None
        max_y = 0.0
        while s.time-start < args.seconds:
            if mission.done:
                reason = 'takeoff_rejected' if isinstance(mission.fly,TakeoffFly) else ('go_around' if mission.fly.go_around else 'landing_completed')
                break
            controls = mission.step(s, max(s.time-previous,1e-3))
            bridge.gear_down = mission.gear_down
            bridge.flaps = FG_FLAPS[mission.config.name]
            entry = mission_row(mission,s,controls)
            if mission.worker.records:
                record = mission.worker.records[-1]
                entry.update(decision_started=record['started'],decision_latency_s=record['latency_s'],
                             decision_accepted=record.get('accepted',True))
            entry['decisions_skipped'] = mission.worker.skipped
            log.append(entry)
            ap_guard.check()
            speed_lock.check()
            if body:
                d = mission.fly.decisions[-1] if mission.fly.decisions else None
                rates = {f'{k}_hz':v for k,v in (d.rates if d else {}).items()}
                body.send(s,mission.phase,args.brain,rates.get('DNp01_hz',0),rates)
            bridge.send(controls)
            previous,was_ground = s.time,s.on_ground
            try:
                s = bridge.read()
            except KeyboardInterrupt:
                reason='interrupted'
                break
            local = mission.control_state(s) if route else s
            runway_length = mission.runway.length if route else RUNWAY_LENGTH
            runway_half = mission.runway.width/2 if route else 30
            if route and mission.collision(s):
                reason='obstacle_collision';break
            if s.on_ground: max_y=max(max_y,abs(local.y))
            warning = engine_asymmetry(s,controls.throttle)
            asym_since=(s.time if asym_since is None else asym_since) if warning else None
            if warning and s.time-asym_since>=2:
                print(warning,flush=True)
                bridge.send(replace(controls,throttle=0.0,brake=1.0))
                reason='engine_asymmetry'
                break
            if s.on_ground and math.degrees(s.pitch)>11:
                reason='tail_strike';break
            if s.on_ground and (abs(local.y)>runway_half or local.x>runway_length or (route and local.x < (0 if isinstance(mission.fly,LandingFly) else -150))):
                reason='runway_departure';break
            if not was_ground and s.on_ground:
                if not isinstance(mission.fly,LandingFly):
                    reason='ground_contact';break
                if touchdown is None:touchdown=(round(local.x),round(-entry['climb_fpm']))
        success = bool(reason=='landing_completed' and touchdown and 0<=touchdown[0]<=900 and touchdown[1]<500)
        if route:
            local=mission.control_state(s)
            success = success and s.on_ground and s.speed<1 and 0<=local.x<route.arrival.length and abs(local.y)<route.arrival.width/2
        if reason=='landing_completed' and not success: reason='landing_outside_criteria'
        return {**(mission.report() if route else {}), 'brain':getattr(mission.brain,'name','?'),'ended_in':mission.phase,
                'handovers':mission.handovers,'touchdown_x_m':touchdown and touchdown[0],
                'touchdown_sink_fpm':touchdown and touchdown[1], 'time_s':round(s.time-start,2),
                'max_centerline_m':round(max_y,1),'outcome':reason,'termination_reason':reason,
                'safe_reject':reason=='takeoff_rejected' and s.speed<1 and abs(s.y)<=30,
                'success':success,'decision_timing':mission.worker.summary(),
                'speed_up_resets':len(speed_lock.events),
                **({'stop_x_m':local.x if s.on_ground else None} if route else {})}
    finally:
        if obstacle_scene: obstacle_scene.close()
        if body: body.close()
        if ap_guard: ap_guard.close()
        if speed_lock: speed_lock.close()
        paused = bridge.close()  # only the end of the run pauses the aircraft
        if mission.worker: mission.worker.close(wait=0)
        print('FlightGear paused (acknowledged), ailerons and rudder centred.' if paused else
              'WARNING: FlightGear did not acknowledge the end-of-run pause.',flush=True)


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
    p.add_argument('--route', choices=['lax-burbank'], help='KLAX 25R to KBUR 08 with known obstacles')
    p.add_argument('--backend', choices=['demo', 'flightgear'], default='demo')
    p.add_argument('--data', default='data/brain')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--noise-seed', type=int, help='standin only: add the connectome\'s spike-count noise')
    p.add_argument('--period', type=float, default=0.25, help='Seconds of sim time between brain trials')
    p.add_argument('--no-calibrate', action='store_true')
    p.add_argument('--seconds', type=float, default=1500)
    p.add_argument('--vision-port',type=int,default=5601,help='Synthetic visual cue stream; 0 disables')
    p.add_argument('--vision-obstacles',help='Obstacles JSON in runway coordinates and heights above runway')
    p.add_argument('--log', help='CSV of every step: state, controls, active fly, inputs, DN rates')
    p.add_argument('--plot', help='PNG of the whole flight with the handovers marked (needs matplotlib)')
    p.add_argument('--telemetry-port', type=int, default=5501)
    p.add_argument('--control-port', type=int, default=5502)
    p.add_argument('--body-port', type=int, default=5600)
    p.add_argument('--no-fly-body', action='store_true')
    args = p.parse_args(argv)
    if not math.isfinite(args.seconds) or args.seconds<=0 or not math.isfinite(args.period) or args.period<=0:
        p.error('seconds and period must be finite and positive')
    vision = runlog = log = None
    code = 1
    try:
        from .runlog import RunLog
        runlog = RunLog(args, ['mission', *(argv if argv is not None else sys.argv[1:])])
        if args.brain == 'standin':
            brain = StandInBrain(noise_seed=args.noise_seed)
        else:
            from .brain import ConnectomeBrain
            brain = ConnectomeBrain(args.data, seed=args.seed)
        print(brain.name, flush=True)
        if args.route:
            from .airport_route import RouteMission
            mission = RouteMission(brain, args.period, calibrate=not args.no_calibrate)
        else:
            mission = Mission(brain, args.period, calibrate=not args.no_calibrate)
        from .vision import VisionPublisher
        vision = VisionPublisher(args.vision_port)
        mission.vision_sink = vision
        if args.vision_obstacles:
            from .__main__ import load_obstacles
            mission.vision_obstacles = load_obstacles(args.vision_obstacles)
        from .takeoff_live import LiveLog
        class MissionLog(LiveLog):
            def append(self, entry):
                self.fly = mission.fly
                super().append(entry)
        log = MissionLog(runlog, mission.fly)
        start = time.monotonic()
        try:
            if args.backend == 'demo':
                result = run_local(mission, args.seconds, log=log)
            else:
                result = run_flightgear(mission, args, log)
        finally:
            save_log(log, args, brain)  # preserve logs on interruption or errors too
        result['wall_s'] = round(time.monotonic() - start, 1)
        runlog.result = result

        print(json.dumps(result, indent=2))
        code = 0 if result['success'] else 2
        return code
    except KeyboardInterrupt:
        print('\nStopped.')
        code=130
        return code
    except (OSError, ValueError, RuntimeError, ImportError, KeyError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    finally:
        if vision: vision.close()
        if log is not None: log.close()
        if runlog: runlog.finish(code)


if __name__ == '__main__':
    sys.exit(main())
