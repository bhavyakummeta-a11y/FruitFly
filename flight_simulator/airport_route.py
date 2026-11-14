"""Explicit airport geometry and an experimental KLAX -> KBUR simulation mission.

Geographic source: FAA runway data reproduced by airnav.com/airport/{KLAX,KBUR},
checked 2026-11-14. Runway bearings below are true, not magnetic. The waypoints
are a simulation test route, not an instrument procedure or terrain database.
"""
from dataclasses import dataclass, replace
import math
from .core import State, Obstacle, clip, wrap, sense
from .runway import FT, KT, AIM_POINT, GLIDESLOPE, RunwayState, RunwaySim, takeoff_start
from .mission import (Mission, CircuitFly, Leg, LandingFly, TakeoffFly, CFG_TAKEOFF,
                      CFG_CIRCUIT, CFG_LANDING, MAX_BANK, HS_GAIN, mission_row)
from .guidance import RouteGuidance, NoSafeRoute
from .route_weather import RouteWeather, runway_briefing, briefing_text

R = 6371000.0

@dataclass(frozen=True)
class AirportRunway:
    airport: str
    runway: str
    lat: float
    lon: float
    heading: float
    elevation_ft: float
    length: float
    width: float = 45.72

    def xy(self, lat, lon):
        east = R*math.radians(lon-self.lon)*math.cos(math.radians(self.lat))
        north = R*math.radians(lat-self.lat)
        h = math.radians(self.heading)
        return north*math.cos(h)+east*math.sin(h), east*math.cos(h)-north*math.sin(h)

    def latlon(self, x, y):
        h = math.radians(self.heading)
        east, north = x*math.sin(h)+y*math.cos(h), x*math.cos(h)-y*math.sin(h)
        return self.lat+math.degrees(north/R), self.lon+math.degrees(east/(R*math.cos(math.radians(self.lat))))

# Published physical runway ends; no displaced threshold on KBUR 08.
LAX = AirportRunway('KLAX', '25R', 33+56.392673/60, -(118+22.786675/60), 263.0, 94.3, 3939.0)
BUR = AirportRunway('KBUR', '08', 34+11.874657/60, -(118+22.148575/60), 91.0, 727.4, 1768.0)

class AirportRoute:
    departure, arrival = LAX, BUR
    name = 'lax-burbank'

    def __init__(self):
        # A long straight final leaves room to align, slow down and descend.
        final = self.to_departure(RunwayState(x=-16000, agl=0))
        intercept = self.to_departure(RunwayState(x=-22000, agl=0))
        points = [(0, 0), (12000, 0), (intercept.x, intercept.y),
                  (final.x, final.y), self.departure.xy(BUR.lat, BUR.lon)]
        names = ['LAX departure', 'northbound', 'Burbank intercept', 'final']
        altitudes = [5000, 5000, 3500, 3500]  # MSL feet
        self.legs = [Leg(n, *a, *b, alt-LAX.elevation_ft, speed)
                     for n,a,b,alt,speed in zip(names,points,points[1:],altitudes,[180,180,160,145])]
        # Deliberately known synthetic obstacles on the transit, rendered in FG too.
        leg = self.legs[1]
        self.obstacles = [Obstacle(f'route-tornado-{i+1}',
                          leg.y0+(leg.y1-leg.y0)*t, leg.x0+(leg.x1-leg.x0)*t,
                          220, 0, 2200) for i,t in enumerate((.38,.72))]

    def to_arrival(self, s):
        lat,lon = LAX.latlon(s.x,s.y)
        x,y = BUR.xy(lat,lon)
        return replace(s,x=x,y=y,psi=wrap(s.psi+math.radians(LAX.heading-BUR.heading)),
                       agl=s.agl+(LAX.elevation_ft-BUR.elevation_ft)*FT)

    def to_departure(self, s):
        lat,lon = BUR.latlon(s.x,s.y)
        x,y = LAX.xy(lat,lon)
        return replace(s,x=x,y=y,psi=wrap(s.psi+math.radians(BUR.heading-LAX.heading)),
                       agl=s.agl+(BUR.elevation_ft-LAX.elevation_ft)*FT)

    def world(self, s):
        h = math.radians(LAX.heading)
        return State(time=s.time,east=s.x*math.sin(h)+s.y*math.cos(h),
                     north=s.x*math.cos(h)-s.y*math.sin(h),
                     altitude=s.agl+LAX.elevation_ft*FT,heading=wrap(s.psi+h),
                     roll=s.roll,pitch=s.pitch,speed=s.speed,climb=s.climb)

    def world_obstacles(self, obstacles):
        out=[]
        for o in obstacles:
            s=self.world(RunwayState(x=o.north,y=o.east,agl=o.bottom))
            out.append(replace(o,east=s.east,north=s.north,bottom=s.altitude,top=o.top+LAX.elevation_ft*FT))
        return out

    def check_start(self,s):
        if not s.on_ground or not -150 <= s.x <= 900 or abs(s.y)>30 or abs(math.degrees(s.psi))>8:
            raise ValueError('Route requires KLAX runway 25R, lined up near its east end. Use launch_fg --route lax-burbank.')

