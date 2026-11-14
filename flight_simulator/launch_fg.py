"""Launch an extra FlightGear instance on its own ports, for side-by-side runs.

Instance 0 uses the documented ports (httpd 8080, telnet 5500, UDP 5501/5502).
Instance N adds 10*N to every port, so instance 1 is 8090 / 5510 / 5511 / 5512.
Each instance gets its own FG_HOME so they don't fight over FlightGear's lock
file and autosave.

    python -m flight_simulator.launch_fg --instance 1
    python -m flight_simulator --backend flightgear --brain reflex \
        --telemetry-port 5511 --control-port 5512

Start with --print to see the command without launching anything.

Takeoff / landing (docs/TAKEOFF_LANDING.md): --phase copies the runway
protocols into FlightGear, starts the 737 at KSFO 28R (on the runway for
takeoff, 3 nm out on final for landing) and prints the controller command:

    python -m flight_simulator.launch_fg --phase takeoff --name "takeoff test"
    python -m flight_simulator.launch_fg --phase landing --name "landing test"
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

def default_fg():
    """FG_INSTALL, else D:\\FlightGear, else fgfs on PATH, else the newest
    ~/Downloads or ~/apps flightgear-*.AppImage (the official Linux build)."""
    if os.environ.get('FG_INSTALL'):
        return Path(os.environ['FG_INSTALL'])
    if Path(r'D:\FlightGear').exists():
        return Path(r'D:\FlightGear')
    on_path = shutil.which('fgfs')
    if on_path:
        return Path(on_path)
    images = sorted(p for d in ('Downloads', 'apps') for p in (Path.home() / d).glob('flightgear-*.AppImage'))
    return images[-1] if images else Path(r'D:\FlightGear')


DEFAULT_FG = default_fg()
# Project default aircraft: 737-800 with fly passengers (run flightgear/setup_aircraft.py once).
REPO = Path(__file__).resolve().parent.parent
REPO_AIRCRAFT = REPO / 'flightgear' / 'Aircraft'
DEFAULT_AIRCRAFT = '738-flies'
# In-air start speed. 100 kt is fine for the C172 but stalls a 737.
START_KT = {'c172p': 100}
PROTOCOLS = Path(__file__).resolve().parent / 'protocols'
RUNWAY_PROTOCOLS = ('flybrain-runway-state.xml', 'flybrain-runway-controls.xml')
# Installed on every launch so a protocol fix (e.g. the freeze/clock chunk) reaches FlightGear.
ALL_PROTOCOLS = ('flybrain-state.xml', 'flybrain-controls.xml', 'flybrain-controls-twin.xml', *RUNWAY_PROTOCOLS)
# Takeoff/landing start. 737 flap detents are 0.125 apart: flaps 5 = 0.375, flaps 30 = 0.875.
AIRPORT, RUNWAY, FINAL_NM = 'KSFO', '28R', 3.0
PHASE_ARGS = {
    # Engines already running at spawn (JSBSim starts them at init), so the 737 autostart
    # only switches systems on: no ~1 min spool-up before the fly can take off.
    'takeoff': ['--prop:/controls/flight/flaps=0.375', '--prop:/controls/gear/brake-parking=0',
                '--prop:bool:/sim/presets/running=true',
                '--prop:bool:/fruitfly/ground-autostart=true'],
    'landing': [f'--offset-distance={FINAL_NM}', '--altitude=1000', '--vc=145', '--in-air',
                '--prop:/controls/flight/flaps=0.875', '--prop:bool:/controls/gear/gear-down=true'],
}


def ports(instance):
    k = 10 * instance
    return {'httpd': 8080 + k, 'telnet': 5500 + k, 'telemetry': 5501 + k, 'control': 5502 + k}


def fg_root(fg):
    """FlightGear's data folder (where Protocol/ lives), or None if unknown."""
    if os.environ.get('FG_ROOT'):
        return Path(os.environ['FG_ROOT'])
    return None if fg.is_file() else fg / 'data'


