"""Synthetic fly view: python -m flight_simulator.vision_view [--port 5601]."""
import argparse
import json
import math
import socket
import time
from .vision import PORT, project_polygon, camera_point


class VisionView:
    def __init__(self):
        import matplotlib.pyplot as plt
        self.plt=plt
        self.fig=plt.figure(figsize=(14,8),layout='constrained')
        grid=self.fig.add_gridspec(2,2,height_ratios=[2,1])
        self.eye=self.fig.add_subplot(grid[0,0]);self.map=self.fig.add_subplot(grid[0,1])
        self.rates=self.fig.add_subplot(grid[1,0]);self.info=self.fig.add_subplot(grid[1,1])
        self.fig.canvas.manager.set_window_title('Fly sensory view — synthetic geometry')
        self.trail=[]
        self.last_time=None
        self.title=self.fig.suptitle('Waiting for controller on localhost — synthetic geometry, not a camera')

    def update(self, frame):
        from matplotlib.patches import Polygon, Circle
        for ax in [self.eye,self.map,self.rates,self.info]:ax.clear()
        s=frame['state'];runway=frame.get('runway')
        if self.last_time is not None and s['time']<self.last_time:self.trail=[]
        if s['time']!=self.last_time:
            self.trail.append((s['east'],s['north']))
            self.trail=self.trail[-3000:];self.last_time=s['time']
        self.title.set_text(f"Synthetic fly view | {frame['phase']} | {s['time']:.1f}s | {frame.get('brain','unknown')}")
        self.eye.set(xlim=(-80,80),ylim=(-60,60),xlabel='Right bearing (degrees)',ylabel='Up angle (degrees)',title='Aircraft-facing view — known geometry')
        if runway:self.eye.set(xlim=(-30,30),ylim=(-15,15))
        self.eye.set_facecolor('#eaf3fa');self.eye.axhline(0,color='#789',lw=.5);self.eye.axvline(0,color='#789',lw=.5)
        self.map.set(title='Runway and intended path',xlabel='East / right (m)',ylabel='North / along (m)')
        self.map.set_aspect('equal',adjustable='datalim');self.map.grid(alpha=.2)
        if runway:
            h=runway['heading'];sn,cs=math.sin(h),math.cos(h)
            corners=[]
            for right,along in [(-runway['width']/2,0),(runway['width']/2,0),(runway['width']/2,runway['length']),(-runway['width']/2,runway['length'])]:
                corners.append((runway['east']+right*cs+along*sn,runway['north']-right*sn+along*cs,runway['elevation']))
            points=project_polygon(s,corners)
            if len(points)>=3:self.eye.add_patch(Polygon(points,color='#555',alpha=.85))
            self.map.add_patch(Polygon([p[:2] for p in corners],color='#777',alpha=.6))
            self.map.plot([runway['east'],runway['east']+runway['length']*sn],
                          [runway['north'],runway['north']+runway['length']*cs],color='#555',lw=5,label='Runway')
            center=[]
            for along in range(0,int(runway['length'])+1,100):
                right,up,forward=camera_point(s,(runway['east']+along*sn,runway['north']+along*cs,runway['elevation']))
                if forward>=1:center.append((math.degrees(math.atan2(right,forward)),math.degrees(math.atan2(up,forward))))
            if center:
                self.eye.plot(*zip(*center),'--',color='white',lw=1)
                self.eye.annotate('Runway',center[-1],xytext=(10,12),textcoords='offset points',fontsize=9)

        else:
            self.eye.text(.02,.03,'Runway not configured in cruise mode',transform=self.eye.transAxes,fontsize=9)
        for o in frame['obstacles']:
            self.map.add_patch(Circle((o['east'],o['north']),o['radius'],color='#d65b45',alpha=.5))
            # Camera-facing rectangular silhouette of a cylinder, no image detection.
            h=s['heading'];dx=o['radius']*math.cos(h);dy=-o['radius']*math.sin(h)
            points=project_polygon(s,[(o['east']-dx,o['north']-dy,o['bottom']),
                                      (o['east']+dx,o['north']+dy,o['bottom']),
                                      (o['east']+dx,o['north']+dy,o['top']),
                                      (o['east']-dx,o['north']-dy,o['top'])])
            if len(points)>=3:
                self.eye.add_patch(Polygon(points,color='#d65b45',alpha=.65))
                x,y=points[-1]
                if -80<x<80 and -60<y<60:self.eye.text(x,y,o['name'],fontsize=8)
        route=frame['route']
        # Look-ahead marker on the intended line; projection uses the aircraft attitude.
        dx,dy=route[-1][0]-route[0][0],route[-1][1]-route[0][1]
        length=max(1,math.hypot(dx,dy));ux,uy=dx/length,dy/length
        along=(s['east']-route[0][0])*ux+(s['north']-route[0][1])*uy+1000
        point=(route[0][0]+along*ux,route[0][1]+along*uy,frame.get('target_altitude_m') if frame.get('target_altitude_m') is not None else s['altitude'])
        right,up,forward=camera_point(s,point)
        if forward>=1:
            self.eye.plot(math.degrees(math.atan2(right,forward)),math.degrees(math.atan2(up,forward)),marker='+',ms=12,color='#b57800',label='Path ahead')
            self.eye.legend(loc='upper right',fontsize=8)
        self.map.plot(*zip(*route),'--',color='#947300',label='Intended path')
        if frame.get('planned_route'):
            self.map.plot(*zip(*frame['planned_route']),':',color='#d76d20',label='Planned avoidance')
        self.map.plot(*zip(*self.trail),color='#14828f',label='Actual path')
        self.map.plot(s['east'],s['north'],marker=(3,0,-math.degrees(s['heading'])),color='#123',ms=10)
        self.map.legend(fontsize=8,loc='upper right')
        inputs=frame.get('inputs',{});applied=frame.get('applied_inputs',{})
        names=sorted(set(inputs)|set(applied));x=list(range(len(names)))
        self.rates.bar([i-.18 for i in x],[inputs.get(n,0) for n in names],width=.35,color='#168395',label='Latest cue sample')
        self.rates.bar([i+.18 for i in x],[applied.get(n,0) for n in names],width=.35,color='#c48b23',label='Last applied brain input')
        self.rates.set(ylim=(0,215),ylabel='Input rate (Hz)',title='Encoded sensory stimulation (not output firing rates)')
        self.rates.set_xticks(x,names,rotation=20,ha='right');self.rates.legend(fontsize=8)
        self.info.axis('off')
        age='not applied yet' if frame.get('applied_time') is None else f"{max(0,s['time']-frame['applied_time']):.1f} s old"
        cue_age='unknown' if frame.get('input_time') is None else f"{max(0,s['time']-frame['input_time']):.1f} s old"
        alerts=', '.join(frame['alerts']) or 'Within configured cue thresholds'
        height=(f"{frame['altitude_error_m']:+.1f} m ({frame['datum']})" if frame.get('target_altitude_m') is not None else 'no fixed target (phase uses pitch/climb cues)')
        text=(f"{alerts}\nCross-track: {frame['cross_track_m']:+.1f} m   Heading error: {frame['heading_error_deg']:+.1f}°\n"
              f"Height error: {height}\n"
              f"Obstacle cue: {frame['obstacle_looming_hz']:.1f} Hz   Threat: {frame['threat'] or 'none'}\n"
              f"Cue sample: {cue_age} | Applied brain sample: {age}\nKnown geometry only; no camera, terrain or unknown-object detection.")
        if frame.get('glideslope_error_deg') is not None:text+=f"\nGlideslope error: {frame['glideslope_error_deg']:+.2f}°"
        self.info.text(0,1,text,va='top',fontsize=10,wrap=True)
        self.fig.canvas.draw_idle()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=PORT)
    parser.add_argument('--snapshot',choices=['landing','takeoff','obstacle'],help='Render a synthetic example and exit')
    parser.add_argument('--output',default='runs/fly-vision.png')
    args=parser.parse_args()
    if args.snapshot:
        import matplotlib
        matplotlib.use('Agg')
    view=VisionView()
    if args.snapshot:
        from pathlib import Path
        from .core import State,Obstacle
        from .vision import scene,phase_scene
        from .flies import LandingFly,TakeoffFly,StandInBrain
        from .runway import RunwayState
        if args.snapshot=='obstacle':
            f=scene(State(east=200,heading=.2),[Obstacle('Tower',100,1800,150)],altitude=900)
        else:
            fly=(LandingFly if args.snapshot=='landing' else TakeoffFly)(StandInBrain())
            s=RunwayState(x=-1800 if args.snapshot=='landing' else 300,y=45,agl=120 if args.snapshot=='landing' else 0,
                          psi=.06,speed=70,on_ground=args.snapshot=='takeoff')
            f=phase_scene(fly,s,fly.encode(s))
        f['brain']='synthetic example — no brain trial'
        view.update(f);Path(args.output).parent.mkdir(parents=True,exist_ok=True)
        view.fig.savefig(args.output,dpi=120)
        return
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    sock.bind(('127.0.0.1',args.port));sock.setblocking(False)
    view.plt.show(block=False);last=time.monotonic();stale=False
    try:
        while view.plt.fignum_exists(view.fig.number):
            newest=None
            for _ in range(100):
                try:data,_=sock.recvfrom(65535)
                except BlockingIOError:break
                try:newest=json.loads(data)
                except (ValueError,UnicodeError):continue
            if newest is not None:
                view.update(newest);last=time.monotonic();stale=False
            elif time.monotonic()-last>2 and not stale:
                view.title.set_text('NO RECENT TELEMETRY — showing the last received synthetic view')
                view.fig.canvas.draw_idle();stale=True
            view.plt.pause(.05)
    finally:sock.close()


if __name__=='__main__':main()
