"""Cabin gag (fly flight attendant + snack cart) and the log page's camera buttons.

Display only: nothing here may touch flight controls or the fly pilot.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import json
import re
import sys
import threading
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'flightgear' / 'tools'))

import make_cabin  # noqa: E402
from flight_simulator import session  # noqa: E402

CABIN = ROOT / 'flightgear/Aircraft/FlyCabin'
SET = ROOT / 'flightgear/overlay/738-flies-set.xml'


def nas_floats(text, name):
    m = re.search(rf'var {name} = \[?([^\];]*)\]?;', text)
    return [float(v) for v in m.group(1).split(',')]


class CabinGagModel(unittest.TestCase):
    def test_rows_file_matches_generator_layout(self):
        rows, x = [], make_cabin.ROW_FIRST
        for r in range(make_cabin.N_ROWS):
            rows.append(x)
            x += make_cabin.ROW_PITCH + (0.35 if r == make_cabin.OVERWING_GAP_AFTER else 0.0)
        nas = (CABIN / 'Nasal/cabin_rows.nas').read_text()
        self.assertEqual(nas_floats(nas, 'ROWS'), [round(v, 3) for v in rows])
        self.assertAlmostEqual(nas_floats(nas, 'START_X')[0], make_cabin.ATT_START_X, places=3)

    def test_animated_objects_exist_in_the_mesh(self):
        ac = (CABIN / 'Models/attendant.ac').read_text()
        meshes = set(re.findall(r'^name "([^"]+)"', ac, re.M))
        xml = ET.parse(CABIN / 'Models/attendant.xml').getroot()
        named = {e.text for e in xml.iter('object-name')}
        self.assertTrue(named)
        self.assertEqual(named - meshes, set())
        for item in ('ItemWater', 'ItemPoop', 'ItemBanana', 'Cart'):
            self.assertIn(item, meshes)

    def test_attendant_and_baby_are_in_the_aircraft_model(self):
        top = (CABIN / 'Models/738-flies.xml').read_text()
        self.assertIn('Aircraft/FlyCabin/Models/attendant.xml', top)
        self.assertIn('Aircraft/FlyCabin/Models/baby.xml', top)

    def test_baby_objects_exist_and_its_row_is_known(self):
        ac = (CABIN / 'Models/baby.ac').read_text()
        meshes = set(re.findall(r'^name "([^"]+)"', ac, re.M))
        named = {e.text for e in ET.parse(CABIN / 'Models/baby.xml').getroot().iter('object-name')}
        self.assertEqual(named - meshes, set())
        nas = (CABIN / 'Nasal/cabin_rows.nas').read_text()
        self.assertIn(nas_floats(nas, 'BABY_ROW_X')[0], nas_floats(nas, 'ROWS'))

    def test_baby_cry_sample_is_a_short_mono_wav(self):
        import wave
        with wave.open(str(CABIN / 'Sounds/baby-cry.wav')) as w:
            self.assertEqual(w.getnchannels(), 1)
            length = w.getnframes() / w.getframerate()
        self.assertTrue(3 < length < 6, length)
        nas = (CABIN / 'Nasal/cabin_show.nas').read_text()
        self.assertIn(f'CRY_LEN = {length:.1f}', nas)

    def test_set_file_loads_the_show_and_the_follow_view(self):
        root = ET.parse(SET).getroot()
        files = [f.text for f in root.find('nasal/fruitfly_cabin').findall('file')]
        self.assertEqual(files, ['Aircraft/FlyCabin/Nasal/cabin_rows.nas',
                                 'Aircraft/FlyCabin/Nasal/cabin_show.nas'])
        for f in files:
            self.assertTrue((ROOT / 'flightgear' / f).exists(), f)
        names = [v.findtext('name') for v in root.find('sim').findall('view')]
        self.assertIn('Cabin: follow the snack cart', names)
        installed = ROOT / 'flightgear/Aircraft/737-800/738-flies-set.xml'
        self.assertEqual(installed.read_text(), SET.read_text(), 'run flightgear/setup_aircraft.py')

    def test_show_is_display_only(self):
        nas = (CABIN / 'Nasal/cabin_show.nas').read_text()
        code = '\n'.join(line.split('#')[0] for line in nas.splitlines())
        for forbidden in ('/controls', '/autopilot', '/fruitfly/pilot', 'brake', 'throttle'):
            self.assertNotIn(forbidden, code)


class CameraButtons(unittest.TestCase):
    def test_project_views_exist(self):
        root = ET.parse(SET).getroot()
        ours = {v.findtext('name') for v in root.find('sim').findall('view')}
        stock = {'Cockpit View', 'Chase View'}   # FlightGear defaults.xml
        for label, name in session.VIEW_BUTTONS.items():
            self.assertIn(name, ours | stock, label)

    def test_set_view_posts_only_allowed_names(self):
        got = []

        class FG(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                got.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{}')

        fg = HTTPServer(('127.0.0.1', 0), FG)
        threading.Thread(target=fg.serve_forever, daemon=True).start()
        try:
            events = []
            stub = type('S', (), {'httpd': fg.server_port,
                                  'event': lambda self, src, text: events.append(text)})()
            self.assertFalse(session.Session.set_view(stub, '/controls/flight/elevator'))
            self.assertFalse(session.Session.set_view(stub, 'Nope'))
            self.assertEqual(got, [])
            self.assertTrue(session.Session.set_view(stub, 'Snack cart'))
            self.assertEqual(got, [('/json/fruitfly/view-request', {'value': 'Cabin: follow the snack cart'})])
            self.assertIn('display only', events[-1])
        finally:
            fg.shutdown()


if __name__ == '__main__':
    unittest.main()
