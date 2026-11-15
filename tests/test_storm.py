"""Tornado obstacles and storm weather: display only, calm air, honest footprint."""
from pathlib import Path
import re
import sys
import unittest
import xml.dom.minidom

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'flightgear' / 'tools'))
import make_obstacles as M  # noqa: E402
from flight_simulator import fg_scene, fg_weather  # noqa: E402

MODELS = ROOT / 'flightgear' / 'Aircraft' / 'FlyCabin' / 'Models' / 'Obstacles'
NASAL = ROOT / 'flightgear' / 'Aircraft' / 'FlyCabin' / 'Nasal'


class TornadoModel(unittest.TestCase):
    def test_tornado_stays_inside_the_obstacle_cylinder(self):
        """The fly avoids a cylinder of radius 1, height 1 (unit model). Nothing the
        viewer sees as 'tornado' may stick out of it, or the picture would lie."""
        meshes = {m.name: m for m in M.tornado_meshes()}
        self.assertEqual(set(meshes), {'Dark', 'Mid', 'Cap', 'Scud', 'Debris', 'Vortices', 'Chunks', 'Bolt', 'Ring'})
        self.assertEqual(set(M.INSIDE), set(meshes) - {'Ring'})
        for name in M.INSIDE:
            for x, y, z in meshes[name].verts:
                self.assertLessEqual((x * x + y * y) ** 0.5, 1.0 + 1e-9, name)
                self.assertTrue(-1e-9 <= z <= 1.0 + 1e-9, name)
        widest = max((x * x + y * y) ** 0.5 for x, y, _ in meshes['Dark'].verts + meshes['Mid'].verts)
        self.assertAlmostEqual(widest, 1.0, places=6)      # as wide as the cylinder at the top
        self.assertLess(M.funnel_radius(0.0), 0.3)         # and a narrow foot: it reads as a funnel
        ring = [(x * x + y * y) ** 0.5 for x, y, _ in meshes['Ring'].verts]
        self.assertAlmostEqual(min(ring), 1.0, places=6)   # footprint ring starts at the true radius

    def test_committed_models_match_the_generator(self):
        files = sorted(MODELS.glob('obstacle-*.xml'))
        self.assertEqual(len(files), M.MAX_OBSTACLES)
        self.assertEqual(M.MAX_OBSTACLES, fg_scene.MAX_OBSTACLES)
        self.assertTrue((MODELS / 'tornado.ac').is_file())
        self.assertFalse((MODELS / 'tower.ac').exists(), 'the old tower model is still there')
        for i in (0, 7, M.MAX_OBSTACLES - 1):
            text = (MODELS / f'obstacle-{i}.xml').read_text(encoding='utf-8')
            self.assertEqual(text.replace('\r\n', '\n'), M.model_xml(i), f'obstacle-{i}.xml is stale: rerun make_obstacles.py')

    def test_model_xml_is_well_formed_and_bound_to_its_index(self):
        for i in (0, 31):
            text = M.model_xml(i)
            doc = xml.dom.minidom.parseString(text)
            self.assertEqual(doc.getElementsByTagName('path')[0].firstChild.data, 'tornado.ac')
            types = [t.firstChild.data for t in doc.getElementsByTagName('type')]
            for needed in ('select', 'scale', 'rotate', 'material'):
                self.assertIn(needed, types)
            self.assertEqual(types.count('rotate'), len(set(M.SPIN.values())))
            self.assertIn('/fruitfly/storm/light', text)
            self.assertIn(f'/fruitfly/obstacles/obstacle[{i}]/visible', text)
            self.assertIn(f'<equals><property>/fruitfly/storm/bolt</property><value>{i}</value></equals>', text)
            self.assertNotIn('tower', text)

    def test_ac_file_objects(self):
        ac = (MODELS / 'tornado.ac').read_text()
        self.assertEqual(re.findall(r'^name "(\w+)"', ac, re.M),
                         ['Dark', 'Mid', 'Cap', 'Scud', 'Debris', 'Vortices', 'Chunks', 'Bolt', 'Ring'])
        self.assertEqual(len(re.findall(r'^MATERIAL ', ac, re.M)), 9)


