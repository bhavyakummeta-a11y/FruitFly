"""FlightGear generic UDP bridge. Protocol XML is shipped alongside this module."""
import math
import socket
import select
import time
from .core import State, Controls, wrap
from .scenery import to_local


def telnet_get(telnet_port, path, timeout=3):
    """Read one property over FlightGear's telnet server; None if unreachable."""
    try:
        with socket.create_connection(('127.0.0.1', telnet_port), timeout=timeout) as s:
            s.sendall(b'data\r\nget ' + path.encode() + b'\r\n')
            reply = b''
            deadline = time.monotonic() + timeout
            while b'\n' not in reply and time.monotonic() < deadline:
                reply += s.recv(256)
            s.sendall(b'quit\r\n')
            return reply.decode(errors='replace').strip()
    except OSError:
        return None


def wait_until_steady(bridge, state, hold=3.0, timeout=120.0, climb=1.5, roll_deg=5.0, pitch_deg=8.0):
    """Keep reading telemetry (the 737 autopilot is still flying) until the plane has been
    level, wings-level and not climbing/descending for `hold` seconds. The controller adopts
    the state at that moment as its hold targets, so taking over mid-recovery (e.g. climbing
    back after the in-air-start sag) would immediately leave the test envelope."""
    print('Waiting for the 737 autopilot to settle into steady flight before taking over...', flush=True)
    start, since = time.monotonic(), None
    while time.monotonic() - start < timeout:
        steady = (abs(state.climb) < climb and abs(state.roll) < math.radians(roll_deg)
                  and abs(state.pitch) < math.radians(pitch_deg))
        if steady:
            since = state.time if since is None else since
            if state.time - since >= hold:
                return state
        else:
            since = None
        state = bridge.read()
    raise RuntimeError(f'Aircraft not in steady flight after {timeout:.0f} s (climb {state.climb:+.1f} m/s, '
                       f'bank {math.degrees(state.roll):+.0f} deg, pitch {math.degrees(state.pitch):+.0f} deg).')


class CockpitFly:
    """Drives the fly pilot in the 737's captain seat (FlyCabin fly-pilot.xml) from the
    brain that is flying the plane. Writes /fruitfly/pilot/{active,power,steer,escape}
    over telnet, at most `hz` times a second. Display only: it never touches the controls,
    and any telnet failure just switches it off.

    Rates are scaled by the largest value seen so far this run (floor 20 Hz), so the
    animation shows changes in activity rather than absolute Hz."""

    def __init__(self, telnet_port, hz=10.0):
        self.period, self.next = 1.0 / hz, 0.0
        self.peak = {}
        self.sock = socket.create_connection(('127.0.0.1', telnet_port), timeout=3)
        self.sock.sendall(b'data\r\nset /fruitfly/pilot/active true\r\n')

    def _norm(self, key, value, floor=20.0):
        self.peak[key] = max(self.peak.get(key, floor), value)
        return max(0.0, min(1.0, value / self.peak[key]))

    def update(self, escape_hz, activity):
        if self.sock is None or time.monotonic() < self.next:
            return
        self.next = time.monotonic() + self.period
        a = {k: v for k, v in (activity or {}).items() if isinstance(v, (int, float)) and math.isfinite(v)}
        gf = max(float(escape_hz or 0.0), a.get('DNp01_hz', 0.0))
        right = a.get('DNa01_R_hz', 0.0) + a.get('DNa02_R_hz', 0.0)
        left = a.get('DNa01_L_hz', 0.0) + a.get('DNa02_L_hz', 0.0)
        values = {'power': self._norm('DNg02', a.get('DNg02_hz', 0.0)),
                  'steer': max(-1.0, min(1.0, (right - left) / (right + left + 20.0))),
                  'escape': self._norm('DNp01', gf)}
        lines = ''.join(f'set /fruitfly/pilot/{k} {v:.3f}\r\n' for k, v in values.items())
        try:
            self.sock.sendall(lines.encode())
        except OSError:
            self.close()

    def close(self):
        if self.sock is None:
            return
        try:
            self.sock.sendall(b'set /fruitfly/pilot/active false\r\nquit\r\n')
        except OSError:
            pass
        self.sock.close()
        self.sock = None


