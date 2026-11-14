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
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import runlog

HERE = Path(__file__).resolve().parent
VIEW = HERE / 'session_view.html'
PAGES = {'/log': HERE / 'session_log.html', '/brain': HERE / 'session_brain.html'}
POLL_S = 0.5
HISTORY = 1200            # points kept for the live charts (10 min at 2 Hz)
NAME_PROP = '/fruitfly/session/name'
WATCHDOG_PORT = 8764      # bound by the watchdog: one per machine
UNNAMED = 'UNNAMED'
# View buttons on the log page: button label -> FlightGear view name. Pressing one writes
# the name to VIEW_PROP and the aircraft's cabin_show.nas switches the camera. It changes
# only what the person watching sees; the fly pilot never uses the camera.
VIEW_PROP = '/fruitfly/view-request'
VIEW_BUTTONS = {
    'Fly pilot': 'Cockpit: fly pilot',
    'Captain seat': 'Cockpit View',
    'Snack cart': 'Cabin: follow the snack cart',
    'Cabin aisle': 'Cabin: aisle, looking forward',
    'Cabin front': 'Cabin: front, facing the passengers',
    'Outside': 'Chase View',
}

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
    'throttle': ('/controls/engines/engine/throttle', 1),      # engine[0]
    'gear_down': ('/controls/gear/gear-down', 1),
    'paused': ('/sim/freeze/clock', 1),
}
FLY = {'cabin_activity': ('/fruitfly/passengers/activity', 1)}
INPUTS = ('aileron', 'elevator', 'rudder', 'throttle')
CONTROL_LABELS = {
    'AUTOPILOT': 'AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying',
    'UNATTRIBUTED': 'UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) '
                    'is moving the controls; not the fly brain',
    'NOBODY': 'Nobody: no controller running and no control inputs',
}


def _branches(props):
    """Group property paths by parent branch: one HTTP request per branch, not per property."""
    out = {}
    for path in props:
        parent, _, leaf = path.rpartition('/')
        out.setdefault(parent, []).append(leaf)
    return out


def _ap_text(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return '1' if value else '0'
    return str(value)


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
    if os.name != 'nt':   # macOS / Linux teammates
        out = subprocess.run(['pgrep', '-x', 'fgfs'], capture_output=True, text=True).stdout
        return [int(pid) for pid in out.split()]
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
        except OSError:   # macOS has no /proc
            return subprocess.run(['ps', '-o', 'command=', '-p', str(pid)],
                                  capture_output=True, text=True).stdout.strip()
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
            'aircraft': find(r'--aircraft=(\S+)'),
            'graphics': find(r'--prop:string:/fruitfly/graphics=(\w+)'),
            'weather': find(r'--prop:string:/fruitfly/weather=(\w+)')}


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
    """A session lock's contents (dict), or None for anything else (e.g. runlog's git.lock)."""
    try:
        info = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return info if isinstance(info, dict) else None


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


_media = {'next': 0.0, 'warned': False}


def ensure_media_recorder():
    """Screenshots in every session: start media.py's recorder while FlightGear runs.

    Optional add-on (needs Pillow): if it can't start, session logging carries on."""
    if time.time() < _media['next']:
        return
    _media['next'] = time.time() + 10
    try:
        from .media import ensure_recorder
        ensure_recorder(quiet=True)
    except Exception as exc:
        if not _media['warned']:
            print(f'{datetime.now():%H:%M:%S} media recorder unavailable: {exc!r}', flush=True)
            _media['warned'] = True


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
            pids = find_fgfs()
            if pids:
                ensure_media_recorder()
            for pid in pids:
                info = read_lock(locks / f'{pid}.lock')
                if info and pid_alive(info.get('watcher_pid')):
                    continue
                if time.time() - spawned.get(pid, 0) < 30:
                    continue      # a logger is starting up for it
                spawned[pid] = time.time()
                print(f'{datetime.now():%H:%M:%S} fgfs pid {pid} has no logger; attaching', flush=True)
                spawn(pid)
            for lock in locks.glob('*.lock'):   # loggers that died without cleaning up
                if not lock.stem.isdigit():      # <fgfs pid>.lock only; git.lock is runlog's push lock
                    continue
                info = read_lock(lock)
                if isinstance(info, dict) and not pid_alive(info.get('watcher_pid')) and not pid_alive(info.get('fgfs_pid')):
                    lock.unlink(missing_ok=True)
        except Exception as exc:  # keep watching no matter what
            print(f'{datetime.now():%H:%M:%S} watchdog error: {exc!r}', flush=True)
        time.sleep(2)


