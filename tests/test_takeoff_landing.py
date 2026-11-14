"""Takeoff fly / Landing fly tests. Standard library only (probe-table stand-in brain)."""
import math
from pathlib import Path
import random
import socket
import unittest
import xml.etree.ElementTree as ET

from flight_simulator.flies import (TakeoffFly, LandingFly, StandInBrain, run_phase,
                                    PITCH_ZERO, STEER_ZERO, V1)
from flight_simulator.flightgear import RunwayFlightGear
from flight_simulator.runway import (RunwaySim, RunwayState, FLAPS5, FLAPS30, FT, KT,
                                     AirlinerControls, takeoff_start, trimmed_approach, trim_elevator)
from flight_simulator.takeoff_landing import judge

PROTOCOLS = Path(__file__).resolve().parent.parent / 'flight_simulator' / 'protocols'


def takeoff(brain=None, **kw):
    sim = RunwaySim(takeoff_start(y=kw.pop('y', 0.0)), FLAPS5, yaw_disturbance=kw.pop('yaw', 0.0))
    fly = TakeoffFly(brain or StandInBrain(), **kw)
    return run_phase(fly, sim, 150), fly


def landing(brain=None, speed_kt=145.0, y=0.0):
    state = trimmed_approach(speed_kt=speed_kt, y=y)
    sim = RunwaySim(state, FLAPS30)
    fly = LandingFly(brain or StandInBrain(), trim_throttle=state.spool, trim_elevator=trim_elevator(state))
    return run_phase(fly, sim, 200), fly


def neutral_rates(**overrides):
    """Readouts that decode to 'no correction' (zero points), plus overrides."""
    r = {k: 0.0 for k in TakeoffFly.readouts}
    r.update({'DNp20_L': 32.0, 'DNp20_R': PITCH_ZERO - 32.0, 'DNp15_R': -STEER_ZERO, 'MN9': 70.0})
    r.update(overrides)
    return r


class TakeoffFlyTests(unittest.TestCase):
    def test_takeoff_to_handover(self):
        r, fly = takeoff(y=3.0, yaw=0.004)
        self.assertTrue(r['completed'], r)
        self.assertEqual(r['phase'], 'HANDOVER (1,000 ft)')
        self.assertFalse(r['tail_strike'])
        self.assertLess(r['max_centerline_m'], 5.0)
        self.assertLess(r['liftoff_x_m'], 2500)
        self.assertTrue(any(d.note.startswith('JUMP') for d in fly.decisions))
        self.assertTrue(judge('takeoff', r))

    def test_reject_below_v1_stops_on_runway(self):
        r, fly = takeoff(fault_at_kt=100)
        self.assertTrue(r['rejected'])
        self.assertTrue(r['completed'])
        self.assertIsNone(r['liftoff_x_m'])
        self.assertLess(r['stop_x_m'], 3600)
        self.assertTrue(judge('takeoff', r))

    def test_fault_after_v1_does_not_reject(self):
        r, _ = takeoff(fault_at_kt=140)
        self.assertFalse(r['rejected'])
        self.assertEqual(r['phase'], 'HANDOVER (1,000 ft)')

    def test_looming_lesion_means_no_rotation(self):
        r, fly = takeoff(StandInBrain(['looming']))
        self.assertIsNone(r['liftoff_x_m'])
        self.assertTrue(r['left_runway'])
        self.assertFalse(judge('takeoff', r))

    def test_standing_gate_ignores_escape_once_airborne(self):
        fly = TakeoffFly(StandInBrain())
        flying = RunwayState(speed=80, agl=50, pitch=math.radians(15), on_ground=False)
        fly.decode(neutral_rates(DNp02=200, DNp04=330, DNp11=150, DNp01=290), flying)
        self.assertAlmostEqual(fly.q_cmd, 0.0, places=6)
        rolling = RunwayState(speed=75, on_ground=True)
        fly.decode(neutral_rates(DNp02=200, DNp04=330, DNp11=150), rolling)
        self.assertGreater(fly.q_cmd, math.radians(2))

    def test_committed_after_v1_even_if_mn9_collapses(self):
        fly = TakeoffFly(StandInBrain())
        s = RunwayState(speed=V1 + 1, on_ground=True)
        for _ in range(3):
            fly.decode(neutral_rates(MN9=0.0), s)
        self.assertFalse(fly.rejected)
        self.assertEqual(fly.throttle, 1.0)