class RouteFly(CircuitFly):
    obstacle_guidance = True
    def __init__(self, brain, period, route):
        super().__init__(brain,period,route.legs)
        self.route=route
        self.guidance=RouteGuidance(self.leg.course,(self.leg.y0,self.leg.x0),margin=300)
        self.avoidance=False
        self.no_safe_route=False
        self.previous_target=self.leg.course
        self.avoidance_count=0

    def altitude_target(self,s):
        leg=self.leg
        target=leg.alt_ft*FT
        if leg.name=='final':
            a=self.route.to_arrival(s)
            target=min(target,(BUR.elevation_ft-LAX.elevation_ft)*FT+
                       max(0,(AIM_POINT-a.x)*math.tan(GLIDESLOPE)))
        elif s.terrain_agl is not None and s.terrain_agl<300:
            target=max(target,s.agl+300-s.terrain_agl)
        return target

    def encode(self,s):
        inputs=super().encode(s)
        leg=self.leg
        target=self.altitude_target(s)
        climb=clip(.1*(target-s.agl),-7.6,7.6)
        gamma=math.asin(clip(climb/max(s.speed,30),-.3,.3))
        pitch=math.degrees(s.pitch)+1.5*math.degrees(gamma-s.gamma)
        inputs.update(self.vs_inputs(s,pitch,self.bank_target))
        state=State(east=s.y,north=s.x,altitude=s.agl,heading=s.psi,roll=s.roll,speed=s.speed)
        self.guidance.heading=leg.course
        self.guidance.origin=(leg.y0,leg.x0)
        was=self.avoidance
        self.no_safe_route=False
        try:
            target,self.avoidance=self.guidance.choose(state,self.vision_obstacles,self.previous_target,
                                                       math.radians(MAX_BANK))
        except NoSafeRoute:
            # Never freeze a live run because a prediction fails. Log the condition;
            # keep flying an escape turn with a climb request, and retry next trial.
            cue=sense(state,self.vision_obstacles,horizon=60)
            target=wrap(s.psi+cue.turn*math.radians(45))
            self.avoidance=self.no_safe_route=True
            inputs.update(self.vs_inputs(s,15,self.bank_target))
        if self.avoidance:
            drift=math.degrees(wrap(s.psi-target)+s.yaw_rate)
            inputs.update(self.hs_inputs(s,drift,HS_GAIN))
        self.previous_target=target
        if self.avoidance and not was:self.avoidance_count+=1
        inputs['looming']=sense(state,self.vision_obstacles,horizon=60).looming_hz
        return inputs

    def check(self,s):
        if not self.avoidance:self.advance_leg(s)
        self.status.phase=('AVOID: ' if self.avoidance else 'ROUTE: ')+self.leg.name
        if self.leg.name=='final':
            a=self.route.to_arrival(s)
            aligned=(abs(a.y)<30 and abs(math.degrees(a.psi))<5 and abs(math.degrees(a.roll))<5
                     and abs(a.glideslope_error())<.6)
            if a.x>=-5556 and (aligned or a.x>=-3500):self.status.done=True

class DestinationLanding(LandingFly):
    def check(self,s):
        super().check(s)
        if s.on_ground and not self.go_around:
            self.status.done = s.speed < 1.0

    def step(self,s,dt):
        # Any known obstruction on final requests a go-around, never a low turn.
        state=State(east=s.y,north=s.x,altitude=s.agl,heading=s.psi,speed=s.speed)
        if not s.on_ground and sense(state,self.vision_obstacles,horizon=35).looming_hz>0:
            self.go_around=True
        c=super().step(s,dt)
        if s.on_ground:
            self.brake=1.0  # Burbank is shorter than the generic test runway
            c=replace(c,throttle=0.0,brake=1.0)
        return c

