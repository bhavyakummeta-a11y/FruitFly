import math
from pathlib import Path
import socket
import threading
import unittest
import xml.etree.ElementTree as ET

from flight_simulator.core import State, Controls, Obstacle, sense, FlightController, DemoSimulator
from flight_simulator.brain import ReflexBrain, SilentBrain
from flight_simulator.flightgear import FlightGear
from flight_simulator.__main__ import load_obstacles, ROOT


class FlightTests(unittest.TestCase):
    def trial(self, brain, state=None, seconds=180):
        sim = DemoSimulator(state)
        controller = FlightController()
        obstacles = load_obstacles(ROOT / 'scenarios/obstacles.json')
        minimum = math.inf
        next_brain, escape = 0, 0
        max_alt_error = 0
        for _ in range(int(seconds / .05)):
            s = sim.state
            stimulus = sense(s, obstacles)
            if s.time >= next_brain:
                escape = brain.escape(stimulus.looming_hz)
                next_brain = s.time + .5
            controls = controller.update(s, stimulus, escape)
            sim.step(controls, .05)
            minimum = min(minimum, *(o.clearance(s) for o in obstacles))
            max_alt_error = max(max_alt_error, abs(s.altitude - 900))
        return sim.state, minimum, max_alt_error, controller.activations

    def test_three_minute_avoidance_and_silenced_ablation(self):
        state, clearance, error, activations = self.trial(ReflexBrain())
        self.assertGreater(clearance, 150)
        self.assertLess(error, 10)
        self.assertGreater(state.north, 7500)
        self.assertGreater(activations, 0)
        self.assertLess(self.trial(SilentBrain())[1], 0)

    def test_recovers_from_initial_disturbance(self):
        state, clearance, _, _ = self.trial(ReflexBrain(), State(altitude=930, roll=.15, pitch=.04, speed=47))
        self.assertGreater(clearance, 0)
        self.assertAlmostEqual(state.altitude, 900, delta=2)
        self.assertAlmostEqual(state.speed, 50, delta=1)
        self.assertAlmostEqual(state.roll, 0, delta=.02)

    def test_bearing_and_vertical_filter(self):
        self.assertEqual(sense(State(), [Obstacle('right', 50, 500, 100)]).turn, -1)
        self.assertEqual(sense(State(), [Obstacle('left', -50, 500, 100)]).turn, 1)
        self.assertEqual(sense(State(), [Obstacle('behind', 0, -500, 100)]).looming_hz, 0)
        self.assertEqual(sense(State(), [Obstacle('below', 0, 500, 100, 0, 500)]).looming_hz, 0)

    def test_escape_is_required_for_avoidance(self):
        c = FlightController()
        s = State()
        stimulus = sense(s, [Obstacle('ahead', 0, 400, 100)])
        c.update(s, stimulus, 0)
        self.assertEqual(c.phase, 'CRUISE')
        s.time = .05
        self.assertGreater(c.update(s, stimulus, 1).aileron, 0)
        self.assertEqual(c.phase, 'AVOID')
        s.time = 20
        s.north = 1000
        c.update(s, sense(s, []), 0)
        self.assertEqual(c.phase, 'CRUISE')

    def test_persistent_escape_cannot_accumulate_full_turns(self):
        sim = DemoSimulator()
        controller = FlightController()
        obstacle = Obstacle('ahead', 0, 1300, 150)
        stimulus = sense(sim.state, [obstacle])
        headings = []
        for _ in range(3600):
            s = sim.state
            controls = controller.update(s, stimulus, 100)
            sim.step(controls, .05)
            headings.append(abs(s.heading))
        self.assertLess(max(headings), math.radians(40))
        self.assertGreater(sim.state.north, 7500)
        self.assertEqual(controller.activations, 1)
        self.assertAlmostEqual(sim.state.heading, 0, delta=.01)

    def test_no_forward_progress_stops_instead_of_circling(self):
        controller = FlightController()
        s = State()
        stimulus = sense(s, [Obstacle('ahead', 0, 400, 100)])
        controller.update(s, stimulus, 100)
        s.time = 91
        with self.assertRaisesRegex(RuntimeError, 'forward progress'):
            controller.update(s, stimulus, 100)

    def test_commands_bounded_and_finite(self):
        self.assertEqual(Controls(8, -4, 2, 3).bounded(), Controls(1, -1, 1, 1))
        with self.assertRaises(ValueError):
            Controls(throttle=math.nan).bounded()


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.sink = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sink.bind(('127.0.0.1', 0))
        self.sink.settimeout(1)
        self.bridge = FlightGear(0, self.sink.getsockname()[1], timeout=.2)

    def tearDown(self):
        self.bridge.close()
        self.sink.close()

    def test_parse_units_and_pause_time(self):
        a = self.bridge.parse(b'10,37,-122,3000,90,10,2,100,5,0\n')
        self.assertAlmostEqual(a.altitude, 914.4)
        self.assertAlmostEqual(a.speed, 51.4444)
        self.assertAlmostEqual(a.heading, math.pi / 2)
        b = self.bridge.parse(b'10.05,37,-121.999,3000,90,11,2,100,5,0\n')
        self.assertGreater(b.east, 80)
        self.assertAlmostEqual(b.roll_rate, math.radians(20))
        self.bridge.parse(b'10.1,37,-121.999,3000,90,11,2,100,5,1\n')
        c = self.bridge.parse(b'40.1,37,-121.999,3000,90,11,2,100,5,1\n')
        self.assertAlmostEqual(c.time, .05)

    def test_reject_malformed_and_clock_reset(self):
        for packet in [b'1,2', b'1,nan,0,3000,0,0,0,100,0,0', b'1,91,0,3000,0,0,0,100,0,0']:
            with self.assertRaises(ValueError):
                self.bridge.parse(packet)
        self.bridge.parse(b'10,37,-122,3000,0,0,0,100,0,0')
        with self.assertRaises(ValueError):
            self.bridge.parse(b'9,37,-122,3000,0,0,0,100,0,0')

    def test_actual_udp_command_and_telemetry(self):
        self.bridge.send(Controls(.1, -.2, .3, .7), True)
        data, _ = self.sink.recvfrom(8192)
        self.assertEqual([float(v) for v in data.decode().split(',')], [.1, -.2, .3, .7, 1])
        self.sink.sendto(b'1,37,-122,3000,0,0,0,100,0,0\n', self.bridge.rx.getsockname())
        self.assertAlmostEqual(self.bridge.read().altitude, 914.4)

    def test_queued_telemetry_uses_latest_state(self):
        for clock in [1, 2, 3]:
            self.sink.sendto(f'{clock},37,-122,3000,0,0,0,100,0,0\n'.encode(), self.bridge.rx.getsockname())
        self.bridge.read()
        self.assertEqual(self.bridge.previous_clock, 3)

    def test_twin_engine_protocol_drives_both_engines(self):
        self.bridge.engines = 2
        self.bridge.send(Controls(throttle=.72))
        data, _ = self.sink.recvfrom(8192)
        self.assertEqual([float(v) for v in data.decode().split(',')], [0, 0, 0, .72, .72, 0])
        chunks = ET.parse(ROOT / 'flight_simulator/protocols/flybrain-controls-twin.xml').findall('./generic/input/chunk')
        self.assertEqual(chunks[4].findtext('node'), '/controls/engines/engine[1]/throttle')
        self.assertEqual(len(chunks), 6)

    def test_freeze_requires_ack(self):
        def reply():
            self.sink.recvfrom(8192)
            self.sink.sendto(b'1,37,-122,3000,0,0,0,100,0,1\n', self.bridge.rx.getsockname())
        worker = threading.Thread(target=reply)
        worker.start()
        self.bridge.freeze(True)
        worker.join(timeout=1)
        self.assertTrue(self.bridge.frozen)
        with self.assertRaises(TimeoutError):
            self.bridge.freeze(False)

    def test_xml_matches_wire_order(self):
        root = ROOT / 'flight_simulator/protocols'
        output = ET.parse(root / 'flybrain-state.xml').findall('./generic/output/chunk')
        inputs = ET.parse(root / 'flybrain-controls.xml').findall('./generic/input/chunk')
        self.assertEqual([x.findtext('name') for x in output],
                         ['elapsed', 'latitude', 'longitude', 'altitude', 'heading', 'roll', 'pitch', 'airspeed', 'climb', 'frozen'])
        self.assertEqual([x.findtext('name') for x in inputs],
                         ['aileron', 'elevator', 'rudder', 'throttle', 'frozen'])



