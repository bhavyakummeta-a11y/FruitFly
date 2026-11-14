"""Full flight: Takeoff fly -> Circuit fly -> Landing fly. Standard library only (stand-in brain)."""
import contextlib
import io
import math
import unittest

from flight_simulator import mission as M
from flight_simulator.flies import StandInBrain
from flight_simulator.runway import RunwaySim, RunwayState, AirlinerControls, FT


def fly_mission(brain=None):
    log = []
    with contextlib.redirect_stdout(io.StringIO()):
        m = M.Mission(brain or StandInBrain(), log=lambda *a: None)
        r = M.run_local(m, log=log, progress=False)
    return m, r, log


class MissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m, cls.r, cls.log = fly_mission(StandInBrain(noise_seed=1))

    def test_three_flies_handed_over_in_flight(self):
        flies = [h['to'] for h in self.r['handovers']]
        self.assertEqual(flies, ['Takeoff fly', 'Circuit fly', 'Landing fly'])
        self.assertEqual([h['state'] for h in self.r['handovers']], ['standing', 'cruising', 'flying'])
        self.assertAlmostEqual(self.r['handovers'][1]['agl_ft'], 1000, delta=60)   # takeoff handover
        self.assertGreater(self.r['handovers'][2]['agl_ft'], 700)                  # established on final

    def test_lands_on_the_runway(self):
        self.assertTrue(self.r['success'], self.r)
        self.assertLess(self.r['touchdown_sink_fpm'], 500)
        self.assertLess(abs(self.r['touchdown_y_m']), 10)

    def test_flies_the_whole_circuit(self):
        legs = [x['leg'] for x in self.log if x['leg']]
        order = [l for i, l in enumerate(legs) if i == 0 or l != legs[i - 1]]
        self.assertEqual(order, ['upwind', 'crosswind', 'downwind', 'base', 'final'])
        downwind = [x for x in self.log if x['leg'] == 'downwind' and -8000 < x['x'] < 6000]
        self.assertLess(max(abs(x['y'] - 5000) for x in downwind), 1000)

    def test_log_marks_the_active_brain_configuration(self):
        first = {}
        for x in self.log:
            first.setdefault(x['fly'], x['brain_state'])
        self.assertEqual(first, {'Takeoff fly': 'standing', 'Circuit fly': 'cruising', 'Landing fly': 'flying'})

    def test_noisy_missions_mostly_land(self):
        good = 0
        for seed in range(2, 6):
            _, r, _ = fly_mission(StandInBrain(noise_seed=seed, steer_bias=10))
            good += r['success']
        self.assertGreaterEqual(good, 3)


class HandoverMechanicsTests(unittest.TestCase):
    def test_controls_carry_over_at_handover(self):
        with contextlib.redirect_stdout(io.StringIO()):
            m = M.Mission(StandInBrain(), log=lambda *a: None)
        m.fly.elevator_i, m.fly.throttle = -0.3, 0.9
        m.fly.status.done = True
        s = RunwayState(agl=1000 * FT, speed=90, on_ground=False, gamma=0.1)
        m.step(s, 0.05)
        self.assertIsInstance(m.fly, M.CircuitFly)
        self.assertLess(abs(m.fly.elevator_i - (-0.3)), 0.05)   # haltere integrator carried over
        self.assertTrue(0.2 < m.fly.throttle <= 1.0)             # no cut to idle at handover

    def test_heading_wraps_after_a_full_turn(self):
        # A full circuit is 360 deg of turning: the runway-relative heading must wrap,
        # or the Landing fly sees itself 360 deg off and steers one way forever.
        sim = RunwaySim(RunwayState(agl=500, speed=80, on_ground=False, psi=math.radians(179)))
        sim.state.yaw_rate = math.radians(10)
        for _ in range(10):
            sim.step(AirlinerControls(throttle=0.5), 0.05)
        self.assertLess(abs(sim.state.psi), math.pi + 1e-9)

    def test_circuit_has_no_obstacle_avoidance_by_default(self):
        self.assertIsNone(M.CircuitFly.obstacle_slot)
        fly = M.CircuitFly(StandInBrain())
        self.assertEqual(fly.encode(RunwayState(agl=900, speed=90, on_ground=False))['looming'], 0.0)


if __name__ == '__main__':
    unittest.main()
