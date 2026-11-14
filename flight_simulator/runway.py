"""Reduced 737-800-like runway dynamics for local takeoff/landing tests.

Point-mass longitudinal model with a simple pitch axis, ground roll, liftoff,
touchdown, tail-strike detection, and a coplanar lateral axis (heading, bank,
centerline offset). Numbers are rough public 737-800 figures. This is a test
bed for the fly controllers, NOT a validated flight model: FlightGear's JSBSim
737 is the reference.

Runway frame: x metres along the runway (0 = threshold for landing, brake
release point for takeoff), y metres right of centerline, heading error psi in
radians clockwise from runway heading.
"""
from dataclasses import dataclass, replace
import math

from .core import Controls, clip

G, RHO = 9.81, 1.225
KT, FT, FPM = 0.514444, 0.3048, 0.3048 / 60
WING_AREA = 124.6           # m^2
MAX_THRUST = 2 * 107e3      # N, two CFM56-7B at sea level
SPOOL_TAU = 2.5             # s, engine response time constant
TAIL_STRIKE_PITCH = math.radians(11)
RUNWAY_LENGTH, RUNWAY_HALF_WIDTH = 3600.0, 30.0
GLIDESLOPE = math.radians(3.0)
AIM_POINT = 300.0           # m past threshold where the glideslope meets the runway


@dataclass(frozen=True)
class Config:
    """Flap/gear configuration: scripted checklist item, never set by the fly."""
    name: str
    mass: float      # kg
    cl0: float       # lift coefficient at zero angle of attack
    cl_max: float
    cd0: float
    cl_alpha: float = 5.5
    k: float = 0.045


FLAPS5 = Config('flaps 5, gear down', 65000, 0.55, 1.9, 0.050)
FLAPS5_GEAR_UP = Config('flaps 5, gear up', 65000, 0.55, 1.9, 0.035)
FLAPS30 = Config('flaps 30, gear down', 60000, 0.95, 2.4, 0.085)


@dataclass
class AirlinerControls(Controls):
    brake: float = 0.0  # 0..1, both main gear

    def bounded(self):
        c = Controls.bounded(self)
        if not math.isfinite(self.brake):
            raise ValueError('Non-finite brake command')
        return AirlinerControls(c.aileron, c.elevator, c.rudder, c.throttle, clip(self.brake, 0, 1))


@dataclass
class RunwayState:
    time: float = 0.0
    x: float = 0.0
    y: float = 0.0
    agl: float = 0.0          # m above runway
    psi: float = 0.0          # heading error, rad
    roll: float = 0.0
    pitch: float = 0.0
    gamma: float = 0.0        # flight path angle, rad
    speed: float = 0.0        # m/s airspeed (no wind)
    pitch_rate: float = 0.0
    roll_rate: float = 0.0
    yaw_rate: float = 0.0
    spool: float = 0.05       # actual thrust fraction (lags the throttle)
    on_ground: bool = True

    @property
    def climb(self):
        return self.speed * math.sin(self.gamma)

    @property
    def alpha(self):
        return self.pitch - self.gamma

    def glideslope_error(self):
        """Degrees above (+) or below (-) the 3 degree glideslope."""
        distance = max(AIM_POINT - self.x, 1.0)
        return math.degrees(math.atan2(self.agl, distance) - GLIDESLOPE)

    def time_to_contact(self):
        sink = -self.climb
        return self.agl / sink if sink > 0.1 else math.inf


@dataclass
class Events:
    liftoff_x: float = None
    tail_strike: bool = False
    stall: bool = False
    touchdown_x: float = None
    touchdown_sink_fpm: float = None
    touchdown_pitch_deg: float = None
    left_runway: bool = False
    stopped: bool = False


