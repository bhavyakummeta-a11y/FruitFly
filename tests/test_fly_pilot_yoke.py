"""Fly pilot holds the 737 yoke: its front legs stay on the wheel horns as the yoke
turns (aileron) and moves fore/aft (elevator). Checks the generated fly-pilot model
against the stock 737 cockpit model. Standard library only."""
import math
from pathlib import Path
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'flightgear' / 'tools'))
import make_cabin as mc  # noqa: E402

MODELS = ROOT / 'flightgear' / 'Aircraft' / 'FlyCabin' / 'Models'
COCKPIT = ROOT / 'flightgear' / 'Aircraft' / '737-800' / 'Models'


def ac_objects(path):
    """{name: [(x, y, z) in FG model axes]} for each poly object of an AC3D file."""
    lines = path.read_text(encoding='latin-1').split('\n')
    out = {}
    for i, line in enumerate(lines):
        if line.startswith('name "'):
            j = i + 1
            while j < len(lines) and not lines[j].startswith(('numvert', 'OBJECT')):
                j += 1
            if j < len(lines) and lines[j].startswith('numvert'):
                n = int(lines[j].split()[1])
                pts = [tuple(map(float, lines[j + 1 + k].split())) for k in range(n)]
                out[line[6:-1]] = [(x, -z, y) for x, y, z in pts]   # AC (x, y, z) = FG (x, z, -y)
    return out


def rotate(p, center, axis, deg):
    a = [c / math.sqrt(sum(v * v for v in axis)) for c in axis]
    t = math.radians(deg)
    v = [p[i] - center[i] for i in range(3)]
    dot = sum(a[i] * v[i] for i in range(3))
    cross = (a[1] * v[2] - a[2] * v[1], a[2] * v[0] - a[0] * v[2], a[0] * v[1] - a[1] * v[0])
    return tuple(center[i] + v[i] * math.cos(t) + cross[i] * math.sin(t) + a[i] * dot * (1 - math.cos(t))
                 for i in range(3))


def yoke_animations():
    """The stock 737 yoke1 rotate animations: {property: (center in model axes, axis, factor)}."""
    root = ET.parse(COCKPIT / 'cockpit.xml').getroot()
    dx = float(root.find('offsets/x-m').text)
    out = {}
    for anim in root.findall('animation'):
        names = [o.text for o in anim.findall('object-name')]
        if anim.findtext('type') == 'rotate' and 'yoke1' in names:
            c = anim.find('center')
            center = (float(c.findtext('x-m')) + dx, float(c.findtext('y-m')), float(c.findtext('z-m')))
            ax = anim.find('axis')
            axis = tuple(float(ax.findtext(k)) for k in 'xyz')
            out[anim.findtext('property').split('/')[-1]] = (center, axis, float(anim.findtext('factor')))
    return out


