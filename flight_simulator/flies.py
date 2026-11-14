"""The Takeoff fly and the Landing fly: two configured brains on one connectome.

Each fly has three thin layers (docs/TAKEOFF_LANDING_PLAN.md):

1. Stimulator rig (``encode``): aircraft state -> sensory input rates, 0-200 Hz.
2. Brain: ``ConnectomeBrain.run`` (or the labelled stand-in), one fresh 200 ms
   trial from rest per decision.
3. Nerve-cord layer (``decode`` + ``haltere``): descending-neuron rates ->
   commands, with the behavioural-state gate a real fly's nerve cord applies
   (standing: looming means jump; flying: looming means land), and a fixed-gain
   pitch-rate reflex standing in for the haltere/wing-motor reflex.

Every channel below was chosen from the step-0 probe of the real connectome
(runs/probe.json, runs/probe_combos.json; summarised in docs/TAKEOFF_LANDING.md).
Nothing is trained or fitted.
"""
from dataclasses import dataclass, field
import math

from .core import clip
from .runway import AirlinerControls, KT, FT, FLAPS5_GEAR_UP

# --- Calibration measured on the connectome (FlyWire 783, Shiu LIF), 2026-11-14 ---
# Zero points: readouts with the tonic 100 Hz VS/HS drive that encodes "no error".
STEER_ZERO = -37.0     # (DNp15_L + DNa02_L) - (DNp15_R + DNa02_R) at HS 100/100
PITCH_ZERO = 107.0     # DNp20_L + DNp20_R at VS 100/100
ROLL_ZERO = -43.0      # DNp20_L - DNp20_R at VS 100/100
MN9_APPROACH = 65.0    # MN9 with sugar 100 Hz plus tonic VS/HS drive (mean over the connectome approach)
ESCAPE_FULL = 600.0    # DNp02 + DNp04 + DNp11 at looming ~150 Hz
TONIC = 100.0          # Hz, VS/HS resting drive
SMOOTHING = 0.5        # weight of the newest trial in the DN-rate low-pass (nerve-cord integration)
# Neurons per readout group (FlyWire 783). Single-neuron readouts are quantised to 5 Hz per 200 ms trial.
GROUP_SIZE = {'DNp01': 2, 'DNp02': 2, 'DNp04': 2, 'DNp11': 2, 'DNp07': 2, 'DNp10': 2, 'MDN': 4,
              'MN9': 1, 'DNp15_L': 1, 'DNp15_R': 1, 'DNa02_L': 1, 'DNa02_R': 1, 'DNp20_L': 1, 'DNp20_R': 1}

# --- 737-800 numbers (weight-dependent; check against the FlightGear model) ---
V1, VR, V2 = 135 * KT, 145 * KT, 152 * KT
VREF = 140 * KT
VAPP = VREF + 5 * KT   # approach speed target
LOOM_TAU = 8.0         # s, time-to-contact at which the runway starts to loom
FLARE_GAIN = 2.5       # deg/s of nose-up per 20 Hz of DNp07
GS_GAIN = 3.0          # deg of pitch target per deg below the glideslope
JUMP_RATE = 2.5        # deg/s nose-up at full escape activity (FG 737 lifted off at 10.9 deg with 3.0)
AIR_RUDDER = 0.1       # max rudder in the air (0.3 held after handover rolled the FG 737 over)
HOLD_PITCH = 10.0      # deg: after the phase ends in the air, keep flying (no Cruise fly yet)
HOLD_THROTTLE = 0.7    # scripted climb power while holding


@dataclass
class Decision:
    """What one brain trial produced, for logs and plots."""
    time: float
    inputs: dict
    rates: dict
    note: str = ''


@dataclass
class Status:
    phase: str
    done: bool = False
    result: dict = field(default_factory=dict)


def tonic_pair(signal, gain):
    """Push-pull around the tonic rate: +signal raises left, lowers right."""
    return clip(TONIC + gain * signal, 0, 200), clip(TONIC - gain * signal, 0, 200)


