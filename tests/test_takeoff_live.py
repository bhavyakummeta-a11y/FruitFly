import os
import shutil
import unittest

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

    def test_fly_row_names_match_brain_page(self):
        row = takeoff_live.fly_row({'time': 1.0, 'phase': 'ROLL', 'in_sugar': 200, 'dn_MN9': 65, 'x': 3})
        self.assertEqual(row, {'time': 1.0, 'phase': 'ROLL', 'in_sugar_hz': 200, 'MN9_hz': 65})


if __name__ == '__main__':
    unittest.main()
