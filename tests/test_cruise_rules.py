import json
import math
from pathlib import Path
import unittest
from flight_simulator.core import State, FlightController, DemoSimulator, Obstacle, sense


class CruiseRulesTests(unittest.TestCase):
    def test_github_descent_commands_pitch_up_and_keeps_power(self):
        data=json.loads((Path(__file__).parent/'fixtures/github_descent.json').read_text())['states']
        first=data[0]
        c=FlightController(first['altitude'],first['heading'],first['speed'],first['pitch'])
        c.configure_course([])
        commands=[]
        for row in data:
            s=State(**{key:value for key,value in row.items() if key in State.__dataclass_fields__})
            command=c.update(s,sense(s,[]),0)
            commands.append(command)
            self.assertGreater(c.target_pitch,s.pitch)
            self.assertGreaterEqual(command.throttle,.65)
        self.assertLess(commands[-1].elevator,data[-1]['elevator'])
        self.assertGreater(commands[-1].throttle,data[-1]['throttle'])

    def test_vertical_speed_changes_command_even_at_target_altitude(self):
        level=FlightController();sink=FlightController()
        for i in range(20):
            level.update(State(time=i*.05),sense(State(),[]),0)
            s=State(time=i*.05,climb=-4)
            sinking=sink.update(s,sense(s,[]),0)
        self.assertLess(sinking.elevator,level.last_controls.elevator-.1)
        self.assertGreater(sinking.throttle,level.last_controls.throttle)

    def test_multiple_obstacles_return_to_route_even_without_neural_escape(self):
        obstacles=[Obstacle('A',0,1300,150),Obstacle('B',350,3300,180),Obstacle('C',0,5400,200)]
        sim=DemoSimulator();c=FlightController();c.configure_course(obstacles)
        minimum=math.inf;max_error=0
        for _ in range(4800):
            s=sim.state
            command=c.update(s,sense(s,obstacles),0)
            sim.step(command,.05)
            minimum=min(minimum,*(o.clearance(s) for o in obstacles))
            max_error=max(max_error,abs(s.altitude-c.altitude))
        self.assertGreater(minimum,100)
        self.assertLess(max_error,10)
        self.assertLess(abs(sim.state.east),100)
        self.assertLess(abs(sim.state.heading),.1)
        self.assertGreater(sim.state.north,10000)
        self.assertGreaterEqual(c.activations,2)

    def test_neural_preference_selects_safe_side(self):
        from flight_simulator.guidance import RouteGuidance
        obstacle=Obstacle("ahead",0,1300,150)
        for turn in [-1,1]:
            guide=RouteGuidance(0)
            target,avoid=guide.choose(State(),[obstacle],0,math.radians(18),turn)
            self.assertTrue(avoid)
            self.assertGreater(target*turn,0)
            self.assertGreaterEqual(guide.clearance,guide.margin)

    def test_large_descent_reduces_bank_budget(self):
        c=FlightController();s=State(altitude=880,climb=-4)
        for i in range(20):
            s.time=i*.05
            c.update(s,sense(s,[]),0)
        self.assertLessEqual(abs(c.target_bank),math.radians(10))
        self.assertIn('ALTITUDE RECOVERY',c.phase)

    def test_process_monitor_sees_live_process_on_posix(self):
        import subprocess,sys
        from flight_simulator.session import Process
        p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)'])
        try:
            self.assertTrue(Process(p.pid).alive())
        finally:
            p.terminate();p.wait(timeout=5)


if __name__=='__main__':
    unittest.main()