def steer_index(r):
    """Positive = the fly steers LEFT (left HS -> left DNp15/DNa02, measured)."""
    return (r['DNp15_L'] + r['DNa02_L']) - (r['DNp15_R'] + r['DNa02_R']) - STEER_ZERO


class PhaseFly:
    readouts = ['DNp01', 'DNp02', 'DNp04', 'DNp11', 'DNp07', 'DNp10', 'MDN', 'MN9',
                'DNp15_L', 'DNp15_R', 'DNa02_L', 'DNa02_R', 'DNp20_L', 'DNp20_R']
    name = 'fly'

    def __init__(self, brain, period=0.5):
        self.brain, self.period = brain, period
        self.next_decision = -1e9
        self.decisions = []
        self.smoothed = None
        self.hold = False  # keep flying after the phase is done (live sim, still airborne)
        self.q_cmd = 0.0        # pitch-rate command, rad/s (from the brain)
        self.elevator_i = 0.0   # haltere reflex integrator
        self.throttle, self.brake, self.aileron, self.rudder = 0.0, 0.0, 0.0, 0.0
        self.status = Status('READY')

    # Shared encoders -------------------------------------------------------
    def vs_inputs(self, s, pitch_target_deg):
        """VS cells: pitch error drives both sides; roll error drives them apart."""
        pitch_error = pitch_target_deg - math.degrees(s.pitch)
        left, right = tonic_pair(-math.degrees(s.roll), 4.0)
        bump = 6.0 * pitch_error
        return {'vs_left': clip(left + bump, 0, 200), 'vs_right': clip(right + bump, 0, 200)}

    def hs_inputs(self, s, drift_deg, gain):
        """HS cells: drifting/yawing right stimulates the LEFT HS cells (optomotor)."""
        left, right = tonic_pair(drift_deg, gain)
        return {'hs_left': left, 'hs_right': right}

    # Shared decoders -------------------------------------------------------
    def pitch_rate_from_vs(self, r):
        """DNp20 pair sum above its zero point -> nose-up rate, deg/s."""
        return 0.049 * (r['DNp20_L'] + r['DNp20_R'] - PITCH_ZERO)

    def roll_from_vs(self, r):
        return (r['DNp20_L'] - r['DNp20_R']) - ROLL_ZERO

    def haltere(self, s, dt):
        """Fixed-gain pitch-rate reflex (the fly's haltere loop): executes q_cmd."""
        error = self.q_cmd - s.pitch_rate
        if s.on_ground and s.pitch <= 1e-3 and self.q_cmd <= 0:
            self.elevator_i = 0.0
        else:
            self.elevator_i = clip(self.elevator_i - 4.0 * error * dt, -1, 1)
        return clip(self.elevator_i - 8.0 * error, -1, 1)

    def step(self, s, dt):
        """Called at the sim rate. Runs a brain trial when one is due."""
        if s.time >= self.next_decision and (not self.status.done or self.hold):
            inputs = self.encode(s)
            rates = self.brain.run(inputs, self.readouts)
            # One 200 ms trial reads 1-2 neurons per group, so rates jitter by +-20 Hz.
            # The nerve cord integrates: low-pass the DN rates across trials.
            if self.smoothed is None:
                self.smoothed = dict(rates)
            else:
                self.smoothed = {k: SMOOTHING * v + (1 - SMOOTHING) * self.smoothed.get(k, v)
                                 for k, v in rates.items()}
            note = self.decode(self.smoothed, s)
            self.decisions.append(Decision(s.time, inputs, rates, note or ''))
            self.next_decision = s.time + self.current_period(s)
        self.check(s)
        return AirlinerControls(self.aileron, self.haltere(s, dt), self.rudder,
                                self.throttle, self.brake)

    def current_period(self, s):
        return self.period

    def decision_due(self, s):
        return s.time >= self.next_decision and (not self.status.done or self.hold)


