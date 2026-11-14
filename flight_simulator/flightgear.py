"""FlightGear generic UDP bridge. Protocol XML is shipped alongside this module."""
import math
import socket
import select
import time
from .core import State, Controls, wrap
from .scenery import to_local


class FlightGear:
    def __init__(self, telemetry_port=5501, control_port=5502, timeout=2.0, engines=1):
        if engines not in (1, 2):
            raise ValueError('Supported engine counts: 1 or 2')
        self.engines = engines
        self.rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.rx.bind(('127.0.0.1', telemetry_port))
        except BaseException:
            self.rx.close()
            raise
        self.tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.address = ('127.0.0.1', control_port)
        self.timeout = timeout
        self.origin = None
        self.previous = None
        self.previous_clock = None
        self.active_time = 0.0
        self.frozen = False
        self.last_controls = Controls()

    def parse(self, packet):
        """Fields match protocols/flybrain-state.xml, all numbers validated."""
        try:
            values = [float(v) for v in packet.decode('ascii').strip().split(',')]
        except (ValueError, UnicodeError) as exc:
            raise ValueError('Malformed FlightGear telemetry') from exc
        if len(values) != 10 or not all(math.isfinite(v) for v in values):
            raise ValueError('Expected ten finite FlightGear telemetry fields')
        clock, lat, lon, alt_ft, heading, roll, pitch, speed_kt, climb_fps, frozen = values
        if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 0 < speed_kt < 1000
                and -180 <= roll <= 180 and -90 <= pitch <= 90 and frozen in (0, 1)):
            raise ValueError('FlightGear state out of range; aircraft must already be airborne')
        if self.previous_clock is not None and clock < self.previous_clock:
            raise ValueError('FlightGear clock reset or out-of-order telemetry; restart controller')
        if self.origin is None:
            self.origin = lat, lon
        east, north = to_local(lat, lon, self.origin)
        delta = 0.0 if self.previous_clock is None else clock - self.previous_clock
        # elapsed-sec is wall-like simulator elapsed time. Exclude pause boundaries.
        active = delta > 0 and not frozen and not self.frozen
        if active:
            self.active_time += delta
        state = State(self.active_time, east, north, alt_ft * 0.3048,
                      math.radians(heading), math.radians(roll), math.radians(pitch),
                      speed_kt * 0.514444, climb_fps * 0.3048)
        if self.previous is not None and active and delta < 0.5:
            state.roll_rate = wrap(state.roll - self.previous.roll) / delta
            state.pitch_rate = (state.pitch - self.previous.pitch) / delta
        self.previous, self.previous_clock, self.frozen = state, clock, bool(frozen)
        return state

    def read(self):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            self.rx.settimeout(max(0.001, deadline - time.monotonic()))
            try:
                packet, peer = self.rx.recvfrom(8192)
            except socket.timeout as exc:
                raise TimeoutError('No FlightGear telemetry; check UDP flags and protocol XML.') from exc
            if peer[0] == '127.0.0.1':
                # Rendering or a slow neural trial can queue telemetry. Control
                # the latest state rather than replaying an obsolete turn.
                for _ in range(128):
                    if not select.select([self.rx], [], [], 0)[0]:
                        break
                    newer, sender = self.rx.recvfrom(8192)
                    if sender[0] == '127.0.0.1':
                        packet = newer
                return self.parse(packet)
        raise TimeoutError('No local FlightGear telemetry')

    def send(self, controls, frozen=False):
        c = controls.bounded()
        self.last_controls = c
        throttles = ','.join([f'{c.throttle:.7f}'] * self.engines)
        data = f'{c.aileron:.7f},{c.elevator:.7f},{c.rudder:.7f},{throttles},{int(frozen)}\n'
        self.tx.sendto(data.encode('ascii'), self.address)

    def freeze(self, frozen):
        """Wait for telemetry acknowledgement before running a slow brain trial."""
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            self.send(self.last_controls, frozen)
            state = self.read()
            if self.frozen == frozen:
                return state
        raise TimeoutError('FlightGear did not acknowledge pause/resume')

    def close(self):
        # Best effort only: a broken UDP link cannot guarantee pause delivery.
        try:
            self.send(self.last_controls, True)
        finally:
            self.rx.close()
            self.tx.close()


