"""The LAX -> Burbank storm story: clear takeoff, a storm with tornadoes on the
way, the sky clearing behind them, a runway briefing for Burbank, a landing.

    distance along the route (KLAX 25R = 0) ------------------------------------>
    | clear        | darkening    | STORM + tornadoes       | clearing  | Burbank   |
    | takeoff, LAX | turn north   | lightning, roar, rain   | rain eases| briefing, |
    |              |              | tornado 1     tornado 2 |           | final     |

Stages are picked from the airplane's position along the route (never from the
clock), and only ever move forward. Weather is LOOKS ONLY: every METAR here has
calm wind (00000KT), no gusts and no wind shear, and turbulence stays 0, so the
storm changes what you see and hear and nothing about how the airplane flies.
tests/test_route_weather.py checks that.

The tornadoes are the route's known obstacles (airport_route.py). The route
planner has their positions from the start, as before; in FlightGear they are
hidden until the storm stage, which begins 8 km before the first one, beyond
the planner's look-ahead (at most 70 s, about 6 km at cruise speed).

The runway briefing is information code gives the fly's landing controller:
Burbank runway 08's threshold, heading, length, width, elevation and the 3 deg
glide path. It is given at the start of the Burbank intercept leg, after the
tornadoes, logged, saved in result.json and shown on FlightGear's screen. The
landing never starts without it.
"""
from dataclasses import dataclass, field
import math

# Calm in every METAR: 00000KT. Cloud bases stay above the route: cruise 5,000 ft,
# tornado tops ~7,300 ft MSL (2,200 m above KLAX), storm base 8,000 ft.
CLEAR_METAR = 'XXXX 012345Z 00000KT 9999 FEW060 SCT250 22/12 Q1016'
DARK_METAR = 'XXXX 012345Z 00000KT 9000 -RA SCT070 BKN090 OVC140 17/14 Q1006'
STORM_METAR = 'XXXX 012345Z 00000KT 5000 +TSRA BKN080CB OVC120 15/14 Q0994'
CLEARING_METAR = 'XXXX 012345Z 00000KT 9999 -RA SCT060 BKN110 17/13 Q1004'
ARRIVAL_METAR = 'XXXX 012345Z 00000KT 9999 FEW070 SCT200 21/12 Q1013'

STORM_LEAD_M = 8000      # storm and tornadoes appear this far before the first tornado
DARK_LEAD_M = 12000      # the sky starts to darken this far before it
CLEAR_AFTER_M = 4000     # the storm eases this far past the last tornado


@dataclass(frozen=True)
class Stage:
    name: str
    metar: str
    rain: bool               # precipitation rendering
    lightning: bool          # storm.nas: lightning, thunder, roar
    tornadoes: bool          # tornado models visible
    message: str             # shown on FlightGear's screen (ATC message line)
    briefing: bool = False   # this stage gives the Burbank runway briefing


STAGES = (
    Stage('clear', CLEAR_METAR, False, False, False,
          'LAX: clear skies, wind calm. Cleared for takeoff runway 25R.'),
    Stage('darkening', DARK_METAR, True, False, False,
          'SIGMET: severe thunderstorms and tornadoes reported ahead on your route.'),
    Stage('storm', STORM_METAR, True, True, True,
          'WARNING: tornadoes ahead. Thunderstorm, heavy rain.'),
    Stage('clearing', CLEARING_METAR, True, False, True,
          'The storm is behind you. Rain easing.'),
    Stage('burbank', ARRIVAL_METAR, False, False, True, '', briefing=True),
)
BY_NAME = {s.name: s for s in STAGES}


def polyline(legs):
    """Route as segments with the distance at which each starts."""
    segs, u = [], 0.0
    for leg in legs:
        length = math.hypot(leg.x1 - leg.x0, leg.y1 - leg.y0)
        segs.append((u, leg.x0, leg.y0, leg.x1, leg.y1, length))
        u += length
    return segs


def progress(segs, x, y):
    """Distance along the route of the point on it nearest to (x, y)."""
    best, at = math.inf, 0.0
    for u0, x0, y0, x1, y1, length in segs:
        dx, dy = x1 - x0, y1 - y0
        t = 0.0 if length == 0 else max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / length ** 2))
        d = math.hypot(x - (x0 + t * dx), y - (y0 + t * dy))
        if d < best:
            best, at = d, u0 + t * length
    return at


