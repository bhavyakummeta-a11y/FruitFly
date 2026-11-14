"""No-autopilot rule: the fly NEVER uses the airplane's autopilot or autothrottle.

Guard behaviour is tested against a fake FlightGear telnet server (no FlightGear
needed); the lint tests stop repo code from engaging an autopilot, reintroducing
an override, or dropping the guard from the controllers.
"""
from pathlib import Path
import re
import socket
import socketserver
import subprocess
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from flight_simulator.flightgear import (AUTOPILOT_OFF, AutopilotEngaged,  # noqa: E402
                                         AutopilotGuard, autopilot_value_engaged)


class FakeFG(socketserver.ThreadingTCPServer):
    """Minimal FlightGear telnet server: data / get / set / quit. Missing nodes
    answer '-ERR ...' like FlightGear. `sticky` props snap back on after a set."""
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, props, sticky=()):
        self.props, self.sticky = dict(props), set(sticky)
        super().__init__(('127.0.0.1', 0), self.Handler)
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def port(self):
        return self.server_address[1]

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            for raw in self.rfile:
                parts = raw.decode().strip().split(' ', 2)
                cmd = parts[0]
                if cmd == 'quit':
                    return
                if cmd == 'get':
                    v = self.server.props.get(parts[1])
                    self.wfile.write((f'-ERR Node "{parts[1]}" not found.' if v is None else v).encode() + b'\r\n')
                elif cmd == 'set':
                    path, value = parts[1], parts[2] if len(parts) > 2 else ''
                    self.server.props[path] = '1' if path in self.server.sticky else value


class ValueParsing(unittest.TestCase):
    def test_engaged_values(self):
        for v in ('1', 'true', '1.0', 'dg-heading-hold', 'altitude-hold'):
            self.assertTrue(autopilot_value_engaged(v), v)
        for v in ('', '0', '0.0', 'false', 'FALSE', '-ERR Node "/x" not found.', None):
            self.assertFalse(autopilot_value_engaged(v), v)

    def test_off_values_really_mean_off(self):
        for path, off in AUTOPILOT_OFF.items():
            self.assertFalse(autopilot_value_engaged(off), path)

    def test_guard_covers_737_c172_and_generic(self):
        for p in ('/autopilot/internal/CMDA', '/autopilot/internal/CMDB', '/autopilot/internal/SPD',
                  '/autopilot/KAP140/locks/roll-axis', '/autopilot/KAP140/locks/pitch-axis',
                  '/autopilot/locks/heading', '/autopilot/locks/altitude', '/autopilot/locks/speed'):
            self.assertIn(p, AUTOPILOT_OFF)


