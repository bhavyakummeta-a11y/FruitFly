"""Synthetic visual cues from known geometry, not camera recognition or a retina model."""
from dataclasses import asdict
import json
import math
import socket
from .core import State, clip, wrap, sense

PORT = 5601


def scene(state, obstacles=(), heading=0.0, origin=(0.0, 0.0), altitude=None, runway=None):
    """All geometry is local east/north/metres, with one consistent altitude datum."""
    sn, cs = math.sin(heading), math.cos(heading)
    cross = (state.east-origin[0])*cs-(state.north-origin[1])*sn
    heading_error = math.degrees(wrap(state.heading-heading))
    height_error = 0.0 if altitude is None else state.altitude-altitude
    stimulus = sense(state, obstacles, horizon=max(25, state.speed/2))
    track = math.degrees(wrap(state.heading-heading)+math.atan2(cross, max(600,state.speed*18)))
    # Engineered optomotor proxies, not reconstructed optical flow.
    inputs = {'looming': stimulus.looming_hz,
              'hs_left': clip(100+8*track,0,200), 'hs_right': clip(100-8*track,0,200),
              'vs_left': clip(100-.8*height_error-8*math.degrees(state.roll),0,200),
              'vs_right': clip(100-.8*height_error+8*math.degrees(state.roll),0,200)}
    alerts = []
    if abs(cross)>100: alerts.append('OFF PATH')
    if abs(heading_error)>15: alerts.append('HEADING DEVIATION')
    if abs(height_error)>30: alerts.append('ALTITUDE DEVIATION')
    if stimulus.looming_hz>0: alerts.append('OBSTACLE AHEAD')
    return {'time':state.time, 'source':'synthetic geometry', 'state':asdict(state),
            'obstacles':[asdict(o) for o in obstacles], 'runway':runway,
            'route':[[origin[0],origin[1]],[origin[0]+15000*sn,origin[1]+15000*cs]],
            'cross_track_m':cross, 'heading_error_deg':heading_error,
            'altitude_error_m':height_error, 'target_altitude_m':altitude,
            'obstacle_looming_hz':stimulus.looming_hz, 'threat':stimulus.obstacle,
            'inputs':inputs, 'alerts':alerts, 'datum':'MSL', 'phase':'CRUISE'}


def phase_scene(fly, s, inputs):
    """Runway-frame state: x along runway, y right; heights above runway datum."""
    from .runway import RUNWAY_LENGTH, RUNWAY_HALF_WIDTH, AIM_POINT, GLIDESLOPE
    state=State(time=s.time,east=s.y,north=s.x,altitude=s.agl,heading=s.psi,
                pitch=s.pitch,roll=s.roll,speed=s.speed,climb=s.climb)
    landing=fly.name=='Landing fly'
    leg=getattr(fly,'leg',None)
    heading=leg.course if leg else 0.0
    origin=(leg.y0,leg.x0) if leg else (0.0,0.0)
    target=leg.altitude_target(s) if leg else (max(0,(AIM_POINT-s.x)*math.tan(GLIDESLOPE)) if landing else None)
    runway={'east':0.0,'north':0.0,'heading':0.0,'length':RUNWAY_LENGTH,
            'width':2*RUNWAY_HALF_WIDTH,'elevation':0.0,'name':'Configured runway'}
    frame=scene(state,fly.vision_obstacles,heading,origin,target,runway)
    frame.update(phase=fly.status.phase,datum='above runway',inputs=dict(inputs))
    frame['runway_distance_m']=-s.x
    frame['glideslope_error_deg']=s.glideslope_error() if landing and not s.on_ground else None
    frame['on_ground']=s.on_ground
    if leg: frame['route']=[[leg.y0,leg.x0],[leg.y1,leg.x1]]
    else: frame['route']=[[0,min(-3000,s.x-1000)],[0,max(RUNWAY_LENGTH,s.x+1000)]]
    if not leg and abs(s.y)>RUNWAY_HALF_WIDTH:
        frame['alerts'].append('OUTSIDE RUNWAY CENTERLINE CORRIDOR')
    if landing and not s.on_ground and fly.off_glideslope(s):
        frame['alerts'].append('OFF GLIDESLOPE')
    # Never confuse an obstacle with the runway's flare/rotation looming signal.
    # An obstacle is an aversive cue; existing phase decoder decides its response.
    if frame['obstacle_looming_hz']>0:
        frame['inputs']['bitter']=max(inputs.get('bitter',0),frame['obstacle_looming_hz'])
    return frame


def visual_escape(brain, inputs):
    """Connectome consumes the entire cue map; baselines remain explicitly non-neural."""
    if hasattr(brain,'run'):
        return brain.run(inputs)['DNp01']
    return brain.escape(inputs['looming'])


def camera_point(state, point):
    """World -> camera (right, up, forward), including aircraft pitch and roll."""
    dx,dy,dz=point[0]-state['east'],point[1]-state['north'],point[2]-state['altitude']
    h,p,r=state['heading'],state['pitch'],state['roll']
    right=dx*math.cos(h)-dy*math.sin(h)
    forward=dx*math.sin(h)+dy*math.cos(h)
    up=dz*math.cos(p)-forward*math.sin(p)
    forward=forward*math.cos(p)+dz*math.sin(p)
    return right*math.cos(r)+up*math.sin(r),up*math.cos(r)-right*math.sin(r),forward


def project_polygon(state, points):
    """Clip to the forward near plane before angular projection (no behind-camera flips)."""
    points=[camera_point(state,p) for p in points]
    clipped=[]
    for a,b in zip(points,points[1:]+points[:1]):
        ain,bin=a[2]>=1,b[2]>=1
        if ain: clipped.append(a)
        if ain != bin:
            t=(1-a[2])/(b[2]-a[2])
            clipped.append(tuple(a[i]+t*(b[i]-a[i]) for i in range(3)))
    return [(math.degrees(math.atan2(x,z)),math.degrees(math.atan2(y,z))) for x,y,z in clipped]


class VisionPublisher:
    """Best-effort display stream; no network operation can wait on a viewer."""
    def __init__(self, port=PORT):
        if not 0<=port<=65535: raise ValueError('vision port must be 0..65535')
        self.port=port
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.next_time=-math.inf

    def send(self, frame, applied_inputs=None, applied_time=None, brain='unknown'):
        if not self.port or frame['time']<self.next_time: return
        self.next_time=frame['time']+.2
        packet={**frame,'applied_inputs':applied_inputs or {},'applied_time':applied_time,'brain':brain}
        # Bound datagram size while retaining nearest known obstacles in the display.
        s=frame['state']
        packet['obstacles']=sorted(frame['obstacles'],key=lambda o:(o['east']-s['east'])**2+(o['north']-s['north'])**2)[:40]
        packet['obstacle_count']=len(frame['obstacles'])
        try:
            data=json.dumps(packet,allow_nan=False).encode()
            if len(data)<=65000: self.sock.sendto(data,('127.0.0.1',self.port))
        except (OSError,ValueError):
            pass

    def close(self):
        self.sock.close()
