"""Project media: screenshots of FlightGear, the session log page and the agents,
captured as the project happens, annotated, and fed into the progress deck.

Everything lands next to the run it belongs to, on the sim-logs branch:

    runs/<session id>/media/
        fg-163015-001.jpg      FlightGear frame (every 5 s + on notable events)
        page-163100-002.jpg    the session's live log page (every 30 s)
        agent-163200-003.jpg   a snap of an agent's terminal / any window
        index.jsonl            one row per image (time, kind, telemetry, caption)
                               plus "note" rows that annotate an image later

Raw images are never drawn on. Annotations (caption, labelled boxes) live in
index.jsonl and are rendered when the deck is built, so they can be added or
fixed at any time.

    python -m flight_simulator.media watch            # recorder for every live session
                                                      # (started by ensure-recorder; one per machine)
    python -m flight_simulator.media ensure-recorder  # start the recorder if it isn't running
    python -m flight_simulator.media snap --caption "737 rotates at 150 kt"            # FlightGear now
    python -m flight_simulator.media snap --page --caption "log shows the pause fix"   # live log page
    python -m flight_simulator.media snap --window "Claude" --caption "agent finds freeze bug"
    python -m flight_simulator.media note latest --caption "..." --box 120,80,300,200=throttle
    python -m flight_simulator.media list             # recent media across runs
    python -m flight_simulator.media deck             # rebuild deck/FruitFly_Progress.pptx

A snap with no live session goes to runs/<UTC time>_<who>_media/ and is pushed
right away (set FRUITFLY_NO_PUSH=1 to keep it local). Session media is pushed by
the session logger when FlightGear exits.
"""
import argparse
import ctypes
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from PIL import Image, ImageDraw, ImageFont

from . import runlog

FG_EVERY_S = float(os.environ.get('FRUITFLY_MEDIA_FG_S', 5))
PAGE_EVERY_S = float(os.environ.get('FRUITFLY_MEDIA_PAGE_S', 30))
EVENT_GAP_S = 2            # min spacing between event-triggered frames
MAX_W = 1280               # stored frame width (JPEG q80, ~80-150 kB)
RECORDER_PORT = 8763       # bound by the recorder: one per machine
EVENT_WORDS = re.compile(r'paused|resumed|connected to property|controller run|crash|collision|\bstop\b|'
                         r'rotate|liftoff|lift-off|touchdown|handover|hands over|exited|error|started|finished', re.I)
