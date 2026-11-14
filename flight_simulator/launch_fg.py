"""Launch an extra FlightGear instance on its own ports, for side-by-side runs.

Instance 0 uses the documented ports (httpd 8080, telnet 5500, UDP 5501/5502).
Instance N adds 10*N to every port, so instance 1 is 8090 / 5510 / 5511 / 5512.
Each instance gets its own FG_HOME so they don't fight over FlightGear's lock
file and autosave.

    python -m flight_simulator.launch_fg --instance 1
    python -m flight_simulator --backend flightgear --brain reflex \
        --telemetry-port 5511 --control-port 5512

Start with --print to see the command without launching anything.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

DEFAULT_FG = Path(os.environ.get('FG_INSTALL', r'D:\FlightGear'))
# Project default aircraft: 737-800 with fly passengers (run flightgear/setup_aircraft.py once).
REPO_AIRCRAFT = Path(__file__).resolve().parent.parent / 'flightgear' / 'Aircraft'
DEFAULT_AIRCRAFT = '738-flies'
# In-air start speed. 100 kt is fine for the C172 but stalls a 737.
START_KT = {'c172p': 100}


def ports(instance):
    k = 10 * instance
    return {'httpd': 8080 + k, 'telnet': 5500 + k, 'telemetry': 5501 + k, 'control': 5502 + k}


def command(args):
    p = ports(args.instance)
    fg = Path(args.fg)
    return [str(fg / 'bin' / 'fgfs.exe' if os.name == 'nt' else fg / 'bin' / 'fgfs'),
            f'--fg-root={fg / "data"}', f'--fg-aircraft={REPO_AIRCRAFT}', f'--aircraft={args.aircraft}',
            f'--httpd={p["httpd"]}', f'--telnet={p["telnet"]}',
            '--lat=37.55', '--lon=-122.75', '--altitude=3000', '--heading=0', f'--vc={START_KT.get(args.aircraft, 220)}',
            '--in-air', '--state=cruise', '--disable-real-weather-fetch', '--wind=0@0',
            '--timeofday=noon', '--disable-ai-traffic',
            f'--generic=socket,out,20,127.0.0.1,{p["telemetry"]},udp,flybrain-state',
            f'--generic=socket,in,20,127.0.0.1,{p["control"]},udp,flybrain-controls',
            *args.extra]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--instance', type=int, default=1, help='0 = default ports, N = ports + 10*N')
    parser.add_argument('--aircraft', default=DEFAULT_AIRCRAFT, help='738-flies (default), 738 = stock 737, c172p')
    parser.add_argument('--fg', default=str(DEFAULT_FG), help='FlightGear install dir (or set FG_INSTALL)')
    parser.add_argument('--print', action='store_true', help='Only print the command')
    parser.add_argument('extra', nargs='*', help='Extra fgfs arguments (after --)')
    args = parser.parse_args()
    if not 0 <= args.instance <= 50:
        parser.error('--instance must be 0..50')
    cmd = command(args)
    env = dict(os.environ)
    if args.instance:
        base = Path(os.environ.get('APPDATA', Path.home())) / f'flightgear.org-instance{args.instance}'
        base.mkdir(parents=True, exist_ok=True)
        env['FG_HOME'] = str(base)
    print(' '.join(cmd))
    p = ports(args.instance)
    print(f'Controller flags: --telemetry-port {p["telemetry"]} --control-port {p["control"]}')
    if not args.print:
        subprocess.Popen(cmd, env=env)
    return 0


if __name__ == '__main__':
    sys.exit(main())
