"""Live 3D fruit fly (flybody model) that mirrors the fly brain while it flies the plane.

    python -m flight_simulator.fly_body              # open the window, wait for the controller
    python -m flight_simulator --backend flightgear --brain connectome ...   # streams to it

The controller sends one small JSON message per control step to UDP 127.0.0.1:5600
(--body-port). This window poses the flybody fly (models/flybody, MuJoCo) from it:

| What you see                         | Driven by                                              |
|--------------------------------------|--------------------------------------------------------|
| Body banks / pitches                 | the airplane's roll and pitch (the fly rides the 737)  |
| Wingbeat amplitude                   | DNg02 rate (wingbeat-amplitude descending neurons)     |
| Left vs right wing amplitude, lean   | steering DNs: (DNa01+DNa02) right minus left           |
| Escape: wings flare, mid legs kick   | DNp01 Giant Fibre firing                               |
| Wings fold, fly rests                | no brain activity yet (or the stand-in brains)         |

This is a kinematic display: joint angles are set directly from firing rates and
nothing here feeds back into the flight controls. flybody's own RL walking/flight
policies are not used. Rates are shown relative to the largest value seen so far
in this window, so the motion shows *changes* in activity, not absolute Hz.

Needs `pip install mujoco` (in requirements-body.txt). Headless pose check:
    MUJOCO_GL=egl python -m flight_simulator.fly_body --render out_dir
"""
import argparse
import json
import math
from pathlib import Path
import socket
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / 'models' / 'flybody' / 'assets' / 'floor.xml'
BODY_PORT = 5600