STARTUP = Path(os.environ.get('APPDATA', '')) / 'Microsoft/Windows/Start Menu/Programs/Startup'
SHORTCUT = STARTUP / 'FruitFly FlightGear session logger.lnk'


def install_autostart():
    if os.name != 'nt':
        raise SystemExit('Autostart is set up for Windows only. On macOS/Linux add this to your '
                         'login items / crontab (@reboot):\n  cd ' + str(runlog.main_root())
                         + ' && python3 -m flight_simulator.session watchdog')
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    alias = Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft/WindowsApps/pythonw.exe'
    target = alias if alias.exists() else pythonw
    ps = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:SC); "
          "$s.TargetPath = $env:TGT; $s.Arguments = '-m flight_simulator.session watchdog'; "
          "$s.WorkingDirectory = $env:WD; $s.WindowStyle = 7; "
          "$s.Description = 'Logs and pushes every FlightGear session (FruitFly)'; $s.Save()")
    env = {**os.environ, 'SC': str(SHORTCUT), 'TGT': str(target), 'WD': str(runlog.main_root())}
    subprocess.run(['powershell', '-NoProfile', '-Command', ps], env=env, check=True,
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
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
        self.graphics = info.get('graphics') or 'not set (FlightGear defaults or launcher settings)'
        self.weather = info.get('weather') or 'not set (FlightGear defaults or launcher settings)'
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
        self.brain_state = {'run': None, 'mode': None, 'active': False}
        self._poll_n = 0
        self.autopilot = []
        self.declared = None             # {'by': 'llm'|'human'|'script', 'who', 'note'} via `session control`
        self.last_inputs, self.inputs_moved = None, 0.0
        self.control = {'who': 'NOBODY', 'label': CONTROL_LABELS['NOBODY'], 'detail': '', 'since': time.time()}
        self.control_log = []            # closed segments
        self.brain_trial = {}
        self.dock = None
        self.maxima = {'alt_ft': None, 'ias_kt': None}
        self._airplane = open(self.dir / 'airplane.csv', 'w', newline='', encoding='utf-8')
        self._aw = csv.writer(self._airplane)
        self._aw.writerow(['wall_utc', *AIRPLANE, 'autopilot', 'in_control'])
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
    def set_view(self, label):
        """Switch the FlightGear camera for whoever is watching (log page button).

        Only names in VIEW_BUTTONS; writes VIEW_PROP, cabin_show.nas does the switch.
        Display only: no flight control, and the fly pilot doesn't see the camera."""
        name = VIEW_BUTTONS.get(label)
        if not name:
            return False
        req = urllib.request.Request(f'http://127.0.0.1:{self.httpd}/json{VIEW_PROP}',
                                     json.dumps({'value': name}).encode(), method='POST')
        try:
            urllib.request.urlopen(req, timeout=2).read()
        except OSError as exc:
            self.event('session', f'View button {label!r}: FlightGear did not answer ({exc})')
            return False
        self.event('session', f'Viewer camera -> {name} (display only; the fly pilot is unaffected)')
        return True

    def _get(self, path):
        url = f'http://127.0.0.1:{self.httpd}/json{path}'
        with urllib.request.urlopen(url, timeout=1.0) as r:
            return json.loads(r.read() or b'{}').get('value')

    def _branch(self, path):
        url = f'http://127.0.0.1:{self.httpd}/json{path}'
        with urllib.request.urlopen(url, timeout=1.0) as r:
            node = json.loads(r.read() or b'{}')
        return {c['name'] + (f"[{c['index']}]" if c.get('index') else ''): c.get('value')
                for c in node.get('children', [])}

    def _read(self, props):
        values = {}
        for parent, leaves in _branches(props).items():
            try:
                kids = self._branch(parent)
            except urllib.error.HTTPError:      # branch absent on this aircraft
                kids = {}
            for leaf in leaves:
                values[f'{parent}/{leaf}'] = kids.get(leaf)
        return values

    def _autopilot(self):
        """Engaged autopilot properties (same list the AutopilotGuard enforces)."""
        from .flightgear import AUTOPILOT_OFF, autopilot_value_engaged
        values = self._read(AUTOPILOT_OFF)
        return [p.rsplit('/', 1)[-1] if '/internal/' in p else p.replace('/autopilot/', '')
                for p, v in values.items() if autopilot_value_engaged(_ap_text(v))]

    def poll(self):
        try:
            raw = self._read([p for p, _ in AIRPLANE.values()] + [p for p, _ in FLY.values()])
            row = {k: raw[p] for k, (p, _) in AIRPLANE.items()}
            fly = {k: raw[p] for k, (p, _) in FLY.items()}
            self._poll_n += 1
            if self._poll_n % 2 == 1:           # autopilot state at 1 Hz
                self.autopilot = self._autopilot()
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
        self._update_control(row)
        self._aw.writerow([wall, *row.values(), ' '.join(self.autopilot) or 'off', self.control['who']])
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

    # ---- who is flying ---------------------------------------------------
    def _active_controller(self):
        for name, st in self.controller.items():
            if not st.get('done') and st.get('control'):
                return name, st['control']
        return None, None

    def _update_control(self, row):
        now = time.time()
        inputs = tuple(row.get(k) for k in INPUTS)
        if self.last_inputs and any(isinstance(a, (int, float)) and isinstance(b, (int, float))
                                    and abs(a - b) > 0.01 for a, b in zip(inputs, self.last_inputs)):
            self.inputs_moved = now
        self.last_inputs = inputs
        run, ctl = self._active_controller()
        if self.autopilot:
            who, label = 'AUTOPILOT', CONTROL_LABELS['AUTOPILOT']
            detail = 'engaged: ' + ', '.join(self.autopilot) + (f'; controller {run} is running' if run else '')
        elif run:
            who, label = ctl.get('kind', 'UNKNOWN'), ctl.get('label', run)
            detail = f"run {run}. Neurons decide: {ctl.get('neurons_decide')}. Code decides: {ctl.get('code_decides')}"
        elif self.declared:
            d = self.declared
            who = d['by'].upper()
            label = {'LLM': 'LLM agent', 'HUMAN': 'Human pilot', 'SCRIPT': 'Script'}.get(who, who) + f": {d['who']}"
            detail = d.get('note') or ''
        elif now - self.inputs_moved < 5:
            who, label, detail = 'UNATTRIBUTED', CONTROL_LABELS['UNATTRIBUTED'], ''
        else:
            who, label, detail = 'NOBODY', CONTROL_LABELS['NOBODY'], ''
        if (who, label) != (self.control['who'], self.control['label']):
            self.control_log.append({**self.control, 'until': now})
            self.control = {'who': who, 'label': label, 'detail': detail, 'since': now}
            self.event('control', f'IN CONTROL: {label}' + (f' ({detail})' if detail else ''))
        else:
            self.control['detail'] = detail

    def declare(self, by, who, note=''):
        if by == 'end':
            if self.declared:
                self.event('control', f"Declared controller ended: {self.declared['by']} {self.declared['who']}")
            self.declared = None
        else:
            self.declared = {'by': by, 'who': who or 'unnamed', 'note': note}
            self.event('control', f'Declared controller: {by} {who}' + (f' ({note})' if note else ''))
        return True

    def control_summary(self):
        segments = self.control_log + [{**self.control, 'until': time.time()}]
        segments = [g for g in segments if g['until'] - g['since'] >= 0.5]
        totals = {}
        for g in segments:
            totals[g['label']] = totals.get(g['label'], 0) + (g['until'] - g['since'])
        return segments, totals

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
                # A teammate's run arriving via git pull is already committed; runs in
                # progress on this machine are not. Only the latter belong to this session.
                if runlog.git('ls-files', '--', f'{runlog.RUNS}/{d.name}', cwd=self.base, check=False):
                    self.controller[d.name] = {'done': True, 'remote': True}
                    continue
                st = self.controller[d.name] = {'console': 0, 'fly': 0, 'spikes': 0, 'done': False}
                self.event('controller', f'Run started: {d.name}')
            if 'brain' not in st and (d / 'meta.json').exists():
                try:
                    meta = json.loads((d / 'meta.json').read_text(encoding='utf-8'))
                    st['control'] = meta.get('control')
                    st['brain'] = meta['args'].get('brain')
                    with self.lock:
                        self.brain_state.update(run=d.name, mode=st['brain'], active=True, stage=None)
                except (OSError, ValueError, KeyError):
                    pass
            if st['done']:
                continue
            # What the fly brain is doing right now (loading / calibrating k of n /
            # flying), written by takeoff_live; the brain page shows it.
            try:
                stage = json.loads((d / 'stage.json').read_text(encoding='utf-8'))
                with self.lock:
                    if self.brain_state.get('run') == d.name:
                        self.brain_state['stage'] = stage
            except (OSError, ValueError):
                pass
            self._tail_spikes(d, st)
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
                with self.lock:
                    if self.brain_state.get('run') == d.name:
                        self.brain_state['active'] = False

    def _tail_spikes(self, d, st):
        """Keep only the newest complete trial from the run's fly_spikes.jsonl."""
        p = d / 'fly_spikes.jsonl'
        if not p.exists():
            return
        with open(p, 'r', encoding='utf-8', errors='replace') as f:
            f.seek(st['spikes'])
            chunk = f.read()
        complete = chunk[:chunk.rfind('\n') + 1]
        st['spikes'] += len(complete.encode('utf-8'))
        lines = [line for line in complete.splitlines() if line.strip()]
        if lines:
            trial = json.loads(lines[-1])
            with self.lock:
                self.brain_trial = {**trial, 'seq': self.brain_trial.get('seq', 0) + len(lines),
                                    'run': d.name}

    # ---- live page ------------------------------------------------------
    def snapshot(self, since):
        with self.lock:
            return {
                'id': self.id, 'name': self.name, 'status': self.status,
                'control': self.control, 'autopilot': self.autopilot,
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
                if self.path not in ('/api/name', '/api/control', '/api/view'):
                    self.send_error(404)
                    return
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
                    if self.path == '/api/view':
                        ok = session.set_view(str(body.get('view', '')))
                    elif self.path == '/api/control':
                        ok = body.get('by') in ('llm', 'human', 'script', 'end') and session.declare(
                            body['by'], str(body.get('who', ''))[:120], str(body.get('note', ''))[:300])
                    else:
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
                elif self.path.startswith('/api/brain_map'):
                    from .brain_map import load
                    text = None
                    for root in {runlog.main_root(), runlog.ROOT}:
                        text = text or load(root / 'data' / 'brain')
                    if text is None:
                        self.send_error(404, 'connectome data not downloaded')
                        return
                    body, ctype = text.encode(), 'application/json'
                elif self.path.startswith('/api/brain'):
                    with session.lock:
                        data = {**session.brain_state, 'trial': session.brain_trial,
                                'control': session.control, 'autopilot': session.autopilot,
                                'name': session.name, 'status': session.status,
                                'fly_header': session.fly_header,
                                'fly_controller': session.fly_ctrl[-120:]}
                    body, ctype = json.dumps(data).encode(), 'application/json'
                elif self.path.startswith('/api/views'):
                    body, ctype = json.dumps({'views': list(VIEW_BUTTONS)}).encode(), 'application/json'
                elif self.path.split('?')[0] in PAGES:
                    html = PAGES[self.path.split('?')[0]].read_text(encoding='utf-8')
                    body = html.replace('{{TAG}}', str(session.a.pid)).encode()
                    ctype = 'text/html; charset=utf-8'
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

        class Server(ThreadingHTTPServer):
            allow_reuse_address = False      # parallel sessions must get distinct ports
            daemon_threads = True

        for port in range(8765, 8800):
            try:
                self.server = Server(('127.0.0.1', port), Handler)
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
            self.open_windows()
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
        # Drop the session lock BEFORE the final commit: the media recorder captures
        # only sessions with a lock, so it stops writing into this folder first.
        self.lockfile.unlink(missing_ok=True)
        time.sleep(10)          # let an in-flight capture (a few seconds) land first
        self.finish(code, crashed)
        self.status = 'FlightGear closed - log saved' + (' and pushed' if self.pushed else ' locally')
        self.event('session', self.status)
        time.sleep(15)            # let the open windows show the final status
        if self.dock:
            self.dock.stop(close=True)
            time.sleep(3)
            import shutil
            shutil.rmtree(sessions_dir() / f'edge-{self.a.pid}', ignore_errors=True)
        self.server.shutdown()

    def open_windows(self):
        """Log window glued under FlightGear, fly-brain window to its right (Windows)."""
        if os.name == 'nt':
            try:
                from .dock import Dock, open_app
                profile = sessions_dir() / f'edge-{self.a.pid}'
                self.dock = Dock(self.a.pid, self.url + 'log', self.url + 'brain', str(self.a.pid),
                                 profile, say=lambda text: self.event('session', text))
                from .dock import EDGE
                if any(Path(p).exists() for p in EDGE):
                    self.dock.start()
                    return
            except Exception as exc:
                self.event('session', f'window docking unavailable: {exc!r}')
        webbrowser.open(self.url)

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
        segments, totals = self.control_summary()
        meta = {'run_id': self.id, 'who': self.who, 'kind': 'flightgear-session',
                'control_timeline': [{'who': g['who'], 'label': g['label'], 'detail': g['detail'],
                                      'from_s': round(g['since'] - self.started, 1),
                                      'to_s': round(g['until'] - self.started, 1)} for g in segments],
                'name': self.name, 'aircraft': self.aircraft, 'graphics': self.graphics,
                'weather': self.weather,
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
                ('Graphics / weather', f'{self.graphics} / {self.weather}'),
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
                + '\n## Who was flying\n\n'
                + '| Who | Time |\n|---|---|\n'
                + ''.join(f'| {label} | {t // 60:.0f} min {t % 60:.0f} s |\n'
                          for label, t in sorted(totals.items(), key=lambda kv: -kv[1]))
                + '\nTimeline (seconds from session start):\n\n'
                + ''.join(f"- {g['since'] - self.started:6.0f} to {g['until'] - self.started:6.0f}: "
                          f"**{g['label']}**" + (f" ({g['detail']})" if g['detail'] else '') + '\n'
                          for g in segments)
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
    ct = sub.add_parser('control', help='declare who is flying when it is not a project controller '
                                        '(required for LLM agents sending control inputs)')
    ct.add_argument('by', choices=['llm', 'human', 'script', 'end'])
    ct.add_argument('--who', default='', help='e.g. the Claude session name')
    ct.add_argument('--note', default='')
    ct.add_argument('--pid', type=int)
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
    elif a.cmd == 'control':
        pids = [a.pid] if a.pid else find_fgfs()
        info = read_lock(sessions_dir() / f'{pids[0]}.lock') if len(pids) == 1 else None
        if not info or not info.get('url'):
            sys.exit('No single logged FlightGear session found; pass --pid.')
        req = urllib.request.Request(info['url'] + 'api/control', method='POST',
                                     data=json.dumps({'by': a.by, 'who': a.who, 'note': a.note}).encode())
        urllib.request.urlopen(req, timeout=3).read()
        print(f"Session {info.get('name')!r}: control declared as {a.by} {a.who}".strip())
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
