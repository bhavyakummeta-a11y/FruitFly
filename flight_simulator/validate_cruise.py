"""Headless JSBSim C172P validation. No FlightGear windows or network writes."""
import argparse
import csv
from dataclasses import asdict
import json
import math
from pathlib import Path
from .core import State,FlightController,sense
from .brain import ReflexBrain
from .scenery import to_local
from .__main__ import load_obstacles,ROOT


def validate(seconds=240,output=None,disturbance=False):
    if not math.isfinite(seconds) or seconds < .05:
        raise ValueError("Validation duration must be finite and at least 0.05 seconds")
    import jsbsim
    fdm=jsbsim.FGFDMExec(None)
    fdm.set_debug_level(0)
    if not fdm.load_model('c172p'):
        raise RuntimeError('JSBSim c172p model missing')
    fdm.set_dt(.01)
    origin=(37.60,-122.35)
    for k,v in {'ic/h-sl-ft':3000,'ic/vc-kts':100,'ic/lat-geod-deg':origin[0],
                'ic/long-gc-deg':origin[1],'ic/psi-true-deg':0}.items():
        fdm[k]=v
    fdm.run_ic()
    fdm['propulsion/set-running']=-1
    fdm.do_trim(0)
    def state():
        east,north=to_local(fdm['position/lat-geod-deg'],fdm['position/long-gc-deg'],origin)
        return State(fdm.get_sim_time(),east,north,fdm['position/h-sl-ft']*.3048,
                     fdm['attitude/psi-rad'],fdm['attitude/phi-rad'],fdm['attitude/theta-rad'],
                     fdm['velocities/vc-kts']*.514444,fdm['velocities/h-dot-fps']*.3048,
                     fdm['velocities/p-rad_sec'],fdm['velocities/q-rad_sec'])
    initial=state()
    controller=FlightController(initial.altitude,initial.heading,initial.speed,initial.pitch)
    obstacles=load_obstacles(ROOT/'scenarios/obstacles.json')
    controller.configure_course(obstacles)
    brain=ReflexBrain()
    rows=[];escape=0;next_brain=0
    for step in range(round(seconds/.05)):
        s=state()
        stimulus=sense(s,obstacles,horizon=max(25,s.speed/2))
        if s.time>=next_brain:
            escape=brain.escape(stimulus.looming_hz);next_brain=s.time+.5
        controls=controller.update(s,stimulus,escape)
        fdm['fcs/aileron-cmd-norm']=controls.aileron
        fdm['fcs/elevator-cmd-norm']=controls.elevator
        fdm['fcs/rudder-cmd-norm']=controls.rudder
        fdm['fcs/throttle-cmd-norm']=controls.throttle
        # A transient pitch-control disturbance tests recovery, not just trim.
        if disturbance and 45 <= s.time < 47:
            fdm['fcs/elevator-cmd-norm']=controls.elevator+.10
        clearance=min(o.clearance(s) for o in obstacles)
        rows.append({**asdict(s),**asdict(controls),'clearance':clearance,'phase':controller.phase,
                     'target_altitude':controller.altitude,'target_heading':controller.target_heading})
        if step%400==0:
            print(f'{s.time:.0f}s altitude error={s.altitude-controller.altitude:+.2f}m '
                  f'climb={s.climb:+.2f}m/s bank={math.degrees(s.roll):+.1f}deg clearance={clearance:.1f}m',flush=True)
        if clearance<=0 or abs(s.altitude-controller.altitude)>40:
            raise RuntimeError('JSBSim test exceeded altitude or obstacle bounds')
        for _ in range(5):
            fdm.run()
    result={'model':'JSBSim c172p','jsbsim_version':jsbsim.__version__,'seconds':seconds,
            'disturbance':disturbance,'minimum_clearance_m':min(r['clearance'] for r in rows),
            'maximum_altitude_error_m':max(abs(r['altitude']-initial.altitude) for r in rows),
            'final_cross_track_m':controller.guidance.cross_track,
            'avoidance_activations':controller.activations,
            'maximum_bank_deg':max(abs(math.degrees(r['roll'])) for r in rows)}
    if output:
        output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('w',newline='') as file:
            writer=csv.DictWriter(file,list(rows[0]));writer.writeheader();writer.writerows(rows)
        output.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=float,default=240)
    parser.add_argument('--output',default='runs/jsbsim-cruise.csv')
    parser.add_argument('--disturbance',action='store_true')
    args=parser.parse_args()
    validate(args.seconds,args.output,args.disturbance)
