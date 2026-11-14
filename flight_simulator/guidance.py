"""Conventional look-ahead rules for cruise; independent of neural decisions."""
import math
from .core import clip, wrap


class NoSafeRoute(RuntimeError):
    pass


class RouteGuidance:
    def __init__(self, heading, origin=(0.0, 0.0), margin=150.0):
        self.heading, self.origin, self.margin = heading, origin, margin
        self.path = []
        self.clearance = math.inf
        self.cross_track = 0.0

    def rollout(self, state, target, obstacles, bank_limit):
        east,north,heading,bank = state.east,state.north,state.heading,state.roll
        speed=max(state.speed,25)
        horizon=max(35.0,min(70.0,speed*.6))
        path=[(east,north)]
        minimum=math.inf
        for _ in range(int(horizon/.5)):
            demand=clip(.65*wrap(target-heading),-bank_limit,bank_limit)
            bank += clip(demand-bank,-math.radians(5)*.5,math.radians(5)*.5)
            heading=wrap(heading+9.81*math.tan(bank)/speed*.5)
            old_east,old_north=east,north
            east+=speed*math.sin(heading)*.5
            north+=speed*math.cos(heading)*.5
            path.append((east,north))
            # Segment distance prevents skipping a small obstacle at high speed.
            dx,dy=east-old_east,north-old_north
            for o in obstacles:
                if not o.bottom-100 <= state.altitude <= o.top+100:
                    continue
                t=clip(((o.east-old_east)*dx+(o.north-old_north)*dy)/(dx*dx+dy*dy),0,1)
                distance=math.hypot(old_east+t*dx-o.east,old_north+t*dy-o.north)-o.radius
                minimum=min(minimum,distance)
        return minimum,path

    def choose(self,state,obstacles,previous,bank_limit,preferred_turn=0):
        sn,cs=math.sin(self.heading),math.cos(self.heading)
        self.cross_track=(state.east-self.origin[0])*cs-(state.north-self.origin[1])*sn
        desired=wrap(self.heading+clip(math.atan2(-self.cross_track,max(800,state.speed*18)),
                                      -math.radians(25),math.radians(25)))
        candidates=[desired]+[wrap(self.heading+math.radians(a)) for a in range(-60,61,5)]
        options=[]
        desired_safe=False
        for i,target in enumerate(candidates):
            clearance,path=self.rollout(state,target,obstacles,bank_limit)
            if clearance < self.margin:
                continue
            if i==0:
                desired_safe=True
            end_cross=(path[-1][0]-self.origin[0])*cs-(path[-1][1]-self.origin[1])*sn
            score=(abs(wrap(target-desired)) + .15*abs(wrap(target-previous))
                   + .10*abs(end_cross)/max(800,state.speed*18))
            if preferred_turn and preferred_turn*wrap(target-self.heading)<0:
                score += .05  # Neural preference can break ties, never waive clearance.
            options.append((score,target,clearance,path))
        if not options:
            raise NoSafeRoute('No predicted route clears all obstacles with the bank limit; pausing instead of flying into them.')
        _,target,self.clearance,self.path=min(options,key=lambda option:option[0])
        return target,not desired_safe
