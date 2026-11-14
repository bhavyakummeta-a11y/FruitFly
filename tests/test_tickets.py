"""Ticket board: two agents must never hold the same ticket or overlapping paths."""
from concurrent.futures import ProcessPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import tickets as T  # noqa: E402


def _race_claim(db, tid, agent):
    con = T.connect(db)
    try:
        T.claim(con, tid, agent)
        return agent
    except T.Conflict:
        return None
    finally:
        con.close()


def _race_start(db, agent):
    con = T.connect(db)
    try:
        T.start(con, f'work by {agent}', agent, ['flight_simulator/core.py'])
        return agent
    except T.Conflict:
        return None
    finally:
        con.close()


class Board(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'board.db'
        self.con = T.connect(self.db)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_second_agent_cannot_claim_a_held_ticket(self):
        t = T.new(self.con, 'Tune gains')
        T.claim(self.con, t, 'alice')
        with self.assertRaisesRegex(T.Conflict, 'claimed by alice'):
            T.claim(self.con, t, 'bob')
        T.claim(self.con, t, 'alice')  # re-claim by owner just renews

    def test_overlapping_paths_block_other_tickets(self):
        T.start(self.con, 'Edit sim package', 'alice', ['flight_simulator'])
        with self.assertRaisesRegex(T.Conflict, 'held by alice'):
            T.start(self.con, 'Edit core', 'bob', ['flight_simulator/core.py'])
        other = T.new(self.con, 'Edit core later', ['flight_simulator/core.py/'])
        with self.assertRaises(T.Conflict):
            T.claim(self.con, other, 'bob')
        # disjoint paths and similar-prefix names are fine
        T.start(self.con, 'Docs', 'bob', ['docs/notes', 'flight_simulator_extra.py'])
        self.assertEqual([p for p, _ in T.check(self.con, ['flight_simulator/core.py'], 'bob')],
                         ['flight_simulator/core.py'])
        self.assertEqual(T.check(self.con, ['flight_simulator/core.py'], 'alice'), [])

    def test_whole_repo_claim_blocks_everything(self):
        T.start(self.con, 'Big refactor', 'alice', ['.'])
        with self.assertRaises(T.Conflict):
            T.start(self.con, 'Small fix', 'bob', ['README.md'])

    def test_stale_claim_can_be_taken_over_and_owner_can_renew(self):
        t = T.start(self.con, 'Abandoned', 'alice', ['tickets.py'], lease_min=0.001)
        time.sleep(0.15)
        self.assertEqual(T.state(T.get(self.con, t)), 'stale')
        self.assertEqual(T.check(self.con, ['tickets.py'], 'bob'), [])
        T.claim(self.con, t, 'bob')
        row = T.get(self.con, t)
        self.assertEqual((row['agent'], T.state(row)), ('bob', 'claimed'))
        actions = [e['action'] for e in self.con.execute('SELECT action FROM events WHERE ticket=?', (t,))]
        self.assertIn('takeover', actions)

    def test_release_and_done_require_ownership_unless_forced(self):
        t = T.start(self.con, 'Mine', 'alice')
        with self.assertRaises(T.Conflict):
            T.release(self.con, t, 'bob')
        T.release(self.con, t, 'bob', force=True)
        self.assertEqual(T.get(self.con, t)['status'], 'open')
        T.claim(self.con, t, 'bob')
        T.release(self.con, t, 'bob', note='shipped', done=True)
        self.assertEqual(T.get(self.con, t)['status'], 'done')
        self.assertIn('shipped', T.get(self.con, t)['notes'])
        with self.assertRaises(T.Conflict):
            T.claim(self.con, t, 'carol')

    def test_agent_name_required(self):
        t = T.new(self.con, 'x')
        for bad in (None, '', '  '):
            with self.assertRaises(ValueError):
                T.claim(self.con, t, bad)

    def test_parallel_processes_exactly_one_winner(self):
        t = T.new(self.con, 'Contested')
        agents = [f'agent{i}' for i in range(8)]
        with ProcessPoolExecutor(8) as pool:
            winners = [w for w in pool.map(_race_claim, [str(self.db)] * 8, [t] * 8, agents) if w]
        self.assertEqual(len(winners), 1, winners)
        self.assertEqual(T.get(self.con, t)['agent'], winners[0])
        with ProcessPoolExecutor(8) as pool:
            started = [w for w in pool.map(_race_start, [str(self.db)] * 8, [f'b{i}' for i in range(8)]) if w]
        self.assertEqual(len(started), 1, started)

    def test_default_board_is_shared_outside_any_checkout(self):
        """Every checkout/worktree must hit the same board, so it can't live in the repo."""
        self.assertFalse(T.DEFAULT_DB.resolve().is_relative_to(ROOT.resolve()), T.DEFAULT_DB)
        t = T.start(self.con, 'Where am I', 'alice')
        self.assertEqual(T.get(self.con, t)['site'], T._where())
        self.assertIn('@', T._where())

    def test_cli_exit_codes(self):
        env = {**os.environ, 'FRUITFLY_TICKETS_DB': str(self.db)}
        def run(*args, agent='alice'):
            return subprocess.run([sys.executable, str(ROOT / 'tickets.py'), '--agent', agent, *args],
                                  env=env, capture_output=True, text=True)
        r = run('start', 'CLI work', '--paths', 'scenarios')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(run('check', 'scenarios/obstacles.json', agent='bob').returncode, 1)
        self.assertEqual(run('check', 'docs', agent='bob').returncode, 0)
        self.assertEqual(run('start', 'clash', '--paths', 'scenarios', agent='bob').returncode, 3)
        self.assertEqual(run('claim', '999').returncode, 2)
        self.assertIn('CLI work', run('list').stdout)


if __name__ == '__main__':
    unittest.main()