class RouteMission(Mission):
    def __init__(self,brain,period=.25,calibrate=True,log=print):
        self.route=AirportRoute()
        self.last_state=None
        self.avoidance_count=0
        self.minimum_clearance=math.inf
        super().__init__(brain,period,calibrate,self.route.legs,log)
        self.vision_obstacles=list(self.route.obstacles)
        # The storm story (route_weather.py): looks only. Built on the first step so
        # a --vision-obstacles file that replaces the tornadoes is used.
        self.weather=None
        self.sky_changes=[]      # stages reached, for the FlightGear runner to show
        self.briefing=None       # Burbank runway briefing; landing never starts without it

    def update_weather(self,s):
        if self.weather is None:
            self.weather=RouteWeather(self.route,list(self.vision_obstacles))
        stage=self.weather.update(s.x,s.y,s.time)
        if stage is None:
            return
        self.say(f'    sky: {stage.name} ({self.weather.u/1000:.1f} km along the route)')
        message=None
        if stage.briefing:
            message=self.give_briefing(s)
        self.sky_changes.append((stage,message))

    def give_briefing(self,s):
        if self.briefing is None:
            self.briefing=dict(runway_briefing(self.route.arrival),time_s=round(s.time,1))
            self.say('    runway briefing: '+briefing_text(self.briefing))
        return briefing_text(self.briefing)

    def control_state(self,s):
        return self.route.to_arrival(s) if isinstance(self.fly,LandingFly) else s

    @property
    def runway(self):
        return BUR if isinstance(self.fly,LandingFly) else LAX

    def step(self,s,dt):
        self.last_state=s
        self.update_weather(s)
        if isinstance(self.fly,TakeoffFly) and self.fly.status.done and not self.fly.rejected:
            self.start_fly(RouteFly(self.brain,self.period,self.route),s)
        elif isinstance(self.fly,RouteFly) and self.fly.status.done:
            self.avoidance_count=self.fly.avoidance_count
            if self.briefing is None:   # cannot normally happen: final comes after the intercept leg
                self.give_briefing(s)
            a=self.route.to_arrival(s)
            fly=DestinationLanding(self.brain,self.period,trim_throttle=self.fly.throttle_trim)
            fly.trim_pitch_deg=math.degrees(a.alpha-GLIDESLOPE)
            self.start_fly(fly,a)
        local=self.control_state(s)
        if not s.on_ground and isinstance(self.fly,TakeoffFly) and s.climb>1 and s.agl>10:
            self.gear_down,self.config=False,CFG_CIRCUIT
        if isinstance(self.fly,RouteFly) and self.fly.leg.name=='final' and self.config is not CFG_LANDING:
            self.gear_down,self.config=True,CFG_LANDING
            self.fly.throttle_trim=clip(self.fly.throttle_trim+.15,0,1)
        obstacles=self.vision_obstacles
        if isinstance(self.fly,LandingFly):
            obstacles=[]
            for o in self.vision_obstacles:
                a=self.route.to_arrival(RunwayState(x=o.north,y=o.east,agl=o.bottom))
                obstacles.append(replace(o,east=a.y,north=a.x,bottom=a.agl,top=a.agl+o.top-o.bottom))
        self.fly.vision_obstacles=obstacles
        self.fly.vision_sink=RouteView(self,self.vision_sink) if self.vision_sink else None
        return self.fly.step(local,dt)

    def collision(self,s):
        state=State(east=s.y,north=s.x,altitude=s.agl)
        clearance=min((o.clearance(state) for o in self.vision_obstacles),default=math.inf)
        self.minimum_clearance=min(self.minimum_clearance,clearance)
        return clearance<=0

    def report(self):
        return dict(departure='KLAX 25R',destination='KBUR 08',route=self.route.name,
                    minimum_clearance_m=None if math.isinf(self.minimum_clearance) else round(self.minimum_clearance,1),
                    avoidance_count=getattr(self.fly,'avoidance_count',self.avoidance_count),
                    sky=self.weather.stage.name if self.weather else 'clear',
                    runway_briefed=self.briefing is not None)

    def story(self):
        """Weather stages reached and the runway briefing, for result.json."""
        return dict(sky_stages=list(self.weather.history) if self.weather else [],
                    runway_briefing=self.briefing)

