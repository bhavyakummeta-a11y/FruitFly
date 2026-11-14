"""One FlightGear at a time on this machine; later launches wait in a queue.

Two simulators at once compete for the CPU/GPU (the fly brain's decisions slow
down, so measurements are skewed) and move the second session's log/brain pages
to other ports. So the project launchers ask this queue first:

    python -m flight_simulator.launch_fg --phase takeoff --fly --name "..."   # waits its turn
    python flightgear/launch.py --name "..."                                    # waits its turn
    ... --no-wait                       # don't queue: exit at once if a sim is running

    python -m flight_simulator.sim_queue status    # what is running, who is waiting

The queue is machine-wide (every checkout and worktree shares it), next to the
ticket board: %LOCALAPPDATA%\\FruitFly\\sim_queue.db. A turn starts when no
fgfs is running (whoever started it) and every earlier request has had its turn;
it ends when that FlightGear exits. Requests from launchers that died while
waiting are dropped automatically.
"""
import argparse
import os
from pathlib import Path
import sqlite3
import sys
import time

POLL_S = 5.0
START_GRACE_S = 120.0  # a turn that just started owns the sim while fgfs is still loading


def db_path():
    base = os.environ.get('LOCALAPPDATA')
    base = Path(base) / 'FruitFly' if base else Path.home() / '.local' / 'share' / 'fruitfly'
    base.mkdir(parents=True, exist_ok=True)
    return base / 'sim_queue.db'


def connect(path=None):
    con = sqlite3.connect(str(path or db_path()), timeout=30, isolation_level=None)
    con.execute('CREATE TABLE IF NOT EXISTS queue (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, '
                'who TEXT, pid INTEGER, created REAL, started REAL, fgfs_pid INTEGER)')
    return con


def pid_alive(pid):
    if not pid:
        return False
    if os.name == 'nt':
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def running_fgfs():
    from .session import find_fgfs
    return find_fgfs()


class SimQueue:
    def __init__(self, path=None, fgfs=running_fgfs, alive=pid_alive, now=time.time):
        self.con, self.fgfs, self.alive, self.now = connect(path), fgfs, alive, now

    def prune(self):
        """Drop finished turns and requests whose launcher died before its turn."""
        for rid, pid, started, fpid in self.con.execute('SELECT id, pid, started, fgfs_pid FROM queue').fetchall():
            if started is None:
                done = not self.alive(pid)
            elif fpid:
                done = not self.alive(fpid)
            else:  # turn started, fgfs pid not reported (yet)
                done = self.now() - started > START_GRACE_S and not self.alive(pid)
            if done:
                self.con.execute('DELETE FROM queue WHERE id = ?', (rid,))

    def request(self, name, who=None, pid=None):
        cur = self.con.execute('INSERT INTO queue (name, who, pid, created) VALUES (?, ?, ?, ?)',
                               (name, who or os.environ.get('FRUITFLY_AGENT') or os.environ.get('USERNAME', ''),
                                pid or os.getpid(), self.now()))
        return cur.lastrowid

    def try_start(self, rid):
        """Start turn `rid` if the sim is free and it is first in line. Returns (started, position, busy_with)."""
        self.con.execute('BEGIN IMMEDIATE')
        try:
            self.prune()
            rows = self.con.execute('SELECT id, name, started, fgfs_pid FROM queue ORDER BY id').fetchall()
            waiting = [r[0] for r in rows if r[2] is None]
            position = waiting.index(rid) + 1 if rid in waiting else 0
            active = [r for r in rows if r[2] is not None and r[0] != rid]
            fgfs = self.fgfs()
            busy = (f'FlightGear running (pid {", ".join(map(str, fgfs))})' if fgfs else
                    f'"{active[0][1]}" is starting FlightGear' if active else None)
            if busy is None and position == 1:
                self.con.execute('UPDATE queue SET started = ? WHERE id = ?', (self.now(), rid))
                self.con.execute('COMMIT')
                return True, 0, None
            self.con.execute('COMMIT')
            return False, position, busy or 'earlier requests are first'
        except BaseException:
            self.con.execute('ROLLBACK')
            raise

    def acquire(self, name, wait=True, timeout=None, out=print, sleep=time.sleep):
        rid = self.request(name)
        deadline = None if timeout is None else self.now() + timeout
        last = None
        try:
            while True:
                started, position, busy = self.try_start(rid)
                if started:
                    return rid
                if not wait:
                    raise SystemExit(f'Not starting FlightGear: {busy}. One simulator at a time '
                                     '(python -m flight_simulator.sim_queue status). Drop --no-wait to queue.')
                msg = f'Queued "{name}": number {position} in line ({busy}). Waiting for the simulator...'
                if msg != last:
                    out(msg, flush=True)
                    last = msg
                if deadline is not None and self.now() > deadline:
                    raise SystemExit(f'Gave up waiting for the simulator after {timeout:.0f} s')
                sleep(POLL_S)
        except BaseException:
            self.con.execute('DELETE FROM queue WHERE id = ? AND started IS NULL', (rid,))
            raise

    def running(self, rid, fgfs_pid):
        self.con.execute('UPDATE queue SET fgfs_pid = ? WHERE id = ?', (fgfs_pid, rid))

    def release(self, rid):
        self.con.execute('DELETE FROM queue WHERE id = ?', (rid,))

    def rows(self):
        self.con.execute('BEGIN IMMEDIATE')
        self.prune()
        self.con.execute('COMMIT')
        return self.con.execute('SELECT id, name, who, created, started, fgfs_pid FROM queue ORDER BY id').fetchall()


def wait_for_turn(name, wait=True):
    """For launchers: block until it's this launch's turn. Returns (queue, ticket id)."""
    q = SimQueue()
    return q, q.acquire(name, wait=wait)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=['status'], nargs='?', default='status')
    ap.parse_args(argv)
    q = SimQueue()
    fgfs = q.fgfs()
    print('FlightGear running: ' + (', '.join(f'pid {p}' for p in fgfs) if fgfs else 'none'))
    rows = q.rows()
    now = time.time()
    if not rows:
        print('Queue: empty')
    for rid, name, who, created, started, fpid in rows:
        state = (f'RUNNING (fgfs {fpid})' if fpid else 'starting') if started else f'waiting {now - created:.0f} s'
        print(f'  #{rid:<4} {state:<22} "{name}"  ({who})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
