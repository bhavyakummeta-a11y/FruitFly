import contextlib
import io
import math
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch,Mock
from flight_simulator.flies import TakeoffFly,LandingFly,StandInBrain
from flight_simulator.runway import RunwayState,KT,FT,AirlinerControls,RunwaySim,takeoff_start
from flight_simulator.mission import Mission,CircuitFly,run_flightgear
from flight_simulator.runlog import outcome_label


class DelayedWorker:
    """Deterministic simulated computation delay; no FlightGear or wall-clock sleep."""
    def __init__(self,brain,delay):
        self.brain=brain;self.delay=delay;self.pending=None;self.records=[];self.skipped=0
    @property
    def busy(self):return self.pending is not None
    def submit(self,t,owner,inputs,missed=0):
        self.pending=(t,owner,inputs,self.brain.run(inputs,TakeoffFly.readouts));return True
    def poll(self,t):
        if not self.pending or t-self.pending[0]<self.delay:return None
        start,owner,inputs,rates=self.pending;self.pending=None
        r={'started':start,'applied':t,'latency_s':t-start,'brain_wall_s':self.delay}
        self.records.append(r)
        return (owner,inputs,rates),r


class StabilityTests(unittest.TestCase):
    def test_flare_checks_pitch_and_upward_rotation_before_tail_strike(self):
        fly = LandingFly(StandInBrain())
        s = RunwayState(agl=5*FT, speed=130*KT, on_ground=False,
                        pitch=math.radians(9), pitch_rate=math.radians(1))
        rates = fly.brain.run(fly.neutral_inputs(), fly.readouts)
        rates['DNp07'] = 200
        fly.decode(rates, s)
        self.assertLessEqual(math.degrees(fly.q_cmd), -1)
        s.agl = 500*FT
        fly.decode(rates, s)
        self.assertGreater(math.degrees(fly.q_cmd), -1)

    def test_ground_authority_falls_with_speed_and_damps_yaw(self):
        fly=TakeoffFly(StandInBrain());fly.ground_steer=.9
        low=fly.ground_rudder(RunwayState(speed=20),1)
        high=fly.ground_rudder(RunwayState(speed=118*KT),1)
        self.assertLess(high,low*.4)
        self.assertGreater(high,0)
        damped=fly.ground_rudder(RunwayState(speed=118*KT,yaw_rate=.06),1)
        self.assertLess(damped,high)
        self.assertLessEqual(abs(fly.ground_rudder(RunwayState(speed=60),.05)),.6*.05)

    def test_delayed_noisy_takeoff_reaches_rotation_without_reject(self):
        for delay in (.2,.7):
            with self.subTest(delay=delay):
                brain=StandInBrain(noise_seed=2)
                fly=TakeoffFly(brain,.25);fly.calibrate()
                fly.worker=DelayedWorker(brain,delay)
                sim=RunwaySim(takeoff_start(y=2),yaw_disturbance=.002)
                maximum=0
                for _ in range(2400):
                    s=sim.state
                    c=fly.step(s,.05);sim.step(c,.05)
                    if s.on_ground:maximum=max(maximum,abs(s.y))
                    if sim.events.liftoff_x is not None or fly.status.done or sim.events.left_runway:break
                self.assertIsNotNone(sim.events.liftoff_x,(maximum,fly.rejected,sim.state))
                self.assertFalse(fly.rejected)
                self.assertLess(maximum,8)

    def test_stale_ground_decision_is_not_applied_at_speed(self):
        fly=TakeoffFly(StandInBrain(),.25);fly.worker=DelayedWorker(fly.brain,1.5)
        s=RunwayState(speed=100*KT)
        fly.step(s,.05);s.time=1.5;fly.step(s,.05)
        self.assertEqual(fly.decisions,[])
        self.assertEqual(fly.stale_decisions,1)
        self.assertFalse(fly.worker.records[0]['accepted'])

    def test_reject_uses_two_raw_suppressed_trials_and_stays_latched(self):
        fly=TakeoffFly(StandInBrain());s=RunwayState(speed=100*KT,y=12)
        inputs=fly.sensory_inputs(s)
        normal=fly.brain.run(fly.neutral_inputs(),fly.readouts)
        fly._apply(fly.neutral_inputs(),normal,s)
        low={**normal,'MN9':0}
        fly._apply(inputs,low,s);self.assertFalse(fly.rejected)
        fly._apply(inputs,low,s);self.assertTrue(fly.rejected)
        s.y=0;fly._apply(fly.neutral_inputs(),normal,s)
        self.assertEqual((fly.throttle,fly.brake),(0,1))
        self.assertTrue(fly.rejected)

    def test_centerline_reject_cue_has_hysteresis(self):
        fly=TakeoffFly(StandInBrain());s=RunwayState(speed=50,y=9)
        self.assertEqual(fly.encode(s)['bitter'],200)
        s.y=6;self.assertEqual(fly.encode(s)['bitter'],200)
        s.y=3;self.assertEqual(fly.encode(s)['bitter'],0)

    def test_safe_reject_is_not_reported_as_collision_or_successful_takeoff(self):
        self.assertEqual(outcome_label({'outcome':'takeoff_rejected','safe_reject':True},2),'takeoff_rejected')
        self.assertEqual(outcome_label({},2),'failed')
        self.assertEqual(outcome_label({'collision':True},2),'COLLISION')


