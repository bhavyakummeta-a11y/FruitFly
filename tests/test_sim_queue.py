import tempfile
import unittest
from pathlib import Path

from flight_simulator.sim_queue import SimQueue, START_GRACE_S


class World:
    """Fake process table and clock."""
    def __init__(self):
        self.fgfs, self.alive_pids, self.t = [], set(), 1000.0

    def queue(self, path):
        return SimQueue(path, fgfs=lambda: list(self.fgfs), alive=lambda p: p in self.alive_pids,
                        now=lambda: self.t)


class SimQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'q.db'
        self.w = World()
        self.q = self.w.queue(self.path)

    def tearDown(self):
        self.q.con.close()
        self.tmp.cleanup()

    def test_free_sim_starts_at_once(self):
        self.w.alive_pids.add(1)
        rid = self.q.request('a', pid=1)
        self.assertEqual(self.q.try_start(rid)[0], True)

    def test_waits_while_any_fgfs_runs_then_first_in_line_goes(self):
        self.w.alive_pids |= {1, 2, 99}
        self.w.fgfs = [99]                       # someone else's FlightGear
        a, b = self.q.request('a', pid=1), self.q.request('b', pid=2)
        started, pos, busy = self.q.try_start(b)
        self.assertEqual((started, pos), (False, 2))
        self.assertIn('99', busy)
        self.w.fgfs = []
        self.assertFalse(self.q.try_start(b)[0])  # a is first in line
        self.assertTrue(self.q.try_start(a)[0])
        self.q.running(a, 50)
        self.w.alive_pids.add(50)
        self.w.fgfs = [50]
        self.assertFalse(self.q.try_start(b)[0])  # a's sim running
        self.w.fgfs, self.w.alive_pids = [], self.w.alive_pids - {50}
        self.assertTrue(self.q.try_start(b)[0])   # a's sim exited -> b's turn

    def test_turn_owns_sim_while_fgfs_loads(self):
        self.w.alive_pids |= {1, 2}
        a, b = self.q.request('a', pid=1), self.q.request('b', pid=2)
        self.assertTrue(self.q.try_start(a)[0])   # fgfs not yet visible
        self.assertFalse(self.q.try_start(b)[0])
        self.w.alive_pids.discard(1)              # launcher died, never reported fgfs
        self.w.t += START_GRACE_S + 1
        self.assertTrue(self.q.try_start(b)[0])

    def test_dead_waiting_launcher_is_dropped(self):
        self.w.alive_pids |= {2}
        a, b = self.q.request('a', pid=1), self.q.request('b', pid=2)  # pid 1 already dead
        self.assertTrue(self.q.try_start(b)[0])

    def test_no_wait_exits_and_leaves_no_request(self):
        self.w.fgfs = [99]
        with self.assertRaises(SystemExit):
            self.q.acquire('x', wait=False, out=lambda *a, **k: None)
        self.assertEqual(self.q.con.execute('SELECT COUNT(*) FROM queue').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
