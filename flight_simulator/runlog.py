"""Per-run logs for simulations, pushed automatically to the `sim-logs` branch.

Every `python -m flight_simulator ...` run creates one folder:

    runs/<UTC time>_<who>_<backend>-<brain>/
        meta.json            args, code commit + dirty files, Python, FlightGear version
        code.diff            uncommitted changes to tracked files (so the run is reproducible)
        console.log          everything the run printed
        airplane.csv         per-step aircraft state + controls (.csv.gz if large)
        fly_activity.csv     every brain decision: looming input, escape output, neuron-group rates
        fly_spikes.jsonl     connectome mode: per brain trial, every neuron that fired + its spike count
        result.json          summary: collision, min clearance, exit code...
        fgfs_warnings.log    FlightGear backend only: WARN/ALERT/Nasal lines from fgfs.log
        feedback.md          summary + your notes

The folder lives in a git worktree of the `sim-logs` branch (`.sim-logs/` in the
repo root, git-ignored), is committed, and pushed to origin. Pushing never
touches `main` or your working tree. If the push fails (offline), the commit
stays local and goes up with the next run or `python -m flight_simulator.runlog push`.

    python -m flight_simulator.runlog list                     # recent runs
    python -m flight_simulator.runlog note "banked too late"   # add feedback to latest run
    python -m flight_simulator.runlog note --run <id> "..."    # ...or to a specific run
    python -m flight_simulator.runlog push                     # retry pending pushes

Opt out for one run with `--no-push` (still logs locally) or `--no-runlog`;
or set FRUITFLY_NO_PUSH=1.
"""
import argparse
import csv
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
BRANCH = 'sim-logs'
RUNS = 'runs'
GZIP_OVER = 5 * 1024 * 1024
DIFF_CAP = 512 * 1024
FG_LINE_CAP = 2000
FG_KEEP = re.compile(r'\[(WARN|ALRT|DEV_WARN|DEV_ALRT|POPUP|MAND)\]|nasal|error', re.I)

BRANCH_README = """# FruitFly simulation logs

Written automatically by `python -m flight_simulator` (see `flight_simulator/runlog.py`
on `main`). One folder per run under `runs/`; open `feedback.md` first.
Add notes with `python -m flight_simulator.runlog note "..."`.
"""


def git(*args, cwd=ROOT, check=True, timeout=60):
    p = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=timeout,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if check and p.returncode:
        raise RuntimeError(f'git {" ".join(args)}: {p.stderr.strip() or p.stdout.strip()}')
    return p.stdout.strip()


def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') or 'unknown'


def run_id(backend, brain, who, when=None):
    when = when or datetime.now(timezone.utc)
    return f'{when:%Y-%m-%dT%H%M%SZ}_{slug(who)}_{backend}-{brain}'