def install_protocols(fg):
    """Copy our generic protocols into $FG_ROOT/Protocol. Returns a problem or None."""
    root = fg_root(fg)
    if root is None:
        return ('FlightGear data folder unknown (AppImage or bare fgfs). Set FG_ROOT, or copy '
                f'{", ".join(ALL_PROTOCOLS)} from {PROTOCOLS} into <fg-root>/Protocol yourself.')
    dest = root / 'Protocol'
    try:
        for name in ALL_PROTOCOLS:
            src = PROTOCOLS / name
            if not (dest / name).exists() or (dest / name).read_bytes() != src.read_bytes():
                shutil.copyfile(src, dest / name)
                print(f'Installed {name} -> {dest}')
    except OSError as exc:
        return (f'Could not copy the protocols into {dest} ({exc}). Copy {", ".join(ALL_PROTOCOLS)} '
                f'from {PROTOCOLS} there yourself (an admin terminal may be needed).')
    return None


def controller_command(args):
    p = ports(args.instance)
    cmd = f'python -m flight_simulator.takeoff_landing {args.phase} --brain standin --backend flightgear'
    if p['telemetry'] != 5501:
        cmd += f' --telemetry-port {p["telemetry"]} --control-port {p["control"]}'
    return cmd


def command(args):
    p = ports(args.instance)
    fg = Path(args.fg)
    if fg.is_file():
        # An fgfs binary or the Linux AppImage: it finds its own data (fg-root).
        exe = [str(fg)]
    else:
        exe = [str(fg / 'bin' / 'fgfs.exe' if os.name == 'nt' else fg / 'bin' / 'fgfs'),
               f'--fg-root={fg / "data"}']
    common = [*exe, f'--fg-aircraft={REPO_AIRCRAFT}', f'--aircraft={args.aircraft}',
              f'--httpd={p["httpd"]}', f'--telnet={p["telnet"]}']
    if getattr(args, 'phase', None):
        return [*common, f'--airport={AIRPORT}', f'--runway={RUNWAY}', *PHASE_ARGS[args.phase],
                '--disable-real-weather-fetch', '--wind=0@0', '--timeofday=noon', '--disable-ai-traffic',
                f'--generic=socket,out,20,127.0.0.1,{p["telemetry"]},udp,flybrain-runway-state',
                f'--generic=socket,in,20,127.0.0.1,{p["control"]},udp,flybrain-runway-controls',
                *args.extra]
    return [*common,
            '--lat=37.55', '--lon=-122.75', '--altitude=3000', '--heading=0', f'--vc={START_KT.get(args.aircraft, 220)}',
            '--in-air', '--disable-real-weather-fetch', '--wind=0@0',
            '--timeofday=noon', '--disable-ai-traffic',
            f'--generic=socket,out,20,127.0.0.1,{p["telemetry"]},udp,flybrain-state',
            f'--generic=socket,in,20,127.0.0.1,{p["control"]},udp,flybrain-controls',
            *args.extra]


def wait_ready(telnet_port, timeout=600):
    """Block until FlightGear has loaded its scenery (telnet answers /sim/sceneryloaded)."""
    from .flightgear import telnet_get
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if telnet_get(telnet_port, '/sim/sceneryloaded', timeout=2) == 'true':
            return True
        time.sleep(1)
    return False


