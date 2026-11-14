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
        self.assertEqual([float(v) for v in data.decode().split(',')], [.1, -.2, .3, .7, .7, .5, .5, 1, 1])

    def test_protocol_xml_matches_wire_order(self):
        state = [c.find('name').text for c in ET.parse(PROTOCOLS / 'flybrain-runway-state.xml').iter('chunk')]
        self.assertEqual(state, ['elapsed', 'latitude', 'longitude', 'agl', 'heading', 'roll', 'pitch',
                                 'airspeed', 'climb', 'wow', 'frozen'])
        controls = [c.find('name').text for c in ET.parse(PROTOCOLS / 'flybrain-runway-controls.xml').iter('chunk')]
        self.assertEqual(controls, ['aileron', 'elevator', 'rudder', 'throttle0', 'throttle1',
                                    'brake_left', 'brake_right', 'gear_down', 'frozen'])


if __name__ == '__main__':
    unittest.main()
