"""Real-time rules: FlightGear at 1x (gh #3), no pause per brain trial (gh #4),
envelope breaches are logged, not fatal (gh #5). No FlightGear needed."""
from pathlib import Path
import math
import socket
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from flight_simulator.__main__ import EnvelopeMonitor  # noqa: E402
from flight_simulator.core import FlightController, State  # noqa: E402
from flight_simulator.flies import StandInBrain, TakeoffFly  # noqa: E402
from flight_simulator.flightgear import DecisionWorker, SpeedLock  # noqa: E402
from flight_simulator.runway import takeoff_start  # noqa: E402
from tests.test_no_autopilot import FakeFG  # noqa: E402


class SpeedLockTests(unittest.TestCase):
    def lock(self, props, sticky=(), **kw):
        fg = FakeFG(props, sticky)
        self.addCleanup(fg.server_close)
        self.addCleanup(fg.shutdown)
        lock = SpeedLock(fg.port, **kw)
        self.addCleanup(lock.close)
        return fg, lock

    def test_sets_1x_at_start(self):
        fg, lock = self.lock({'/sim/speed-up': '8'})
        self.assertEqual(float(fg.props['/sim/speed-up']), 1.0)
        self.assertEqual(lock.events, [])

    def test_drift_is_reset_and_recorded(self):
        fg, lock = self.lock({'/sim/speed-up': '1'})
        lock.check(force=True)
        self.assertEqual(lock.events, [])
        fg.props['/sim/speed-up'] = '0.5'
        lock.check()  # rate-limited: not polled yet
        self.assertEqual(fg.props['/sim/speed-up'], '0.5')
        lock.check(force=True)
        self.assertEqual(float(fg.props['/sim/speed-up']), 1.0)
        self.assertEqual([v for _, v in lock.events], ['0.5'])

    def test_fails_loudly_without_telnet_or_if_speed_wont_change(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            free = s.getsockname()[1]
        with self.assertRaisesRegex(RuntimeError, 'Cannot lock FlightGear at 1x'):
            SpeedLock(free, timeout=0.5)

        class Frozen(dict):          # a FlightGear that ignores `set`
            def __setitem__(self, key, value):
                pass
        fg = FakeFG({})
        self.addCleanup(fg.server_close)
        self.addCleanup(fg.shutdown)
        fg.props = Frozen({'/sim/speed-up': '8'})
        with self.assertRaisesRegex(RuntimeError, 'would not go to 1x'):
            SpeedLock(fg.port)


class DecisionWorkerTests(unittest.TestCase):
    def test_slow_brain_never_blocks_and_latency_is_logged(self):
        worker = DecisionWorker(lambda x: (time.sleep(0.3), x * 2)[1])
        t0 = time.monotonic()
        self.assertTrue(worker.submit(10.0, 21))
        self.assertFalse(worker.submit(10.5, 99))      # still busy: nothing started
        self.assertIsNone(worker.poll(10.6))
        self.assertLess(time.monotonic() - t0, 0.2)    # none of that waited for the brain
        while worker.poll(12.5) is None and time.monotonic() - t0 < 5:
            time.sleep(0.02)
        self.assertEqual(len(worker.records), 1)
        rec = worker.records[0]
        self.assertEqual((rec['started'], rec['applied'], rec['latency_s']), (10.0, 12.5, 2.5))
        self.assertGreaterEqual(rec['brain_wall_s'], 0.25)
        self.assertIsNone(worker.poll(13.0))           # handed back once
        self.assertTrue(worker.submit(13.0, 1, missed=5.9))
        self.assertEqual(worker.skipped, 5)
        worker.close()
        self.assertEqual(worker.summary()['applied'], 1)

    def test_result_and_brain_errors_reach_the_loop(self):
        worker = DecisionWorker(lambda x: x + 1)
        worker.submit(0.0, 41)
        worker.close()
        self.assertEqual(worker.poll(0.1)[0], 42)
        worker = DecisionWorker(lambda: 1 / 0)
        worker.submit(0.0)
        worker.close()
        with self.assertRaises(ZeroDivisionError):
            worker.poll(0.1)


class SlowBrain(StandInBrain):
    delay = 0.25

    def run(self, inputs, readouts):
        time.sleep(self.delay)
        return super().run(inputs, readouts)


class FlyInBackground(unittest.TestCase):
    def test_step_does_not_wait_for_the_brain(self):
        fly = TakeoffFly(SlowBrain([]), 0.5)
        worker = fly.run_in_background()
        s = takeoff_start()
        t0 = time.monotonic()
        for i in range(20):                      # 1 s of sim time at 20 Hz
            s.time = i * 0.05
            controls = fly.step(s, 0.05)
        self.assertLess(time.monotonic() - t0, 0.2, 'step() waited for the brain')
        self.assertEqual(fly.decisions, [])      # nothing decided yet: flying on defaults
        self.assertTrue(all(math.isfinite(v) for v in (controls.aileron, controls.elevator, controls.throttle)))
        worker.close()
        s.time = 3.0
        fly.step(s, 0.05)                        # the late decision is applied now
        self.assertEqual(len(fly.decisions), 1)
        self.assertAlmostEqual(worker.records[0]['latency_s'], 3.0)
        worker.close()

    def test_inline_mode_unchanged_without_worker(self):
        fly = TakeoffFly(StandInBrain([]), 0.5)
        s = takeoff_start()
        fly.step(s, 0.05)
        self.assertEqual(len(fly.decisions), 1)


class Envelope(unittest.TestCase):
    def test_breach_is_logged_once_and_run_continues(self):
        env, ctl = EnvelopeMonitor(), FlightController(900.0, 0.0, 50.0)
        self.assertEqual(env.update(State(time=1.0), ctl), [])
        new = env.update(State(time=2.0, roll=math.radians(62)), ctl)   # past 50 deg: no exception
        self.assertEqual([b['kind'] for b in new], ['bank'])
        self.assertEqual(env.update(State(time=2.1, roll=math.radians(70)), ctl), [])  # same breach
        env.update(State(time=3.0), ctl)                                 # recovered
        new = env.update(State(time=4.0, roll=math.radians(-55), altitude=800.0, pitch=math.radians(-30)), ctl)
        self.assertEqual(sorted(b['kind'] for b in new), ['altitude', 'bank', 'pitch'])
        r = env.result()
        self.assertEqual(r['breaches'], 4)
        self.assertEqual((r['first_breach']['time_s'], r['first_breach']['kind']), (2.0, 'bank'))
        self.assertAlmostEqual(r['worst_bank_deg'], 70.0, places=1)
        self.assertAlmostEqual(r['worst_pitch_deg'], 30.0, places=1)
        self.assertAlmostEqual(r['worst_altitude_error_m'], 100.0, places=1)

    def test_no_breach_result(self):
        r = EnvelopeMonitor().result()
        self.assertEqual((r['breaches'], r['first_breach']), (0, None))


class Lint(unittest.TestCase):
    def src(self, name):
        return (ROOT / 'flight_simulator' / name).read_text(encoding='utf-8')

    def test_takeoff_landing_never_pauses_or_slows_the_sim(self):
        src = self.src('takeoff_landing.py')
        for banned in ('.freeze(', '--speed-up', '_set_speed_up'):
            self.assertNotIn(banned, src)
        for needed in ('SpeedLock(', 'speed_lock.check()', 'run_in_background()'):
            self.assertIn(needed, src)

    def test_mission_never_pauses_for_a_trial_or_handover(self):
        src=self.src('mission.py')
        self.assertNotIn('.freeze(',src)
        for needed in ('SpeedLock(', 'speed_lock.check()', 'run_in_background()', 'prepare_realtime()'):
            self.assertIn(needed,src)

    def test_cruise_controller_is_real_time_and_does_not_abort_on_envelope(self):
        src = self.src('__main__.py')
        self.assertNotIn('Flight departed the test envelope', src)
        for needed in ('SpeedLock(', 'speed_lock.check()', 'DecisionWorker(', 'envelope.update('):
            self.assertIn(needed, src)
        # The only per-trial pause left is the training path.
        loop = src[src.index('while args.seconds == 0'):src.index("result = {'backend'")]
        self.assertEqual(loop.count('bridge.freeze(True)'), 2)   # training trial + training collision
        self.assertIn('if worker:', loop)

    def test_launcher_has_no_speed_or_pause_option(self):
        src = self.src('launch_fg.py')
        for banned in ("'--speed'", '--no-smooth', '--speed-up'):
            self.assertNotIn(banned, src)


if __name__ == '__main__':
    unittest.main()
