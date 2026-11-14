"""Glue companion windows to the FlightGear window (Windows only).

    +---------------------------+-----------+
    |                           |           |
    |        FlightGear         |  fly      |
    |                           |  brain    |
    +---------------------------+           |
    |  session log              |           |
    +---------------------------+-----------+

The companions are chromeless Edge app windows (--app=URL) on the session's live
pages. A loop follows the FlightGear window: move/resize it and the companions
follow; minimize it and they minimize; bring it to the front and they come too.
Display only: nothing here talks to the simulator or the pilot.
"""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import threading
import time

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

LOG_H = 230          # logical px (scaled by the FlightGear monitor's DPI)
BRAIN_W = 460
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE = 0x1, 0x2, 0x4, 0x10
SW_RESTORE, SW_SHOWMINNOACTIVE, SW_SHOWNOACTIVATE = 9, 7, 4
HWND_TOP = 0
WM_CLOSE = 0x0010
EDGE = [Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe',
        Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Microsoft/Edge/Application/msedge.exe']

try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))   # per-monitor v2: real pixels
except (AttributeError, OSError):
    pass


class MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]


def _windows():
    found = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True
    user32.EnumWindows(proc(cb), 0)
    return found


def title(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def frame(hwnd):
    """Visible bounds (without Windows 11's invisible resize borders)."""
    r = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(r), ctypes.sizeof(r)) == 0:
        return r.left, r.top, r.right, r.bottom
    return rect(hwnd)


def window_of_pid(pid):
    """FlightGear's main window: the largest visible top-level window of the process."""
    best, area = None, 0
    for hwnd in _windows():
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid or not title(hwnd):
            continue
        l, t, r, b = rect(hwnd)
        if (r - l) * (b - t) > area:
            best, area = hwnd, (r - l) * (b - t)
    return best


def window_titled(prefix):
    for hwnd in _windows():
        if title(hwnd).startswith(prefix):
            return hwnd
    return None


def work_area(hwnd):
    mon = user32.MonitorFromWindow(hwnd, 2)
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    user32.GetMonitorInfoW(mon, ctypes.byref(info))
    w, m = info.rcWork, info.rcMonitor
    return (w.left, w.top, w.right, w.bottom), (m.left, m.top, m.right, m.bottom)


def scale(hwnd):
    """Display scaling of the monitor hwnd is on (not the window's own DPI awareness)."""
    try:
        mon = user32.MonitorFromWindow(hwnd, 2)
        x, y = wintypes.UINT(), wintypes.UINT()
        if ctypes.windll.shcore.GetDpiForMonitor(mon, 0, ctypes.byref(x), ctypes.byref(y)) == 0:
            return x.value / 96 or 1
    except (AttributeError, OSError):
        pass
    return 1


def place(hwnd, x, y, w, h):
    """Put the *visible* frame of hwnd at x,y,w,h."""
    wl, wt, wr, wb = rect(hwnd)
    fl, ft, fr, fb = frame(hwnd)
    dl, dt, dr, db = fl - wl, ft - wt, wr - fr, wb - fb
    user32.SetWindowPos(hwnd, None, x - dl, y - dt, w + dl + dr, h + dt + db, SWP_NOZORDER | SWP_NOACTIVATE)


def open_app(url, profile, x=0, y=0, w=600, h=300):
    exe = next((p for p in EDGE if p.exists()), None)
    if not exe:
        return None
    return subprocess.Popen([str(exe), f'--app={url}', f'--user-data-dir={profile}', '--no-first-run',
                             '--no-default-browser-check', '--disable-features=Translate',
                             f'--window-position={x},{y}', f'--window-size={w},{h}'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


class Dock:
    """Open the log + brain windows and keep them glued to FlightGear until stop()."""

    def __init__(self, fgfs_pid, log_url, brain_url, tag, profile, say=print):
        self.pid, self.tag, self.say = fgfs_pid, tag, say
        self.urls = {'log': log_url, 'brain': brain_url}
        self.profile = profile
        self.hwnd = {'log': None, 'brain': None}
        self.fg = None
        self.stopped = threading.Event()
        self.procs = []

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self, close=True):
        self.stopped.set()
        if close:
            for hwnd in self.hwnd.values():
                if hwnd and user32.IsWindow(hwnd):
                    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

    def _layout(self):
        fl, ft, fr, fb = frame(self.fg)
        k = scale(self.fg)
        log_h, brain_w = int(LOG_H * k), int(BRAIN_W * k)
        return {'log': (fl, fb, fr - fl, log_h), 'brain': (fr, ft, brain_w, fb - ft + log_h)}

    def _arrange_fg(self):
        """Once: make room on FlightGear's monitor for the two companions."""
        (wl, wt, wr, wb), monitor = work_area(self.fg)
        if frame(self.fg) == monitor:
            self.say('FlightGear is fullscreen; companions open but cannot dock beside it')
            return
        k = scale(self.fg)
        if user32.IsZoomed(self.fg):
            user32.ShowWindow(self.fg, SW_RESTORE)
        place(self.fg, wl, wt, (wr - wl) - int(BRAIN_W * k), (wb - wt) - int(LOG_H * k))

    def _run(self):
        deadline = time.time() + 600
        while not self.stopped.is_set() and time.time() < deadline:
            self.fg = window_of_pid(self.pid)
            if self.fg and 'FlightGear' in title(self.fg):
                break
            time.sleep(1)
        if not self.fg:
            self.say('FlightGear window not found; companion windows not docked')
            return
        self._arrange_fg()
        for name, (x, y, w, h) in self._layout().items():
            self.procs.append(open_app(self.urls[name], self.profile, x, y, w, h))
        for _ in range(120):
            for name in self.hwnd:
                self.hwnd[name] = self.hwnd[name] or window_titled(f'FruitFly {name} · {self.tag}')
            if all(self.hwnd.values()):
                break
            time.sleep(0.5)
        self.say('Docked: log below and fly brain right of FlightGear'
                 if all(self.hwnd.values()) else f'Docking incomplete: {self.hwnd}')
        last, was_min, was_front = None, False, False
        while not self.stopped.is_set():
            if not user32.IsWindow(self.fg):
                break
            minimized = bool(user32.IsIconic(self.fg))
            if minimized != was_min:
                for hwnd in filter(None, self.hwnd.values()):
                    user32.ShowWindow(hwnd, SW_SHOWMINNOACTIVE if minimized else SW_SHOWNOACTIVATE)
                was_min = minimized
            if not minimized:
                now = self._layout()
                if now != last:
                    for name, (x, y, w, h) in now.items():
                        if self.hwnd[name] and user32.IsWindow(self.hwnd[name]):
                            place(self.hwnd[name], x, y, w, h)
                    last = now
                front = user32.GetForegroundWindow() == self.fg
                if front and not was_front:   # FlightGear came forward: bring companions along
                    for hwnd in filter(None, self.hwnd.values()):
                        user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
                was_front = front
            time.sleep(0.15)
