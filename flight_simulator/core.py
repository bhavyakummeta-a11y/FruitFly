"""Shared SI-unit state, obstacle sensing, and explicit conventional stabilization."""
from dataclasses import dataclass
import math


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def wrap(angle):
    return (angle + math.pi) % (2 * math.pi) - math.pi


@dataclass
class State:
    time: float = 0.0
    east: float = 0.0
    north: float = 0.0
    altitude: float = 900.0  # metres MSL
    heading: float = 0.0   # radians clockwise from north
    roll: float = 0.0      # radians, positive right bank
    pitch: float = 0.0     # radians, positive nose up
    speed: float = 50.0    # m/s true airspeed
    climb: float = 0.0     # m/s
    roll_rate: float = 0.0 # rad/s
    pitch_rate: float = 0.0


@dataclass
class Controls:
    aileron: float = 0.0   # positive right bank
    elevator: float = 0.0  # positive nose DOWN, as FlightGear's conventional axis
    rudder: float = 0.0
    throttle: float = 0.65

    def bounded(self):
        values = (self.aileron, self.elevator, self.rudder, self.throttle)
        if not all(math.isfinite(v) for v in values):
            raise ValueError('Non-finite control command')
        return Controls(*(clip(v, -1, 1) for v in values[:3]), clip(values[3], 0, 1))


@dataclass(frozen=True)
class Obstacle:
    name: str
    east: float
    north: float
    radius: float
    bottom: float = 0.0  # m MSL, vertical cylinder
    top: float = 2000.0

    def clearance(self, state):
        horizontal = math.hypot(state.east - self.east, state.north - self.north) - self.radius
        vertical = max(self.bottom - state.altitude, state.altitude - self.top)
        return max(horizontal, vertical)


@dataclass
class Stimulus:
    looming_hz: float = 0.0
    turn: int = 1          # +1 right, -1 left; geometric decoder, NOT a learned output
    obstacle: str = ''
    clearance: float = math.inf
    east: float = 0.0
    north: float = 0.0
    radius: float = 0.0


def sense(state, obstacles, horizon=25.0, margin=180.0):
    """Map known obstacle geometry to a looming proxy; no camera/terrain detection.

    Use straight-line closest approach and an expanded cylinder. Rollout/turn
    planning is deliberately absent. The brain supplies escape activation;
    obstacle bearing supplies turn direction.
    """
    best = Stimulus()
    sn, cs = math.sin(state.heading), math.cos(state.heading)
    for obstacle in obstacles:
        if not obstacle.bottom - 80 <= state.altitude <= obstacle.top + 80:
            continue
        dx, dy = obstacle.east - state.east, obstacle.north - state.north
        ahead = dx * sn + dy * cs
        right = dx * cs - dy * sn
        clearance = obstacle.clearance(state)
        best.clearance = min(best.clearance, clearance)
        if ahead < -obstacle.radius or ahead > state.speed * horizon + obstacle.radius:
            continue
        if abs(right) > obstacle.radius + margin:
            continue
        ttc = max(0.0, ahead - obstacle.radius) / max(state.speed, 1.0)
        hz = clip(200 * (1 - ttc / horizon), 0, 200)
        if hz > best.looming_hz:
            best.looming_hz = hz
            best.turn = -1 if right > 0 else 1
            best.obstacle = obstacle.name
            best.east, best.north, best.radius = obstacle.east, obstacle.north, obstacle.radius
    return best


