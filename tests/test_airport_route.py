"""Airport frames, destination completion and known-obstacle route regression."""
import contextlib
from dataclasses import replace
import io
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flight_simulator.airport_route import (AirportRoute, RouteMission, RouteFly, DestinationLanding,
                                            LAX, BUR, run_local, RouteView)
from flight_simulator.flies import StandInBrain
from flight_simulator.flightgear import RunwayFlightGear
from flight_simulator.runway import RunwayState, FT, KT
from flight_simulator.core import Obstacle
from flight_simulator.launch_fg import command, fly_command

class AirportGeometryTests(unittest.TestCase):
    def test_distinct_airports_and_reversible_heading_altitude_frames(self):
        route=AirportRoute()
        a=RunwayState(x=400,y=10,agl=300,psi=.1,speed=75,on_ground=False)
        world=route.to_departure(a)
        self.assertGreater(math.hypot(world.x,world.y),25000)
        self.assertAlmostEqual(world.agl,300+(727.4-94.3)*FT)
        back=route.to_arrival(world)
        for k in ('x','y','agl','psi'): self.assertAlmostEqual(getattr(a,k),getattr(back,k),places=6)
        self.assertEqual((LAX.airport,BUR.airport),('KLAX','KBUR'))

    def test_final_points_at_burbank_and_descends_to_its_datum(self):
        route=AirportRoute();fly=RouteFly(StandInBrain(),.25,route)
        fly.leg_index=len(fly.legs)-1
        state=route.to_departure(RunwayState(x=-5500,agl=1000*FT,on_ground=False))
        self.assertAlmostEqual(fly.altitude_target(state),
            (727.4-94.3)*FT+(5500+300)*math.tan(math.radians(3)),delta=3)
        end=route.to_arrival(RunwayState(x=fly.leg.x1,y=fly.leg.y1))
        self.assertAlmostEqual(end.x,0,places=5);self.assertAlmostEqual(end.y,0,places=5)

    def test_wrong_airport_and_misalignment_rejected(self):
        route=AirportRoute();route.check_start(RunwayState(x=300))
        for s in (RunwayState(x=90000),RunwayState(y=100),RunwayState(psi=math.pi),RunwayState(on_ground=False)):
            with self.assertRaises(ValueError):route.check_start(s)

    def test_launcher_selects_lax_and_full_mission(self):
        args=SimpleNamespace(instance=0,fg='/tmp/fg',aircraft='738-flies',extra=[],phase='takeoff',
                             route='lax-burbank',fly='connectome')
        cmd=command(args)
        self.assertIn('--airport=KLAX',cmd);self.assertIn('--runway=25R',cmd)
        self.assertIn('--prop:/controls/gear/brake-parking=1',cmd)
        controller=fly_command(args)
        self.assertIn('flight_simulator.mission',controller)
        self.assertIn('lax-burbank',controller)

    def test_live_msl_not_terrain_agl_drives_airport_altitude(self):
        bridge=RunwayFlightGear(0,5502,runway=(LAX.lat,LAX.lon,LAX.heading),elevation_ft=LAX.elevation_ft)
        self.addCleanup(bridge.rx.close);self.addCleanup(bridge.tx.close)
        fields=[0,LAX.lat,LAX.lon,8,LAX.heading,0,0,0,0,1,0,50,50,LAX.elevation_ft+8]
        packet=lambda f:(','.join(map(str,f))+'\n').encode()
        first=bridge.parse(packet(fields));self.assertAlmostEqual(first.agl,0)
        fields[0]=1;fields[3]=508;fields[9]=0;fields[13]=5008
        s=bridge.parse(packet(fields))
        self.assertAlmostEqual(s.agl,(5000-LAX.elevation_ft)*FT)
        self.assertAlmostEqual(s.terrain_agl,500*FT)
        with self.assertRaisesRegex(ValueError,'MSL telemetry'):bridge.parse(packet(fields[:-1]))

    def test_terrain_clearance_does_not_replace_destination_glideslope(self):
        f=RouteFly(StandInBrain(),.25,AirportRoute())
        s=RunwayState(agl=6000*FT,terrain_agl=100)
        self.assertGreater(f.altitude_target(s),s.agl)
        f.leg_index=len(f.legs)-1
        s=f.route.to_departure(RunwayState(x=-1000,agl=100,terrain_agl=100))
        self.assertLess(f.altitude_target(s),s.agl)