# periodic controller status line, e.g. "[controller]   43.0s AVOID  altitude=..."; only a phase change is an event
STATUS = re.compile(r'\]\s+[\d.]+s\s+([A-Z][A-Z_-]+)\s+\w+=')
EDGE = [Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe',
        Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Microsoft/Edge/Application/msedge.exe']
TELEMETRY = {'alt_ft': '/position/altitude-ft', 'agl_ft': '/position/altitude-agl-ft',
             'ias_kt': '/velocities/airspeed-kt', 'heading_deg': '/orientation/heading-deg',
             'pitch_deg': '/orientation/pitch-deg', 'roll_deg': '/orientation/roll-deg',
             'sim_time_s': '/sim/time/elapsed-sec', 'paused': '/sim/freeze/clock'}


def now_utc():
    return datetime.now(timezone.utc)


def who():
    return runlog.git('config', 'user.name', check=False) or os.environ.get('USERNAME', 'unknown')


# ---- capture -------------------------------------------------------------------
def http_json(port, path, timeout=1.0):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/json{path}', timeout=timeout) as r:
        return json.loads(r.read() or b'{}').get('value')


def fg_frame(port, timeout=10):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/screenshot?type=png', timeout=timeout) as r:
        return Image.open(io.BytesIO(r.read())).convert('RGB')


def fg_telemetry(port):
    out = {}
    for k, p in TELEMETRY.items():
        try:
            v = http_json(port, p)
        except (OSError, ValueError):
            continue
        out[k] = round(v, 2) if isinstance(v, float) else v
    return out


def page_frame(url, size=(1400, 900), timeout=40):
    """Headless Edge screenshot of a web page (the session's live log page)."""
    edge = next((p for p in EDGE if p.exists()), None)
    if not edge:
        raise RuntimeError('Microsoft Edge not found for page screenshots')
    # One reused profile (Edge's helper processes linger and lock a fresh one); a unique output file per shot.
    profile = Path(tempfile.gettempdir()) / 'fruitfly-media-edge'
    profile.mkdir(exist_ok=True)
    out = profile / f'page-{os.getpid()}-{time.time_ns()}.png'
    try:
        subprocess.run([str(edge), '--headless=new', '--disable-gpu', '--hide-scrollbars', '--mute-audio',
                        f'--user-data-dir={profile / "profile"}', f'--window-size={size[0]},{size[1]}',
                        '--virtual-time-budget=4000', f'--screenshot={out}', url],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        with Image.open(out) as img:
            return img.convert('RGB')
    finally:
        try:
            out.unlink(missing_ok=True)
        except OSError:
            pass


def find_windows(title):
    """[(hwnd, title)] of visible top-level windows whose title contains `title` (case-insensitive)."""
    user32 = ctypes.windll.user32
    found = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if title.lower() in buf.value.lower():
                    found.append((hwnd, buf.value))
        return True
    user32.EnumWindows(proto(cb), 0)
    return found


def window_frame(hwnd):
    """Capture one window's own pixels (works when it is covered), via PrintWindow."""
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    try:
        user32.SetProcessDPIAware()
    except AttributeError:
        pass

    class RECT(ctypes.Structure):
        _fields_ = [('l', ctypes.c_long), ('t', ctypes.c_long), ('r', ctypes.c_long), ('b', ctypes.c_long)]
    rc = RECT()
    user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rc))
    w, h = rc.r - rc.l, rc.b - rc.t
    if w <= 0 or h <= 0:
        raise RuntimeError('window has no size (minimised?)')
    hdc = user32.GetWindowDC(ctypes.c_void_p(hwnd))
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(ctypes.c_void_p(hwnd), mem, 2)   # PW_RENDERFULLCONTENT

    class BMI(ctypes.Structure):
        _fields_ = [('size', ctypes.c_uint32), ('w', ctypes.c_long), ('h', ctypes.c_long), ('planes', ctypes.c_uint16),
                    ('bits', ctypes.c_uint16), ('comp', ctypes.c_uint32), ('img', ctypes.c_uint32),
                    ('xp', ctypes.c_long), ('yp', ctypes.c_long), ('used', ctypes.c_uint32), ('imp', ctypes.c_uint32)]
    bmi = BMI(ctypes.sizeof(BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(ctypes.c_void_p(hwnd), hdc)
    img = Image.frombuffer('RGB', (w, h), buf, 'raw', 'BGRX', 0, 1)
    if not ok or img.getextrema() == ((0, 0), (0, 0), (0, 0)):
        from PIL import ImageGrab        # fall back to what is on screen there
        img = ImageGrab.grab(bbox=(rc.l, rc.t, rc.r, rc.b), all_screens=True)
    return img.convert('RGB')


def screen_frame():
    from PIL import ImageGrab
    return ImageGrab.grab(all_screens=True).convert('RGB')


# ---- media folders -------------------------------------------------------------
class MediaDir:
    def __init__(self, run_dir):
        self.run_dir = Path(run_dir)
        self.dir = self.run_dir / 'media'

    @property
    def index(self):
        return self.dir / 'index.jsonl'

    def rows(self):
        if not self.index.exists():
            return []
        out = []
        for line in self.index.read_text(encoding='utf-8').splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
        return out

    def _append(self, row):
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.index, 'a', encoding='utf-8') as f:
            f.write(json.dumps(row, default=str) + '\n')

    def add(self, img, kind, caption='', telemetry=None, source='', who_=None):
        self.dir.mkdir(parents=True, exist_ok=True)
        n = sum(1 for r in self.rows() if r.get('type') == 'image') + 1
        t = now_utc()
        name = f'{kind}-{t:%H%M%S}-{n:03d}.jpg'
        if img.width > MAX_W:
            img = img.resize((MAX_W, round(img.height * MAX_W / img.width)), Image.LANCZOS)
        tmp = self.dir / (name + '.part')
        img.save(tmp, 'JPEG', quality=80, optimize=True)
        os.replace(tmp, self.dir / name)          # never leave half a file for the pusher
        row = {'type': 'image', 'file': name, 'kind': kind, 'utc': t.isoformat(timespec='seconds'),
               'caption': caption, 'source': source, 'who': who_ or who(), 'w': img.width, 'h': img.height,
               'telemetry': telemetry or {}}
        self._append(row)
        return self.dir / name

    def note(self, file, caption=None, boxes=(), who_=None):
        row = {'type': 'note', 'file': file, 'utc': now_utc().isoformat(timespec='seconds'), 'who': who_ or who()}
        if caption is not None:
            row['caption'] = caption
        if boxes:
            row['boxes'] = list(boxes)
        self._append(row)

    def images(self):
        """Image rows with their notes merged in (latest caption wins, boxes accumulate)."""
        imgs, order = {}, []
        for r in self.rows():
            if r.get('type') == 'image':
                imgs[r['file']] = {**r, 'boxes': list(r.get('boxes', [])), 'notes': []}
                order.append(r['file'])
            elif r.get('type') == 'note' and r.get('file') in imgs:
                im = imgs[r['file']]
                if r.get('caption') is not None:
                    im['caption'] = r['caption']
                    im['notes'].append(r)
                im['boxes'] += r.get('boxes', [])
        return [imgs[f] for f in order if (self.dir / f).exists()]


def live_sessions():
    """Lock files of FlightGear sessions whose fgfs is still running."""
    from .session import sessions_dir, read_lock, pid_alive
    out = []
    for lock in sessions_dir().glob('*.lock'):
        info = read_lock(lock)
        if isinstance(info, dict) and info.get('run_id') and pid_alive(info.get('fgfs_pid')):
            out.append(info)
    return sorted(out, key=lambda i: i.get('started', 0))


def session_httpd(info):
    from .session import parse_cmdline, fgfs_cmdline
    try:
        return parse_cmdline(fgfs_cmdline(info['fgfs_pid'])).get('httpd') or 8080
    except Exception:
        return 8080


def session_dir(info):
    return runlog.ensure_worktree() / runlog.RUNS / info['run_id']


def loose_dir():
    """Folder for snaps taken while no FlightGear session is live (one per hour per person)."""
    base = runlog.ensure_worktree() / runlog.RUNS
    t = now_utc()
    return base / f'{t:%Y-%m-%dT%H}0000Z_{runlog.slug(who())}_media'


def push_loose(run_dir, what):
    if os.environ.get('FRUITFLY_NO_PUSH'):
        print(f'FRUITFLY_NO_PUSH set: kept locally in {run_dir}')
        return
    runlog.push(f'media: {what} ({who()})', [f'{runlog.RUNS}/{run_dir.name}'], quiet=True)


# ---- recorder ------------------------------------------------------------------
class Track:
    """Recording state for one live session."""
    def __init__(self, info):
        self.info = info
        self.httpd = session_httpd(info)
        self.next_fg = 0.0
        self.next_page = time.time() + 15     # let the page load first
        self.last_event_frame = 0.0
        self.events_offset = None
        self.phase = None
        self.failures = 0

    def media(self):
        return MediaDir(session_dir(self.info))

    def new_events(self):
        path = session_dir(self.info) / 'events.log'
        if not path.exists():
            return []
        size = path.stat().st_size
        if self.events_offset is None or size < self.events_offset:
            self.events_offset = size if self.events_offset is None else 0
            return []
        with open(path, encoding='utf-8', errors='replace') as f:
            f.seek(self.events_offset)
            text = f.read()
            self.events_offset = f.tell()
        out = []
        for line in text.splitlines():
            m = STATUS.search(line)
            if m:
                if m.group(1) != self.phase:
                    if self.phase is not None:
                        out.append(f'Phase {self.phase} -> {m.group(1)}: ' + line.split(']', 1)[-1].strip())
                    self.phase = m.group(1)
            elif EVENT_WORDS.search(line):
                out.append(line)
        return out

    def fg_screenshots_off(self):
        """A session can opt out of FlightGear screenshots with
        --prop:bool:/fruitfly/no-screenshots=true (e.g. launch_fg ... -- that prop).
        Used to test whether /screenshot requests mid-render crash fgfs (2026-11-14:
        in-air runs crashed with 0xC0000005 shortly before the next screenshot)."""
        if getattr(self, '_off_checked', 0) > time.time() - 30:
            return self._off
        try:
            self._off = bool(http_json(self.httpd, '/fruitfly/no-screenshots'))
        except (OSError, ValueError):
            self._off = False
        self._off_checked = time.time()
        if self._off and not getattr(self, '_off_said', False):
            print(f'{self.info["run_id"]}: FlightGear screenshots OFF for this session (/fruitfly/no-screenshots)',
                  flush=True)
            self._off_said = True
        return self._off

    def tick(self):
        now = time.time()
        events = self.new_events()
        due = now >= self.next_fg
        if events and now - self.last_event_frame >= EVENT_GAP_S:
            due, caption = True, re.sub(r'^\d\d:\d\d:\d\d ', '', events[-1])[:160]
            self.last_event_frame = now
        else:
            caption = ''
        if due and self.fg_screenshots_off():
            due = False
            self.next_fg = now + FG_EVERY_S
        if due:
            try:
                tel = fg_telemetry(self.httpd)
                self.media().add(fg_frame(self.httpd), 'fg', caption, tel, f'httpd:{self.httpd}', 'recorder')
                self.failures = 0
            except (OSError, ValueError) as exc:
                self.failures += 1
                if self.failures in (1, 10):
                    print(f'{self.info["run_id"]}: FlightGear frame skipped: {exc!r}', flush=True)
            self.next_fg = now + FG_EVERY_S
        if PAGE_EVERY_S > 0 and now >= self.next_page and self.info.get('url'):
            try:
                self.media().add(page_frame(self.info['url'] + 'log'), 'page', 'Live session log page',
                                 source=self.info['url'] + 'log', who_='recorder')
            except Exception as exc:
                print(f'{self.info["run_id"]}: page frame skipped: {exc!r}', flush=True)
            self.next_page = now + PAGE_EVERY_S


def watch():
    guard = socket.socket()
    try:
        guard.bind(('127.0.0.1', RECORDER_PORT))
    except OSError:
        print('media recorder already running')
        return 0
    print(f'media recorder: FlightGear every {FG_EVERY_S:g} s, log page every {PAGE_EVERY_S:g} s', flush=True)
    tracks = {}
    while True:
        try:
            live = {i['fgfs_pid']: i for i in live_sessions()}
        except Exception as exc:
            print(f'session scan failed: {exc!r}', flush=True)
            live = {}
        for pid in list(tracks):
            if pid not in live:
                print(f'stopped recording {tracks.pop(pid).info["run_id"]}', flush=True)
        for pid, info in live.items():
            if pid not in tracks:
                tracks[pid] = Track(info)
                print(f'recording {info["run_id"]} (httpd {tracks[pid].httpd})', flush=True)
            tracks[pid].info = info           # name / run id can change while it runs
            tracks[pid].tick()
        time.sleep(1)


def recorder_running():
    s = socket.socket()
    try:
        s.bind(('127.0.0.1', RECORDER_PORT))
        return False
    except OSError:
        return True
    finally:
        s.close()


def ensure_recorder(quiet=False):
    if recorder_running():
        if not quiet:
            print('media recorder: running')
        return
    from .session import detached
    detached([sys.executable, '-m', 'flight_simulator.media', 'watch'], '.media-recorder.log')
    if not quiet:
        print('media recorder: started')


# ---- annotation rendering -------------------------------------------------------
def font(size, bold=False):
    for name in (('arialbd.ttf', 'DejaVuSans-Bold.ttf') if bold else ('arial.ttf', 'DejaVuSans.ttf')):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def parse_box(text):
    """'x0,y0,x1,y1=label' in image pixels (or 0..1 fractions) -> dict."""
    coords, _, label = text.partition('=')
    vals = [float(v) for v in coords.split(',')]
    if len(vals) != 4:
        raise ValueError(f'box needs x0,y0,x1,y1: {text!r}')
    return {'xyxy': vals, 'label': label.strip()}


def render(path, row, title='', width=1280):
    """Annotated copy: title/telemetry banner on top, caption strip below, labelled boxes."""
    img = Image.open(path).convert('RGB')
    scale = width / img.width
    img = img.resize((width, round(img.height * scale)), Image.LANCZOS)
    d = ImageDraw.Draw(img, 'RGBA')
    s = width / 1280
    pad = round(14 * s)
    for b in row.get('boxes', []):
        x0, y0, x1, y1 = b['xyxy']
        if max(x0, y0, x1, y1) <= 1.0:      # fractions of the stored image
            w0, h0 = row.get('w') or width / scale, row.get('h') or img.height / scale
            x0, x1, y0, y1 = x0 * w0, x1 * w0, y0 * h0, y1 * h0
        x0, y0, x1, y1 = (v * scale for v in (x0, y0, x1, y1))
        d.rectangle([x0, y0, x1, y1], outline=(255, 64, 160, 255), width=max(2, round(3 * s)))
        if b.get('label'):
            f = font(round(20 * s), True)
            tw = d.textlength(b['label'], font=f)
            ty = y0 - round(28 * s) if y0 > 30 * s else y1 + round(4 * s)
            d.rounded_rectangle([x0, ty, x0 + tw + 12, ty + round(26 * s)], 5, fill=(255, 64, 160, 230))
            d.text((x0 + 6, ty + 2), b['label'], font=f, fill='white')
    t = row.get('telemetry') or {}
    stamp = row.get('utc', '')[11:19]
    head = '  ·  '.join(x for x in [title, f'{stamp} UTC' if stamp else '', row.get('kind', '').upper()] if x)
    chips = []
    if 'alt_ft' in t:
        chips.append(f"ALT {t['alt_ft']:,.0f} ft")
    if isinstance(t.get('agl_ft'), (int, float)) and t['agl_ft'] < 2000:
        chips.append(f"AGL {t['agl_ft']:,.0f} ft")
    if 'ias_kt' in t:
        chips.append(f"IAS {t['ias_kt']:.0f} kt")
    if 'heading_deg' in t:
        chips.append(f"HDG {t['heading_deg']:03.0f}")
    if 'pitch_deg' in t:
        chips.append(f"PITCH {t['pitch_deg']:+.0f}")
    if 'roll_deg' in t:
        chips.append(f"ROLL {t['roll_deg']:+.0f}")
    if t.get('paused'):
        chips.append('PAUSED')
    fh, fc = font(round(22 * s), True), font(round(19 * s))
    bh = round(44 * s) + (round(30 * s) if chips else 0)
    d.rectangle([0, 0, width, bh], fill=(10, 18, 30, 190))
    d.text((pad, round(8 * s)), head, font=fh, fill=(255, 255, 255))
    if chips:
        d.text((pad, round(42 * s)), '   '.join(chips), font=fc, fill=(255, 214, 102))
    cap = row.get('caption') or ''
    if cap:
        fcap = font(round(24 * s), True)
        lines, line = [], ''
        for word in cap.split():
            trial = f'{line} {word}'.strip()
            if d.textlength(trial, font=fcap) > width - 2 * pad and line:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
        lines = lines[:3]
        ch = len(lines) * round(32 * s) + 2 * pad
        d.rectangle([0, img.height - ch, width, img.height], fill=(10, 18, 30, 200))
        for i, l in enumerate(lines):
            d.text((pad, img.height - ch + pad + i * round(32 * s)), l, font=fcap, fill=(255, 255, 255))
    return img


def timelapse(frames, out, width=720, frame_ms=500, max_frames=80):
    """Annotated GIF (plays in PowerPoint slideshow) from [(path, row, title)]."""
    if len(frames) > max_frames:
        step = len(frames) / max_frames
        frames = [frames[int(i * step)] for i in range(max_frames)]
    imgs = [render(p, r, t, width).convert('P', palette=Image.ADAPTIVE, colors=128) for p, r, t in frames]
    if not imgs:
        return None
    imgs[0].save(out, save_all=True, append_images=imgs[1:], duration=frame_ms, loop=0, optimize=True)
    return out


# ---- CLI -----------------------------------------------------------------------
def all_media_dirs():
    base = runlog.ensure_worktree() / runlog.RUNS
    return sorted((MediaDir(p) for p in base.iterdir() if (p / 'media' / 'index.jsonl').exists()),
                  key=lambda m: m.run_dir.name)


def resolve(target):
    """'latest' or a path to an image -> (MediaDir, file name)."""
    if target == 'latest':
        best = None
        for m in all_media_dirs():
            for r in m.rows():
                if r.get('type') == 'image' and (best is None or r['utc'] >= best[1]['utc']):
                    best = (m, r)
        if not best:
            raise SystemExit('no media yet')
        return best[0], best[1]['file']
    p = Path(target).resolve()
    if not p.exists():
        raise SystemExit(f'no such image: {target}')
    return MediaDir(p.parent.parent), p.name


def cmd_snap(a):
    live = live_sessions()
    info = live[-1] if live else None
    if a.session:
        info = next((i for i in live if a.session.lower() in (i.get('name') or i['run_id']).lower()), None)
        if not info:
            raise SystemExit(f'no live session matching {a.session!r}')
    if a.window:
        wins = find_windows(a.window)
        if not wins:
            raise SystemExit(f'no visible window title contains {a.window!r}')
        hwnd, title = wins[0]
        img, kind, source, tel = window_frame(hwnd), 'agent', f'window:{title}', {}
    elif a.screen:
        img, kind, source, tel = screen_frame(), 'screen', 'screen', {}
    elif a.page:
        if not info or not info.get('url'):
            raise SystemExit('no live session page to capture')
        img, kind, source, tel = page_frame(info['url'] + 'log'), 'page', info['url'] + 'log', {}
    else:
        if not info:
            raise SystemExit('no live FlightGear session (start one with a launcher, or use --window/--screen)')
        port = session_httpd(info)
        img, kind, source, tel = fg_frame(port), 'fg', f'httpd:{port}', fg_telemetry(port)
    # Agent / desktop snaps are project-wide unless --session ties them to a flight.
    in_session = info is not None and (kind in ('fg', 'page') or a.session)
    run_dir = session_dir(info) if in_session else loose_dir()
    m = MediaDir(run_dir)
    path = m.add(img, kind, a.caption or '', tel, source)
    for b in a.box or []:
        m.note(path.name, boxes=[parse_box(b)])
    print(path)
    if not in_session:
        push_loose(run_dir, f'{kind} snap "{a.caption or path.name}"')


def cmd_note(a):
    m, file = resolve(a.image)
    m.note(file, a.caption, [parse_box(b) for b in a.box or []])
    print(f'noted {m.dir / file}')
    live_ids = {i['run_id'] for i in live_sessions()}
    if m.run_dir.name not in live_ids:   # finished run: push the note now
        push_loose(m.run_dir, f'note on {file}')


def cmd_list(a):
    rows = []
    for m in all_media_dirs():
        for r in m.images():
            rows.append((r['utc'], m.dir / r['file'], r.get('caption', '')))
    for utc, p, cap in sorted(rows)[-a.n:]:
        print(f'{utc}  {p}  {cap}')


def cmd_render(a):
    m, file = resolve(a.image)
    row = next(r for r in m.images() if r['file'] == file)
    out = Path(a.out or (Path(tempfile.gettempdir()) / f'annotated-{file}'))
    title = a.title or next((i.get('name') for i in live_sessions() if i['run_id'] == m.run_dir.name), None)
    if not title and (m.run_dir / 'meta.json').exists():
        title = json.loads((m.run_dir / 'meta.json').read_text(encoding='utf-8')).get('name')
    render(m.dir / file, row, title or m.run_dir.name).save(out, quality=90)
    print(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('watch', help='record every live FlightGear session (one per machine)')
    sub.add_parser('ensure-recorder', help='start the recorder in the background if needed')
    s = sub.add_parser('snap', help='capture one image now')
    g = s.add_mutually_exclusive_group()
    g.add_argument('--page', action='store_true', help='the live session log page')
    g.add_argument('--window', metavar='TITLE', help='a window whose title contains TITLE (agent terminal...)')
    g.add_argument('--screen', action='store_true', help='the whole desktop')
    s.add_argument('--session', help='which live session (name substring); default: newest')
    s.add_argument('--caption')
    s.add_argument('--box', action='append', metavar='X0,Y0,X1,Y1=LABEL')
    n = sub.add_parser('note', help='caption / box an existing image')
    n.add_argument('image', help="'latest' or a path to a media image")
    n.add_argument('--caption')
    n.add_argument('--box', action='append', metavar='X0,Y0,X1,Y1=LABEL')
    l = sub.add_parser('list', help='recent media')
    l.add_argument('-n', type=int, default=20)
    r = sub.add_parser('render', help='write an annotated copy of one image')
    r.add_argument('image')
    r.add_argument('--title')
    r.add_argument('--out')
    sub.add_parser('deck', help='rebuild deck/FruitFly_Progress.pptx')
    a = ap.parse_args(argv)
    if a.cmd == 'watch':
        return watch()
    if a.cmd == 'ensure-recorder':
        return ensure_recorder()
    if a.cmd == 'deck':
        root = Path(__file__).resolve().parent.parent
        return subprocess.call([sys.executable, str(root / 'deck' / 'build.py')])
    return {'snap': cmd_snap, 'note': cmd_note, 'list': cmd_list, 'render': cmd_render}[a.cmd](a)


if __name__ == '__main__':
    sys.exit(main())
