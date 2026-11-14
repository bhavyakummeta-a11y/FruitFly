import json
import math
import socket
import unittest
from flight_simulator.core import State, Obstacle
from flight_simulator.vision import scene, phase_scene, visual_escape, project_polygon, VisionPublisher
from flight_simulator.flies import TakeoffFly, LandingFly, StandInBrain
from flight_simulator.runway import RunwayState


class VisionTests(unittest.TestCase):
    def test_path_and_height_errors_become_bounded_brain_inputs(self):
        f=scene(State(east=250,altitude=950,heading=.4),altitude=900)
        self.assertGreater(f['inputs']['hs_left'],f['inputs']['hs_right'])
        self.assertLess(f['inputs']['vs_left'],100)
        self.assertIn('OFF PATH',f['alerts'])
        self.assertIn('HEADING DEVIATION',f['alerts'])
        self.assertTrue(all(0<=x<=200 for x in f['inputs'].values()))

    def test_heading_wrap_does_not_report_full_circle(self):
        f=scene(State(heading=math.radians(1)),heading=math.radians(359))
        self.assertAlmostEqual(f['heading_error_deg'],2)

    def test_obstacles_behind_do_not_trigger_looming(self):
        f=scene(State(),[Obstacle('behind',0,-1000,100)])
        self.assertEqual(f['inputs']['looming'],0)
        ahead=scene(State(),[Obstacle('ahead',0,700,100)])
        self.assertGreater(ahead['inputs']['looming'],0)

    def test_projection_clips_behind_camera(self):
        s=scene(State(altitude=0))['state']
        self.assertEqual(project_polygon(s,[(-1,-10,0),(1,-10,0),(0,-20,1)]),[])
        p=project_polygon(s,[(-1,-2,0),(1,10,0),(0,10,1)])
        self.assertTrue(p)
        self.assertTrue(all(math.isfinite(v) and abs(v)<=90 for pair in p for v in pair))

    def test_runway_threshold_datum_and_glideslope(self):
        fly=LandingFly(StandInBrain())
        s=RunwayState(x=-1000,y=40,agl=150,speed=70,on_ground=False)
        f=phase_scene(fly,s,fly.encode(s))
        self.assertEqual(f['state']['east'],40)
        self.assertEqual(f['runway_distance_m'],1000)
        self.assertIn('OFF GLIDESLOPE',f['alerts'])
        self.assertEqual(f['datum'],'above runway')

    def test_obstacle_does_not_turn_into_runway_flare_stimulus(self):
        fly=LandingFly(StandInBrain())
        fly.vision_obstacles=[Obstacle('approach hazard',0,-700,100,0,200)]
        s=RunwayState(x=-1000,agl=100,speed=70,on_ground=False)
        original=fly.encode(s)
        cues=fly.sensory_inputs(s)
        self.assertEqual(cues['looming'],original['looming'])
        self.assertGreater(cues['bitter'],0)

    def test_phase_brain_receives_obstacle_cues(self):
        class Recording(StandInBrain):
            def run(self, inputs, readouts=None):
                self.received=dict(inputs)
                return super().run(inputs,readouts)
        brain=Recording();fly=TakeoffFly(brain)
        fly.vision_obstacles=[Obstacle('blocked runway',0,600,100,0,200)]
        fly.step(RunwayState(speed=40),.05)
        self.assertGreater(brain.received['bitter'],0)
        self.assertEqual(brain.received,fly.decisions[-1].inputs)

    def test_cruise_brain_receives_full_map(self):
        class Brain:
            def run(self, inputs):
                self.inputs=inputs
                return {'DNp01':42}
        brain=Brain();cues=scene(State(east=200))['inputs']
        self.assertEqual(visual_escape(brain,cues),42)
        self.assertIn('hs_left',brain.inputs)
        self.assertIn('vs_right',brain.inputs)

    def test_udp_snapshot_retains_applied_sample_time(self):
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as receiver:
            receiver.bind(('127.0.0.1',0));receiver.settimeout(1)
            publisher=VisionPublisher(receiver.getsockname()[1])
            try:
                frame=scene(State(time=10))
                publisher.send(frame,{'looming':20},3,'test baseline')
                packet=json.loads(receiver.recv(65000))
                self.assertEqual(packet['time'],10)
                self.assertEqual(packet['applied_time'],3)
                self.assertEqual(packet['applied_inputs'],{'looming':20})
            finally:publisher.close()


if __name__=='__main__':unittest.main()