def filter_fg_log(lines, cap=FG_LINE_CAP):
    """Keep FlightGear warnings/alerts/Nasal errors; drop the terrasync/INFO flood."""
    kept = [line.rstrip() for line in lines if FG_KEEP.search(line) and '[INFO]' not in line]
    if len(kept) > cap:
        kept = kept[:cap // 2] + [f'... {len(kept) - cap} lines omitted ...'] + kept[-cap // 2:]
    return kept


def fg_home(telemetry_port):
    """FG_HOME of the instance that sends to this port (see launch_fg.py port scheme)."""
    appdata = Path(os.environ.get('APPDATA', Path.home()))
    instance, rem = divmod(telemetry_port - 5501, 10)
    if rem == 0 and instance > 0:
        return appdata / f'flightgear.org-instance{instance}'
    return Path(os.environ['FG_HOME']) if os.environ.get('FG_HOME') else appdata / 'flightgear.org'


def shared_worktree():
    """The sim-logs checkout of this repo, wherever it is.

    A branch can be checked out in only one worktree, so every worktree/clone of the
    repo on this machine (FruitFly, FruitFly-obst, ...) must write to the same one."""
    path = None
    for line in git('worktree', 'list', '--porcelain', check=False).splitlines():
        if line.startswith('worktree '):
            path = Path(line[len('worktree '):])
        elif line == f'branch refs/heads/{BRANCH}' and path is not None and (path / '.git').exists():
            return path
    return None


def main_root():
    """Root of the main checkout (not a linked worktree); .sim-logs/ lives there."""
    return Path(git('rev-parse', '--path-format=absolute', '--git-common-dir')).parent


def ensure_worktree():
    """Return the sim-logs checkout, creating it (and the branch) if needed."""
    found = shared_worktree()
    if found:
        return found
    # Parallel first runs on a fresh machine would race to create it: serialise.
    common = Path(git('rev-parse', '--path-format=absolute', '--git-common-dir'))
    with _Lock(common / 'fruitfly-sim-logs.lock', timeout=180):
        found = shared_worktree()
        if found:
            return found
        return _create_worktree()


def _create_worktree():
    git('worktree', 'prune', check=False)
    target = main_root() / '.sim-logs'
    git('fetch', '-q', 'origin', BRANCH, check=False, timeout=30)
    local = git('rev-parse', '--verify', '-q', f'refs/heads/{BRANCH}', check=False)
    remote = git('rev-parse', '--verify', '-q', f'refs/remotes/origin/{BRANCH}', check=False)
    if local:
        git('worktree', 'add', '-q', str(target), BRANCH)
    elif remote:
        git('worktree', 'add', '-q', '--track', '-b', BRANCH, str(target), f'origin/{BRANCH}')
    else:
        git('worktree', 'add', '-q', '--orphan', '-b', BRANCH, str(target))
        (target / 'README.md').write_text(BRANCH_README, encoding='utf-8')
        git('add', 'README.md', cwd=target)
        git('commit', '-q', '-m', 'Start sim-logs branch', cwd=target)
    return target


class _Lock:
    """Cross-process lock for the shared sim-logs checkout.

    Several loggers on one machine (parallel FlightGear sessions, controller runs,
    worktrees) commit in the same checkout; git allows one index writer at a time."""

    def __init__(self, path, timeout=120, stale=300):
        self.path, self.timeout, self.stale = Path(path), timeout, stale

    def __enter__(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > self.stale:
                        self.path.unlink(missing_ok=True)   # holder died
                        continue
                except FileNotFoundError:
                    continue
                if time.time() > deadline:
                    raise RuntimeError(f'sim-logs checkout busy ({self.path} held too long)')
                time.sleep(0.2)

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)


def push(message=None, paths=(), quiet=False, attempts=4):
    """Commit the given run folders (if any) and push the branch. Never raises.

    Safe in parallel: on one machine a lock serialises commits and each commit
    contains only its own paths; across machines (teammates pushing at the same
    time) a rejected push is rebased onto the new remote state and retried."""
    say = (lambda *a: None) if quiet else (lambda *a: print(*a, file=sys.__stdout__, flush=True))
    try:
        wt = ensure_worktree()
        if os.environ.get('FRUITFLY_NO_PUSH'):
            # Not even a local commit: the sim-logs checkout is shared by every
            # session on this machine, so a local commit would ride along with
            # someone else's next push. The files stay on disk, untracked.
            say(f'[runlog] FRUITFLY_NO_PUSH set; saved on disk only (not committed): {", ".join(paths)}')
            return True
        sessions = wt / '.sessions'
        sessions.mkdir(exist_ok=True)
        with _Lock(sessions / 'git.lock'):
            if paths:
                git('add', '--', *paths, cwd=wt)
                if git('diff', '--cached', '--name-only', '--', *paths, cwd=wt):
                    git('commit', '-q', '-m', message or 'sim log', '--', *paths, cwd=wt)
            # Files changed after their run was committed (e.g. a late media capture)
            # would make `pull --rebase` refuse and block every push on this machine.
            # Tracked files only exist in finished, committed runs, so commit them too.
            late = git('diff', '--name-only', cwd=wt).splitlines()
            if late:
                runs = sorted({'/'.join(f.split('/')[:2]) for f in late if f.startswith(f'{RUNS}/')})
                git('add', '--', *late, cwd=wt)
                git('commit', '-q', '-m', 'sim log: late files for ' + (', '.join(runs) or 'finished runs'),
                    '--', *late, cwd=wt)
                late_untracked = [f for f in git('ls-files', '--others', '--exclude-standard', '--', *runs,
                                                 cwd=wt).splitlines()] if runs else []
                if late_untracked:   # new files in those same finished runs (e.g. the late .jpg)
                    git('add', '--', *late_untracked, cwd=wt)
                    git('commit', '-q', '-m', 'sim log: late files (new) for ' + ', '.join(runs),
                        '--', *late_untracked, cwd=wt)
            for attempt in range(attempts):
                if git('ls-remote', '--heads', 'origin', BRANCH, cwd=wt, timeout=30):
                    git('pull', '-q', '--rebase', 'origin', BRANCH, cwd=wt, timeout=60)
                try:
                    git('push', '-q', '-u', 'origin', BRANCH, cwd=wt, timeout=90)
                    break
                except RuntimeError as exc:
                    if attempt == attempts - 1 or 'rejected' not in str(exc) and 'fetch first' not in str(exc):
                        raise
                    time.sleep(1 + attempt * 2)   # someone else pushed meanwhile: rebase and retry
        url = git('remote', 'get-url', 'origin', check=False).removesuffix('.git')
        say(f'[runlog] pushed -> {url}/tree/{BRANCH}' if url.startswith('https://github.com')
            else '[runlog] pushed')
        return True
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        say(f'[runlog] push failed ({exc}); log kept locally on the {BRANCH} branch. '
            'Retry: python -m flight_simulator.runlog push')
        return False


class Tee:
    def __init__(self, stream, file):
        self.stream, self.file = stream, file

    def write(self, text):
        self.stream.write(text)
        self.file.write(text)
        return len(text)

    def flush(self):
        self.stream.flush()
        self.file.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def outcome_label(result, code):
    if code in (0,2) and result.get('outcome'):
        return result['outcome']
    return {0:'completed',1:'error',2:'COLLISION' if result.get('collision') else 'failed',
            130:'stopped (Ctrl-C)'}.get(code,f'exit {code}')


class RunLog:
    """Context for one simulation run. Use start(), then finish() in a finally block."""

    def __init__(self, args, argv, auto_push=True):
        self.args, self.argv, self.auto_push = args, list(argv), auto_push
        self.result = None
        self._fly = None
        self._spikes = None
        self.started = time.time()
        who = git('config', 'user.name', check=False) or os.environ.get('USERNAME', 'unknown')
        self.id = run_id(args.backend, args.brain, who)
        self.who = who
        try:
            self.base = ensure_worktree()
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            print('!' * 70 + f'\n[runlog] WARNING: sim-logs checkout unavailable ({exc}).\n'
                  '[runlog] This run is saved to runs/ ONLY and will NOT be pushed.\n' + '!' * 70)
            self.base, self.auto_push = ROOT, False
        (self.base / RUNS).mkdir(parents=True, exist_ok=True)
        for n in range(1, 100):   # same person, same second, same brain: keep runs apart
            candidate = self.id if n == 1 else f'{self.id}-{n}'
            try:
                (self.base / RUNS / candidate).mkdir()
                self.id = candidate
                break
            except FileExistsError:
                continue
        self.dir = self.base / RUNS / self.id
        self._console = open(self.dir / 'console.log', 'w', encoding='utf-8')
        self._saved = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = Tee(sys.stdout, self._console), Tee(sys.stderr, self._console)
        self._write_meta()
        self.control = control_attribution(calling_program(self.argv), self.args)
        self._meta['control'] = self.control
        sessions = active_sessions(self.base)
        if sessions:
            self._meta['fg_sessions'] = sessions
        self._dump('meta.json', self._meta)
        print(f'[runlog] {self.dir}', flush=True)
        print(f"[control] {self.control['label']}\n"
              f"[control]   neurons decide: {self.control['neurons_decide']}\n"
              f"[control]   code decides:   {self.control['code_decides']}\n"
              f"[control]   autopilot:      {self.control['autopilot']}", flush=True)

    def _write_meta(self):
        status = git('status', '--porcelain', check=False).splitlines()
        diff = git('diff', 'HEAD', check=False)
        if diff:
            if len(diff) > DIFF_CAP:
                diff = diff[:DIFF_CAP] + '\n... diff truncated ...\n'
            (self.dir / 'code.diff').write_text(diff + '\n', encoding='utf-8')
        meta = {
            'run_id': self.id, 'who': self.who,
            'started_utc': datetime.fromtimestamp(self.started, timezone.utc).isoformat(),
            'command': 'python -m flight_simulator ' + shlex.join(self.argv),
            'args': {k: v for k, v in vars(self.args).items() if not k.startswith('_')},
            'code': {'commit': git('rev-parse', 'HEAD', check=False),
                     'branch': git('rev-parse', '--abbrev-ref', 'HEAD', check=False),
                     'dirty': [s for s in status if not s.startswith('??')],
                     'untracked': [s[3:] for s in status if s.startswith('??')]},
            'python': sys.version.split()[0],
            'platform': f'{platform.system()} {platform.release()}',
        }
        self._meta = meta
        self._dump('meta.json', meta)

    def _dump(self, name, data):
        (self.dir / name).write_text(json.dumps(data, indent=2, default=str) + '\n', encoding='utf-8')

    def _capture_flightgear(self):
        log = fg_home(self.args.telemetry_port) / 'fgfs.log'
        if not log.exists() or log.stat().st_mtime < self.started - 5:
            return None
        lines = log.read_text(encoding='utf-8', errors='replace').splitlines()
        info = {'fgfs_log': str(log)}
        for line in lines[:200]:
            if m := re.search(r'FlightGear:\s+Version\s+(\S+)', line):
                info['version'] = m.group(1)
            if m := re.search(r'aircraft = (\S+)', line):
                info['aircraft'] = m.group(1)
        kept = filter_fg_log(lines)
        info['warning_lines'] = len(kept)
        (self.dir / 'fgfs_warnings.log').write_text('\n'.join(kept) + '\n', encoding='utf-8')
        return info

    def fly(self, row):
        """Append one fly-activity row (brain inputs/outputs) to fly_activity.csv."""
        if self._fly is None:
            self._fly = open(self.dir / 'fly_activity.csv', 'w', newline='', encoding='utf-8')
            self._fly_writer = csv.DictWriter(self._fly, list(row), extrasaction='ignore')
            self._fly_writer.writeheader()
        self._fly_writer.writerow(row)
        self._fly.flush()
        # Observe (read-only) the brain object of the caller for this trial's spike
        # counts. This deliberately does not touch the pilot code (brain.py /
        # __main__.py belong to the flight-behaviour team): ConnectomeBrain already
        # publishes last_counts after every trial; we only read it.
        try:
            brain = sys._getframe(1).f_locals.get('brain')
        except (AttributeError, ValueError):
            brain = None
        counts = getattr(brain, 'last_counts', None)
        if counts is not None and hasattr(counts, 'nonzero'):
            self._spike_row(row.get('time'), counts, getattr(brain, 'ms', None))

    def _spike_row(self, sim_time, counts, trial_ms):
        fired = counts.nonzero()[0]
        if self._spikes is None:
            self._spikes = open(self.dir / 'fly_spikes.jsonl', 'w', encoding='utf-8')
        self._spikes.write(json.dumps({'time': sim_time, 'ms': trial_ms,
                                       'idx': fired.tolist(), 'count': counts[fired].tolist()},
                                      separators=(',', ':')) + '\n')
        self._spikes.flush()

    def _compress_logs(self):
        for name in ('airplane.csv', 'fly_activity.csv', 'fly_spikes.jsonl'):
            path = self.dir / name
            if path.exists() and path.stat().st_size > GZIP_OVER:
                with open(path, 'rb') as src, gzip.open(str(path) + '.gz', 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                path.unlink()

    def _feedback(self, code, fg):
        r = self.result or {}
        outcome = outcome_label(r, code)
        rows = [('Outcome', outcome), ('Backend / brain', f'{self.args.backend} / {self.args.brain}'),
                ('Elapsed', f"{r.get('elapsed_s', '?')} s"),
                ('Min clearance', f"{r.get('minimum_clearance_m', '?')} m"),
                ('Min altitude', f"{r.get('minimum_altitude_m', '?')} m"),
                ('Avoidance activations', r.get('avoidance_activations', '?')),
                ('Code', f"{self._meta['code']['commit'][:9]} on {self._meta['code']['branch']}"
                         + (' (+ uncommitted, see code.diff)' if self._meta['code']['dirty'] else ''))]
        if fg:
            rows.append(('FlightGear', f"{fg.get('version', '?')}, {fg.get('aircraft', '?')}, "
                                       f"{fg['warning_lines']} warning lines"))
        notes = getattr(self.args, 'note', None)
        c = self.control
        who_flew = ('\n## Who was flying\n\n'
                    f"**{c['label']}**\n\n"
                    f"- Neurons decide: {c['neurons_decide']}\n"
                    f"- Code decides: {c['code_decides']}\n"
                    f"- Airplane autopilot: {c['autopilot']} (actual autopilot state over time is in the "
                    'FlightGear session log)\n')
        text = (f'# {self.id}\n\nRun by {self.who}. Command: `{self._meta["command"]}`\n\n'
                '| | |\n|---|---|\n' + ''.join(f'| {k} | {v} |\n' for k, v in rows)
                + who_flew
                + '\n## Notes\n\n' + (f'- {notes}\n' if notes else '')
                + '\n<!-- add feedback: python -m flight_simulator.runlog note "..." -->\n')
        (self.dir / 'feedback.md').write_text(text, encoding='utf-8')
        return outcome

    def finish(self, code):
        sys.stdout, sys.stderr = self._saved
        self._console.close()
        fg = None
        try:
            fg = self._capture_flightgear() if self.args.backend == 'flightgear' else None
        except OSError as exc:
            print(f'[runlog] could not read fgfs.log: {exc}')
        if fg:
            self._meta['flightgear'] = fg
        self._meta['finished_utc'] = datetime.now(timezone.utc).isoformat()
        self._meta['exit_code'] = code
        self._dump('meta.json', self._meta)
        self._dump('result.json', {**(self.result or {}), 'exit_code': code})
        if self._fly:
            self._fly.close()
        if self._spikes:
            self._spikes.close()
        self._compress_logs()
        outcome = self._feedback(code, fg)
        if self.base == ROOT:
            return
        message = f'sim log: {self.args.backend}/{self.args.brain} {outcome} ({self.who})'
        if self.auto_push:
            push(message, [f'{RUNS}/{self.id}'])
        else:
            # Never commit: the shared sim-logs checkout would push it with the next run.
            print(f'[runlog] --no-push: saved on disk only (not committed): {self.dir}')


def active_sessions(base):
    """FlightGear sessions currently being logged (see session.py lock files)."""
    found = []
    for lock in (Path(base) / '.sessions').glob('*.lock'):
        if not lock.stem.isdigit():          # <fgfs pid>.lock only (git.lock is the push lock)
            continue
        try:
            info = json.loads(lock.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(info, dict):
            found.append({'name': info.get('name'), 'run_id': info.get('run_id')})
    return found


AUTOPILOT_RULE = ('never: the fly does not use the airplane autopilot/autothrottle; '
                  'AutopilotGuard forces it off and stops the run if it cannot')


def control_attribution(program, args):
    """Who controls the airplane in this run, stated plainly for the logs.

    `kind` is one of: FLY_BRAIN (connectome neurons make decisions), NO_FLY_BRAIN
    (code or a table decides; labelled baseline/stand-in). The airplane autopilot is
    never part of a controller (repo rule); the session log records its real state.
    Update this table when a controller changes what it hands to the neurons."""
    brain = getattr(args, 'brain', None)
    phase = getattr(args, 'phase', None)
    if program in ('flight_simulator.takeoff_live', 'flight_simulator.takeoff_landing',
                   'flight_simulator.mission'):
        what = {'flight_simulator.mission': 'full mission (takeoff, circuit, landing)'}.get(program, f'{phase or "takeoff"} ')
        if brain == 'connectome':
            return {'kind': 'FLY_BRAIN', 'label': f'FLY BRAIN (connectome) flying the {what.strip()}',
                    'neurons_decide': 'pitch (jump/rotation, flare), steering and roll through descending-neuron '
                                      'rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9)',
                    'code_decides': 'synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to '
                                    'controls, the behavioural-state gate (standing/flying), a fixed-gain '
                                    'pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, '
                                    'stale-decision rejection, a fixed flare pitch envelope, and phase handover (flies.py)'
                                    + ('; takeoff_live holds the parking brake while the brain calibrates and '
                                       'releases it at the handover' if program == 'flight_simulator.takeoff_live' else ''),
                    'autopilot': AUTOPILOT_RULE}
        return {'kind': 'NO_FLY_BRAIN', 'label': f'NO FLY BRAIN: probe-table stand-in flying the {what.strip()}',
                'neurons_decide': 'nothing (no connectome is simulated in this run)',
                'code_decides': 'everything: a lookup table of DN rates measured earlier from the connectome',
                'autopilot': AUTOPILOT_RULE}
    # obstacle avoidance: python -m flight_simulator
    if brain == 'connectome':
        return {'kind': 'FLY_BRAIN', 'label': 'FLY BRAIN (connectome) decides when to escape; code flies the airplane',
                'neurons_decide': 'escape request: Giant Fibre (DNp01) response to synthetic looming and path cues; training retains looming-only input',
                'code_decides': 'synthetic visual encoding, turn direction (from obstacle geometry), holding altitude, speed and heading, '
                                'and flying the avoidance turn (conventional FlightController)',
                'autopilot': AUTOPILOT_RULE}
    if brain == 'reflex':
        return {'kind': 'NO_FLY_BRAIN', 'label': 'NO FLY BRAIN: reflex baseline (a threshold rule) + conventional controller',
                'neurons_decide': 'nothing (no connectome is simulated in this run)',
                'code_decides': 'everything: escape = looming above a fixed threshold; the conventional '
                                'controller holds altitude/speed/heading and flies the turn',
                'autopilot': AUTOPILOT_RULE}
    if brain == 'silent':
        return {'kind': 'NO_FLY_BRAIN', 'label': 'NO FLY BRAIN: silenced-escape control; conventional controller only',
                'neurons_decide': 'nothing (no connectome; escape disabled)',
                'code_decides': 'everything: the conventional controller holds altitude/speed/heading',
                'autopilot': AUTOPILOT_RULE}
    return {'kind': 'UNKNOWN', 'label': f'UNKNOWN controller ({program}, brain={brain}): add it to control_attribution()',
            'neurons_decide': '?', 'code_decides': '?', 'autopilot': AUTOPILOT_RULE}


def calling_program(argv):
    if argv and argv[0] in ('takeoff_live','mission'):
        return 'flight_simulator.'+argv[0]
    spec = getattr(sys.modules.get('__main__'), '__spec__', None)
    return getattr(spec, 'name', None) or 'flight_simulator.__main__'


def runs_dir():
    return ensure_worktree() / RUNS


def latest_runs(n=10):
    d = runs_dir()
    return sorted((p for p in d.iterdir() if p.is_dir()), reverse=True)[:n] if d.exists() else []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('push', help='push pending log commits')
    ls = sub.add_parser('list', help='show recent runs')
    ls.add_argument('-n', type=int, default=10)
    note = sub.add_parser('note', help='append feedback to a run and push')
    note.add_argument('text')
    note.add_argument('--run', help='run id (default: most recent)')
    a = ap.parse_args(argv)
    if a.cmd == 'push':
        return 0 if push() else 1
    if a.cmd == 'list':
        for p in latest_runs(a.n):
            r = json.loads((p / 'result.json').read_text()) if (p / 'result.json').exists() else {}
            print(f"{p.name}  exit={r.get('exit_code', '?')}  collision={r.get('collision', '?')}")
        return 0
    runs = [runs_dir() / a.run] if a.run else latest_runs(1)
    if not runs or not runs[0].is_dir():
        print('No such run.', file=sys.stderr)
        return 1
    fb = runs[0] / 'feedback.md'
    who = git('config', 'user.name', check=False) or os.environ.get('USERNAME', 'unknown')
    text = fb.read_text(encoding='utf-8') if fb.exists() else f'# {runs[0].name}\n\n## Notes\n'
    marker = '\n<!-- add feedback'
    entry = f'- **{who}** ({datetime.now():%Y-%m-%d %H:%M}): {a.text}\n'
    text = text.replace(marker, entry + marker, 1) if marker in text else text + entry
    fb.write_text(text, encoding='utf-8')
    print(f'Added note to {runs[0].name}')
    return 0 if push(f'feedback on {runs[0].name} ({who})', [f'{RUNS}/{runs[0].name}']) else 1


if __name__ == '__main__':
    sys.exit(main())