class RunwaySim:
    def __init__(self, state=None, config=FLAPS5, yaw_disturbance=0.0):
        self.state = state or RunwayState()
        self.config = config
        self.yaw_disturbance = yaw_disturbance  # rad/s heading drift on the ground (crosswind-like)
        self.events = Events()

    def lift_drag(self, s):
        c = self.config
        qbar = 0.5 * RHO * s.speed ** 2
        cl = c.cl0 + c.cl_alpha * s.alpha
        if cl > c.cl_max:
            self.events.stall = self.events.stall or not s.on_ground
            cl = c.cl_max - 2.0 * (cl - c.cl_max)  # lift falls off past stall
        cl = max(cl, -0.5)
        return qbar * WING_AREA * cl, qbar * WING_AREA * (c.cd0 + c.k * cl ** 2), qbar

    def step(self, controls, dt):
        c, s, cfg = controls.bounded(), self.state, self.config
        weight = cfg.mass * G
        s.spool += (c.throttle - s.spool) * dt / SPOOL_TAU
        thrust = MAX_THRUST * s.spool * max(0.6, 1 - 0.003 * s.speed)
        lift, drag, qbar = self.lift_drag(s)
        ratio = (s.speed / 77.0) ** 2  # control power relative to rotation speed

        # Pitch axis: elevator (positive = nose down), alpha stability, damping.
        pitch_acc = ratio * (0.6 * -c.elevator - 1.5 * (s.alpha - 0.04)) - 4.0 * s.pitch_rate
        if s.on_ground:
            pitch_acc -= 0.12  # weight on the nose gear
        s.pitch_rate += pitch_acc * dt
        s.pitch += s.pitch_rate * dt

        if s.on_ground:
            if s.pitch <= 0 and s.pitch_rate < 0:
                s.pitch, s.pitch_rate = 0.0, 0.0
            friction = (0.02 + 0.4 * c.brake) * max(0.0, weight - lift)
            s.speed = max(0.0, s.speed + (thrust - drag - friction) / cfg.mass * dt)
            s.gamma, s.roll, s.roll_rate = 0.0, 0.0, 0.0
            s.yaw_rate = 0.12 * c.rudder * min(1.0, s.speed / 30) + self.yaw_disturbance
            if s.speed < 0.5 and c.throttle < 0.1:
                s.yaw_rate = 0.0
            if s.pitch > TAIL_STRIKE_PITCH:
                self.events.tail_strike = True
            if lift > weight and s.speed > 30:
                s.on_ground = False
                self.events.liftoff_x = s.x
        else:
            s.speed = max(1.0, s.speed + ((thrust - drag) / cfg.mass - G * math.sin(s.gamma)) * dt)
            s.gamma += (lift - weight * math.cos(s.gamma)) / (cfg.mass * s.speed) * dt
            s.roll_rate += (1.5 * c.aileron * ratio - 2.0 * s.roll_rate) * dt
            s.roll = clip(s.roll + s.roll_rate * dt, -1.0, 1.0)
            s.yaw_rate = G * math.tan(s.roll) / s.speed + 0.03 * c.rudder

        s.psi += s.yaw_rate * dt
        horizontal = s.speed * math.cos(s.gamma)
        s.x += horizontal * math.cos(s.psi) * dt
        s.y += horizontal * math.sin(s.psi) * dt
        s.agl += s.speed * math.sin(s.gamma) * dt
        if not s.on_ground and s.agl <= 0:
            self.events.touchdown_x = self.events.touchdown_x or s.x
            if self.events.touchdown_sink_fpm is None:
                self.events.touchdown_sink_fpm = -s.climb / FPM
                self.events.touchdown_pitch_deg = math.degrees(s.pitch)
            s.agl, s.gamma, s.on_ground = 0.0, 0.0, True
        if s.on_ground and (abs(s.y) > RUNWAY_HALF_WIDTH or s.x > RUNWAY_LENGTH):
            self.events.left_runway = True
        if s.on_ground and self.events.touchdown_x is not None and s.speed < 1:
            self.events.stopped = True
        s.time += dt
        return s


def takeoff_start(y=0.0, psi=0.0):
    """Lined up at the brake release point, engines at idle."""
    return RunwayState(y=y, psi=psi)


def trimmed_approach(distance=5556.0, speed_kt=145.0, y=0.0, psi=0.0, config=FLAPS30):
    """Stabilised on a 3 degree glideslope `distance` metres before the threshold."""
    x = -distance
    agl = (AIM_POINT - x) * math.tan(GLIDESLOPE)
    speed, gamma = speed_kt * KT, -GLIDESLOPE
    qbar = 0.5 * RHO * speed ** 2
    cl = config.mass * G * math.cos(gamma) / (qbar * WING_AREA)
    alpha = (cl - config.cl0) / config.cl_alpha
    drag = qbar * WING_AREA * (config.cd0 + config.k * cl ** 2)
    thrust = drag + config.mass * G * math.sin(gamma)
    spool = thrust / (MAX_THRUST * max(0.6, 1 - 0.003 * speed))
    return RunwayState(x=x, y=y, agl=agl, psi=psi, pitch=alpha + gamma, gamma=gamma,
                       speed=speed, spool=spool, on_ground=False)


def trim_elevator(state):
    """Elevator that holds the current alpha in the air (zero pitch acceleration)."""
    return -1.5 * (state.alpha - 0.04) / 0.6