class BodyLink:
    """Fire-and-forget sender used by the controller. Never raises into the control loop."""

    def __init__(self, port=BODY_PORT):
        self.address = ('127.0.0.1', port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.activity = {}

    def send(self, state, phase, brain, escape_hz, activity=None):
        if activity:
            self.activity = {k: round(v, 2) for k, v in activity.items()
                             if k.endswith('_hz') and isinstance(v, (int, float)) and math.isfinite(v)}
        alt = getattr(state, 'altitude', None)
        msg = {'roll': round(state.roll, 4), 'pitch': round(state.pitch, 4), 'phase': phase,
               'brain': brain, 'escape_hz': round(float(escape_hz), 2),
               'alt_m': round(alt if alt is not None else getattr(state, 'agl', 0.0), 1),
               'alt_kind': 'MSL' if alt is not None else 'AGL',
               'on_ground': bool(getattr(state, 'on_ground', False)),
               'speed_ms': round(state.speed, 1), 'activity': self.activity}
        try:
            self.sock.sendto(json.dumps(msg).encode(), self.address)
        except OSError:
            pass

    def close(self):
        self.sock.close()


def clip(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


class Drive:
    """Turns the latest message into smoothed 0..1 drives for the pose."""

    def __init__(self):
        self.peak = {}
        self.roll = self.pitch = 0.0
        self.power = self.steer = self.escape = 0.0
        self.jump_t = -10.0
        self.last = {}
        self.on_ground = False

    def norm(self, key, value, floor=20.0):
        self.peak[key] = max(self.peak.get(key, floor), value)
        return clip(value / self.peak[key], 0.0, 1.0)

    def update(self, msg, now):
        self.last = msg
        self.on_ground = bool(msg.get('on_ground', False))
        a = msg.get('activity', {})
        gf = max(float(msg.get('escape_hz', 0.0)), float(a.get('DNp01_hz', 0.0)))
        self.target = {
            'roll': float(msg.get('roll', 0.0)),
            'pitch': float(msg.get('pitch', 0.0)),
            'power': self.norm('DNg02', float(a.get('DNg02_hz', 0.0))) if 'DNg02_hz' in a else (0.6 if msg else 0.0),
            'escape': self.norm('DNp01', gf),
        }
        right = float(a.get('DNa01_R_hz', 0.0)) + float(a.get('DNa02_R_hz', 0.0))
        left = float(a.get('DNa01_L_hz', 0.0)) + float(a.get('DNa02_L_hz', 0.0))
        self.target['steer'] = clip((right - left) / (right + left + 20.0), -1.0, 1.0)
        if gf > 0 and self.escape < 0.2 and now - self.jump_t > 1.5:
            self.jump_t = now

    def step(self, dt):
        t = getattr(self, 'target', None)
        if not t:
            return
        k = 1 - math.exp(-dt / 0.15)
        self.roll += (t['roll'] - self.roll) * k
        self.pitch += (t['pitch'] - self.pitch) * k
        self.power += (t['power'] - self.power) * k
        self.steer += (t['steer'] - self.steer) * k
        self.escape += (t['escape'] - self.escape) * (1 - math.exp(-dt / 0.3))


class FlyPose:
    """Writes joint angles for the flybody fly from a Drive."""

    HOVER = 0.32   # cm above the floor while flying

    def __init__(self, model):
        import mujoco
        self.mujoco = mujoco
        self.model = model
        self.adr = {mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j): model.jnt_qposadr[j]
                    for j in range(model.njnt)}
        self.range = {mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j): tuple(model.jnt_range[j])
                      for j in range(model.njnt)}

    def set(self, q, name, value):
        lo, hi = self.range[name]
        q[self.adr[name]] = clip(value, lo, hi) if hi > lo else value

    def apply(self, data, t, drive, connected):
        q = data.qpos
        q[:] = self.model.qpos0
        jump = clip(1 - (t - drive.jump_t) / 0.8, 0.0, 1.0)  # 1 right after a Giant Fibre spike, fades
        # On the runway the Takeoff fly is a standing fly (wings folded); it flies once airborne.
        standing = connected and drive.on_ground and jump == 0.0
        flying = connected and not standing
        # Body: hover and ride the airplane's attitude (roll about x, pitch about y).
        bob = 0.01 * math.sin(2 * math.pi * 1.3 * t) if flying else 0.0
        q[0:3] = (0.0, 0.0, (self.HOVER + bob + 0.12 * jump) if flying else 0.0)
        roll, pitch = (drive.roll, drive.pitch) if connected else (0.0, 0.0)
        cr, sr, cp, sp = math.cos(roll / 2), math.sin(roll / 2), math.cos(-pitch / 2), math.sin(-pitch / 2)
        q[3:7] = (cr * cp, sr * cp, cr * sp, -sr * sp)
        if not flying:
            return
        # Wings: stroke (yaw) sweeps, rotation (pitch) flips at stroke reversal.
        hz = 9.0 + 6.0 * drive.power                    # slowed ~20x from a real ~200 Hz wingbeat
        phase = 2 * math.pi * hz * t
        base = 0.55 + 0.6 * drive.power + 0.4 * max(drive.escape, jump)
        for side, s in (('left', -1.0), ('right', 1.0)):
            amp = base * (1 + 0.35 * s * drive.steer)   # steering DNs: ipsilateral amplitude up
            self.set(q, f'wing_yaw_{side}', 0.15 + amp * math.sin(phase))
            self.set(q, f'wing_roll_{side}', 0.25 + 0.5 * jump)
            self.set(q, f'wing_pitch_{side}', 1.0 + 0.9 * math.cos(phase))
        # Legs tucked in flight; mid (T2) legs kick out on an escape (the Giant Fibre's jump).
        for leg in ('T1', 'T2', 'T3'):
            for side in ('left', 'right'):
                kick = jump if leg == 'T2' else 0.0
                # tucked: femur 0.6, tibia folded (legs trail under the body); kick: straight down
                self.set(q, f'femur_{leg}_{side}', 0.6 * (1 - kick))
                self.set(q, f'tibia_{leg}_{side}', 1.3 * (1 - kick))
        # Head turns into the steer, abdomen trails it.
        self.set(q, 'head_twist', 0.25 * drive.steer)
        self.set(q, 'abdomen_abduct', -0.15 * drive.steer)
        self.set(q, 'abdomen', 0.1 * math.sin(phase / 6))
        for h, s in (('haltere_left', 1), ('haltere_right', -1)):
            self.set(q, h, 0.6 * math.sin(phase + math.pi))


def caption(drive, connected):
    m = drive.last
    if not connected:
        return 'Waiting for the controller (UDP 127.0.0.1:%d)' % BODY_PORT, ''
    a = m.get('activity', {})
    left = ('brain: %s   phase: %s\nGiant Fibre: %.0f Hz   DNg02 wing power: %.0f Hz\n'
            'steer DNs L/R: %.0f / %.0f Hz' % (
                m.get('brain', '?'), m.get('phase', '?'), max(m.get('escape_hz', 0), a.get('DNp01_hz', 0)),
                a.get('DNg02_hz', 0), a.get('DNa01_L_hz', 0) + a.get('DNa02_L_hz', 0),
                a.get('DNa01_R_hz', 0) + a.get('DNa02_R_hz', 0)))
    right = 'Boeing 737: %.0f m %s, %.0f kt%s\nbank %+.0f deg, pitch %+.0f deg' % (
        m.get('alt_m', 0), m.get('alt_kind', 'MSL'), m.get('speed_ms', 0) / 0.514444,
        ', on the runway' if m.get('on_ground') else '',
        math.degrees(m.get('roll', 0)), math.degrees(m.get('pitch', 0)))
    return left, right