class LandingFlyTests(unittest.TestCase):
    def test_stabilised_approach_flares_and_lands(self):
        r, fly = landing(y=15.0)
        self.assertEqual(r['phase'], 'ROLLOUT')
        self.assertFalse(r['go_around'])
        self.assertLess(r['touchdown_sink_fpm'], 500)
        self.assertGreater(r['touchdown_x_m'], 0)
        self.assertLess(r['touchdown_x_m'], 900)
        self.assertGreater(r['flare_decisions'], 3)
        self.assertTrue(judge('landing', r))

    def test_looming_lesion_lands_harder(self):
        intact, _ = landing()
        lesion, _ = landing(StandInBrain(['looming']))
        self.assertEqual(lesion['flare_decisions'], 0)
        self.assertGreater(lesion['touchdown_sink_fpm'], intact['touchdown_sink_fpm'] + 200)

    def test_fast_unstable_approach_goes_around(self):
        r, fly = landing(speed_kt=175)
        self.assertTrue(r['go_around'])
        self.assertIsNone(r['touchdown_x_m'])
        self.assertTrue(any(d.note.startswith('GO-AROUND') for d in fly.decisions))

    def test_flying_gate_decouples_giant_fibre_and_limits_flare_height(self):
        fly = LandingFly(StandInBrain())
        high = RunwayState(agl=300 * FT, speed=74, gamma=-0.05, on_ground=False)
        fly.decode(neutral_rates(DNp01=290, DNp04=330, DNp07=30), high)
        self.assertAlmostEqual(fly.q_cmd, 0.0, places=6)   # neither jump nor flare at 300 ft
        low = RunwayState(agl=40 * FT, speed=74, gamma=-0.05, on_ground=False)
        fly.decode(neutral_rates(DNp01=290, DNp04=330, DNp07=30), low)
        self.assertGreater(fly.q_cmd, math.radians(1.5))  # flare, from DNp07 only


class EncoderTests(unittest.TestCase):
    def test_all_stimulator_rates_within_0_200(self):
        rng = random.Random(1)
        for fly in (TakeoffFly(StandInBrain()), LandingFly(StandInBrain(), trim_pitch=2.0)):
            for _ in range(500):
                s = RunwayState(x=rng.uniform(-6000, 3000), y=rng.uniform(-50, 50),
                                agl=rng.uniform(0, 600), psi=rng.uniform(-.5, .5),
                                roll=rng.uniform(-.8, .8), pitch=rng.uniform(-.3, .4),
                                gamma=rng.uniform(-.2, .2), speed=rng.uniform(0, 110),
                                yaw_rate=rng.uniform(-.3, .3), on_ground=rng.random() < .5)
                for name, hz in fly.encode(s).items():
                    self.assertTrue(0 <= hz <= 200, (type(fly).__name__, name, hz))

    def test_drift_right_stimulates_left_hs(self):
        fly = TakeoffFly(StandInBrain())
        inputs = fly.encode(RunwayState(y=5.0, speed=30))
        self.assertGreater(inputs['hs_left'], inputs['hs_right'])

    def test_standin_is_labelled(self):
        self.assertIn('NOT', StandInBrain.__doc__)
        self.assertIn('no connectome', StandInBrain().name)


class RunwaySimTests(unittest.TestCase):
    def test_trimmed_approach_holds_glideslope_without_control(self):
        state = trimmed_approach()
        sim = RunwaySim(state, FLAPS30)
        c = AirlinerControls(elevator=trim_elevator(state), throttle=state.spool)
        for _ in range(100):
            sim.step(c, .05)
        self.assertLess(abs(sim.state.glideslope_error()), 0.1)

    def test_bounded_controls_include_brake(self):
        self.assertEqual(AirlinerControls(3, 0, 0, 2, 5).bounded(), AirlinerControls(1, 0, 0, 1, 1))
        with self.assertRaises(ValueError):
            AirlinerControls(brake=math.nan).bounded()


