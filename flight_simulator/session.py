"""FlightGear session log: starts with FlightGear, shows a live log page, pushes on exit.

The launchers start this automatically right after fgfs:
    python flightgear/launch.py            (737 + fly cabin)
    python -m flight_simulator.launch_fg   (extra instances)
    flightgear_api/launch_fg.ps1           (C172 / obstacle mode)

For FlightGear opened another way (desktop shortcut, Qt launcher):
    python -m flight_simulator.session attach            # finds the running fgfs.exe

It writes runs/<UTC time>_<who>_fg-session/ on the sim-logs branch:
    airplane.csv        aircraft state + controls, 2 Hz, from the HTTP property API
    fly_activity.csv    fly-side signals in FlightGear (cabin fly activity; more to come)
    events.log          the running log: session events, FlightGear warnings, controller output
    fgfs_warnings.log   WARN/ALERT/Nasal lines from fgfs.log
    meta.json, feedback.md

Controller runs (python -m flight_simulator) during the session keep their own
folders (airplane.csv + fly_activity.csv); the live page streams them too and
the session's feedback.md links them. When fgfs exits, the folder is committed
and pushed (see runlog.py; FRUITFLY_NO_PUSH=1 to keep it local).
"""
import argparse
import csv
from datetime import datetime, timezone
import json
import os
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
            return Path(f'/proc/{self.pid}').exists()
        import ctypes
        code = ctypes.c_ulong()
        self.k.GetExitCodeProcess(self.h, ctypes.byref(code))
        if code.value == 259:  # STILL_ACTIVE
            return True
        self.code = code.value
        return False


def find_fgfs():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq fgfs.exe', '/FO', 'CSV', '/NH'],
                         capture_output=True, text=True).stdout
    pids = [int(line.split('","')[1]) for line in out.splitlines() if line.startswith('"fgfs.exe"')]
    return pids


def spawn(pid, httpd=8080, telemetry_port=5501, fg_home=None, label='', open_browser=True):
    """Start the watcher detached from the launcher; returns immediately."""
    cmd = [sys.executable, '-m', 'flight_simulator.session', 'watch', '--pid', str(pid),
           '--httpd', str(httpd), '--telemetry-port', str(telemetry_port), '--label', label]
    if fg_home:
        cmd += ['--fg-home', str(fg_home)]
    if not open_browser:
        cmd.append('--no-browser')
    flags = 0
    if os.name == 'nt':
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    log = open(runlog.ensure_worktree() / '.watcher.log', 'a')
    subprocess.Popen(cmd, cwd=runlog.ROOT, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                     creationflags=flags, close_fds=True)
    print('Session log starting: a live log page will open in your browser '
          '(it is pushed to the sim-logs branch when FlightGear closes).')