class YokeGeometry(unittest.TestCase):
    def test_constants_match_the_737_cockpit_model(self):
        anims = yoke_animations()
        (pc, pa, pf), (hc, ha, hf) = anims['elevator'], anims['aileron']
        self.assertEqual((pa, ha), ((0, -1, 0), (-1, 0, 0)))
        self.assertEqual((pf, hf), (mc.YOKE_ELEVATOR_DEG, mc.YOKE_AILERON_DEG))
        self.assertAlmostEqual(pc[0], mc.YOKE_ELEVATOR_PIVOT[0], places=3)   # axis along y
        self.assertAlmostEqual(pc[2], mc.YOKE_ELEVATOR_PIVOT[2], places=3)
        self.assertAlmostEqual(hc[1], mc.YOKE_HUB[1], places=3)              # axis along x
        self.assertAlmostEqual(hc[2], mc.YOKE_HUB[2], places=3)

    def test_pilot_seat_matches_the_aircraft_model(self):
        xml = (MODELS / '738-flies.xml').read_text()
        m = re.search(r'<name>flypilot</name>.*?<x-m>([-\d.]+)</x-m><y-m>([-\d.]+)</y-m><z-m>([-\d.]+)</z-m>', xml)
        self.assertEqual(tuple(map(float, m.groups())), mc.PILOT_SEAT)

    def test_claws_stay_on_the_horns_and_elbows_attached_as_the_yoke_moves(self):
        yoke = ac_objects(COCKPIT / 'cockpit.ac')['yoke1']
        yoke = [(x - 18.31, y, z) for x, y, z in yoke]
        seat = mc.PILOT_SEAT
        world = lambda p: tuple(p[i] + seat[i] for i in range(3))
        for ail, elv in ((0, 0), (0.5, 0), (-0.5, 0), (0, 0.5), (0, -0.5), (0.3, 0.3)):
            def move(p, lower=True):
                p = rotate(p, mc.YOKE_ELEVATOR_PIVOT, (0, -1, 0), mc.YOKE_ELEVATOR_DEG * elv)
                return rotate(p, mc.YOKE_HUB, (-1, 0, 0), mc.YOKE_AILERON_DEG * ail) if lower else p
            wheel = [move(p) for p in yoke]
            for s in (-1, 1):
                (shoulder, elbow_up), (elbow_low, wrist, over, claw) = mc.pilot_arm_points(s)
                for name, p in (('wrist', wrist), ('over', over), ('claw', claw)):
                    q = move(world(p))
                    gap = min(math.dist(q, w) for w in wheel)
                    self.assertLess(gap, 0.035, f'{name} side {s} ail {ail} elv {elv}: {gap:.3f} m off the wheel')
                gap = math.dist(move(world(elbow_up), lower=False), move(world(elbow_low)))
                self.assertLess(gap, 0.026, f'elbow side {s} ail {ail} elv {elv} opens {gap:.3f} m')

    def test_arms_start_inside_the_thorax_beyond_lean_and_hop(self):
        thorax_c, thorax_r = (0.0, 0.0, 0.55), 0.17
        lean_shift = (0.55 - 0.10) * math.sin(math.radians(12))   # fruitfly.nas: lean <= 12 deg
        hop = 0.12
        # Full lean or a full escape hop alone never shows the end of the leg outside the
        # body. (Both at full at once only during the 0.8 s hop in a hard turn.)
        for s in (-1, 1):
            shoulder = mc.pilot_arm_points(s)[0][0]
            for shift in (lean_shift, hop):
                self.assertLess(math.dist(shoulder, thorax_c) + shift, thorax_r)


class GeneratedModel(unittest.TestCase):
    def test_committed_files_match_the_generator(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = mc.OUT
            try:
                mc.OUT = tmp
                mc.build_pilot()
                built = (Path(tmp) / 'fly-pilot.ac').read_text()
            finally:
                mc.OUT = out
        self.assertEqual(built, (MODELS / 'fly-pilot.ac').read_text(),
                         'run python flightgear/tools/make_cabin.py')
        self.assertEqual(mc.pilot_xml(), (MODELS / 'fly-pilot.xml').read_text())

    def test_arm_objects_and_animations(self):
        objects = ac_objects(MODELS / 'fly-pilot.ac')
        for name in mc.ARM_OBJECTS + ('Body', 'Head', 'Legs', 'WingL', 'WingR'):
            self.assertIn(name, objects)
        root = ET.parse(MODELS / 'fly-pilot.xml').getroot()
        self.assertEqual(root.findtext('path'), 'fly-pilot.ac')
        by_prop = {}
        for anim in root.findall('animation'):
            names = {o.text for o in anim.findall('object-name')}
            by_prop[anim.findtext('property') or anim.findtext('type')] = names
        self.assertEqual(by_prop['/controls/flight/elevator'], set(mc.ARM_OBJECTS))
        self.assertEqual(by_prop['/controls/flight/aileron'], {'ArmLowerL', 'ArmLowerR'})
        self.assertTrue(set(mc.ARM_OBJECTS) <= by_prop['select'])         # hidden in the captain view too
        for prop in ('/fruitfly/pilot/lean-deg', '/fruitfly/pilot/hop-m'):  # body moves, hands stay on the wheel
            self.assertFalse(set(mc.ARM_OBJECTS) & by_prop[prop])

    def test_passenger_flies_keep_their_hanging_front_legs(self):
        legs = ac_objects(MODELS / 'fly.ac')['Legs']
        self.assertFalse(any(name.startswith('Arm') for name in ac_objects(MODELS / 'fly.ac')))
        self.assertEqual(len(legs), 3 * 2 * 2 * 16)   # 3 legs a side, 2 square tubes of 16 verts


if __name__ == '__main__':
    unittest.main()
