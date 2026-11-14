r"""Local ticket board so two agents never work on the same thing at once.

Every agent (Claude session or person) on this machine shares ONE SQLite board,
whichever checkout or worktree it runs from (FruitFly, FruitFly-obst, ...):
%LOCALAPPDATA%\FruitFly\board.db (~/.local/share/fruitfly/board.db elsewhere).
Paths are repo-relative, so they mean the same files in every checkout. Claims are atomic: if two agents claim the
same ticket, or tickets that lock overlapping paths, exactly one wins.
Claims are leases: an agent that stops renewing (crashed/closed session) loses
the claim after --lease minutes (default 60) and the ticket can be taken over.

Identify yourself once per shell with FRUITFLY_AGENT (or pass --agent):

    $env:FRUITFLY_AGENT = "micha-68"           # PowerShell
    export FRUITFLY_AGENT=micha-68             # bash

Typical agent loop:

    python tickets.py list                               # what's taken, what's open
    python tickets.py start "Tune 737 climb gains" --paths flight_simulator/takeoff.py
    python tickets.py check flight_simulator/core.py     # before editing: exit 1 if someone else holds it
    python tickets.py renew                              # every ~30 min while working (any claim/note also renews)
    python tickets.py done 7 --note "gains in b402b8c"   # or: release 7 (back to open)

Other commands: new, claim, note, show, log, board (markdown). `python tickets.py -h`.
"""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parent
def _default_db():
    base = os.environ.get('LOCALAPPDATA')
    base = Path(base) / 'FruitFly' if base else Path.home() / '.local' / 'share' / 'fruitfly'
    return base / 'board.db'


DEFAULT_DB = _default_db()


def _where():
    """'<checkout folder>@<branch>' so the board shows where a claim was made."""
    head = ROOT / '.git'
    try:
        if head.is_file():  # worktree: .git is a 'gitdir: ...' pointer file
            head = Path(head.read_text().split(':', 1)[1].strip())
        ref = (head / 'HEAD').read_text().strip()
        branch = ref.rsplit('/', 1)[-1] if ref.startswith('ref:') else ref[:7]
    except (OSError, IndexError):
        branch = '?'
    return f'{ROOT.name}@{branch}'
DEFAULT_LEASE_MIN = 60.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    paths TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'claimed', 'done')),
    agent TEXT,
    heartbeat REAL,
    lease_min REAL,
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket INTEGER NOT NULL,
    at REAL NOT NULL,
    agent TEXT,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
