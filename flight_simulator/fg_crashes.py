"""Which FlightGear crashes are the same bug? Read fgfs's own crash dumps.

FlightGear 2024 catches its crashes with Sentry/Crashpad and writes a minidump per crash
to %APPDATA%/flightgear.org/sentry_db/reports/*.dmp (Windows Error Reporting never sees
the mid-run ones). A minidump holds the exception code, the faulting address and the
loaded modules, so grouping crashes by `module+offset` tells which runs hit the same bug.
Each dump is matched to the FlightGear session (sim-logs runs/*/events.log) that exited
within a few seconds of it.

    python -m flight_simulator.fg_crashes            # last 20 crashes, grouped by fault site
    python -m flight_simulator.fg_crashes -n 50 --json

Read-only; standard library only. Without symbols the offset can't be turned into a
function name, but the same offset across runs means the same code path.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import struct
import sys

CODES = {0xC0000005: 'access violation', 0xC0000374: 'heap corruption',
         0x40000015: 'fatal app exit (abort)', 0xC0000409: 'stack buffer overrun'}
EXIT_RE = re.compile(r'^(\d\d:\d\d:\d\d) \[session\] FlightGear exited \(code (\d+|None)\)')


def dump_dir():
    return Path(os.environ.get('APPDATA', Path.home())) / 'flightgear.org' / 'sentry_db' / 'reports'


def parse_minidump(data):
    """{'code', 'address', 'site', 'access', 'target'} from a minidump's bytes."""
    if data[:4] != b'MDMP':
        raise ValueError('not a minidump')
    _, _, count, dir_rva = struct.unpack_from('<4sIII', data, 0)
    streams = {}
    for i in range(count):
        kind, size, rva = struct.unpack_from('<III', data, dir_rva + 12 * i)
        streams[kind] = (rva, size)
    modules = []
    if 4 in streams:                                   # ModuleListStream
        rva, _ = streams[4]
        n, = struct.unpack_from('<I', data, rva)
        for i in range(n):
            base, size, _, _, name_rva = struct.unpack_from('<QIIII', data, rva + 4 + 108 * i)
            length, = struct.unpack_from('<I', data, name_rva)
            name = data[name_rva + 4:name_rva + 4 + length].decode('utf-16-le', 'replace')
            modules.append((base, size, name.replace('\\', '/').rsplit('/', 1)[-1]))
    if 6 not in streams:                               # ExceptionStream
        return {'code': None, 'address': None, 'site': 'no exception record', 'access': '', 'target': None}
    rva, _ = streams[6]
    code, _, _, address, nparams = struct.unpack_from('<IIQQI', data, rva + 8)
    params = struct.unpack_from('<QQ', data, rva + 8 + 32) if nparams >= 2 else (None, None)
    site = next((f'{name}+0x{address - base:x}' for base, size, name in modules if base <= address < base + size),
                f'0x{address:x} (no module)')
    access = {0: 'read', 1: 'write', 8: 'execute'}.get(params[0], '') if code == 0xC0000005 else ''
    return {'code': code, 'address': address, 'site': site, 'access': access,
            'target': params[1] if access else None}


def session_exits(runs_dir):
    """[(datetime, run folder name, exit code)] from the session logs on this machine."""
    out = []
    for log in Path(runs_dir).glob('*/events.log'):
        day = log.parent.name[:10]                     # runs/<YYYY-MM-DD>T..._<who>_fg-<name>
        try:
            for line in log.read_text(encoding='utf-8', errors='replace').splitlines():
                m = EXIT_RE.match(line)
                if m:
                    out.append((datetime.strptime(f'{day} {m.group(1)}', '%Y-%m-%d %H:%M:%S'),
                                log.parent.name, m.group(2)))
        except (OSError, ValueError):
            continue
    return out


def crashes(n=20, runs_dir=None):
    files = sorted(dump_dir().glob('*.dmp'), key=lambda p: p.stat().st_mtime)[-n:]
    exits = session_exits(runs_dir) if runs_dir else []
    rows = []
    for f in files:
        when = datetime.fromtimestamp(f.stat().st_mtime)
        try:
            info = parse_minidump(f.read_bytes())
        except (OSError, ValueError, struct.error) as exc:
            info = {'code': None, 'site': f'unreadable ({exc})', 'access': '', 'target': None}
        # Session logs print local wall time; dumps are written a moment before the exit is seen.
        near = [e for e in exits if abs((e[0] - when).total_seconds()) <= 15]
        rows.append({'time': when.isoformat(timespec='seconds'), 'dump': f.name,
                     'code': f'0x{info["code"]:08X}' if info['code'] is not None else None,
                     'what': CODES.get(info['code'], ''), 'site': info['site'],
                     'access': info['access'], 'target': f'0x{info["target"]:x}' if info.get('target') is not None else None,
                     'session': near[0][1] if near else None})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-n', type=int, default=20, help='newest N dumps')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    runs = None
    try:
        from .runlog import runs_dir
        runs = runs_dir()
    except Exception:
        pass
    rows = crashes(a.n, runs)
    if a.json:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print(f'No FlightGear crash dumps in {dump_dir()}')
        return 0
    groups = {}
    for r in rows:
        groups.setdefault(r['site'], []).append(r)
    for site, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        first = items[0]
        print(f'{len(items)} x {site}  {first["code"] or ""} {first["what"]} {first["access"]}'.rstrip())
        for r in items:
            print(f'    {r["time"]}  {r["session"] or "(no matching session log)"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
