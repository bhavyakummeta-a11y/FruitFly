"""LAX -> Burbank storm story (route_weather.py): looks only, stages in route order,
tornadoes revealed before the planner could react to them, briefing before landing."""
from pathlib import Path
import math
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from flight_simulator import route_weather as W  # noqa: E402
from flight_simulator.airport_route import AirportRoute, RouteMission, LAX  # noqa: E402
from flight_simulator.flies import StandInBrain  # noqa: E402
from flight_simulator.mission import LandingFly  # noqa: E402
from flight_simulator.runway import RunwayState, FT  # noqa: E402
from tests.test_no_autopilot import FakeFG  # noqa: E402

METARS = [s.metar for s in W.STAGES]


def along(route, step=250.0):
    """Points every `step` m along the route's legs, in the LAX 25R frame."""
    for leg in route.legs:
        n = max(1, int(math.hypot(leg.x1 - leg.x0, leg.y1 - leg.y0) / step))
        for k in range(n):
            t = k / n
            yield leg.x0 + t * (leg.x1 - leg.x0), leg.y0 + t * (leg.y1 - leg.y0)


class LooksOnly(unittest.TestCase):
    def test_every_metar_is_calm(self):
        for m in METARS:
            self.assertRegex(m, r' 00000KT ', m)
            self.assertNotRegex(m, r'\d{5}G\d+KT', m)
            self.assertNotIn('WS', m)
            self.assertNotRegex(m, r'\bV\d{3}\b|\d{3}V\d{3}', m)   # no variable wind

    def test_clouds_stay_above_the_route_and_the_tornadoes(self):
        route = AirportRoute()
        cruise_ft = max(leg.alt_ft for leg in route.legs) + LAX.elevation_ft
        tornado_top_ft = max(o.top for o in route.obstacles) / FT + LAX.elevation_ft
        for m in METARS:
            for base in re.findall(r'(?:FEW|SCT|BKN|OVC)(\d{3})', m):
                self.assertGreater(int(base) * 100, cruise_ft, m)
        storm_base = min(int(b) * 100 for b in re.findall(r'(?:BKN|OVC)(\d{3})', W.STORM_METAR))
        self.assertGreater(storm_base, tornado_top_ft)

    def test_stage_props_touch_only_display_values(self):
        allowed = ('/environment/metar/data', '/environment/params/metar-updates-environment',
                   '/environment/realwx/enabled', '/environment/turbulence/magnitude-norm',
                   '/sim/rendering/precipitation-enable', '/fruitfly/storm/enabled', '/fruitfly/weather',
                   '/sim/messages/atc', W.FILTERING, *W.LOOK)
        for stage in W.STAGES:
            for path, value in W.stage_props(stage, 2, 'brief'):
                ok = path in allowed or re.fullmatch(r'/fruitfly/obstacles/obstacle\[\d+\]/visible', path)
                self.assertTrue(ok, path)
                if path == '/environment/turbulence/magnitude-norm':
                    self.assertEqual(value, '0')
                self.assertNotIn('\n', value)
        args = W.launch_args()
        self.assertIn('--turbulence=0.0', args)
        self.assertIn(f'--metar={W.CLEAR_METAR}', args)
        self.assertIn('--prop:bool:/fruitfly/storm/enabled=false', args)


class Look(unittest.TestCase):
    def test_storm_look_matches_fg_weather_and_clear_resets_it(self):
        from flight_simulator import fg_weather
        storm = dict(W.look_props(1.0))
        for arg in fg_weather.STORM_LOOK:
            if arg.startswith('--prop:') and '=' in arg:
                path, value = arg.split(':', 2)[-1].split('=', 1) if arg.count(':') > 1 else arg[7:].split('=', 1)
                self.assertIn(path, storm, path)
                if value not in ('true', 'false'):
                    self.assertAlmostEqual(float(storm[path]), float(value), places=3, msg=path)
        clear = dict(W.look_props(0.0))
        self.assertEqual(clear[W.FILTERING], 'false')
        self.assertEqual(float(clear['/environment/air-pollution-norm']), 0.0)
        self.assertEqual(W.BY_NAME['storm'].look, 1.0)
        self.assertEqual((W.BY_NAME['clear'].look, W.BY_NAME['burbank'].look), (0.0, 0.0))
        self.assertTrue(any(a.startswith('--prop:/environment/air-pollution-norm=0.000') for a in W.launch_args()))


