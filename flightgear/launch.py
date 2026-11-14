"""Start FlightGear with the fly-passenger 737-800 and the property server on.

    python flightgear/launch.py                      # KSFO 28R, cabin ready
    python flightgear/launch.py --airport KSEA --runway 16L
    python flightgear/launch.py --fgfs "D:/FlightGear/bin/fgfs.exe"
    python flightgear/launch.py --stock              # plain 737-800, no flies

Run setup_aircraft.py once first. Python then talks to the sim on
telnet port 5500 (same convention as flight_simulator/launch_fg.py) or http://localhost:8080 (see flightgear/README.md).
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = [
    os.environ.get("FGFS", ""),
    shutil.which("fgfs") or "",
    r"D:\FlightGear\bin\fgfs.exe",
    r"C:\Program Files\FlightGear 2024.1\bin\fgfs.exe",
    r"C:\Program Files\FlightGear\bin\fgfs.exe",
    "/Applications/FlightGear.app/Contents/MacOS/fgfs",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fgfs", help="path to fgfs (or set FGFS env var)")
    ap.add_argument("--airport", default="KSFO")
    ap.add_argument("--runway", default="28R")
    ap.add_argument("--stock", action="store_true", help="stock 737-800 without the cabin")
    ap.add_argument("--telnet", type=int, default=5500)
    ap.add_argument("--httpd", type=int, default=8080)
    ap.add_argument("--name", required=True,
                    help="session name (required): what this FlightGear session is for")
    sys.path.insert(0, os.path.dirname(HERE))
    from flight_simulator.fg_graphics import add_argument as add_graphics_argument, profile_args
    add_graphics_argument(ap)
    ap.add_argument("--no-wait", action="store_true",
                    help="one FlightGear at a time: exit instead of queueing if a sim is running")
    ap.add_argument("extra", nargs="*", help="extra fgfs args, after --")
    a = ap.parse_args()

    fgfs = a.fgfs or next((c for c in CANDIDATES if c and os.path.exists(c)), None)
    if not fgfs:
        sys.exit("fgfs not found: pass --fgfs or set FGFS")
    if not os.path.exists(os.path.join(HERE, "Aircraft", "737-800", "738-flies-set.xml")):
        sys.exit("Run python flightgear/setup_aircraft.py first")

    sys.path.insert(0, os.path.dirname(HERE))
    from flight_simulator.session import ensure_watchdog, name_arg

    cmd = [fgfs, name_arg(a.name), *profile_args(a.graphics),
           "--fg-aircraft=" + os.path.join(HERE, "Aircraft"),
           "--aircraft=" + ("738" if a.stock else "738-flies"),
           f"--airport={a.airport}", f"--runway={a.runway}",
           f"--telnet={a.telnet}", f"--httpd={a.httpd}",
           "--timeofday=noon", "--disable-real-weather-fetch",
           *a.extra]
    print(" ".join(f'"{c}"' if " " in c else c for c in cmd))
    # Every session is logged (live page) and pushed to sim-logs when FlightGear
    # closes: the watchdog spots this fgfs and reads the name from its command line.
    # One FlightGear at a time on this machine (flight_simulator/sim_queue.py).
    from flight_simulator.sim_queue import wait_for_turn
    queue, turn = wait_for_turn(a.name, wait=not a.no_wait)
    ensure_watchdog()
    queue.running(turn, subprocess.Popen(cmd).pid)


if __name__ == "__main__":
    main()
