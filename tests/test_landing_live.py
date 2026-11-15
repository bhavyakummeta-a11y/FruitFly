"""Live FlightGear landing fixes (2026-11-14 failure logs). Standard library only.

- Every FG landing sank 1,300-2,300 fpm right after the handover: the 737 spawns
  untrimmed (JSBSim trim fails) and the pitch reflex started at elevator 0 holding
  1.5 deg. Now it starts at the measured approach elevator/pitch (Paula's KLAX data).
- The first landing after that ballooned: the flare pitched 3.4 -> 8.5 deg and MN9
  put power back on (0.22 -> 0.59) over the runway, so it floated 700 m."""
import math
import unittest

from flight_simulator import flies, takeoff_landing
from flight_simulator.flies import LandingFly, StandInBrain, FT, KT
from flight_simulator.runway import RunwayState


def rates(**kw):
    r = {k: 0.0 for k in LandingFly.readouts}
    r.update({'MN9': 65.0, 'DNp20_L': 53.5, 'DNp20_R': 53.5, 'DNp15_R': 37.0})
    r.update(kw)
    return r


def flying(agl_ft, climb_fpm=-700.0, pitch_deg=3.7, **kw):
    return RunwayState(agl=agl_ft * FT, speed=145 * KT, on_ground=False, x=-500.0,
                       pitch=math.radians(pitch_deg), gamma=math.atan2(climb_fpm * FT / 60, 145 * KT), **kw)


class HandoverTrim(unittest.TestCase):
    def test_measured_approach_trim(self):
        self.assertEqual((takeoff_landing.FG_APPROACH_ELEVATOR, takeoff_landing.FG_APPROACH_PITCH), (-0.22, 3.7))


class Flare(unittest.TestCase):
    def fly(self):
        f = LandingFly(StandInBrain())
        f.trim_pitch_deg = 3.7
        return f

    def test_flare_latches_idle_and_stays_flare(self):
        f = self.fly()
        s = flying(60)
        f.decode(rates(DNp07=20.0, MN9=120.0), s)
        self.assertTrue(f.flaring)
        self.assertEqual(f.throttle, 0.0)
        f.decode(rates(DNp07=0.0, MN9=150.0), flying(40, climb_fpm=+200))   # a float: MN9 high
        self.assertEqual(f.throttle, 0.0, 'no power back on in the flare')
        f.check(flying(40))
        self.assertEqual(f.status.phase, 'FLARE')

    def test_idle_below_30_ft_even_without_a_flare(self):
        f = self.fly()
        f.decode(rates(DNp07=0.0, MN9=120.0), flying(20))
        self.assertEqual(f.throttle, 0.0)

    def test_approach_power_above_the_flare(self):
        f = self.fly()
        f.trim_throttle = 0.5
        f.decode(rates(DNp07=0.0, MN9=65.0), flying(300))
        self.assertAlmostEqual(f.throttle, 0.5)
        self.assertFalse(f.flaring)

    def test_no_pitch_up_once_the_sink_is_arrested(self):
        f = self.fly()
        f.decode(rates(DNp07=30.0), flying(40, climb_fpm=-900))
        self.assertGreater(f.q_cmd, 0)                         # sinking: the flare pitches up
        f.decode(rates(DNp07=30.0), flying(30, climb_fpm=+50))
        self.assertLessEqual(f.q_cmd, 0)                       # climbing: no balloon

    def test_flare_envelope_relative_to_the_approach_attitude(self):
        f = self.fly()
        cap = min(9.0, 3.7 + flies.FLARE_PITCH_ABOVE_APPROACH)
        f.decode(rates(DNp07=30.0), flying(40, climb_fpm=-900, pitch_deg=cap))
        self.assertLessEqual(f.q_cmd, 0)                       # at the cap: no more nose-up


if __name__ == '__main__':
    unittest.main()
