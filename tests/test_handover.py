"""Ticket #1: the fly takes over an in-air start at once and holds the spawn preset."""
import math
import unittest
from unittest import mock

from flight_simulator import flightgear
from flight_simulator.core import State


class FakeBridge:
    def __init__(self, states):
        self.states = list(states)

    def read(self):
        return self.states.pop(0)


class HandoverTests(unittest.TestCase):
    def test_takes_over_while_sagging_no_level_wait(self):
        # Sinking 8 m/s after spawn: the old wait_until_steady blocked here for minutes.
        sag = State(time=2.0, altitude=850.0, speed=113.0, climb=-8.0, roll=math.radians(2))
        got = flightgear.wait_until_flying(FakeBridge([]), sag)
        self.assertIs(got, sag)

    def test_waits_only_until_flying_and_wings_near_level(self):
        rolled = State(time=1.0, speed=113.0, roll=math.radians(35))
        ok = State(time=1.5, speed=113.0, roll=math.radians(5))
        self.assertIs(flightgear.wait_until_flying(FakeBridge([ok]), rolled), ok)

    def test_targets_are_the_spawn_preset_not_the_sag(self):
        sag = State(altitude=850.0, speed=110.0)
        values = {'/sim/presets/altitude-ft': '3000', '/sim/presets/airspeed-kt': '220'}
        with mock.patch.object(flightgear, 'telnet_get', side_effect=lambda port, path: values[path]):
            alt, speed = flightgear.takeover_targets(5500, sag)
        self.assertAlmostEqual(alt, 914.4, places=1)
        self.assertAlmostEqual(speed, 113.18, places=1)

    def test_targets_fall_back_to_current_state(self):
        now = State(altitude=700.0, speed=50.0)
        with mock.patch.object(flightgear, 'telnet_get', return_value=None):
            self.assertEqual(flightgear.takeover_targets(5500, now), (700.0, 50.0))
        with mock.patch.object(flightgear, 'telnet_get', return_value='0'):   # runway start: no air preset
            self.assertEqual(flightgear.takeover_targets(5500, now), (700.0, 50.0))


if __name__ == '__main__':
    unittest.main()
