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
    return best


class FlightController:
    """Conventional altitude/speed/heading hold plus neural-triggered avoidance.

    This is an assisted autopilot, not evidence of direct neural stabilization.
    """
    def __init__(self, altitude=900.0, heading=0.0, speed=50.0):
        self.altitude, self.heading, self.speed = altitude, heading, speed
        self.avoid_until = -1.0
        self.turn = 1
        self.phase = 'CRUISE'
        self.activations = 0

    def update(self, state, stimulus, escape_hz):
        if escape_hz > 0 and stimulus.looming_hz > 0:
            if state.time >= self.avoid_until:
                self.turn = stimulus.turn
                self.activations += 1
            self.avoid_until = state.time + 2.5
        if state.time < self.avoid_until:
            self.phase = 'AVOID'
            target_bank = self.turn * math.radians(27)
        else:
            self.phase = 'CRUISE'
            target_bank = clip(1.4 * wrap(self.heading - state.heading),
                               -math.radians(22), math.radians(22))
        # Reduce bank if slow. These gains are a starting point for FG C172 tuning.
        if state.speed < 35:
            target_bank = clip(target_bank, -0.15, 0.15)
        desired_climb = clip(0.08 * (self.altitude - state.altitude), -4, 4)
        target_pitch = clip(desired_climb / max(state.speed, 25), -0.10, 0.12)
        elevator = -2.5 * (target_pitch - state.pitch) + 0.7 * state.pitch_rate
        throttle = 0.65 + 0.05 * (self.speed - state.speed) + 0.02 * desired_climb
        return Controls(
            2.0 * (target_bank - state.roll) - 0.65 * state.roll_rate,
            elevator, 0.0, throttle,
        ).bounded()


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
