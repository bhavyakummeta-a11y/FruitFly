"""Screen recording of a run: FlightGear and the docked Log / Fly brain panel together.

FlightGear's own video recorder (session.py) films only the 3D view. The panel is a
separate window, docked to the right of FlightGear (dock.py), so a demo that shows the
fly's brain next to the airplane needs a desktop capture. This uses the ffmpeg that the
imageio-ffmpeg package bundles (pip install imageio-ffmpeg, no admin) and Windows' GDI
grabber. Local files only; nothing is uploaded or committed.

    rec = ScreenRecorder('takeoff LAX').start()
    ...
    rec.stop()          # -> %LOCALAPPDATA%/FruitFly/videos/screen_<utc>_<name>.mp4 (+ .json sidecar)

    python -m flight_simulator.screen_record --seconds 10 --name test    # quick check

Sidecar <video>.json (for flight_simulator/demo_cut.py, to line the video up with
events.log / airplane.csv): started_utc (ISO 8601, ms), fps, width, height,
region [x, y, w, h], session_id, name.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

# Next to FlightGear's own session videos; FRUITFLY_SCREEN_DIR overrides (e.g. a sandboxed
# agent that can only write inside the repo uses <repo>/runs/videos, which git ignores).
VIDEO_ROOT = Path(os.environ.get('FRUITFLY_SCREEN_DIR')
                  or Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'FruitFly' / 'videos')


def ffmpeg_exe():
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError('Screen recording needs imageio-ffmpeg: pip install imageio-ffmpeg') from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def desktop_size():
    """Virtual-desktop size in physical pixels (what gdigrab 'desktop' captures)."""
    if os.name != 'nt':
        return None
    import ctypes
    u = ctypes.windll.user32
    try:
        u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))   # per-monitor v2: real pixels
    except (AttributeError, OSError):
        pass
    return (u.GetSystemMetrics(76), u.GetSystemMetrics(77),     # SM_X/YVIRTUALSCREEN
            u.GetSystemMetrics(78), u.GetSystemMetrics(79))     # SM_CX/CYVIRTUALSCREEN


class ScreenRecorder:
    def __init__(self, name='run', fps=30, session_id=None, out_dir=VIDEO_ROOT):
        self.name, self.fps, self.session_id = name, fps, session_id
        self.out_dir = Path(out_dir)
        self.proc = self.path = None

    def start(self):
        if os.name != 'nt':
            raise RuntimeError('Screen recording is implemented for Windows (gdigrab) only')
        self.out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        slug = re.sub(r'[^A-Za-z0-9]+', '-', self.name).strip('-')[:60] or 'run'
        self.path = self.out_dir / f'screen_{stamp}_{slug}.mp4'
        x, y, w, h = desktop_size() or (0, 0, 0, 0)
        w, h = w - w % 2, h - h % 2                     # H.264 wants even sizes
        cmd = [ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-y',
               '-f', 'gdigrab', '-framerate', str(self.fps), '-draw_mouse', '1',
               '-offset_x', str(x), '-offset_y', str(y), '-video_size', f'{w}x{h}', '-i', 'desktop',
               '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '26', '-pix_fmt', 'yuv420p',
               '-movflags', '+faststart', str(self.path)]
        self.started = datetime.now(timezone.utc)
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        time.sleep(0.5)
        if self.proc.poll() is not None:
            raise RuntimeError('Screen recording failed to start: '
                               + self.proc.stderr.read().decode(errors='replace')[-300:])
        sidecar = {'started_utc': self.started.isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
                   'fps': self.fps, 'width': w, 'height': h, 'region': [x, y, w, h],
                   'session_id': self.session_id, 'name': self.name}
        self.path.with_suffix('.json').write_text(json.dumps(sidecar, indent=2) + '\n', encoding='utf-8')
        return self

    def stop(self, timeout=20):
        """Finish the file cleanly ('q' to ffmpeg); returns the video path."""
        if not self.proc:
            return None
        try:
            if self.proc.poll() is None:
                self.proc.stdin.write(b'q')
                self.proc.stdin.flush()
                self.proc.wait(timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()
        finally:
            self.proc = None
        return self.path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--seconds', type=float, default=10)
    ap.add_argument('--name', default='test')
    a = ap.parse_args(argv)
    rec = ScreenRecorder(a.name).start()
    print(f'recording {a.seconds:g} s -> {rec.path}', flush=True)
    time.sleep(a.seconds)
    path = rec.stop()
    print(f'saved {path} ({path.stat().st_size / 1e6:.1f} MB)' if path and path.exists() else 'no file written')
    return 0


if __name__ == '__main__':
    sys.exit(main())