class RouteBehaviorTests(unittest.TestCase):
    def test_destination_landing_waits_for_stop(self):
        f=DestinationLanding(StandInBrain())
        f.check(RunwayState(speed=20*KT));self.assertFalse(f.status.done)
        f.check(RunwayState(speed=.5));self.assertTrue(f.status.done)
        c=f.step(RunwayState(speed=5),.05)
        self.assertEqual((c.throttle,c.brake),(0,1))

    def test_obstruction_on_final_requests_go_around(self):
        f=DestinationLanding(StandInBrain())
        f.vision_obstacles=[Obstacle('blocked runway',0,-500,100,0,300)]
        f.step(RunwayState(x=-1000,agl=100,speed=70,on_ground=False),.05)
        self.assertTrue(f.go_around)

    def test_route_obstacles_reach_brain_without_cutting_cruise_appetite(self):
        r=AirportRoute();f=RouteFly(StandInBrain(),.25,r);f.leg_index=1
        f.vision_obstacles=r.obstacles
        o=r.obstacles[0];h=f.leg.course
        s=RunwayState(x=o.north-3000*math.cos(h),y=o.east-3000*math.sin(h),
                      psi=h,agl=1500,speed=90,on_ground=False)
        inputs=f.sensory_inputs(s)
        self.assertGreater(inputs['looming'],0);self.assertEqual(inputs['bitter'],0)
        self.assertTrue(f.avoidance)

    def test_companion_keeps_global_frame_across_handover(self):
        m=RouteMission(StandInBrain(),calibrate=False,log=lambda *a:None)
        m.last_state=m.route.to_departure(RunwayState(x=-1000,agl=100,on_ground=False))
        m.fly=DestinationLanding(m.brain)
        sink=Mock();view=RouteView(m,sink)
        frame=dict(inputs={},target_altitude_m=100,cross_track_m=0,heading_error_deg=0,altitude_error_m=0,alerts=[])
        view.send(frame)
        result=sink.send.call_args.args[0]
        self.assertEqual(result['runway']['name'],'KBUR 08')
        self.assertAlmostEqual(result['state']['altitude'],727.4*FT+100)
        self.assertGreater(len(result['route']),3)
        self.assertEqual(len(result['obstacles']),2)

    def test_live_runner_uses_arrival_frame_for_touchdown_and_runway_bounds(self):
        from flight_simulator.mission import run_flightgear
        m=RouteMission(StandInBrain(),calibrate=False,log=lambda *a:None)
        m.vision_obstacles=[]
        landing=DestinationLanding(m.brain)
        states=[RunwayState(), RunwayState(time=.1),
                m.route.to_departure(RunwayState(time=.2,x=-500,agl=50,speed=70,on_ground=False)),
                m.route.to_departure(RunwayState(time=.3,x=500,speed=60)),
                m.route.to_departure(RunwayState(time=.4,x=1200,speed=0)),
                m.route.to_departure(RunwayState(time=.5,x=1200,speed=0))]
        bridge=Mock()
        bridge.read.side_effect=states
        bridge.close.return_value=True
        def step(s,dt):
            from flight_simulator.runway import AirlinerControls
            if s.time>=.2:
                m.fly=landing
                m.fly.check(m.control_state(s))
            return AirlinerControls(throttle=0,brake=1)
        m.step=step
        args=SimpleNamespace(telemetry_port=5501,control_port=5502,seconds=10,no_fly_body=True,brain='standin')
        with patch('flight_simulator.flightgear.RunwayFlightGear',return_value=bridge), \
             patch('flight_simulator.flightgear.AutopilotGuard'), \
             patch('flight_simulator.flightgear.SpeedLock',return_value=Mock(events=[])), \
             patch('flight_simulator.flightgear.hand_over',return_value=True), \
             patch('flight_simulator.takeoff_live.parking_brake',return_value=True), \
             patch('flight_simulator.fg_scene.ObstacleScene'), contextlib.redirect_stdout(io.StringIO()):
            r=run_flightgear(m,args,[])
        self.assertTrue(r['success'],r)
        self.assertEqual(r['touchdown_x_m'],500)
        self.assertAlmostEqual(r['stop_x_m'],1200,places=5)
        bridge.freeze.assert_not_called()

    def test_full_route_avoids_both_obstacles_and_stops_at_burbank(self):
        with contextlib.redirect_stdout(io.StringIO()):
            m=RouteMission(StandInBrain(),log=lambda *a:None)
            r=run_local(m,progress=False)
        self.assertTrue(r['success'],r)
        self.assertEqual(r['destination'],'KBUR 08')
        self.assertGreaterEqual(r['avoidance_count'],2)
        self.assertGreater(r['minimum_clearance_m'],150)
        self.assertLess(r['stop_x_m'],BUR.length)
        self.assertLess(r['touchdown_sink_fpm'],500)

if __name__=='__main__':unittest.main()