class RunLogHelpers(unittest.TestCase):
    """Pure helpers only; nothing here touches git or the network."""

    def test_run_id_is_sortable_and_safe(self):
        from datetime import datetime, timezone
        from flight_simulator.runlog import run_id
        rid = run_id('flightgear', 'reflex', 'Ada Lovelace!', datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
        self.assertEqual(rid, '2026-01-02T030405Z_ada-lovelace_flightgear-reflex')

    def test_fg_log_filter_drops_info_keeps_problems(self):
        from flight_simulator.runlog import filter_fg_log
        lines = ['1.0 [INFO]:terrasync Removing dirindex.txt',
                 '2.0 [WARN]:aircraft missing state node for:cruise',
                 '3.0 [ALRT]:nasal Nasal runtime error: nil used in numeric context']
        self.assertEqual(filter_fg_log(lines), lines[1:])
        self.assertEqual(len(filter_fg_log(['[WARN] x'] * 50, cap=10)), 11)

    def test_fg_home_follows_instance_ports(self):
        from flight_simulator.runlog import fg_home
        self.assertTrue(str(fg_home(5511)).endswith('flightgear.org-instance1'))
        self.assertFalse(str(fg_home(5501)).endswith('instance0'))


if __name__ == '__main__':
    unittest.main()