def hand_over(telnet_port, attempts=5):
    """Tell the 737 overlay (FlyCabin/Nasal/fruitfly.nas) that a controller is connected,
    so it switches the 737's own autopilot off now rather than leaving it holding the plane.
    Returns True if FlightGear acknowledged. Harmless for aircraft without the overlay."""
    for _ in range(attempts):
        try:
            with socket.create_connection(('127.0.0.1', telnet_port), timeout=3) as s:
                s.sendall(b'data\r\nset /fruitfly/controller-connected true\r\n'
                          b'get /fruitfly/controller-connected\r\n')
                reply = b''
                deadline = time.monotonic() + 3
                while b'\n' not in reply and time.monotonic() < deadline:
                    reply += s.recv(256)
                s.sendall(b'quit\r\n')
                if reply.strip().lower() in (b'true', b'1'):
                    return True
        except OSError:
            time.sleep(1)
    return False


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
        if self.previous is not None and active and delta <= 2.0:
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
        # 'frozen' goes out twice: /sim/freeze/master and /sim/freeze/clock. Setting
        # master alone does not stop the flight model in FlightGear 2024.
        c = controls.bounded()
        self.last_controls = c
        throttles = ','.join([f'{c.throttle:.7f}'] * self.engines)
        data = f'{c.aileron:.7f},{c.elevator:.7f},{c.rudder:.7f},{throttles},{int(frozen)},{int(frozen)}\n'
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


GEAR_AGL_FT = 7.95  # 738-flies parked: altitude-agl-ft with the wheels on the runway


class RunwayFlightGear(FlightGear):
    """Takeoff/landing bridge: protocols/flybrain-runway-{state,controls}.xml.

    Converts FlightGear's lat/lon into the runway frame used by RunwayState:
    x metres along the runway from `origin` (threshold or brake-release point),
    y metres right of centerline, psi heading error. If no runway is given, the
    first packet's position and heading define it (aircraft lined up for takeoff),
    moved `ahead_m` metres along that heading (aircraft placed on final that far
    before the threshold, e.g. FlightGear's --offset-distance).
    """
    def __init__(self, telemetry_port=5501, control_port=5502, timeout=2.0,
                 runway=None, ahead_m=0.0):
        super().__init__(telemetry_port, control_port, timeout, engines=2)
        self.runway = runway  # (lat, lon, true heading deg) or None
        # /position/altitude-agl-ft is the CG height: the 738 reads ~7.95 ft parked.
        # Measured from the first on-ground packet; this default covers airborne starts.
        self.agl_offset_ft = None
        self.ahead_m = ahead_m
        self.gear_down = True
        self.flaps = 0.375  # flaps 5 (737 detent); set by the scripted checklist
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
        if self.agl_offset_ft is None:
            self.agl_offset_ft = agl_ft if wow else GEAR_AGL_FT
        if self.runway is None:
            h = math.radians(heading)
            self.runway = (lat + math.degrees(self.ahead_m * math.cos(h) / 6371000),
                           lon + math.degrees(self.ahead_m * math.sin(h) / (6371000 * math.cos(math.radians(lat)))),
                           heading)
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
        state = RunwayState(time=self.active_time, x=x, y=y, agl=max(0.0, (agl_ft - self.agl_offset_ft) * FT),
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
                f'{brake:.7f},{brake:.7f},{int(self.gear_down)},{int(frozen)},{int(frozen)},{self.flaps:.3f}\n')
        self.tx.sendto(data.encode('ascii'), self.address)

    def close(self):
        """Centre ailerons and rudder, then pause; returns True if FG acknowledged.

        FlightGear keeps the last received controls, so leaving a bank or rudder
        input latched is what crashed the first live takeoff test."""
        from dataclasses import replace
        paused = False
        try:
            self.last_controls = replace(self.last_controls, aileron=0.0, rudder=0.0)
            for _ in range(5):  # UDP: repeat rather than trust one packet
                self.send(self.last_controls, True)
                time.sleep(0.05)
            try:
                self.freeze(True)
                paused = True
            except (TimeoutError, ValueError, OSError):
                pass
        finally:
            self.rx.close()
            self.tx.close()
        return paused
