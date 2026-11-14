"""Guards against launching FlightGear with a --state the aircraft doesn't define (issue #2)."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from flight_simulator.aircraft_states import (REPO_AIRCRAFT, check_command,  # noqa: E402
                                              defined_states, find_set_xml)

ROOT = Path(__file__).resolve().parent.parent
REPO_IDS = sorted(p.name[:-len('-set.xml')] for p in REPO_AIRCRAFT.glob('*/*-set.xml'))


class StateParsing(unittest.TestCase):
    def test_reads_sim_state_names_and_follows_includes(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d) / 'Plane'
            d.mkdir()
            (d / 'base-set.xml').write_text(
                '<PropertyList><sim><state><name>take-off</name></state></sim>'
                '<autopilot><state type="int">0</state></autopilot></PropertyList>')
            (d / 'plane-set.xml').write_text(
                '<PropertyList include="base-set.xml"><sim><state n="1"><name>cruise</name>'
                '<name>approach</name></state></sim></PropertyList>')
            self.assertEqual(defined_states(d / 'plane-set.xml'), {'take-off', 'cruise', 'approach'})
            cmd = ['fgfs', f'--fg-aircraft={d.parent}', '--aircraft=plane']
            self.assertIsNone(check_command(cmd + ['--state=cruise']))
            with self.assertRaises(ValueError):
                check_command(cmd + ['--state=landing'])

    def test_738_flies_has_no_cruise_state(self):
        """Regression for issue #2: this exact command must be rejected."""
        cmd = ['fgfs', f'--fg-aircraft={REPO_AIRCRAFT}', '--aircraft=738-flies', '--state=cruise']
        with self.assertRaisesRegex(ValueError, "does not define state 'cruise'"):
            check_command(cmd)


class LauncherCommands(unittest.TestCase):
    def test_launch_fg_command_is_valid_for_every_repo_aircraft(self):
        from flight_simulator import launch_fg
        self.assertTrue(REPO_IDS, 'no aircraft found under flightgear/Aircraft')
        for aircraft in REPO_IDS + ['c172p']:
            with self.subTest(aircraft=aircraft):
                args = type('A', (), {'instance': 0, 'fg': r'D:\FlightGear', 'aircraft': aircraft,
                                      'extra': []})()
                cmd = launch_fg.command(args)
                check_command(cmd)  # raises on an undefined --state


class Lint(unittest.TestCase):
    """Any hard-coded --state=X in launcher code must exist on every repo aircraft."""
    # Backtick-quoted mentions (`--state=x`) are documentation, not arguments.
    PATTERN = re.compile(r'(?<!`)--state=([A-Za-z0-9_.-]+)')

    def test_no_hardcoded_undefined_state(self):
        files = subprocess.run(['git', 'ls-files', '*.py', '*.ps1', '*.sh', '*.bat'], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.split()
        files = [f for f in files if not f.startswith('tests/')]
        common = None
        for ac in REPO_IDS:
            s = defined_states(find_set_xml(ac, [REPO_AIRCRAFT]))
            common = s if common is None else common & s
        problems = []
        for f in files:
            for n, line in enumerate((ROOT / f).read_text(errors='ignore').splitlines(), 1):
                for state in self.PATTERN.findall(line):
                    if state not in (common or set()):
                        problems.append(f'{f}:{n}: --state={state} (not defined by every repo aircraft)')
        self.assertEqual(problems, [], '\n'.join(problems))


if __name__ == '__main__':
    unittest.main()