class MissionRealtimeTests(unittest.TestCase):
    def test_handover_does_not_calibrate_or_accept_previous_phase_result(self):
        with contextlib.redirect_stdout(io.StringIO()):
            m=Mission(StandInBrain(),calibrate=False,log=lambda *a:None)
            m.prepare_realtime()
            worker=m.worker
            worker.submit(0,m.fly.name,m.fly.neutral_inputs());worker.close()
            m.fly.status.done=True
            s=RunwayState(time=.1,speed=90,agl=1000*FT,on_ground=False)
            with patch.object(CircuitFly,'calibrate',side_effect=AssertionError('in-flight calibration')):
                m.step(s,.05)
            self.assertIsInstance(m.fly,CircuitFly)
            self.assertIs(m.fly.worker,worker)
            self.assertFalse(worker.records[0]['accepted'])
            self.assertEqual(worker.records[0]['discard_reason'],'phase_changed')
            self.assertEqual(m.fly.decisions,[])
            worker.close()

    def test_live_mission_keeps_sending_without_pause_while_brain_is_busy(self):
        gate=threading.Event()
        class Slow(StandInBrain):
            def run(self,inputs,readouts=None):
                gate.wait(2)
                return super().run(inputs,readouts)
        class Bridge:
            def __init__(self,*a,**kw):
                self.time=-.05;self.last_controls=AirlinerControls(brake=1);self.sent=[]
            def read(self):
                self.time+=.05
                return RunwayState(time=self.time)
            def send(self,c):self.sent.append(c)
            def freeze(self,*a):raise AssertionError('in-flight freeze')
            def close(self):return True
        bridge=Bridge();guard=Mock();speed=Mock(events=[])
        args=SimpleNamespace(telemetry_port=5501,control_port=5502,seconds=.5,no_fly_body=True,brain='standin')
        m=Mission(Slow(),calibrate=False,log=lambda *a:None)
        try:
            with patch('flight_simulator.flightgear.RunwayFlightGear',return_value=bridge), \
                 patch('flight_simulator.flightgear.AutopilotGuard',return_value=guard), \
                 patch('flight_simulator.flightgear.SpeedLock',return_value=speed), \
                 patch('flight_simulator.flightgear.hand_over',return_value=True),contextlib.redirect_stdout(io.StringIO()):
                start=time.monotonic();r=run_flightgear(m,args,[])
                self.assertLess(time.monotonic()-start,.5)
            self.assertGreater(len(bridge.sent),5)
            guard.wait_off.assert_called_once()
            self.assertTrue(guard.check.called and speed.check.called)
            self.assertEqual(r['termination_reason'],'time_limit')
        finally:
            gate.set()
            if m.worker:m.worker.close()


if __name__=='__main__':unittest.main()