class TakeoffFly(PhaseFly):
    """A STANDING fly: something looms as the plane nears Vr, the fly jumps,
    and the jump is the rotation."""
    name = 'Takeoff fly'

    def __init__(self, brain, period=0.5, fault_at_kt=None):
        super().__init__(brain, period)
        self.fault_at = None if fault_at_kt is None else fault_at_kt * KT
        self.rejected = False
        self.low_appetite = 0
        self.status = Status('TAKEOFF ROLL')
        self.config_changed = None

    def encode(self, s):
        airborne = not s.on_ground
        # Sugar: "go". Bitter: reject conditions while a reject is still allowed.
        fault = self.fault_at is not None and s.speed >= self.fault_at
        off_centerline = abs(s.y) > 8.0
        bitter = 200.0 if (s.speed < V1 and not airborne and (fault or off_centerline)) else 0.0
        # Looming ramps over the last few knots around Vr, only while on the wheels.
        looming = 0.0 if airborne else clip(200 * (s.speed - (VR - 5 * KT)) / (10 * KT), 0, 200)
        # VS: hold the nose level on the wheels (the jump alone rotates), 15 deg once flying.
        pitch_target = HOLD_PITCH if self.hold else (15.0 if airborne else 0.0)
        drift = math.degrees(s.psi + math.atan2(s.y, 150.0)) + 0.5 * math.degrees(s.yaw_rate)
        inputs = {'sugar': 200.0, 'bitter': bitter, 'looming': looming}
        inputs.update(self.vs_inputs(s, pitch_target))
        inputs.update(self.hs_inputs(s, drift, 8.0))
        return inputs

    def decode(self, r, s):
        note = ''
        escape = r['DNp02'] + r['DNp04'] + r['DNp11']
        steer = steer_index(r)
        committed = s.speed >= V1 or not s.on_ground
        # Throttle: MN9 ("go for it"). Nerve-cord gate: past V1 we are committed,
        # because looming suppresses MN9 (escape overrides feeding, measured).
        if self.rejected:
            self.throttle, self.brake = 0.0, 1.0
        elif committed:
            self.throttle, self.brake = (HOLD_THROTTLE if self.hold else 1.0), 0.0
        else:
            self.throttle, self.brake = clip(r['MN9'] / 90.0, 0, 1), 0.0
            self.low_appetite = self.low_appetite + 1 if (r['MN9'] < 10 and s.speed > 20 * KT) else 0
            if self.low_appetite >= 2:
                self.rejected, note = True, 'REJECT: bitter suppressed MN9 below V1'
                self.throttle, self.brake = 0.0, 1.0
        # Pitch: the jump (standing-state gate: escape DNs act only on the wheels).
        jump = JUMP_RATE * clip(escape / ESCAPE_FULL, 0, 1.2) if s.on_ground and not self.rejected else 0.0
        q_deg = clip(jump + self.pitch_rate_from_vs(r), -3.0, 3.0)
        self.q_cmd = math.radians(q_deg)
        if jump > 0.5 and not note:
            note = f'JUMP: escape DNs {escape:.0f} Hz'
        # Steering: positive index = steer left.
        if s.on_ground:
            self.rudder, self.aileron = clip(-steer / 50.0, -1, 1), 0.0
        else:
            self.rudder = clip(-steer / 150.0, -AIR_RUDDER, AIR_RUDDER)
            self.aileron = clip(0.004 * self.roll_from_vs(r) - 0.002 * steer, -0.5, 0.5)
        return note

    def check(self, s):
        if self.rejected:
            self.status.phase = 'REJECTED'
            if s.speed < 1:
                self.status.done = True
        elif not s.on_ground:
            self.status.phase = 'CLIMB'
            if s.agl >= 1000 * FT:
                self.status.phase, self.status.done = 'HANDOVER (1,000 ft)', True
        elif s.speed >= V1:
            self.status.phase = 'ROTATE' if s.pitch > math.radians(1) else 'V1'