def render_checks(out_dir):
    """Headless: render a few synthetic states to PNG to check the poses."""
    import mujoco
    model = mujoco.MjModel.from_xml_path(str(MODEL))
    data = mujoco.MjData(model)
    pose = FlyPose(model)
    renderer = mujoco.Renderer(model, 360, 480)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cases = {
        'waiting': None,
        'cruise': {'roll': 0.0, 'pitch': 0.05, 'escape_hz': 0, 'activity': {'DNg02_hz': 30, 'DNa01_L_hz': 10, 'DNa01_R_hz': 10}},
        'bank_right': {'roll': 0.4, 'pitch': 0.0, 'escape_hz': 0, 'activity': {'DNg02_hz': 60, 'DNa02_R_hz': 60, 'DNa02_L_hz': 5}},
        'escape': {'roll': 0.0, 'pitch': 0.0, 'escape_hz': 270, 'activity': {'DNg02_hz': 80, 'DNp01_hz': 270}},
    }
    for name, msg in cases.items():
        drive = Drive()
        t = 0.0
        if msg:
            drive.update({'activity': {'DNg02_hz': 80, 'DNp01_hz': 270}}, -5)  # set peaks
            drive.update(msg, t)
            for _ in range(60):
                drive.step(0.02)
            t = 0.05
            if name == 'escape':
                drive.jump_t = 0.0
        pose.apply(data, t, drive, msg is not None)
        mujoco.mj_forward(model, data)
        for cam in ('hero', 'back'):
            renderer.update_scene(data, camera=cam)
            write_png(out / f'{name}_{cam}.png', renderer.render())
    print(f'Rendered {len(cases) * 2} frames to {out}')


def write_png(path, img):
    import struct
    import zlib
    h, w, _ = img.shape
    raw = b''.join(b'\x00' + img[y].tobytes() for y in range(h))

    def chunk(tag, payload):
        c = struct.pack('>I', len(payload)) + tag + payload
        return c + struct.pack('>I', zlib.crc32(tag + payload) & 0xffffffff)

    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
                          + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port', type=int, default=BODY_PORT, help='UDP port to listen on (controller: --body-port)')
    parser.add_argument('--render', metavar='DIR', help='Render test poses to DIR and exit (no window)')
    args = parser.parse_args()
    try:
        import mujoco
        import mujoco.viewer
    except ImportError:
        sys.exit('Install MuJoCo first: pip install -r requirements-body.txt')
    if args.render:
        render_checks(args.render)
        return 0

    model = mujoco.MjModel.from_xml_path(str(MODEL))
    data = mujoco.MjData(model)
    pose = FlyPose(model)
    drive = Drive()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('127.0.0.1', args.port))
    sock.setblocking(False)
    thorax = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, 'thorax')
    print(f'Fly body window: listening on UDP 127.0.0.1:{args.port}. Close the window to quit.', flush=True)

    last_msg = -1e9
    with mujoco.viewer.launch_passive(model, data, show_left_ui=False, show_right_ui=False) as viewer:
        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_TRACKING
        viewer.cam.trackbodyid = thorax
        viewer.cam.distance, viewer.cam.azimuth, viewer.cam.elevation = 0.75, 150, -12
        start = prev = time.monotonic()
        while viewer.is_running():
            now = time.monotonic()
            while True:
                try:
                    packet, _ = sock.recvfrom(65536)
                except BlockingIOError:
                    break
                try:
                    drive.update(json.loads(packet), now - start)
                    last_msg = now
                except (ValueError, TypeError):
                    continue
            connected = now - last_msg < 3.0
            drive.step(now - prev)
            pose.apply(data, now - start, drive, connected)
            mujoco.mj_forward(model, data)
            if hasattr(viewer, 'set_texts'):
                left, right = caption(drive, connected)
                viewer.set_texts([(mujoco.mjtFontScale.mjFONTSCALE_150, mujoco.mjtGridPos.mjGRID_TOPLEFT, left, ''),
                                  (mujoco.mjtFontScale.mjFONTSCALE_150, mujoco.mjtGridPos.mjGRID_TOPRIGHT, right, '')])
            viewer.sync()
            prev = now
            time.sleep(max(0.0, 1 / 60 - (time.monotonic() - now)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
