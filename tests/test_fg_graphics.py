"""Graphics profiles: every flag must be one FlightGear actually knows."""
import os
from pathlib import Path
import re
import unittest

from flight_simulator.fg_graphics import PROFILES, profile_args
from flight_simulator.session import parse_cmdline

OPTIONS = Path(os.environ.get('FG_INSTALL', r'D:\FlightGear')) / 'data' / 'options.xml'


class Profiles(unittest.TestCase):
    def test_profile_is_recorded_on_the_command_line(self):
        cmd = ' '.join(['fgfs.exe', *profile_args('light')])
        self.assertEqual(parse_cmdline(cmd)['graphics'], 'light')
        self.assertEqual(profile_args('full'), ['--prop:string:/fruitfly/graphics=full'])

    def test_light_caps_frame_rate_and_drops_trees(self):
        light = PROFILES['light']
        self.assertIn('--disable-random-vegetation', light)
        self.assertIn('--prop:/sim/frame-rate-throttle-hz=30', light)

    @unittest.skipUnless(OPTIONS.is_file(), 'FlightGear not installed here')
    def test_every_option_exists_in_this_flightgear(self):
        known = set(re.findall(r'<name>([a-z0-9-]+)</name>', OPTIONS.read_text(encoding='utf-8', errors='replace')))
        for flag in PROFILES['light']:
            if flag.startswith('--prop:'):
                continue
            name = flag[2:]
            base = re.sub(r'^(disable|enable)-', '', name)
            self.assertTrue(name in known or base in known, f'{flag} is not a FlightGear option')


if __name__ == '__main__':
    unittest.main()