class Story(unittest.TestCase):
    def test_stages_follow_the_route_in_order(self):
        route = AirportRoute()
        weather = W.RouteWeather(route)
        seen = ['clear']
        for x, y in along(route):
            stage = weather.update(x, y)
            if stage:
                seen.append(stage.name)
        self.assertEqual(seen, [s.name for s in W.STAGES])
        first, last = weather.tornado_at[0], weather.tornado_at[-1]
        self.assertLess(weather.starts['storm'], first)
        self.assertGreater(weather.starts['clearing'], last)
        # The takeoff and the whole departure leg are under a clear sky.
        self.assertGreater(weather.starts['darkening'], math.hypot(route.legs[0].x1, route.legs[0].y1))

    def test_tornadoes_appear_before_the_planner_can_see_them(self):
        """guidance.py looks ahead at most 70 s; at a generous 100 m/s that is 7 km."""
        self.assertGreater(W.STORM_LEAD_M, 70 * 100)
        storm = W.BY_NAME['storm']
        self.assertTrue(storm.tornadoes and storm.lightning and storm.rain)
        self.assertFalse(W.BY_NAME['clear'].tornadoes or W.BY_NAME['darkening'].tornadoes)

    def test_never_goes_backwards(self):
        route = AirportRoute()
        weather = W.RouteWeather(route)
        o = route.obstacles[0]
        weather.update(o.north, o.east)
        self.assertEqual(weather.stage.name, 'storm')
        self.assertIsNone(weather.update(0, 0))      # back at LAX (e.g. a glitch): stays storm
        self.assertEqual(weather.stage.name, 'storm')

    def test_mission_briefs_before_landing(self):
        mission = RouteMission(StandInBrain(), calibrate=False, log=lambda *_: None)
        route = mission.route
        briefed_at = None
        for i, (x, y) in enumerate(along(route, 500)):
            mission.update_weather(RunwayState(x=x, y=y, agl=1500, time=float(i)))
            if mission.briefing and briefed_at is None:
                briefed_at = (x, y)
        self.assertIsNotNone(mission.briefing)
        self.assertEqual((mission.briefing['airport'], mission.briefing['runway']), ('KBUR', '08'))
        self.assertIn('not perceived', mission.briefing['source'])
        story = mission.story()
        self.assertEqual([s['stage'] for s in story['sky_stages']], [s.name for s in W.STAGES[1:]])
        stage, message = mission.sky_changes[-1]
        self.assertTrue(stage.briefing)
        self.assertIn('runway 08', message)
        self.assertTrue(mission.report()['runway_briefed'])
        self.assertFalse(isinstance(mission.fly, LandingFly))

    def test_replaced_obstacles_move_the_storm(self):
        route = AirportRoute()
        default = W.RouteWeather(route).starts['storm']
        moved = W.RouteWeather(route, [route.obstacles[1]]).starts['storm']
        self.assertGreater(moved, default)
        none = W.RouteWeather(route, [])
        self.assertTrue(math.isinf(none.starts['storm']))
        self.assertFalse(math.isinf(none.starts['burbank']))   # still briefed without tornadoes


class Director(unittest.TestCase):
    def scene(self):
        from flight_simulator.fg_scene import ObstacleScene
        fg = FakeFG({})
        self.addCleanup(fg.server_close)
        self.addCleanup(fg.shutdown)
        scene = ObstacleScene(fg.port)
        self.addCleanup(scene.sock.close)
        return fg, scene

    def test_applies_a_stage_and_confirms_the_metar(self):
        fg, scene = self.scene()
        sky = W.SkyDirector(scene, 2, say=lambda *_: None)
        sky.apply(W.BY_NAME['storm'])
        self.assertEqual(sky.applied, [{'stage': 'storm', 'metar_confirmed': True}])
        self.assertEqual(fg.props['/fruitfly/storm/enabled'], 'true')
        self.assertEqual(fg.props['/fruitfly/obstacles/obstacle[1]/visible'], 'true')

    def test_a_dead_connection_never_stops_the_flight(self):
        fg, scene = self.scene()
        scene.sock.close()
        sky = W.SkyDirector(scene, 2, say=lambda *_: None)
        sky.apply(W.BY_NAME['clear'])              # must not raise
        self.assertIn('error', sky.applied[0])


class Launcher(unittest.TestCase):
    def cmd(self, *extra):
        out = subprocess.run([sys.executable, '-m', 'flight_simulator.launch_fg', '--route', 'lax-burbank',
                              '--name', 'test', '--print', *extra], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout

    def test_route_starts_clear_unless_weather_is_given(self):
        self.assertIn('lax-burbank story: clear', self.cmd())
        self.assertIn('/fruitfly/storm/enabled=false', self.cmd())
        self.assertNotIn('lax-burbank story', self.cmd('--weather', 'storm'))
        self.assertIn('/fruitfly/storm/enabled=true', self.cmd('--weather', 'storm'))

    def test_explicit_weather_tells_the_controller_to_keep_it(self):
        self.addCleanup(setattr, sys, 'argv', list(sys.argv))
        sys.argv = ['launch_fg', '--route', 'lax-burbank', '--weather', 'clear']
        from flight_simulator import launch_fg
        self.assertTrue(launch_fg.weather_given())
        sys.argv = ['launch_fg', '--route', 'lax-burbank']
        self.assertFalse(launch_fg.weather_given())
        src = (ROOT / 'flight_simulator' / 'launch_fg.py').read_text(encoding='utf-8')
        self.assertIn("['--sky','fixed'] if weather_given()", src)


if __name__ == '__main__':
    unittest.main()