class LandingFly(PhaseFly):
    """A FLYING fly: the runway rushes up, the fly extends its legs, and that
    leg extension is the flare."""
    name = 'Landing fly'

    def __init__(self, brain, period=0.5, final_period=0.25, trim_pitch=None, trim_throttle=0.3,
                 trim_elevator=0.0):
        super().__init__(brain, period)
        self.elevator_i = trim_elevator
        self.final_period = final_period
        self.trim_pitch_deg = trim_pitch
        self.trim_throttle = trim_throttle
        self.throttle = trim_throttle
        self.low_appetite = 0
        self.go_around = False
        self.touched_down = False
        self.flare_pitch_deg = None
        self.status = Status('APPROACH')

    def unstable(self, s):
        # Judged between 1,000 and 100 ft; below 100 ft the pilot flies the flare by eye.
        return (100 * FT < s.agl < 1000 * FT and not s.on_ground and
                (abs(s.glideslope_error()) > 0.7 or abs(s.y) > 40
                 or not -8 * KT <= s.speed - VREF <= 15 * KT))

    def encode(self, s):
        if self.trim_pitch_deg is None:
            self.trim_pitch_deg = math.degrees(s.pitch)
        if self.go_around:
            pitch_target = HOLD_PITCH if self.hold else 15.0
        elif s.on_ground:
            pitch_target = 0.0
        else:
            if s.agl > 100 * FT or self.flare_pitch_deg is None:
                # Follow the glideslope. The angular error is clipped: it grows without
                # bound near the aim point. Below 100 ft the target is frozen.
                gs = clip(s.glideslope_error(), -1.5, 1.5)
                self.flare_pitch_deg = self.trim_pitch_deg - GS_GAIN * gs
            pitch_target = self.flare_pitch_deg
        sugar = clip(TONIC + 4.0 * (VAPP - s.speed) / KT, 80, 200)
        bitter = 200.0 if (self.unstable(s) and not self.go_around) else 0.0
        tau = s.time_to_contact()
        looming = 0.0 if (s.on_ground or self.go_around) else clip(200 * (1 - tau / LOOM_TAU), 0, 200)
        drift = math.degrees(s.psi + math.atan2(s.y, 1500.0)) + 2.0 * math.degrees(s.yaw_rate)
        inputs = {'sugar': sugar, 'bitter': bitter, 'looming': looming}
        inputs.update(self.vs_inputs(s, pitch_target))
        inputs.update(self.hs_inputs(s, drift, 8.0))
        return inputs

    def decode(self, r, s):
        note = ''
        steer = steer_index(r)
        q_deg = self.pitch_rate_from_vs(r)
        if s.on_ground:
            # Scripted rollout checklist: idle, autobrake. The fly keeps the nose and centerline.
            self.throttle, self.brake = 0.0, 0.5
            self.rudder, self.aileron = clip(-steer / 50.0, -1, 1), 0.0
        else:
            self.brake = 0.0
            # Flying-state gate: DNp07 (landing) acts below 100 ft; DNp01/02/04/11
            # (takeoff jump) are decoupled and only logged.
            if s.agl < 100 * FT and not self.go_around:
                flare = FLARE_GAIN * clip(r["DNp07"] / 20.0, 0, 1.6)
                q_deg += flare
                if flare > 0.3:
                    note = f'FLARE: DNp07 {r["DNp07"]:.0f} Hz'
            # Throttle from MN9 around the approach power. Go-around: MN9 collapses
            # (bitter suppresses appetite) while still above 100 ft.
            if self.go_around:
                self.throttle = HOLD_THROTTLE if self.hold else 1.0
            else:
                self.throttle = clip(self.trim_throttle + 0.005 * (r['MN9'] - MN9_APPROACH), 0, 1)
                if s.agl > 100 * FT:
                    self.low_appetite = self.low_appetite + 1 if r['MN9'] < 5 else 0
                    if self.low_appetite >= 2:
                        self.go_around, note = True, 'GO-AROUND: bitter suppressed MN9'
                        self.throttle = 1.0
            self.rudder = clip(-steer / 150.0, -AIR_RUDDER, AIR_RUDDER)
            self.aileron = clip(0.004 * self.roll_from_vs(r) - 0.002 * steer, -0.5, 0.5)
        self.q_cmd = math.radians(clip(q_deg, -3.0, 3.0))
        return note

    def current_period(self, s):
        return self.final_period if s.agl < 200 * FT else self.period

    def check(self, s):
        if self.go_around:
            self.status.phase = 'GO-AROUND'
            if s.agl > 1000 * FT or (s.climb > 0 and s.agl > 400 * FT and s.time > 0 and
                                     self.status.result.get('ga_time', s.time) + 25 < s.time):
                self.status.done = True
            self.status.result.setdefault('ga_time', s.time)
        elif s.on_ground:
            self.touched_down = True
            self.status.phase = 'ROLLOUT'
            if s.speed < 30 * KT:
                self.status.done = True
        elif s.agl < 100 * FT:
            self.status.phase = 'FLARE' if self.q_cmd > math.radians(0.5) else 'FINAL'