class Guard(unittest.TestCase):
    def guard(self, props, sticky=()):
        fg = FakeFG(props, sticky)
        self.addCleanup(fg.server_close)
        self.addCleanup(fg.shutdown)
        g = AutopilotGuard(fg.port)
        self.addCleanup(g.close)
        return fg, g

    def test_no_telnet_means_no_flying(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            free = s.getsockname()[1]
        with self.assertRaisesRegex(AutopilotEngaged, 'Cannot verify'):
            AutopilotGuard(free, timeout=0.5)

    def test_all_off_passes_and_missing_nodes_count_as_off(self):
        fg, g = self.guard({'/autopilot/internal/CMDA': '0', '/autopilot/internal/SPD': 'false'})
        self.assertEqual(g.engaged(), [])
        g.wait_off(timeout=0.5)
        g.check(force=True)
        self.assertEqual(g.violations, [])

    def test_737_autopilot_and_autothrottle_forced_off_and_counted(self):
        fg, g = self.guard({'/autopilot/internal/CMDA': '1', '/autopilot/internal/SPD': '1'})
        g.check(force=True)
        self.assertEqual(g.violations, [['/autopilot/internal/CMDA', '/autopilot/internal/SPD']])
        self.assertEqual(fg.props['/autopilot/internal/CMDA'], '0')
        self.assertEqual(fg.props['/autopilot/internal/SPD'], '0')

    def test_c172_kap140_and_generic_locks_forced_off(self):
        fg, g = self.guard({'/autopilot/KAP140/locks/roll-axis': 'true',
                            '/autopilot/locks/heading': 'dg-heading-hold'})
        g.check(force=True)
        self.assertEqual(fg.props['/autopilot/KAP140/locks/roll-axis'], 'false')
        self.assertEqual(fg.props['/autopilot/locks/heading'], '')

    def test_autopilot_that_wont_turn_off_stops_the_run(self):
        fg, g = self.guard({'/autopilot/internal/CMDB': '1'}, sticky={'/autopilot/internal/CMDB'})
        with self.assertRaisesRegex(AutopilotEngaged, 'could not be switched off'):
            g.check(force=True)
        with self.assertRaisesRegex(AutopilotEngaged, 'will not take the controls'):
            g.wait_off(timeout=0.3)

    def test_wait_off_forces_leftover_autopilot_off(self):
        fg, g = self.guard({'/autopilot/internal/CMDA': '1'})
        g.wait_off(timeout=0.3)
        self.assertEqual(fg.props['/autopilot/internal/CMDA'], '0')

    def test_check_is_rate_limited(self):
        fg, g = self.guard({'/autopilot/internal/CMDA': '0'}, )
        g.every = 60
        g.check()
        fg.props['/autopilot/internal/CMDA'] = '1'
        g.check()  # within the interval: not polled
        self.assertEqual(g.violations, [])
        g.check(force=True)
        self.assertEqual(len(g.violations), 1)


def tracked(*globs):
    out = subprocess.run(['git', 'ls-files', '-z', *globs], cwd=ROOT, capture_output=True, text=True, check=True)
    return [f for f in out.stdout.split('\0') if f  # -z: filenames may contain spaces
            and not f.startswith(('tests/', 'flightgear/Aircraft/737-800/'))]  # stock 737 is upstream code


class Lint(unittest.TestCase):
    CODE = ('*.py', '*.nas', '*.xml', '*.ps1', '*.sh')
    ENGAGE = [
        (re.compile(r'keep-737-autopilot'), 'autopilot override switch (removed by the no-autopilot rule)'),
        (re.compile(r'autopilot737\.(?!ap_disengage\b)\w+'), 'calls a 737 autopilot function other than ap_disengage'),
        (re.compile(r'setprop\(\s*"/?autopilot/[^"]+"\s*,\s*(1|true|"[^"]+")\s*\)'), 'sets an autopilot property on'),
        (re.compile(r'\bset /autopilot/\S+ (1|true|[a-z][\w-]*-hold)\b'), 'telnet-sets an autopilot property on'),
        (re.compile(r'--prop:[^\s\'"]*/autopilot/\S*=(1|true)'), 'launch flag turns an autopilot on'),
        (re.compile(r'<node>\s*/autopilot/'), 'generic protocol reads/writes autopilot nodes'),
    ]

    def test_no_repo_code_engages_an_autopilot(self):
        problems = []
        for f in tracked(*self.CODE):
            for n, line in enumerate((ROOT / f).read_text(errors='ignore').splitlines(), 1):
                for pattern, why in self.ENGAGE:
                    if pattern.search(line):
                        problems.append(f'{f}:{n}: {why}: {line.strip()[:100]}')
        self.assertEqual(problems, [], 'No-autopilot rule violated:\n' + '\n'.join(problems))

    def test_controllers_keep_the_guard(self):
        for f in ('flight_simulator/__main__.py', 'flight_simulator/takeoff_landing.py'):
            src = (ROOT / f).read_text()
            for needle in ('AutopilotGuard(', '.wait_off()', 'ap_guard.check()'):
                self.assertIn(needle, src, f'{f} lost {needle}: the fly must not fly unguarded')

    def test_737_overlay_locks_the_autopilot_out(self):
        nas = (ROOT / 'flightgear/Aircraft/FlyCabin/Nasal/fruitfly.nas').read_text()
        self.assertIn('enforce_no_ap', nas)
        for prop in ('CMDA', 'CMDB', 'SPD'):
            self.assertIn(f'"/autopilot/internal/{prop}"', nas)
        self.assertRegex(nas, r'foreach \(var p; AP_ON\) setlistener\(p, enforce_no_ap')


if __name__ == '__main__':
    unittest.main()