@dataclass
class RouteWeather:
    """Which stage of the story the flight is in. update() returns a newly reached stage."""
    route: object
    obstacles: list = None   # default: route.obstacles (a --vision-obstacles file replaces them)
    stage: Stage = STAGES[0]
    history: list = field(default_factory=list)

    def __post_init__(self):
        self.segs = polyline(self.route.legs)
        # Obstacles store x (along LAX 25R) in .north and y (right of it) in .east.
        obstacles = self.route.obstacles if self.obstacles is None else self.obstacles
        at = sorted(progress(self.segs, o.north, o.east) for o in obstacles)
        first, last = (at[0], at[-1]) if at else (math.inf, math.inf)
        names = [leg.name for leg in self.route.legs]
        briefing_at = self.segs[names.index('Burbank intercept')][0] if 'Burbank intercept' in names else -math.inf
        self.starts = {'clear': -math.inf, 'darkening': first - DARK_LEAD_M, 'storm': first - STORM_LEAD_M,
                       'clearing': last + CLEAR_AFTER_M,
                       'burbank': max(briefing_at, last + CLEAR_AFTER_M) if at else briefing_at}
        self.tornado_at = at
        self.u = 0.0

    def update(self, x, y, time=None):
        self.u = max(self.u, progress(self.segs, x, y))   # forward only: no flicker
        reached = self.stage
        for s in STAGES[STAGES.index(self.stage) + 1:]:
            if self.u >= self.starts[s.name]:
                reached = s
        if reached is self.stage:
            return None
        self.stage = reached
        self.history.append({'stage': reached.name, 'time_s': None if time is None else round(time, 1),
                             'route_km': round(self.u / 1000, 2)})
        return reached


def runway_briefing(runway, glideslope_deg=3.0):
    """What the fly's landing controller is told about the destination runway."""
    return {'airport': runway.airport, 'runway': runway.runway,
            'threshold_lat': round(runway.lat, 6), 'threshold_lon': round(runway.lon, 6),
            'heading_true_deg': runway.heading, 'length_m': runway.length, 'width_m': runway.width,
            'threshold_elevation_ft': runway.elevation_ft, 'glideslope_deg': glideslope_deg,
            'wind': 'calm', 'source': 'code-supplied runway data (FAA via airnav.com), not perceived'}


def briefing_text(b):
    return (f"{b['airport']} runway {b['runway']}: heading {b['heading_true_deg']:.0f} true, "
            f"{b['length_m']:.0f} m long, {b['width_m']:.0f} m wide, threshold {b['threshold_elevation_ft']:.0f} ft, "
            f"{b['glideslope_deg']:.0f} degree glide path, wind {b['wind']}. Cleared to land runway {b['runway']}.")


def stage_props(stage, tornado_count, message=None):
    """Telnet (path, value) pairs that put FlightGear into this stage. Display only."""
    text = stage.message if message is None else message
    pairs = [('/environment/params/metar-updates-environment', 'true'),
             ('/environment/realwx/enabled', 'false'),
             ('/environment/metar/data', stage.metar),
             ('/environment/turbulence/magnitude-norm', '0'),
             ('/sim/rendering/precipitation-enable', 'true' if stage.rain else 'false'),
             ('/fruitfly/storm/enabled', 'true' if stage.lightning else 'false'),
             ('/fruitfly/weather', f'lax-burbank story: {stage.name}')]
    pairs += [(f'/fruitfly/obstacles/obstacle[{i}]/visible', 'true' if stage.tornadoes else 'false')
              for i in range(tornado_count)]
    if text:
        pairs.append(('/sim/messages/atc', text))
    return pairs


def launch_args():
    """fgfs flags for the start of the story: clear skies at LAX, calm air, storm script
    loaded but quiet. Precipitation rendering is switched on later by the storm stage."""
    return ['--prop:string:/fruitfly/weather=lax-burbank story: clear', f'--metar={CLEAR_METAR}',
            '--prop:bool:/sim/rendering/precipitation-gui-enable=true',
            '--prop:bool:/sim/rendering/precipitation-enable=false',
            '--prop:bool:/fruitfly/storm/enabled=false', '--turbulence=0.0']


class SkyDirector:
    """Applies stages through an open telnet property connection (ObstacleScene's).
    A failure is logged and the flight goes on: weather never stops a run."""

    def __init__(self, scene, tornado_count, say=print):
        self.scene, self.count, self.say = scene, tornado_count, say
        self.applied = []

    def apply(self, stage, message=None):
        try:
            self.scene._set(stage_props(stage, self.count, message))
            got = self.scene.get('/environment/metar/data')
            ok = ' '.join(got.split()) == stage.metar
            self.applied.append({'stage': stage.name, 'metar_confirmed': ok})
            self.say(f'Sky -> {stage.name}' + ('' if ok else f' (WARNING: FlightGear METAR reads {got!r})'))
        except OSError as exc:
            self.applied.append({'stage': stage.name, 'error': repr(exc)})
            self.say(f'Sky -> {stage.name} failed: {exc!r} (flight continues)')