class StandInBrain:
    """NOT A FLY BRAIN. A deterministic lookup of the step-0 probe table, for
    offline tests and for comparing against the connectome. Supports the same
    ``silence`` lesions as ConnectomeBrain."""
    name = 'PROBE-TABLE STAND-IN (no connectome)'

    def __init__(self, silence=(), noise_seed=None):
        import random
        self.silenced = set(silence)
        self.rng = None if noise_seed is None else random.Random(noise_seed)
        if self.rng:
            self.name += f' | spike-count noise (seed {noise_seed})'
        if self.silenced:
            self.name += ' | silenced: ' + ', '.join(sorted(self.silenced))

    def poisson(self, lam):
        if lam > 30:
            return max(0, round(self.rng.gauss(lam, lam ** 0.5)))
        k, p, limit = 0, 1.0, math.exp(-lam)
        while True:
            p *= self.rng.random()
            if p <= limit:
                return k
            k += 1

    @staticmethod
    def interp(x, xs, ys):
        if x <= xs[0]:
            return ys[0]
        for (x0, y0), (x1, y1) in zip(zip(xs, ys), zip(xs[1:], ys[1:])):
            if x <= x1:
                return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
        return ys[-1]

    def run(self, inputs, readouts=None):
        from .brain import validate_inputs, READOUTS
        validate_inputs(inputs)
        hz = {name: (0.0 if name in self.silenced else inputs.get(name, 0.0))
              for name in ['sugar', 'bitter', 'looming', 'hs_left', 'hs_right',
                           'vs_left', 'vs_right', 'translational_flow']}
        f = self.interp
        loom, flow = hz['looming'], hz['translational_flow']
        mn9 = (f(hz['sugar'], [0, 50, 100, 200], [0, 10, 65, 105])
               * f(hz['bitter'], [0, 50, 100, 200], [1, .69, .27, 0])
               * f(loom, [0, 100, 200], [1, .08, 0]))
        steer_l = f(hz['hs_left'] - 0.6 * hz['hs_right'], [0, 50, 100, 200], [0, 10, 25, 80])
        steer_r = f(hz['hs_right'] - 0.3 * hz['hs_left'], [0, 50, 100, 200], [0, 30, 60, 135])
        out = {name: 0.0 for name in READOUTS}
        out.update({
            'MN9': mn9,
            'DNp01': f(loom, [0, 50, 100, 200], [0, 165, 238, 292]),
            'DNp02': f(loom, [0, 50, 100, 200], [0, 52, 120, 202]),
            'DNp04': f(loom, [0, 50, 100, 200], [0, 180, 260, 330]),
            'DNp11': f(loom, [0, 50, 100, 200], [0, 48, 88, 152]),
            'DNp07': f(loom, [0, 50, 100, 200], [0, 5, 15, 33]) + f(flow, [0, 100, 200], [0, 15, 40]),
            'DNp10': f(loom, [0, 50, 100, 200], [0, 8, 5, 2]),
            'MDN': f(flow, [0, 50, 100, 200], [0, 26, 42, 67]) + f(loom, [0, 100, 200], [0, 4, 23]),
            'DNp15_L': steer_l, 'DNp15_R': steer_r,
            'DNp20_L': f(hz['vs_left'], [0, 50, 100, 150, 200], [0, 8, 32, 52, 75]),
            'DNp20_R': f(hz['vs_right'], [0, 50, 100, 150, 200], [0, 35, 75, 105, 125]),
        })
        for name in self.silenced & set(out):
            out[name] = 0.0
        if self.rng:  # a 200 ms trial counts spikes from 1-4 neurons: Poisson count noise
            for name, n in GROUP_SIZE.items():
                out[name] = self.poisson(out[name] * 0.2 * n) / (0.2 * n)
        return {name: out[name] for name in (readouts or out)}


