import os
import shutil
from pathlib import Path
import unittest
from unittest import mock

os.environ['FRUITFLY_NO_PUSH'] = '1'  # never commit test runs to the shared sim-logs branch

from flight_simulator import takeoff_live, takeoff_landing


class TakeoffLiveTests(unittest.TestCase):
    def test_stage_sequence_and_calibration_progress(self):
        seen = []
        real_write = takeoff_live.Stage._write

        def record(stage):
            seen.append(dict(stage.state))
            real_write(stage)
            self.run_dir = stage.runlog.dir
        takeoff_live.Stage._write = record
        saved = takeoff_landing.make_brain, takeoff_landing.run_demo, takeoff_landing.run_flightgear
        try:
            code = takeoff_live.main(['takeoff', '--brain', 'standin', '--backend', 'demo'])
        finally:
            takeoff_live.Stage._write = real_write
            takeoff_landing.make_brain, takeoff_landing.run_demo, takeoff_landing.run_flightgear = saved
            if getattr(self, 'run_dir', None):
                shutil.rmtree(self.run_dir, ignore_errors=True)
        self.assertEqual(code, 0)
        stages = [s['stage'] for s in seen]
        self.assertEqual(stages[0], 'loading')
        self.assertEqual(stages[-2:], ['flying', 'finished'])
        progress = [s['done'] for s in seen if s['stage'] == 'calibrating']
        self.assertEqual(progress, list(range(0, takeoff_live.CALIBRATION_TRIALS + 1)))
        self.assertTrue(all(s['total'] == takeoff_live.CALIBRATION_TRIALS
                            for s in seen if s['stage'] == 'calibrating'))

    def test_fly_activity_keeps_neuron_columns(self):
        import csv
        written = []

        class FakeRunLog:
            def fly(self, row):
                written.append(row)

            def _spike_row(self, *a):
                pass

        class Fly:
            brain = None
        log = takeoff_live.LiveLog.__new__(takeoff_live.LiveLog)
        list.__init__(log)
        log.runlog, log.fly = FakeRunLog(), Fly()
        log._air = open(os.devnull, 'w')
        log._air_writer = csv.DictWriter(log._air, ['time'], extrasaction='ignore')
        log._last_counts = log._last_dn = None
        log.append({'time': 0.0, 'phase': 'ROLL'})                    # before any decision
        log.append({'time': 1.0, 'phase': 'ROLL', 'in_hs_left': 120, 'dn_DNp15_L': 40})
        log._air.close()
        self.assertEqual(len(written), 1)
        self.assertIn('DNp15_L_hz', written[0])
        self.assertIn('in_hs_left_hz', written[0])

    def test_stage_write_survives_locked_file(self):
        import tempfile
        from pathlib import Path
        from unittest import mock

        class FakeRunLog:
            dir = Path(tempfile.mkdtemp())
        stage = takeoff_live.Stage(FakeRunLog())
        calls, real_replace = [], os.replace

        def flaky_replace(src, dst):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError(5, 'Access is denied')
            real_replace(src, dst)
        with mock.patch.object(takeoff_live.os, 'replace', side_effect=flaky_replace),                 mock.patch.object(takeoff_live.time, 'sleep'):
            stage.set('calibrating', done=1)
        self.assertEqual(len(calls), 3)
        self.assertIn('calibrating', (FakeRunLog.dir / 'stage.json').read_text())
        with mock.patch.object(takeoff_live.os, 'replace', side_effect=PermissionError(5, 'denied')),                 mock.patch.object(takeoff_live.time, 'sleep'):
            stage.set('flying')          # gives up quietly, no exception
        shutil.rmtree(FakeRunLog.dir, ignore_errors=True)

    def test_landing_stays_paused_until_autopilot_off(self):
        """Every control packet carries 'paused' until the handover is confirmed."""
        from flight_simulator import flightgear as fg
        sent = []
        saved = fg.RunwayFlightGear.send, fg.AutopilotGuard.wait_off, takeoff_landing.run_flightgear
        try:
            fg.RunwayFlightGear.send = lambda self, c, frozen=False: sent.append(frozen)
            fg.AutopilotGuard.wait_off = lambda self: None

            def fake_run(args, fly, log):     # the order takeoff_landing.run_flightgear uses
                bridge = fg.RunwayFlightGear.__new__(fg.RunwayFlightGear)
                bridge.send(None)             # 'idle + brakes' before the handover
                fg.AutopilotGuard.__new__(fg.AutopilotGuard).wait_off()
                bridge.send(None)             # the fly's first decision
                return {'phase': 'APPROACH'}
            takeoff_landing.run_flightgear = fake_run
            with mock.patch.object(takeoff_live, 'freeze', return_value=True),                     mock.patch.object(takeoff_landing, 'main', lambda argv: takeoff_landing.run_flightgear(None, None, []) and 0):
                takeoff_live.main(['landing', '--brain', 'standin', '--backend', 'flightgear'])
        finally:
            fg.RunwayFlightGear.send, fg.AutopilotGuard.wait_off, takeoff_landing.run_flightgear = saved
        self.assertEqual(sent, [True, False])

    def test_stop_at_ft_is_ours_not_takeoff_landings(self):
        seen = {}
        with mock.patch.object(takeoff_landing, 'main', lambda argv: seen.setdefault('argv', list(argv)) and 0):
            takeoff_live.main(['takeoff', '--brain', 'standin', '--backend', 'demo', '--stop-at-ft', '2000'])
        self.assertEqual(seen['argv'], ['takeoff', '--brain', 'standin', '--backend', 'demo'])
        for d in Path(takeoff_live.__file__).resolve().parents[1].glob('.sim-logs/runs/*demo-standin*'):
            shutil.rmtree(d, ignore_errors=True)

    def test_fly_row_names_match_brain_page(self):
        row = takeoff_live.fly_row({'time': 1.0, 'phase': 'ROLL', 'in_sugar': 200, 'dn_MN9': 65, 'x': 3})
        self.assertEqual(row, {'time': 1.0, 'phase': 'ROLL', 'in_sugar_hz': 200, 'MN9_hz': 65})


if __name__ == '__main__':
    unittest.main()