class RouteView:
    """Keep the companion map in one EN/MSL frame through both airport handovers."""
    def __init__(self,mission,sink):self.mission,self.sink=mission,sink
    def send(self,frame,*args):
        from .vision import scene
        m=self.mission;r=m.route;s=m.last_state
        state=r.world(s)
        runway=m.runway
        x,y=LAX.xy(runway.lat,runway.lon)
        point=r.world(RunwayState(x=x,y=y))
        rw=dict(east=point.east,north=point.north,heading=math.radians(runway.heading),
                elevation=runway.elevation_ft*FT,length=runway.length,width=runway.width,
                name=f'{runway.airport} {runway.runway}')
        result=scene(state,r.world_obstacles(m.vision_obstacles),runway=rw)
        result.update(inputs=frame['inputs'],input_time=frame.get('input_time'),phase=m.phase,
                      route=[],destination='KBUR 08',on_ground=s.on_ground)
        points=[(r.legs[0].x0,r.legs[0].y0)]+[(l.x1,l.y1) for l in r.legs]
        for x,y in points:
            p=r.world(RunwayState(x=x,y=y));result['route'].append([p.east,p.north])
        result['target_altitude_m'] = (m.fly.altitude_target(s)+LAX.elevation_ft*FT if isinstance(m.fly,RouteFly)
                                       else frame.get('target_altitude_m'))
        if isinstance(m.fly,LandingFly) and result['target_altitude_m'] is not None:
            result['target_altitude_m'] += BUR.elevation_ft*FT
        for key in ('cross_track_m','heading_error_deg','altitude_error_m','alerts'):
            result[key]=frame[key]
        if isinstance(m.fly,RouteFly):
            result['planned_route']=[(r.world(RunwayState(x=n,y=e)).east,
                                       r.world(RunwayState(x=n,y=e)).north) for e,n in m.fly.guidance.path]
            if m.fly.no_safe_route:result['alerts'].append('NO PREDICTED CLEAR ROUTE')
        self.sink.send(result,*args)


def run_local(mission,seconds=1800,dt=.05,log=None,progress=True):
    """Reduced flat-airport model; explicitly no terrain database between airports."""
    sim=RunwaySim(takeoff_start(),CFG_TAKEOFF)
    reason='time_limit';touchdown=None;next_print=0
    while sim.state.time<seconds and not mission.done:
        s=sim.state
        c=mission.step(s,dt)
        if log is not None:log.append(mission_row(mission,s,c))
        if progress and s.time>=next_print:
            next_print=s.time+30
            print(f'{s.time:.0f}s {mission.phase} MSL={s.agl/FT+LAX.elevation_ft:.0f}ft',flush=True)
        landing=isinstance(mission.fly,LandingFly)
        if landing:sim.state=mission.route.to_arrival(s)
        sim.config=mission.config
        sim.step(c,dt)
        local=sim.state
        if landing and sim.events.touchdown_x is not None:touchdown=sim.events.touchdown_x
        departed=local.on_ground and (abs(local.y)>mission.runway.width/2 or local.x>mission.runway.length or local.x<0)
        if landing:sim.state=mission.route.to_departure(local)
        if mission.collision(sim.state):reason='obstacle_collision';break
        if departed:reason='runway_departure';break
        if sim.events.tail_strike or sim.events.stall:
            reason='tail_strike' if sim.events.tail_strike else 'stall';break
    if mission.done:
        reason=('takeoff_rejected' if isinstance(mission.fly,TakeoffFly) else
                'go_around' if mission.fly.go_around else 'landing_completed')
    a=mission.control_state(sim.state)
    success=(reason=='landing_completed' and touchdown is not None and 0<=touchdown<=900
             and sim.events.touchdown_sink_fpm<500 and 0<=a.x<=BUR.length and abs(a.y)<BUR.width/2 and a.speed<1)
    if reason=='landing_completed' and not success: reason='landing_outside_criteria'
    return dict(mission.report(),**mission.story(),success=success,outcome=reason,termination_reason=reason,
                touchdown_x_m=touchdown,touchdown_sink_fpm=sim.events.touchdown_sink_fpm,
                stop_x_m=a.x if a.on_ground else None,time_s=sim.state.time,
                handovers=mission.handovers,ended_in=mission.phase)