def run_phase(fly, sim, seconds, dt=0.05, log=None, on_tick=None):
    """Fly a phase in the local RunwaySim. Returns a result dict."""
    gear_up = False
    max_y = 0.0
    while sim.state.time < seconds and not fly.status.done:
        s = sim.state
        if s.on_ground or s.agl < 100 * FT:
            max_y = max(max_y, abs(s.y))
        controls = fly.step(s, dt)
        # Scripted checklist: gear up at positive climb (takeoff only).
        if isinstance(fly, TakeoffFly) and not gear_up and not s.on_ground and s.climb > 1 and s.agl > 10:
            sim.config, gear_up = FLAPS5_GEAR_UP, True
        if log is not None:
            log.append(row(fly, s, controls))
        if on_tick:
            on_tick(fly, s, controls)
        sim.step(controls, dt)
        ev = sim.events
        if ev.left_runway or ev.tail_strike or ev.stall:
            break
    return summarize(fly, sim, max_y)


def row(fly, s, c):
    last = fly.decisions[-1] if fly.decisions else None
    data = {'time': round(s.time, 3), 'phase': fly.status.phase, 'x': s.x, 'y': s.y,
            'agl_ft': s.agl / FT, 'ias_kt': s.speed / KT, 'pitch_deg': math.degrees(s.pitch),
            'roll_deg': math.degrees(s.roll), 'climb_fpm': s.climb / FT * 60,
            'on_ground': s.on_ground, 'aileron': c.aileron, 'elevator': c.elevator,
            'rudder': c.rudder, 'throttle': c.throttle, 'brake': c.brake}
    if last:
        data.update({f'in_{k}': v for k, v in last.inputs.items()})
        data.update({f'dn_{k}': v for k, v in last.rates.items()})
    return data


def summarize(fly, sim, max_y=None):
    s, ev = sim.state, sim.events
    r = {'fly': fly.name, 'brain': getattr(fly.brain, 'name', '?'), 'phase': fly.status.phase,
         'completed': fly.status.done, 'time_s': round(s.time, 1), 'decisions': len(fly.decisions),
         'max_centerline_m': None if max_y is None else round(max_y, 1), 'tail_strike': ev.tail_strike, 'stall': ev.stall,
         'left_runway': ev.left_runway}
    if isinstance(fly, TakeoffFly):
        r.update({'liftoff_x_m': None if ev.liftoff_x is None else round(ev.liftoff_x),
                  'rejected': fly.rejected, 'agl_ft': round(s.agl / FT),
                  'ias_kt': round(s.speed / KT, 1), 'stop_x_m': round(s.x) if fly.rejected else None})
    else:
        r.update({'touchdown_x_m': None if ev.touchdown_x is None else round(ev.touchdown_x),
                  'touchdown_sink_fpm': None if ev.touchdown_sink_fpm is None else round(ev.touchdown_sink_fpm),
                  'touchdown_pitch_deg': None if ev.touchdown_pitch_deg is None else round(ev.touchdown_pitch_deg, 1),
                  'go_around': fly.go_around,
                  'flare_decisions': sum(d.note.startswith('FLARE') for d in fly.decisions)})
    notes = [f'{d.time:.1f}s {d.note}' for d in fly.decisions if d.note]
    r['events'] = notes[:3] + (['...'] if len(notes) > 6 else []) + notes[-3:] if len(notes) > 6 else notes
    return r