def fly_command(args):
    p = ports(args.instance)
    # takeoff_live = takeoff_landing + a run log, so the session's brain page shows the fly live.
    # The connectome needs the project venv (requirements-brain.txt) if there is one.
    venv = REPO / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    python = str(venv) if venv.exists() else sys.executable
    cmd = [python, '-m', 'flight_simulator.takeoff_live', args.phase, '--brain', args.fly,
           '--backend', 'flightgear', '--telemetry-port', str(p['telemetry']), '--control-port', str(p['control'])]
    # Always real time: the controller locks FlightGear at 1x and never pauses it for a
    # brain trial (project rules, gh #3 / #4). There is no speed or pause option.
    return cmd + ['--period', '1.0']


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--phase', choices=list(PHASE_ARGS),
                        help='Takeoff/landing test at KSFO 28R with the runway protocols')
    parser.add_argument('--instance', type=int, help='0 = default ports, N = ports + 10*N '
                        '(default 1, or 0 with --phase)')
    parser.add_argument('--aircraft', default=DEFAULT_AIRCRAFT, help='738-flies (default), 738 = stock 737, c172p')
    parser.add_argument('--fg', default=str(DEFAULT_FG), help='FlightGear install dir, or an fgfs/AppImage file (or set FG_INSTALL)')
    parser.add_argument('--print', action='store_true', help='Only print the command')
    parser.add_argument('--name', help='Session name (required to launch): what this session is for')
    from .fg_graphics import add_argument as add_graphics_argument
    add_graphics_argument(parser)
    parser.add_argument('--fly', nargs='?', const='connectome', choices=['connectome', 'standin'],
                        help='With --phase: start the fly-brain controller as soon as FlightGear is ready '
                             '(default brain: connectome)')
    parser.add_argument('extra', nargs='*', help='Extra fgfs arguments (after --)')
    args = parser.parse_args()
    if args.instance is None:
        args.instance = 0 if args.phase else 1
    if not 0 <= args.instance <= 50:
        parser.error('--instance must be 0..50')
    if not args.print and not (args.name or '').strip():
        parser.error('A FlightGear session needs a name: --name "what this session is testing"')
    cmd = command(args)
    # Graphics profile (fg_graphics.py) goes before the user's extra args so those still win.
    from .fg_graphics import profile_args
    at = next(i for i, a in enumerate(cmd) if a.startswith('--fg-aircraft='))
    cmd[at:at] = profile_args(args.graphics)
    # Refuse a --state the aircraft doesn't define (FlightGear would ignore it; issue #2).
    from .aircraft_states import check_command
    try:
        warning = check_command(cmd)
    except ValueError as exc:
        parser.error(str(exc))
    if warning:
        print('Warning:', warning, file=sys.stderr)
    env = dict(os.environ)
    if args.instance:
        base = Path(os.environ.get('APPDATA', Path.home())) / f'flightgear.org-instance{args.instance}'
        base.mkdir(parents=True, exist_ok=True)
        env['FG_HOME'] = str(base)
    if not args.print:
        problem = install_protocols(Path(args.fg))
        if problem:
            print('WARNING:', problem)
    print(' '.join(cmd))
    p = ports(args.instance)
    if args.phase and not args.fly:
        wait = ('The engines start already running; once the 737 is on the runway'
                if args.phase == 'takeoff' else 'Once the sim is flying (the controller hands over the autopilot)')
        print(f'\n{wait}, in a second terminal run:\n\n    {controller_command(args)}\n\n'
              'For the real fly brain use --brain connectome (see docs/TAKEOFF_LANDING.md), '
              'or relaunch with --fly to start it automatically.')
    else:
        print(f'Controller flags: --telemetry-port {p["telemetry"]} --control-port {p["control"]}')
    if not args.print:
        # Every session is logged and pushed; the watchdog reads the name from fgfs's args.
        from .session import ensure_watchdog, name_arg
        cmd.insert(1, name_arg(args.name))
        ensure_watchdog()
        subprocess.Popen(cmd, env=env)
        if args.phase and args.fly:
            print('Waiting for FlightGear to load, then the fly brain takes the controls...', flush=True)
            if not wait_ready(p['telnet']):
                print('FlightGear did not finish loading; start the controller by hand:\n    '
                      + ' '.join(fly_command(args)))
                return 1
            print(' '.join(fly_command(args)), flush=True)
            return subprocess.call(fly_command(args))
    return 0


if __name__ == '__main__':
    sys.exit(main())