class FlightController:
    """Conventional altitude/speed/heading hold plus neural-triggered avoidance.

    This is an assisted autopilot, not evidence of direct neural stabilization.
    """
    def __init__(self, altitude=900.0, heading=0.0, speed=50.0, pitch=0.0, safety=True):
        from .guidance import RouteGuidance
        self.altitude, self.heading, self.speed = altitude, heading, speed
        self.trim_pitch = pitch
        self.phase = 'CRUISE'
        self.activations = 0
        self.target_heading = heading
        self.target_bank = 0.0
        self.target_pitch = pitch
        self.desired_climb = 0.0
        self.last_time = None
        self.last_controls = Controls()
        self.safety = safety
        self.obstacles = []
        self.guidance = RouteGuidance(heading)
        self.next_plan = 0.0
        self.avoidance = False
        self.decision_source = 'cruise rules'
        self.pitch_integral = 0.0
        self.speed_integral = 0.0
        self.trim_elevator = 0.0
        self.trim_throttle = .65
        self.preferred_turn = 0
        self.initialized = False

    def configure_course(self, obstacles, origin=(0.0, 0.0)):
        self.obstacles = list(obstacles)
        self.guidance.origin = origin
        self.next_plan = 0.0

    def update(self, state, stimulus, escape_hz):
        dt = .05 if self.last_time is None else clip(state.time-self.last_time,0,.5)
        self.last_time = state.time
        if not self.initialized:
            # Nose attitude alone is not level-flight trim: subtract flight-path
            # angle. The GitHub descent log starts nose-up but sinking at 4.7 m/s.
            gamma=math.atan2(state.climb,max(state.speed,25))
            self.trim_pitch=clip(state.pitch-gamma,-.05,.15)
            self.initialized=True
        if stimulus.obstacle and not any(o.name==stimulus.obstacle for o in self.obstacles):
            self.obstacles.append(Obstacle(stimulus.obstacle,stimulus.east,stimulus.north,stimulus.radius))
        altitude_error=self.altitude-state.altitude
        # Damped vertical-speed feedback acts before a large altitude error builds.
        self.desired_climb=clip(.06*altitude_error,-1.5,2.0)
        vertical_error=self.desired_climb-state.climb
        self.pitch_integral=clip(self.pitch_integral+.001*vertical_error*dt,-.06,.10)
        bank_lift=self.trim_pitch*(1/max(math.cos(state.roll),.75)-1)
        pitch_demand=clip(self.trim_pitch+math.atan2(self.desired_climb,max(state.speed,25))
                               +.006*vertical_error+self.pitch_integral+bank_lift,-.10,.22)
        self.target_pitch+=clip(pitch_demand-self.target_pitch,-math.radians(2)*dt,math.radians(2)*dt)
        pitch_error=self.target_pitch-state.pitch
        # Integral trim removes persistent airframe/control bias. Anti-windup:
        # integrate only when the resulting elevator has room to move.
        elevator=-1.2*pitch_error+1.6*state.pitch_rate+self.trim_elevator
        if abs(elevator)<.65:
            self.trim_elevator=clip(self.trim_elevator-.06*pitch_error*dt,-.35,.35)
        speed_error=self.speed-state.speed
        self.speed_integral=clip(self.speed_integral+.004*speed_error*dt,-.25,.25)
        throttle=self.trim_throttle+.035*speed_error+self.speed_integral+.025*max(self.desired_climb,0)
        throttle+=.25*(1/max(math.cos(state.roll),.75)-1)
        if state.climb < -1 or altitude_error > 5:
            # Do not cut power just because a descent has increased airspeed.
            throttle=max(throttle,self.trim_throttle+.08)
        bank_limit=math.radians(18 if abs(altitude_error)<10 and state.climb>-2 else 10)
        if state.speed < .85*self.speed:
            bank_limit=math.radians(5)
        if state.time >= self.next_plan:
            if self.safety or escape_hz>0:
                if not self.avoidance:
                    self.preferred_turn=stimulus.turn if escape_hz>0 else 0
                target,avoid=self.guidance.choose(state,self.obstacles,self.target_heading,bank_limit,
                                                  self.preferred_turn)
                if avoid and not self.avoidance:
                    self.activations+=1
                self.avoidance=avoid
                self.target_heading=target
                self.decision_source=('neural + obstacle rules' if self.preferred_turn else 'obstacle rules') if avoid else 'route recovery rules'
            else:
                self.target_heading=self.heading
                self.avoidance=False
                self.decision_source='neural-only experiment'
            self.next_plan=state.time+.5
        heading_error=wrap(self.target_heading-state.heading)
        self.phase='AVOID' if self.avoidance else ('RECOVER' if abs(self.guidance.cross_track)>50 or abs(heading_error)>math.radians(3) else 'CRUISE')
        if altitude_error > 10 or state.climb < -2:
            self.phase='ALTITUDE RECOVERY / '+self.phase
        desired_bank=clip(.65*heading_error,-bank_limit,bank_limit)
        self.target_bank+=clip(desired_bank-self.target_bank,-math.radians(6)*dt,math.radians(6)*dt)
        raw=Controls(clip(.85*(self.target_bank-state.roll)-.55*state.roll_rate,-.35,.35),
                     clip(elevator,-.65,.65),0.0,clip(throttle,.2,1))
        old=self.last_controls
        self.last_controls=Controls(old.aileron+clip(raw.aileron-old.aileron,-.35*dt,.35*dt),
                                    old.elevator+clip(raw.elevator-old.elevator,-.35*dt,.35*dt),0.0,
                                    old.throttle+clip(raw.throttle-old.throttle,-.20*dt,.20*dt)).bounded()
        return self.last_controls


class DemoSimulator:
    """Reduced coordinated-turn dynamics, NOT a full aerodynamic aircraft model."""
    def __init__(self, state=None):
        self.state = state or State()

    def step(self, controls, dt):
        c, s = controls.bounded(), self.state
        s.roll_rate += (1.8 * c.aileron - 1.5 * s.roll_rate) * dt
        s.pitch_rate += (-0.8 * c.elevator - 1.6 * s.pitch_rate) * dt
        s.roll = clip(s.roll + s.roll_rate * dt, -1.0, 1.0)
        s.pitch = clip(s.pitch + s.pitch_rate * dt, -0.3, 0.3)
        s.speed = max(1, s.speed + (6 * (c.throttle - 0.65)
                                 - 0.12 * (s.speed - 50) - 9.81 * math.sin(s.pitch)) * dt)
        s.heading = wrap(s.heading + 9.81 * math.tan(s.roll) / s.speed * dt)
        s.climb = s.speed * math.sin(s.pitch)
        s.altitude += s.climb * dt
        horizontal = s.speed * math.cos(s.pitch)
        s.east += horizontal * math.sin(s.heading) * dt
        s.north += horizontal * math.cos(s.heading) * dt
        s.time += dt
        return s