class RunwayProtocolTests(unittest.TestCase):
    def setUp(self):
        self.sink = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sink.bind(('127.0.0.1', 0))
        self.sink.settimeout(1)
        self.bridge = RunwayFlightGear(0, self.sink.getsockname()[1], timeout=.2,
                                       runway=(37.0, -122.0, 90.0))

    def tearDown(self):
        self.bridge.close()
        self.sink.close()

    def test_parse_runway_frame(self):
        # 0.001 deg east of the threshold on a 090 runway: ~89 m down the runway, on centerline.
        s = self.bridge.parse(b'1,37.0,-121.999,0,90,0,0,0,0,1,0\n')
        self.assertAlmostEqual(s.x, 88.8, delta=0.5)
        self.assertAlmostEqual(s.y, 0.0, delta=0.01)
        self.assertTrue(s.on_ground)
        s = self.bridge.parse(b'2,36.9999,-121.999,500,95,0,3,140,-12,0,0\n')
        self.assertAlmostEqual(s.y, 11.1, delta=0.2)   # south of a 090 runway = right of centerline
        self.assertAlmostEqual(s.psi, math.radians(5))
        self.assertAlmostEqual(s.agl, 500 * FT)
        self.assertAlmostEqual(s.speed, 140 * KT)
        self.assertLess(s.gamma, 0)
        self.assertFalse(s.on_ground)

    def test_rejects_malformed(self):
        for packet in [b'1,2,3', b'1,37,-122,0,90,0,0,0,0,2,0', b'1,nan,-122,0,90,0,0,0,0,1,0']:
            with self.assertRaises(ValueError):
                self.bridge.parse(packet)

    def test_send_both_engines_and_brakes(self):
        self.bridge.send(AirlinerControls(.1, -.2, .3, .7, .5), True)
        data, _ = self.sink.recvfrom(8192)
        self.assertEqual([float(v) for v in data.decode().split(',')], [.1, -.2, .3, .7, .7, .5, .5, 1, 1, 1])

    def test_protocol_xml_matches_wire_order(self):
        state = [c.find('name').text for c in ET.parse(PROTOCOLS / 'flybrain-runway-state.xml').iter('chunk')]
        self.assertEqual(state, ['elapsed', 'latitude', 'longitude', 'agl', 'heading', 'roll', 'pitch',
                                 'airspeed', 'climb', 'wow', 'frozen'])
        controls = [c.find('name').text for c in ET.parse(PROTOCOLS / 'flybrain-runway-controls.xml').iter('chunk')]
        self.assertEqual(controls, ['aileron', 'elevator', 'rudder', 'throttle0', 'throttle1',
                                    'brake_left', 'brake_right', 'gear_down', 'frozen', 'frozen_clock'])

    def test_landing_threshold_from_final_start(self):
        # Spawned 3 nm before the threshold of a 090 runway: the first packet is at x = -5556 m.
        bridge = RunwayFlightGear(0, self.sink.getsockname()[1], timeout=.2, ahead_m=3 * 1852.0)
        try:
            s = bridge.parse(b'1,37.0,-122.0,1000,90,0,0,145,-12,0,0\n')
            self.assertAlmostEqual(s.x, -5556, delta=5)
            self.assertAlmostEqual(s.y, 0.0, delta=0.5)
            self.assertAlmostEqual(bridge.runway[1], -122.0 + 5556 / (6371000 * math.cos(math.radians(37))) * 180 / math.pi, places=6)
        finally:
            bridge.close()


class LaunchPhaseTests(unittest.TestCase):
    def args(self, phase, instance=0, fg='/opt/FlightGear'):
        import argparse
        return argparse.Namespace(phase=phase, instance=instance, fg=fg, aircraft='738-flies', extra=[])

    def test_takeoff_and_landing_commands(self):
        from flight_simulator.launch_fg import command, controller_command
        takeoff = command(self.args('takeoff'))
        self.assertIn('--airport=KSFO', takeoff)
        self.assertIn('--runway=28R', takeoff)
        self.assertNotIn('--in-air', takeoff)
        self.assertIn('--generic=socket,out,20,127.0.0.1,5501,udp,flybrain-runway-state', takeoff)
        self.assertIn('--generic=socket,in,20,127.0.0.1,5502,udp,flybrain-runway-controls', takeoff)
        landing = command(self.args('landing', instance=1))
        self.assertIn('--in-air', landing)
        self.assertIn('--offset-distance=3.0', landing)
        self.assertIn('--generic=socket,out,20,127.0.0.1,5511,udp,flybrain-runway-state', landing)
        self.assertIn('--telemetry-port 5511 --control-port 5512', controller_command(self.args('landing', 1)))
        self.assertNotIn('--telemetry-port', controller_command(self.args('takeoff')))

    def test_install_protocols(self):
        import tempfile
        from flight_simulator.launch_fg import install_protocols, RUNWAY_PROTOCOLS
        fg = Path(tempfile.mkdtemp())
        (fg / 'data' / 'Protocol').mkdir(parents=True)
        self.assertIsNone(install_protocols(fg))
        for name in RUNWAY_PROTOCOLS:
            self.assertEqual((fg / 'data' / 'Protocol' / name).read_bytes(), (PROTOCOLS / name).read_bytes())
        self.assertIn('Could not copy', install_protocols(fg / 'missing'))


