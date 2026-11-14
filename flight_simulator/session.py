"""FlightGear session log. Every FlightGear session is NAMED, LOGGED and PUSHED.

Rules (they apply to people and to AI agents alike):
  1. Every FlightGear launch carries a session name. The project launchers refuse
     to start without --name; the name travels on fgfs's own command line as
     --prop:string:/fruitfly/session/name=<name>, so it cannot get separated.
  2. Logging starts automatically. A background watchdog (installed to run at logon
     with `install-autostart`) notices ANY fgfs.exe, however it was started, and
     attaches a session logger. FlightGear opened without a name (desktop shortcut,
     a bare fgfs call) is logged as UNNAMED and the live page asks for a name.
  3. When fgfs exits, the session folder is committed and pushed to the sim-logs branch.

    python flightgear/launch.py --name "737 cabin smoke test"
    python -m flight_simulator.launch_fg --instance 1 --name "obstacle course v2"
    python -m flight_simulator.session attach --name "..."   # name/attach a running fgfs now
    python -m flight_simulator.session status                # watchdog + live sessions
    python -m flight_simulator.session install-autostart     # once per machine

Each session writes runs/<UTC time>_<who>_fg-<name>/ on the sim-logs branch:
    airplane.csv        aircraft state + controls, 2 Hz, from the HTTP property API
    fly_activity.csv    fly-side signals in FlightGear (cabin fly activity; more to come)
    events.log          the running log: session events, FlightGear warnings, controller output
    fgfs_warnings.log   WARN/ALERT/Nasal lines from fgfs.log
    meta.json, feedback.md

A live page (http://127.0.0.1:8765/, next free port for more sessions) shows the
airplane and fly-activity charts and the running log while FlightGear is open.
Controller runs (python -m flight_simulator) keep their own folders, are streamed
on the page, and are linked from the session's feedback.md.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
import os
import re
import socket
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import runlog

HERE = Path(__file__).resolve().parent
VIEW = HERE / 'session_view.html'
POLL_S = 0.5
HISTORY = 1200            # points kept for the live charts (10 min at 2 Hz)
NAME_PROP = '/fruitfly/session/name'
WATCHDOG_PORT = 8764      # bound by the watchdog: one per machine
UNNAMED = 'UNNAMED'

# column -> (property path, scale)
AIRPLANE = {
    'sim_time_s': ('/sim/time/elapsed-sec', 1),
    'lat_deg': ('/position/latitude-deg', 1),
    'lon_deg': ('/position/longitude-deg', 1),
    'alt_ft': ('/position/altitude-ft', 1),
    'agl_ft': ('/position/altitude-agl-ft', 1),
    'ias_kt': ('/velocities/airspeed-kt', 1),
    'vs_fpm': ('/velocities/vertical-speed-fps', 60),
    'heading_deg': ('/orientation/heading-deg', 1),
    'pitch_deg': ('/orientation/pitch-deg', 1),
    'roll_deg': ('/orientation/roll-deg', 1),
    'aileron': ('/controls/flight/aileron', 1),
    'elevator': ('/controls/flight/elevator', 1),
    'rudder': ('/controls/flight/rudder', 1),
    'flaps': ('/controls/flight/flaps', 1),
    'throttle': ('/controls/engines/engine[0]/throttle', 1),
    'gear_down': ('/controls/gear/gear-down', 1),
    'paused': ('/sim/freeze/clock', 1),
}
FLY = {'cabin_activity': ('/fruitfly/passengers/activity', 1)}


class Process:
    """Watch a pid without signalling it (os.kill(pid, 0) is Ctrl-C on Windows)."""

    def __init__(self, pid):
        self.pid, self.code = pid, None
        if os.name == 'nt':
            import ctypes
            self.k = ctypes.windll.kernel32
            self.h = self.k.OpenProcess(0x1000 | 0x00100000, False, pid)  # query + synchronize
            if not self.h:
                raise ProcessLookupError(f'No process {pid}')

    def alive(self):
        if os.name != 'nt':
            # macOS has no /proc. Signal 0 probes existence on POSIX without
            # sending a signal; never use this branch on Windows.
            try:
                os.kill(self.pid, 0)
            except ProcessLookupError:
                return False
            except PermissionError:
                return True
            return True
        import ctypes
        code = ctypes.c_ulong()
        self.k.GetExitCodeProcess(self.h, ctypes.byref(code))
        if code.value == 259:  # STILL_ACTIVE
            return True
        self.code = code.value
        return False


def find_fgfs():
    # CREATE_NO_WINDOW: the watchdog runs windowless and polls every 2 s; without it
    # each tasklist call pops up a new console window.
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq fgfs.exe', '/FO', 'CSV', '/NH'],
                         capture_output=True, text=True,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
    pids = [int(line.split('","')[1]) for line in out.splitlines() if line.startswith('"fgfs.exe"')]
    return pids


def name_arg(name):
    """fgfs argument carrying the session name. Launchers must refuse to start without one."""
    name = (name or '').strip()
    if not name:
        raise SystemExit('A FlightGear session needs a name: --name "what this session is testing"')
    return f'--prop:string:{NAME_PROP}={name}'


def fgfs_cmdline(pid):
    if os.name != 'nt':
        try:
            return Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0', b' ').decode()
        except OSError:
            return ''
    ps = f'(Get-CimInstance Win32_Process -Filter "ProcessId={int(pid)}").CommandLine'
    out = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return out.stdout.strip()


def parse_cmdline(cmd):
    """Session name, ports and aircraft from an fgfs command line."""
    def find(pattern):
        m = re.search(pattern, cmd)
        return m.group(1) if m else None
    name = find(r'--prop:(?:string:)?' + re.escape(NAME_PROP) + r'=(.*?)(?:"|\s--|$)')
    httpd = find(r'--httpd=(\d+)')
    telemetry = find(r'--generic=socket,out,\d+,[^,]*,(\d+),udp')
    return {'name': name.strip() if name and name.strip() else None,
            'httpd': int(httpd) if httpd else None,
            'telemetry_port': int(telemetry) if telemetry else None,
            'aircraft': find(r'--aircraft=(\S+)')}


def sessions_dir():
    d = runlog.ensure_worktree() / '.sessions'
    d.mkdir(exist_ok=True)
    return d


def pid_alive(pid):
    try:
        return Process(int(pid)).alive()
    except (ProcessLookupError, ValueError, TypeError, OSError):
        return False


def read_lock(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def detached(cmd, log_name):
    flags = 0
    if os.name == 'nt':
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    log = open(runlog.ensure_worktree() / log_name, 'a')
    return subprocess.Popen(cmd, cwd=runlog.ROOT, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                            creationflags=flags, close_fds=True)


def spawn(pid, name=None, open_browser=True):
    """Start a session logger for one fgfs pid (no-op if one is already attached)."""
    cmd = [sys.executable, '-m', 'flight_simulator.session', 'watch', '--pid', str(pid)]
    if name:
        cmd += ['--name', name]
    if not open_browser:
        cmd.append('--no-browser')
    detached(cmd, '.watcher.log')


def watchdog_running():
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(('127.0.0.1', WATCHDOG_PORT)) == 0


def ensure_watchdog(quiet=False):
    """Make sure the FlightGear watchdog runs; launchers call this before starting fgfs."""
    if watchdog_running():
        return
    detached([sys.executable, '-m', 'flight_simulator.session', 'watchdog'], '.watchdog.log')
    for _ in range(20):
        if watchdog_running():
            break
        time.sleep(0.25)
    if not quiet:
        print('[session] FlightGear watchdog started: every fgfs session will be logged and pushed.')


def watchdog():
    """Attach a session logger to every fgfs.exe that appears. One per machine."""
    guard = socket.socket()
    try:
        guard.bind(('127.0.0.1', WATCHDOG_PORT))
    except OSError:
        print('watchdog already running')
        return
    guard.listen(8)
    threading.Thread(target=lambda: [guard.accept()[0].close() for _ in iter(int, 1)], daemon=True).start()
    print(f'{datetime.now():%H:%M:%S} watchdog up (pid {os.getpid()})', flush=True)
    spawned = {}
    while True:
        try:
            locks = sessions_dir()
            for pid in find_fgfs():
                info = read_lock(locks / f'{pid}.lock')
                if info and pid_alive(info.get('watcher_pid')):
                    continue
                if time.time() - spawned.get(pid, 0) < 30:
                    continue      # a logger is starting up for it
                spawned[pid] = time.time()
                print(f'{datetime.now():%H:%M:%S} fgfs pid {pid} has no logger; attaching', flush=True)
                spawn(pid)
            for lock in locks.glob('*.lock'):   # loggers that died without cleaning up
                info = read_lock(lock)
                if info and not pid_alive(info.get('watcher_pid')) and not pid_alive(info.get('fgfs_pid')):
                    lock.unlink(missing_ok=True)
        except Exception as exc:  # keep watching no matter what
            print(f'{datetime.now():%H:%M:%S} watchdog error: {exc!r}', flush=True)
        time.sleep(2)


STARTUP = Path(os.environ.get('APPDATA', '')) / 'Microsoft/Windows/Start Menu/Programs/Startup'
SHORTCUT = STARTUP / 'FruitFly FlightGear session logger.lnk'


def install_autostart():
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    alias = Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft/WindowsApps/pythonw.exe'
    target = alias if alias.exists() else pythonw
    ps = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:SC); "
          "$s.TargetPath = $env:TGT; $s.Arguments = '-m flight_simulator.session watchdog'; "
          "$s.WorkingDirectory = $env:WD; $s.WindowStyle = 7; "
          "$s.Description = 'Logs and pushes every FlightGear session (FruitFly)'; $s.Save()")
    env = {**os.environ, 'SC': str(SHORTCUT), 'TGT': str(target), 'WD': str(runlog.main_root())}
    subprocess.run(['powershell', '-NoProfile', '-Command', ps], env=env, check=True)
    print(f'Installed {SHORTCUT}')
    ensure_watchdog()


def status():
    print('watchdog:', 'running' if watchdog_running() else 'NOT running',
          '| autostart:', 'installed' if SHORTCUT.exists() else 'not installed')
    pids = find_fgfs()
    for pid in pids:
        info = read_lock(sessions_dir() / f'{pid}.lock')
        if info and pid_alive(info.get('watcher_pid')):
            print(f"fgfs {pid}: logging as {info.get('name') or UNNAMED!r}  {info.get('url', '')}")
        else:
            print(f'fgfs {pid}: NOT logged yet')
    if not pids:
        print('FlightGear is not running.')


class Session:
    def __init__(self, a):
        self.a = a
        self.proc = Process(a.pid)
        self.started = time.time()
        self.lockfile = self._take_lock()
        info = parse_cmdline(fgfs_cmdline(a.pid))
        self.name = a.name or info['name']
        self.httpd = a.httpd or info['httpd'] or 8080
        telemetry = info['telemetry_port'] or 5501
        self.aircraft = info['aircraft']
        self.who = runlog.git('config', 'user.name', check=False) or os.environ.get('USERNAME', 'unknown')
        self.stamp = datetime.fromtimestamp(self.started, timezone.utc).strftime('%Y-%m-%dT%H%M%SZ')
        self.id = self._run_id()
        base = runlog.ensure_worktree()
        self.base = base
        self.dir = base / runlog.RUNS / self.id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.events = []          # (wall time, source, text)
        self.series = {k: [] for k in ('t', 'alt_ft', 'ias_kt', 'vs_fpm', 'roll_deg', 'cabin_activity')}
        self.latest = {}
        self.connected = False
        self.paused = None
        self.status = 'FlightGear starting'
        self.fg_info, self.fg_kept = {}, []
        self.fg_log = (Path(a.fg_home) if a.fg_home else runlog.fg_home(telemetry)) / 'fgfs.log'
        self.fg_offset = 0
        self.controller = {}      # run id -> {'console_offset', 'fly_offset', 'result'}
        self.fly_ctrl = []        # recent controller fly rows for the page
        self.samples = 0
        self.pushed = False
        self.fly_header = ''
        self.maxima = {'alt_ft': None, 'ias_kt': None}
        self._airplane = open(self.dir / 'airplane.csv', 'w', newline='', encoding='utf-8')
        self._aw = csv.writer(self._airplane)
        self._aw.writerow(['wall_utc', *AIRPLANE])
        self._fly = open(self.dir / 'fly_activity.csv', 'w', newline='', encoding='utf-8')
        self._fw = csv.writer(self._fly)
        self._fw.writerow(['wall_utc', 'sim_time_s', 'source', *FLY])
        self._airplane.flush()
        self._fly.flush()
        self._events = open(self.dir / 'events.log', 'w', encoding='utf-8')
        self.url = ''
        self._write_lock()
        self.event('session', f'Session {self.name or UNNAMED!r} watching fgfs pid {a.pid}'
                   + (f' ({self.aircraft})' if self.aircraft else ''))
        if not self.name:
            self.event('session', 'This session has NO NAME - enter one on the live page '
                                  '(or: python -m flight_simulator.session attach --name "...")')

    # ---- naming + lock -------------------------------------------------
    def _run_id(self):
        return f'{self.stamp}_{runlog.slug(self.who)}_fg-{runlog.slug(self.name) if self.name else UNNAMED}'

    def _take_lock(self):
        """One logger per fgfs process, however many launchers/watchdogs try."""
        path = sessions_dir() / f'{self.a.pid}.lock'
        for _ in range(2):
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return path
            except FileExistsError:
                info = read_lock(path)
                if info is None and time.time() - path.stat().st_mtime < 10:
                    raise SystemExit(f'fgfs {self.a.pid}: another logger is starting')
                if info and pid_alive(info.get('watcher_pid')):
                    if self.a.name and info.get('url'):   # just (re)name the running session
                        req = urllib.request.Request(info['url'] + 'api/name', method='POST',
                                                     data=json.dumps({'name': self.a.name}).encode())
                        urllib.request.urlopen(req, timeout=3).read()
                        raise SystemExit(f"fgfs {self.a.pid}: already logged; renamed to {self.a.name!r}")
                    raise SystemExit(f"fgfs {self.a.pid}: already logged as {info.get('name')!r}")
                path.unlink(missing_ok=True)
        raise SystemExit('could not take the session lock')

    def _write_lock(self):
        data = {'fgfs_pid': self.a.pid, 'watcher_pid': os.getpid(), 'name': self.name,
                'run_id': self.id, 'url': self.url, 'started': self.started}
        self.lockfile.write_text(json.dumps(data), encoding='utf-8')

    def set_name(self, name):
        name = (name or '').strip()[:120]
        if not name:
            return False
        old, self.name = self.name, name
        self._write_lock()
        self.event('session', f'Session named {name!r}' + (f' (was {old!r})' if old else ''))
        return True

    # ---- logging -------------------------------------------------------
    def event(self, source, text):
        now = time.time()
        line = f'{datetime.now():%H:%M:%S} [{source}] {text}'
        with self.lock:
            self.events.append((now, source, text))
            del self.events[:-2000]
        if not self._events.closed:
            self._events.write(line + '\n')
            self._events.flush()

    # ---- FlightGear property API ----------------------------------------
    def _get(self, path):
        url = f'http://127.0.0.1:{self.httpd}/json{path}'
        with urllib.request.urlopen(url, timeout=1.0) as r:
            return json.loads(r.read() or b'{}').get('value')

    def poll(self):
        try:
            row = {k: self._get(p) for k, (p, _) in AIRPLANE.items()}
            fly = {k: self._get(p) for k, (p, _) in FLY.items()}
        except (OSError, ValueError):
            if self.connected:
                self.event('session', 'Property API stopped answering')
                self.connected = False
            return
        if not self.connected:
            self.connected = True
            self.status = 'FlightGear running'
            self.event('session', f'Connected to property API on :{self.httpd}')
        for k, (_, scale) in AIRPLANE.items():
            if isinstance(row[k], (int, float)) and not isinstance(row[k], bool) and scale != 1:
                row[k] = row[k] * scale
        wall = datetime.now(timezone.utc).isoformat(timespec='milliseconds')
        self._aw.writerow([wall, *row.values()])
        self._fw.writerow([wall, row['sim_time_s'], 'flightgear', *fly.values()])
        self.samples += 1
        if self.samples % 10 == 0:
            self._airplane.flush()
            self._fly.flush()
        paused = bool(row.get('paused'))
        if paused != self.paused and self.paused is not None:
            self.event('flightgear', 'Paused' if paused else 'Resumed')
        self.paused = paused
        for k in self.maxima:
            v = row.get(k)
            if isinstance(v, (int, float)):
                self.maxima[k] = v if self.maxima[k] is None else max(self.maxima[k], v)
        with self.lock:
            self.latest = {**row, **fly}
            s = self.series
            s['t'].append(round(time.time() - self.started, 1))
            for k in ('alt_ft', 'ias_kt', 'vs_fpm', 'roll_deg'):
                s[k].append(row.get(k))
            s['cabin_activity'].append(fly.get('cabin_activity'))
            for v in s.values():
                del v[:-HISTORY]

    # ---- fgfs.log -------------------------------------------------------
    def tail_fg_log(self):
        try:
            if not self.fg_log.exists() or self.fg_log.stat().st_mtime < self.started - 120:
                return
            if self.fg_log.stat().st_size < self.fg_offset:
                self.fg_offset = 0
            with open(self.fg_log, 'r', encoding='utf-8', errors='replace') as f:
                f.seek(self.fg_offset)
                chunk = f.read()
                self.fg_offset = f.tell()
        except OSError:
            return
        lines = chunk.splitlines()
        for line in lines:
            if 'version' not in self.fg_info and 'FlightGear:  Version' in line:
                self.fg_info['version'] = line.split('Version', 1)[1].strip()
            if 'aircraft' not in self.fg_info and 'aircraft = ' in line:
                self.fg_info['aircraft'] = line.split('aircraft = ', 1)[1].strip()
        for line in runlog.filter_fg_log(lines, cap=10 ** 9):
            self.fg_kept.append(line)
            text = line.strip()
            # drop the source-file path FlightGear puts in front of every message
            if '.cxx:' in text or '.hxx:' in text:
                head, _, rest = text.partition(' C:\\')
                text = head + ' ' + rest.split(': ', 1)[-1] if rest else text
            self.event('fgfs', text)

    # ---- controller runs (python -m flight_simulator) during this session --
    def tail_controller(self):
        runs = self.base / runlog.RUNS
        for d in runs.iterdir() if runs.exists() else []:
            if d.name == self.id or '_fg-' in d.name or not d.is_dir():   # skip FG sessions
                continue
            st = self.controller.get(d.name)
            if st is None:
                if d.stat().st_mtime < self.started:
                    continue
                st = self.controller[d.name] = {'console': 0, 'fly': 0, 'done': False}
                self.event('controller', f'Run started: {d.name}')
            if st['done']:
                continue
            for name, key in (('console.log', 'console'), ('fly_activity.csv', 'fly')):
                p = d / name
                if not p.exists():
                    continue
                with open(p, 'r', encoding='utf-8', errors='replace') as f:
                    f.seek(st[key])
                    chunk = f.read()
                    st[key] = f.tell()
                if key == 'console':
                    for line in chunk.splitlines():
                        if line.strip():
                            self.event('controller', line.rstrip())
                else:
                    rows = [r for r in chunk.splitlines() if r and not r.startswith('time,')]
                    with self.lock:
                        self.fly_ctrl.extend(rows)
                        del self.fly_ctrl[:-HISTORY]
                        if 'header' not in st:
                            lines = p.read_text(encoding='utf-8').splitlines()
                            if lines:
                                st['header'] = self.fly_header = lines[0]
            if (d / 'result.json').exists():
                st['done'] = True
                st['result'] = json.loads((d / 'result.json').read_text())
                self.event('controller', f"Run finished: {d.name} exit={st['result'].get('exit_code')}")

    # ---- live page ------------------------------------------------------
    def snapshot(self, since):
        with self.lock:
            return {
                'id': self.id, 'name': self.name, 'status': self.status,
                'connected': self.connected, 'paused': self.paused,
                'elapsed_s': round(time.time() - self.started),
                'flightgear': self.fg_info, 'latest': self.latest,
                'series': self.series,
                'fly_header': self.fly_header,
                'fly_controller': self.fly_ctrl[-300:],
                'events': [{'i': i, 't': datetime.fromtimestamp(t).strftime('%H:%M:%S'),
                            'src': s, 'text': x}
                           for i, (t, s, x) in enumerate(self.events) if i >= since][-500:],
                'event_count': len(self.events),
                'dir': str(self.dir),
            }

    def serve(self):
        session = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                if self.path != '/api/name':
                    self.send_error(404)
                    return
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
                    ok = session.set_name(str(body.get('name', '')))
                except ValueError:
                    ok = False
                self.send_response(200 if ok else 400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': ok, 'name': session.name}).encode())

            def do_GET(self):
                if self.path.startswith('/api/state'):
                    since = int(self.path.partition('since=')[2] or 0)
                    body = json.dumps(session.snapshot(since), default=str).encode()
                    ctype = 'application/json'
                elif self.path in ('/', '/index.html'):
                    body, ctype = VIEW.read_bytes(), 'text/html; charset=utf-8'
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Type', ctype)
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)

        for port in range(8765, 8800):
            try:
                self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
                break
            except OSError:
                continue
        else:
            raise OSError('No free port for the live log page')
        self.url = f'http://127.0.0.1:{self.server.server_port}/'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self._write_lock()
        self.event('session', f'Live log page: {self.url}')

    # ---- main loop and wrap-up -----------------------------------------
    def run(self):
        self.serve()
        if not self.a.no_browser:
            webbrowser.open(self.url)
        next_slow = 0
        while self.proc.alive():
            try:
                self.poll()
            except Exception as exc:
                self.event('session', f'poll skipped: {exc!r}')
            if time.time() >= next_slow:
                self._tails()
                next_slow = time.time() + 1
            time.sleep(POLL_S)
        self._tails()
        code = self.proc.code
        crashed = code not in (0, None)
        self.event('session', f'FlightGear exited (code {code})' + (' - crashed or force-closed' if crashed else ''))
        self.status = 'FlightGear closed - saving log'
        try:
            self.finish(code, crashed)
        finally:
            self.lockfile.unlink(missing_ok=True)
        self.status = 'FlightGear closed - log saved' + (' and pushed' if self.pushed else ' locally')
        self.event('session', self.status)
        time.sleep(15)            # let the open page show the final status
        self.server.shutdown()

    def _tails(self):
        """Side streams must never take the logger down; the session log matters more."""
        for tail in (self.tail_fg_log, self.tail_controller):
            try:
                tail()
            except Exception as exc:
                self.event('session', f'{tail.__name__} skipped: {exc!r}')

    def finish(self, code, crashed):
        self._airplane.close()
        self._fly.close()
        self._events.close()
        final = self._run_id()          # the name may have been set during the session
        if final != self.id:
            target = self.dir.with_name(final)
            os.replace(self.dir, target)
            self.id, self.dir = final, target
        (self.dir / 'fgfs_warnings.log').write_text(
            '\n'.join(runlog.filter_fg_log(self.fg_kept)) + '\n', encoding='utf-8')
        duration = round(time.time() - self.started)
        controller = {k: v.get('result') for k, v in self.controller.items()}
        meta = {'run_id': self.id, 'who': self.who, 'kind': 'flightgear-session',
                'name': self.name, 'aircraft': self.aircraft,
                'fgfs_pid': self.a.pid, 'fgfs_exit_code': code,
                'started_utc': datetime.fromtimestamp(self.started, timezone.utc).isoformat(),
                'duration_s': duration, 'httpd_port': self.httpd,
                'flightgear': {**self.fg_info, 'fgfs_log': str(self.fg_log),
                               'warning_lines': len(self.fg_kept)},
                'airplane_samples': self.samples, 'controller_runs': controller,
                'code': {'commit': runlog.git('rev-parse', 'HEAD', check=False),
                         'branch': runlog.git('rev-parse', '--abbrev-ref', 'HEAD', check=False)}}
        (self.dir / 'meta.json').write_text(json.dumps(meta, indent=2, default=str) + '\n', encoding='utf-8')
        outcome = 'FlightGear crashed or was force-closed' if crashed else 'closed normally'
        rows = [('Outcome', f'{outcome} (exit {code})'),
                ('Duration', f'{duration // 60} min {duration % 60} s'),
                ('FlightGear', f"{self.fg_info.get('version', '?')}, {self.fg_info.get('aircraft', '?')}"),
                ('Airplane samples', f'{self.samples} at {1 / POLL_S:g} Hz'
                                     + ('' if self.samples else ' (property API never answered: launched without --httpd?)')),
                ('Max altitude / IAS', f"{self.maxima['alt_ft'] and round(self.maxima['alt_ft'])} ft / "
                                       f"{self.maxima['ias_kt'] and round(self.maxima['ias_kt'])} kt"),
                ('FlightGear warnings', f'{len(self.fg_kept)} lines (fgfs_warnings.log)'),
                ('Controller runs', ', '.join(f'[{k}](../{k}/feedback.md)' for k in controller) or 'none')]
        title = self.name or 'UNNAMED SESSION'
        text = (f'# {title}\n\n`{self.id}`, FlightGear session by {self.who}.\n\n'
                + ('' if self.name else '> **This session was never named.** Name sessions with '
                   '`--name` on the launcher or on the live page.\n\n')
                + '| | |\n|---|---|\n' + ''.join(f'| {k} | {v} |\n' for k, v in rows)
                + '\n## Notes\n\n<!-- add feedback: python -m flight_simulator.runlog note "..." -->\n')
        (self.dir / 'feedback.md').write_text(text, encoding='utf-8')
        message = f'sim log: FlightGear session "{title}" {outcome}, {duration // 60} min ({self.who})'
        self.pushed = runlog.push(message, [f'{runlog.RUNS}/{self.id}'])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    w = sub.add_parser('watch', help='(internal) log one fgfs process until it exits')
    w.add_argument('--pid', type=int, required=True)
    w.add_argument('--name')
    w.add_argument('--httpd', type=int, help='default: from the fgfs command line, else 8080')
    w.add_argument('--fg-home', help='FlightGear home holding fgfs.log')
    w.add_argument('--no-browser', action='store_true')
    at = sub.add_parser('attach', help='log (or name) an already running fgfs now')
    at.add_argument('--pid', type=int)
    at.add_argument('--name')
    at.add_argument('--no-browser', action='store_true')
    sub.add_parser('watchdog', help='(internal) attach a logger to every fgfs that appears')
    sub.add_parser('ensure-watchdog', help='start the watchdog if it is not running')
    sub.add_parser('install-autostart', help='run the watchdog at every Windows logon')
    sub.add_parser('status', help='watchdog state and which FlightGear sessions are logged')
    a = ap.parse_args(argv)
    if a.cmd == 'watch':
        Session(a).run()
    elif a.cmd == 'attach':
        pids = [a.pid] if a.pid else find_fgfs()
        if len(pids) != 1:
            sys.exit(f'Found {len(pids)} fgfs.exe processes; pass --pid.' if pids else 'FlightGear is not running.')
        ensure_watchdog(quiet=True)
        info = read_lock(sessions_dir() / f'{pids[0]}.lock')
        if info and pid_alive(info.get('watcher_pid')):
            if a.name:
                req = urllib.request.Request(info['url'] + 'api/name', method='POST',
                                             data=json.dumps({'name': a.name}).encode())
                urllib.request.urlopen(req, timeout=3).read()
                print(f'Session renamed to {a.name!r}. Live page: {info["url"]}')
            else:
                print(f"Already logged as {info.get('name') or UNNAMED!r}. Live page: {info.get('url')}")
        else:
            spawn(pids[0], a.name, not a.no_browser)
            print('Session logger attached; live page opening.')
    elif a.cmd == 'watchdog':
        watchdog()
    elif a.cmd == 'ensure-watchdog':
        ensure_watchdog()
    elif a.cmd == 'install-autostart':
        install_autostart()
    elif a.cmd == 'status':
        status()
    return 0


if __name__ == '__main__':
    sys.exit(main())