class StormWeather(unittest.TestCase):
    def test_storm_is_gray_rain_and_thunder(self):
        metar = fg_weather.STORM_METAR
        self.assertIn('TSRA', metar)                      # thunderstorm with rain
        self.assertRegex(metar, r'\bOVC\d{3}CB\b')        # overcast cumulonimbus
        args = fg_weather.weather_args('storm')
        self.assertIn(f'--metar={metar}', args)
        self.assertIn('--prop:bool:/sim/rendering/precipitation-enable=true', args)
        self.assertIn('--prop:bool:/fruitfly/storm/enabled=true', args)

    def test_every_weather_profile_has_calm_air(self):
        for name in fg_weather.PROFILES:
            args = fg_weather.weather_args(name)
            self.assertIn('--turbulence=0.0', args, name)
            for a in args:
                self.assertNotRegex(a, r'^--(wind|random-wind)', name)
                if a.startswith('--metar='):
                    self.assertRegex(a, r' 00000KT ', 'METAR wind must be calm')
                    self.assertNotRegex(a, r'\d{5}G\d+KT', 'no gusts')
                    self.assertNotIn('WS', a)
        self.assertEqual(fg_weather.DEFAULT, 'storm')

    def test_cloud_base_is_above_the_test_flights(self):
        base_ft = int(re.search(r'OVC(\d{3})', fg_weather.STORM_METAR).group(1)) * 100
        self.assertGreater(base_ft, 3000 + 1700)   # cruise test altitude + tornado top (alt + 500 m)

    def test_launchers_add_the_weather_after_their_calm_wind(self):
        from flight_simulator import launch_fg
        src = (ROOT / 'flight_simulator' / 'launch_fg.py').read_text(encoding='utf-8')
        self.assertIn('weather_args(args.weather)', src)
        self.assertEqual(src.count("'--wind=0@0'"), 2)
        self.assertTrue(hasattr(launch_fg, 'command'))
        src = (ROOT / 'flightgear' / 'launch.py').read_text(encoding='utf-8')
        self.assertIn('"--wind=0@0"', src)
        self.assertIn('weather_args(a.weather)', src)


class StormScript(unittest.TestCase):
    def test_storm_nas_is_visuals_and_sound_only(self):
        nas = (NASAL / 'storm.nas').read_text(encoding='utf-8')
        code = '\n'.join(line.split('#')[0] for line in nas.splitlines())
        # The only 'wind' allowed is the name of FlightGear's sound sample for the roar.
        code = code.replace('"wind1.wav"', '"<roar sample>"')
        for banned in ('/controls', 'wind', 'turbulence', '/fdm/', '/environment/config', 'gust', 'jsbsim',
                       '/velocities', '/orientation', '/position'):
            self.assertNotIn(banned, code, f'storm.nas must not touch {banned}')
        # Every property it writes is a storm display value or FlightGear's lightning flash.
        for path in re.findall(r'setprop\("([^"]+)"', code):
            self.assertTrue(path.startswith('/environment/lightning/'), path)
        self.assertIn('fdm-initialized', code)   # nothing runs while FlightGear is loading
        self.assertIn('/environment/lightning/flash', code)
        self.assertIn('play-audio-sample', code)
        self.assertIn('/fruitfly/obstacles/count', code)

    def test_aircraft_loads_the_storm_script_in_both_copies(self):
        overlay = (ROOT / 'flightgear' / 'overlay' / '738-flies-set.xml').read_text(encoding='utf-8')
        self.assertIn('Aircraft/FlyCabin/Nasal/storm.nas', overlay)
        installed = ROOT / 'flightgear' / 'Aircraft' / '737-800' / '738-flies-set.xml'
        if not installed.exists():   # the stock 737 is not committed
            self.skipTest('stock 737-800 not installed: run flightgear/setup_aircraft.py')
        installed = installed.read_text(encoding='utf-8')
        self.assertEqual(overlay.replace('\r\n', '\n'), installed.replace('\r\n', '\n'))


if __name__ == '__main__':
    unittest.main()