class NoiseRobustnessTests(unittest.TestCase):
    """The connectome reads 1-2 neurons per readout, so trial-to-trial rates jitter.
    The stand-in with spike-count noise reproduces that (it broke the first landing)."""

    def test_noisy_landings_mostly_succeed(self):
        good = 0
        for seed in range(8):
            r, _ = landing(StandInBrain(noise_seed=seed), y=15.0)
            good += judge('landing', r) and not r['go_around']
        self.assertGreaterEqual(good, 6)

    def test_noisy_takeoffs_succeed(self):
        for seed in range(4):
            r, _ = takeoff(StandInBrain(noise_seed=seed), y=3.0, yaw=0.004)
            self.assertTrue(judge('takeoff', r), (seed, r))

    def test_glideslope_ignored_below_100_ft(self):
        # Near the aim point the angular glideslope error explodes; it must not dive the nose.
        fly = LandingFly(StandInBrain(), trim_pitch=2.0)
        fly.encode(RunwayState(x=-400, agl=120 * FT, speed=74, gamma=-0.05, on_ground=False))
        frozen = fly.flare_pitch_deg
        fly.encode(RunwayState(x=290, agl=30 * FT, speed=74, gamma=-0.05, on_ground=False))
        self.assertEqual(fly.flare_pitch_deg, frozen)

    def test_no_bitter_below_100_ft(self):
        fly = LandingFly(StandInBrain(), trim_pitch=2.0)
        inputs = fly.encode(RunwayState(x=290, agl=30 * FT, speed=60, gamma=-0.05, on_ground=False))
        self.assertEqual(inputs['bitter'], 0.0)


class PlotTests(unittest.TestCase):
    def test_plot_from_run_log(self):
        import tempfile
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            self.skipTest('matplotlib not installed')
        from flight_simulator.plot_run import main as plot_main
        from flight_simulator.takeoff_landing import main as run_main
        d = Path(tempfile.mkdtemp())
        self.assertEqual(run_main(['landing', '--brain', 'standin', '--log', str(d / 'l.csv'),
                                   '--plot', str(d / 'direct.png')]), 0)
        self.assertEqual(plot_main([str(d / 'l.csv')]), 0)
        for png in (d / 'direct.png', d / 'l.png'):
            self.assertEqual(png.read_bytes()[:4], b'\x89PNG')


class AfterHandoverTests(unittest.TestCase):
    """2026-11-14 FlightGear test: the takeoff fly handed over at 1,000 ft, the
    controller exited, FlightGear kept the last controls (rudder -0.2) and the 737
    spiralled into the ground. The fly must keep flying while airborne."""

    def test_hold_keeps_wings_level_and_climbing(self):
        sim = RunwaySim(takeoff_start(y=3.0), FLAPS5, yaw_disturbance=0.004)
        fly = TakeoffFly(StandInBrain(noise_seed=1))
        run_phase(fly, sim, 150)
        self.assertTrue(fly.status.phase.startswith('HANDOVER'))
        fly.hold = True
        start_agl, worst_roll = sim.state.agl, 0.0
        for _ in range(int(60 / 0.05)):
            sim.step(fly.step(sim.state, 0.05), 0.05)
            worst_roll = max(worst_roll, abs(sim.state.roll))
        self.assertLess(math.degrees(worst_roll), 15)
        self.assertGreater(sim.state.agl, start_agl)
        self.assertGreater(len(fly.decisions), 100)  # still deciding after handover

    def test_air_rudder_capped(self):
        fly = TakeoffFly(StandInBrain())
        fly.decode(neutral_rates(DNp15_L=200.0), RunwayState(speed=90, agl=300, on_ground=False))
        self.assertLessEqual(abs(fly.rudder), 0.1)


class SafeExitTests(unittest.TestCase):
    def test_close_centres_surfaces_and_requests_pause(self):
        sink = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sink.bind(('127.0.0.1', 0))
        sink.settimeout(1)
        bridge = RunwayFlightGear(0, sink.getsockname()[1], timeout=.2, runway=(37.0, -122.0, 90.0))
        bridge.send(AirlinerControls(-.08, .04, -.2, 1.0))
        sink.recvfrom(8192)
        self.assertFalse(bridge.close())  # nobody acknowledges in this test
        fields = [float(v) for v in sink.recvfrom(8192)[0].decode().split(',')]
        self.assertEqual(fields[0], 0.0)    # aileron centred
        self.assertEqual(fields[2], 0.0)    # rudder centred
        self.assertEqual(fields[-1], 1.0)   # freeze requested
        sink.close()

    def test_agl_offset_from_parked_aircraft(self):
        bridge = RunwayFlightGear(0, 9, timeout=.2, runway=(37.0, -122.0, 90.0))
        try:
            parked = bridge.parse(b'1,37.0,-122.0,7.95,90,0,0,0,0,1,0\n')
            self.assertAlmostEqual(parked.agl, 0.0)
            flying = bridge.parse(b'2,37.0,-121.999,107.95,90,0,5,150,10,0,0\n')
            self.assertAlmostEqual(flying.agl, 100 * FT)
        finally:
            bridge.rx.close()
            bridge.tx.close()


if __name__ == '__main__':
    unittest.main()