class Session:
    def __init__(self, a):
        self.a = a
        self.proc = Process(a.pid)
        self.started = time.time()
        self.who = runlog.git('config', 'user.name', check=False) or os.environ.get('USERNAME', 'unknown')
        self.id = runlog.run_id('fg', 'session', self.who)
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
        self.fg_log = (Path(a.fg_home) if a.fg_home else runlog.fg_home(a.telemetry_port)) / 'fgfs.log'
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
        self._events = open(self.dir / 'events.log', 'w', encoding='utf-8')
        self.event('session', f'Session {self.id} watching fgfs pid {a.pid}'
                   + (f' ({a.label})' if a.label else ''))

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
        url = f'http://127.0.0.1:{self.a.httpd}/json{path}'
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
            self.event('session', f'Connected to property API on :{self.a.httpd}')
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
            if d.name == self.id or 'fg-session' in d.name or not d.is_dir():
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
                        if 'header' not in st and p.exists():
                            st['header'] = p.read_text(encoding='utf-8').splitlines()[0]
                            self.fly_header = st['header']
            if (d / 'result.json').exists():
                st['done'] = True
                st['result'] = json.loads((d / 'result.json').read_text())
                self.event('controller', f"Run finished: {d.name} exit={st['result'].get('exit_code')}")

    # ---- live page ------------------------------------------------------
    def snapshot(self, since):
        with self.lock:
            return {
                'id': self.id, 'label': self.a.label, 'status': self.status,
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
        self.event('session', f'Live log page: {self.url}')

    # ---- main loop and wrap-up -----------------------------------------
    def run(self):
        self.serve()
        if not self.a.no_browser:
            webbrowser.open(self.url)
        next_slow = 0
        while self.proc.alive():
            self.poll()
            if time.time() >= next_slow:
                self.tail_fg_log()
                self.tail_controller()
                next_slow = time.time() + 1
            time.sleep(POLL_S)
        self.tail_fg_log()
        self.tail_controller()
        code = self.proc.code
        crashed = code not in (0, None)
        self.event('session', f'FlightGear exited (code {code})' + (' - looks like a crash' if crashed else ''))
        self.status = 'FlightGear closed - saving log'
        self.finish(code, crashed)
        self.status = 'FlightGear closed - log saved' + (' and pushed' if self.pushed else ' locally')
        self.event('session', self.status)
        time.sleep(15)            # let the open page show the final status
        self.server.shutdown()

    def finish(self, code, crashed):
        self._airplane.close()
        self._fly.close()
        (self.dir / 'fgfs_warnings.log').write_text(
            '\n'.join(runlog.filter_fg_log(self.fg_kept)) + '\n', encoding='utf-8')
        duration = round(time.time() - self.started)
        controller = {k: v.get('result') for k, v in self.controller.items()}
        meta = {'run_id': self.id, 'who': self.who, 'kind': 'flightgear-session',
                'label': self.a.label, 'fgfs_pid': self.a.pid, 'fgfs_exit_code': code,
                'started_utc': datetime.fromtimestamp(self.started, timezone.utc).isoformat(),
                'duration_s': duration, 'httpd_port': self.a.httpd,
                'flightgear': {**self.fg_info, 'fgfs_log': str(self.fg_log),
                               'warning_lines': len(self.fg_kept)},
                'airplane_samples': self.samples, 'controller_runs': controller,
                'code': {'commit': runlog.git('rev-parse', 'HEAD', check=False),
                         'branch': runlog.git('rev-parse', '--abbrev-ref', 'HEAD', check=False)}}
        (self.dir / 'meta.json').write_text(json.dumps(meta, indent=2, default=str) + '\n', encoding='utf-8')
        outcome = 'FlightGear CRASHED' if crashed else 'closed normally'
        rows = [('Outcome', f'{outcome} (exit {code})'),
                ('Duration', f'{duration // 60} min {duration % 60} s'),
                ('FlightGear', f"{self.fg_info.get('version', '?')}, {self.fg_info.get('aircraft', '?')}"),
                ('Airplane samples', f'{self.samples} at {1 / POLL_S:g} Hz'
                                     + ('' if self.samples else ' (property API never answered: launched without --httpd?)')),
                ('Max altitude / IAS', f"{self.maxima['alt_ft'] and round(self.maxima['alt_ft'])} ft / "
                                       f"{self.maxima['ias_kt'] and round(self.maxima['ias_kt'])} kt"),
                ('FlightGear warnings', f'{len(self.fg_kept)} lines (fgfs_warnings.log)'),
                ('Controller runs', ', '.join(f'[{k}](../{k}/feedback.md)' for k in controller) or 'none')]
        text = (f'# {self.id}\n\nFlightGear session by {self.who}'
                + (f' ({self.a.label})' if self.a.label else '') + '.\n\n'
                '| | |\n|---|---|\n' + ''.join(f'| {k} | {v} |\n' for k, v in rows)
                + '\n## Notes\n\n<!-- add feedback: python -m flight_simulator.runlog note "..." -->\n')
        (self.dir / 'feedback.md').write_text(text, encoding='utf-8')
        self._events.close()
        message = f'sim log: FlightGear session {outcome}, {duration // 60} min ({self.who})'
        self.pushed = runlog.push(message, [f'{runlog.RUNS}/{self.id}'])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('watch', 'attach'):
        p = sub.add_parser(name)
        p.add_argument('--pid', type=int, required=(name == 'watch'))
        p.add_argument('--httpd', type=int, default=8080)
        p.add_argument('--telemetry-port', type=int, default=5501, help='picks the FG_HOME of that instance')
        p.add_argument('--fg-home', help='FlightGear home holding fgfs.log')
        p.add_argument('--label', default='')
        p.add_argument('--no-browser', action='store_true')
    a = ap.parse_args(argv)
    if a.cmd == 'attach':
        if not a.pid:
            pids = find_fgfs()
            if len(pids) != 1:
                sys.exit(f'Found {len(pids)} fgfs.exe processes; pass --pid.' if pids else 'FlightGear is not running.')
            a.pid = pids[0]
        spawn(a.pid, a.httpd, a.telemetry_port, a.fg_home, a.label or 'attached', not a.no_browser)
        return 0
    Session(a).run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