class RunwayFlightGear(FlightGear):
    """Takeoff/landing bridge: protocols/flybrain-runway-{state,controls}.xml.

    Converts FlightGear's lat/lon into the runway frame used by RunwayState:
    x metres along the runway from `origin` (threshold or brake-release point),
    y metres right of centerline, psi heading error. If no runway is given, the
    first packet's position and heading define it (aircraft lined up for takeoff).
    """
    def __init__(self, telemetry_port=5501, control_port=5502, timeout=2.0,
                 runway=None):
        super().__init__(telemetry_port, control_port, timeout, engines=2)
        self.runway = runway  # (lat, lon, true heading deg) or None
        self.gear_down = True
        from .runway import AirlinerControls
        self.last_controls = AirlinerControls()

    def parse(self, packet):
        from .runway import RunwayState, KT, FT
        try:
            values = [float(v) for v in packet.decode('ascii').strip().split(',')]
        except (ValueError, UnicodeError) as exc:
            raise ValueError('Malformed FlightGear telemetry') from exc
        if len(values) != 11 or not all(math.isfinite(v) for v in values):
            raise ValueError('Expected eleven finite runway telemetry fields')
        clock, lat, lon, agl_ft, heading, roll, pitch, speed_kt, climb_fps, wow, frozen = values
        if not (-90 <= lat <= 90 and -180 <= lon <= 180 and -5 < speed_kt < 1000
                and -180 <= roll <= 180 and -90 <= pitch <= 90 and frozen in (0, 1) and wow in (0, 1)):
            raise ValueError('FlightGear runway state out of range')
        if self.previous_clock is not None and clock < self.previous_clock:
            raise ValueError('FlightGear clock reset or out-of-order telemetry; restart controller')
        if self.runway is None:
            self.runway = (lat, lon, heading)
        lat0, lon0, rwy = self.runway
        east = 6371000 * wrap(math.radians(lon - lon0)) * math.cos(math.radians(lat0))
        north = 6371000 * math.radians(lat - lat0)
        h = math.radians(rwy)
        x = east * math.sin(h) + north * math.cos(h)
        y = east * math.cos(h) - north * math.sin(h)
        delta = 0.0 if self.previous_clock is None else clock - self.previous_clock
        active = delta > 0 and not frozen and not self.frozen
        if active:
            self.active_time += delta
        speed = max(0.0, speed_kt) * KT
        climb = climb_fps * 0.3048
        gamma = math.asin(max(-1.0, min(1.0, climb / speed))) if speed > 5 else 0.0
        state = RunwayState(time=self.active_time, x=x, y=y, agl=max(0.0, agl_ft * FT),
                            psi=wrap(math.radians(heading - rwy)), roll=math.radians(roll),
                            pitch=math.radians(pitch), gamma=gamma, speed=speed,
                            on_ground=bool(wow))
        if self.previous is not None and active and delta < 0.5:
            state.roll_rate = wrap(state.roll - self.previous.roll) / delta
            state.pitch_rate = (state.pitch - self.previous.pitch) / delta
            state.yaw_rate = wrap(state.psi - self.previous.psi) / delta
        self.previous, self.previous_clock, self.frozen = state, clock, bool(frozen)
        return state

    def send(self, controls, frozen=False):
        c = controls.bounded()
        self.last_controls = c
        brake = getattr(c, 'brake', 0.0)
        data = (f'{c.aileron:.7f},{c.elevator:.7f},{c.rudder:.7f},{c.throttle:.7f},{c.throttle:.7f},'
                f'{brake:.7f},{brake:.7f},{int(self.gear_down)},{int(frozen)}\n')
        self.tx.sendto(data.encode('ascii'), self.address)