"""


class Conflict(Exception):
    """Another agent holds the ticket or an overlapping path."""


# ---------------------------------------------------------------- storage

def connect(db=None):
    db = Path(db or os.environ.get('FRUITFLY_TICKETS_DB') or DEFAULT_DB)
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db, timeout=30, isolation_level=None)  # explicit transactions
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.executescript(SCHEMA)
    if 'site' not in {r[1] for r in con.execute('PRAGMA table_info(tickets)')}:
        try:
            con.execute("ALTER TABLE tickets ADD COLUMN site TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # another process added it first
    return con


class tx:
    """BEGIN IMMEDIATE: takes the write lock up front, so check-then-claim is atomic."""
    def __init__(self, con):
        self.con = con

    def __enter__(self):
        self.con.execute('BEGIN IMMEDIATE')
        return self.con

    def __exit__(self, exc_type, *_):
        self.con.execute('ROLLBACK' if exc_type else 'COMMIT')


def _event(con, ticket, agent, action, detail=''):
    con.execute('INSERT INTO events (ticket, at, agent, action, detail) VALUES (?,?,?,?,?)',
                (ticket, time.time(), agent, action, detail))


# ---------------------------------------------------------------- paths

def norm_path(p):
    """Repo-relative POSIX path, no trailing slash. '.' / '' means the whole repo."""
    p = Path(p)
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(ROOT)
        except ValueError:
            raise ValueError(f'{p} is outside the repository')
    s = str(PurePosixPath(*p.parts)) if p.parts else '.'
    s = s.replace('\\', '/').strip('/')
    if s.startswith('./'):
        s = s[2:]
    return s or '.'


def overlaps(a, b):
    if a == '.' or b == '.' or a == b:
        return True
    return a.startswith(b + '/') or b.startswith(a + '/')


# ---------------------------------------------------------------- model

def is_live(row, now=None):
    now = now or time.time()
    return (row['status'] == 'claimed' and row['heartbeat'] is not None
            and now - row['heartbeat'] < 60 * (row['lease_min'] or DEFAULT_LEASE_MIN))


def state(row, now=None):
    if row['status'] == 'claimed' and not is_live(row, now):
        return 'stale'
    return row['status']


def get(con, tid):
    row = con.execute('SELECT * FROM tickets WHERE id=?', (tid,)).fetchone()
    if row is None:
        raise KeyError(f'no ticket #{tid}')
    return row


def holders(con, paths, agent=None, exclude=None):
    """Live claims by OTHER agents whose paths overlap `paths`."""
    out = []
    for row in con.execute("SELECT * FROM tickets WHERE status='claimed'"):
        if row['id'] == exclude or row['agent'] == agent or not is_live(row):
            continue
        hit = [(p, q) for p in paths for q in json.loads(row['paths']) if overlaps(p, q)]
        if hit:
            out.append((row, hit))
    return out


def new(con, title, paths=(), notes='', agent=None):
    if not title.strip():
        raise ValueError('title must not be empty')
    paths = sorted({norm_path(p) for p in paths})
    now = time.time()
    with tx(con):
        cur = con.execute('INSERT INTO tickets (title, notes, paths, created, updated) VALUES (?,?,?,?,?)',
                          (title.strip(), notes, json.dumps(paths), now, now))
        _event(con, cur.lastrowid, agent, 'new', title.strip())
    return cur.lastrowid


def claim(con, tid, agent, lease_min=DEFAULT_LEASE_MIN):
    """Atomically claim ticket `tid` for `agent`. Raises Conflict if anyone else holds it
    (or holds an overlapping path). Re-claiming your own ticket just renews it."""
    _need_agent(agent)
    with tx(con):
        row = get(con, tid)
        if row['status'] == 'done':
            raise Conflict(f'#{tid} is done; open a new ticket instead')
        if is_live(row) and row['agent'] != agent:
            raise Conflict(f"#{tid} is claimed by {row['agent']} ({_age(row['heartbeat'])} since last renew)")
        blocking = holders(con, json.loads(row['paths']), agent, exclude=tid)
        if blocking:
            r, hit = blocking[0]
            raise Conflict(f"#{tid} paths overlap #{r['id']} \"{r['title']}\" held by {r['agent']}: "
                           + ', '.join(f'{p} ~ {q}' for p, q in hit))
        takeover = row['status'] == 'claimed' and row['agent'] != agent
        now = time.time()
        con.execute("UPDATE tickets SET status='claimed', agent=?, heartbeat=?, lease_min=?, updated=?, site=? WHERE id=?",
                    (agent, now, lease_min, now, _where(), tid))
        _event(con, tid, agent, 'takeover' if takeover else 'claim',
               f"from stale {row['agent']}" if takeover else '')
        _renew_all(con, agent, now)


def start(con, title, agent, paths=(), notes='', lease_min=DEFAULT_LEASE_MIN):
    """Create + claim in one step; refuses (and creates nothing) if paths are held."""
    _need_agent(agent)
    paths = sorted({norm_path(p) for p in paths})
    with tx(con):
        blocking = holders(con, paths, agent)
        if blocking:
            r, hit = blocking[0]
            raise Conflict(f"paths held by {r['agent']} on #{r['id']} \"{r['title']}\": "
                           + ', '.join(f'{p} ~ {q}' for p, q in hit))
        now = time.time()
        cur = con.execute("INSERT INTO tickets (title, notes, paths, status, agent, heartbeat, lease_min, created, updated, site)"
                          " VALUES (?,?,?,'claimed',?,?,?,?,?,?)",
                          (title.strip(), notes, json.dumps(paths), agent, now, lease_min, now, now, _where()))
        _event(con, cur.lastrowid, agent, 'start', title.strip())
        _renew_all(con, agent, now)
    return cur.lastrowid


def _own(con, tid, agent):
    row = get(con, tid)
    if row['status'] != 'claimed' or row['agent'] != agent:
        raise Conflict(f"#{tid} is not claimed by {agent} (status {state(row)}, agent {row['agent']})")
    return row


def release(con, tid, agent, note='', done=False, force=False):
    _need_agent(agent)
    with tx(con):
        row = get(con, tid)
        if not force:
            _own(con, tid, agent)
        now = time.time()
        con.execute('UPDATE tickets SET status=?, agent=?, heartbeat=NULL, updated=? WHERE id=?',
                    ('done' if done else 'open', agent if done else None, now, tid))
        if note:
            con.execute('UPDATE tickets SET notes = notes || ? WHERE id=?', (_stamp(agent, note), tid))
        _event(con, tid, agent, ('done' if done else 'release') + (' (forced)' if force else ''),
               note or (f"was {row['agent']}" if force else ''))


def note(con, tid, agent, text):
    _need_agent(agent)
    with tx(con):
        get(con, tid)
        con.execute('UPDATE tickets SET notes = notes || ?, updated=? WHERE id=?',
                    (_stamp(agent, text), time.time(), tid))
        _event(con, tid, agent, 'note', text)
        _renew_all(con, agent, time.time())


def renew(con, agent):
    _need_agent(agent)
    with tx(con):
        return _renew_all(con, agent, time.time())


def _renew_all(con, agent, now):
    """Renew every claim this agent still holds (including ones gone stale, if nobody took them)."""
    return con.execute("UPDATE tickets SET heartbeat=? WHERE status='claimed' AND agent=?", (now, agent)).rowcount


def check(con, paths, agent=None):
    """[(path, ticket row)] for paths a live claim by someone else covers."""
    paths = [norm_path(p) for p in paths]
    return [(p, r) for r, hit in holders(con, paths, agent) for p, _ in hit]


def _need_agent(agent):
    if not agent or not agent.strip():
        raise ValueError('who are you? set FRUITFLY_AGENT or pass --agent NAME')


def _stamp(agent, text):
    return f"[{time.strftime('%Y-%m-%d %H:%M')} {agent or '?'}] {text}\n"


def _age(t):
    s = max(0, time.time() - (t or 0))
    return f'{s / 60:.0f} min' if s < 5400 else f'{s / 3600:.1f} h'


# ---------------------------------------------------------------- CLI

def _fmt(row):
    paths = json.loads(row['paths'])
    who = f" {row['agent']}" if row['agent'] and row['status'] != 'open' else ''
    if who and row['site']:
        who += f" ({row['site']})"
    age = f" ({_age(row['heartbeat'])} ago)" if row['status'] == 'claimed' else ''
    p = f"  [{', '.join(paths)}]" if paths else ''
    return f"#{row['id']:<4} {state(row):7}{who}{age}  {row['title']}{p}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--agent', default=os.environ.get('FRUITFLY_AGENT'), help='your name (default $FRUITFLY_AGENT)')
    ap.add_argument('--db', help=f'board file (default {DEFAULT_DB} or $FRUITFLY_TICKETS_DB)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('list', help='open/claimed tickets (--all includes done)')
    s.add_argument('--all', action='store_true')
    s.add_argument('--mine', action='store_true')
    for name, h in (('new', 'add an open ticket'), ('start', 'add a ticket and claim it now')):
        s = sub.add_parser(name, help=h)
        s.add_argument('title')
        s.add_argument('--paths', nargs='*', default=[], help='files/dirs this work will edit (locked while claimed)')
        s.add_argument('--notes', default='')
        if name == 'start':
            s.add_argument('--lease', type=float, default=DEFAULT_LEASE_MIN, help='minutes without renew before claim goes stale')
    s = sub.add_parser('claim', help='take an open or stale ticket')
    s.add_argument('id', type=int)
    s.add_argument('--lease', type=float, default=DEFAULT_LEASE_MIN)
    sub.add_parser('renew', help='renew all of your claims')
    for name in ('release', 'done'):
        s = sub.add_parser(name, help='give the ticket back' if name == 'release' else 'mark finished')
        s.add_argument('id', type=int)
        s.add_argument('--note', default='')
        s.add_argument('--force', action='store_true', help="act on someone else's claim (ask the user first)")
    s = sub.add_parser('note', help='append a note (also renews your claims)')
    s.add_argument('id', type=int)
    s.add_argument('text')
    s = sub.add_parser('check', help='exit 1 if another agent holds any of these paths')
    s.add_argument('paths', nargs='+')
    s = sub.add_parser('show', help='one ticket with notes and history')
    s.add_argument('id', type=int)
    sub.add_parser('board', help='markdown board of all non-done tickets')
    a = ap.parse_args(argv)

    con = connect(a.db)
    try:
        if a.cmd == 'list':
            q = 'SELECT * FROM tickets' + ('' if a.all else " WHERE status != 'done'") + ' ORDER BY id'
            rows = [r for r in con.execute(q) if not a.mine or r['agent'] == a.agent]
            print('\n'.join(_fmt(r) for r in rows) if rows else '(no tickets)')
        elif a.cmd == 'new':
            print(f'#{new(con, a.title, a.paths, a.notes, a.agent)} opened')
        elif a.cmd == 'start':
            print(f'#{start(con, a.title, a.agent, a.paths, a.notes, a.lease)} claimed by {a.agent}')
        elif a.cmd == 'claim':
            claim(con, a.id, a.agent, a.lease)
            print(f'#{a.id} claimed by {a.agent}')
        elif a.cmd == 'renew':
            print(f'renewed {renew(con, a.agent)} claim(s) for {a.agent}')
        elif a.cmd in ('release', 'done'):
            release(con, a.id, a.agent, a.note, done=a.cmd == 'done', force=a.force)
            print(f"#{a.id} {'done' if a.cmd == 'done' else 'released'}")
        elif a.cmd == 'note':
            note(con, a.id, a.agent, a.text)
            print(f'#{a.id} noted')
        elif a.cmd == 'check':
            hits = check(con, a.paths, a.agent)
            for p, r in hits:
                print(f"HELD {p}: #{r['id']} \"{r['title']}\" by {r['agent']} ({_age(r['heartbeat'])} ago)")
            if not hits:
                print('free')
            return 1 if hits else 0
        elif a.cmd == 'show':
            r = get(con, a.id)
            print(_fmt(r))
            if r['notes']:
                print(r['notes'].rstrip())
            for e in con.execute('SELECT * FROM events WHERE ticket=? ORDER BY id', (a.id,)):
                print(f"  {time.strftime('%m-%d %H:%M', time.localtime(e['at']))} {e['agent'] or '?':12} {e['action']} {e['detail']}")
        elif a.cmd == 'board':
            print('| # | State | Agent | Where | Title | Paths |\n|---|---|---|---|---|---|')
            for r in con.execute("SELECT * FROM tickets WHERE status != 'done' ORDER BY id"):
                print(f"| {r['id']} | {state(r)} | {r['agent'] or ''} | {r['site']} | {r['title']} | {', '.join(json.loads(r['paths']))} |")
        return 0
    except Conflict as exc:
        print(f'BLOCKED: {exc}', file=sys.stderr)
        return 3
    except (KeyError, ValueError) as exc:
        print(f'Error: {exc.args[0] if exc.args else exc}', file=sys.stderr)
        return 2
    finally:
        con.close()


if __name__ == '__main__':
    sys.exit(main())
