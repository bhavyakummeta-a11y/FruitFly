"""Weather for the project launchers. Looks only: the air the fly flies in is always calm.

    storm (default)  a dark, gross thunderstorm sky: thick 3D cumulonimbus at 5,000 ft
                     under two more overcast decks, mist (4 km), dirty brown-yellow haze,
                     patchy fog, heavy rain, and a darker, washed-out picture; lightning
                     and thunder come from FlyCabin/Nasal/storm.nas (738-flies aircraft)
    clear            FlightGear's default fair weather

Both profiles have zero wind, zero gusts and zero turbulence. The storm is set with a
METAR whose wind group is 00000KT (calm), and turbulence is forced to 0, so the weather
changes what you see and hear and nothing about how the airplane flies.
tests/test_storm.py checks that.

Launchers add `weather_args(name)` to the fgfs command, after their own
`--disable-real-weather-fetch` / `--wind=0@0`. The name is also put on fgfs's command
line (/fruitfly/weather) so session logs record it.
"""

# Overcast cumulonimbus base at 5,000 ft: above the 3,000 ft cruise test and the
# takeoff/landing pattern, so the fly's flights stay below the cloud, in the rain.
# Two more overcast decks above it block the sun (a dark sky); BR = mist, 4 km.
STORM_METAR = 'XXXX 012345Z 00000KT 4000 +TSRA BR OVC050CB OVC080 OVC120 14/13 Q0985'

# The gross look. All rendering-only properties (sky shader, clouds, post filter).
STORM_LOOK = [
    '--enable-clouds3d',                                    # the CB deck as real 3D clouds
    '--prop:/sim/rendering/clouds3d-density=1.0',           # default 0.25: thick, lumpy
    '--prop:/environment/air-pollution-norm=0.7',           # dirty brown-yellow sky and haze
    '--prop:/environment/fog-structure=0.6',                # patchy, uneven fog
    '--prop:/environment/ground-haze-thickness-m=3500',     # default 2000: murk up to the cloud
    '--prop:bool:/sim/rendering/als-filters/use-filtering=true',
    '--prop:/sim/rendering/als-filters/brightness=0.8',     # darker picture
    '--prop:/sim/rendering/als-filters/grey-factor=0.35',   # washed-out colour
]
# FlightGear saves some of these (userarchive) into the user's autosave, so 'clear'
# sets them back explicitly; otherwise a storm would leak into the next session.
CLEAR_LOOK = [
    '--prop:/sim/rendering/clouds3d-density=0.25',
    '--prop:/environment/air-pollution-norm=0.0',
    '--prop:/environment/fog-structure=0.0',
    '--prop:bool:/sim/rendering/als-filters/use-filtering=false',
]

CALM = ['--turbulence=0.0']
PROFILES = {
    'storm': [f'--metar={STORM_METAR}',
              '--prop:bool:/sim/rendering/precipitation-enable=true',
              '--prop:bool:/sim/rendering/precipitation-gui-enable=true',
              '--prop:bool:/fruitfly/storm/enabled=true',
              *STORM_LOOK,
              *CALM],
    'clear': ['--prop:bool:/fruitfly/storm/enabled=false', *CLEAR_LOOK, *CALM],
}
DEFAULT = 'storm'


def weather_args(name=DEFAULT):
    if name not in PROFILES:
        raise SystemExit(f'Unknown weather {name!r}; choose from {", ".join(PROFILES)}')
    return [f'--prop:string:/fruitfly/weather={name}', *PROFILES[name]]


def add_argument(parser):
    parser.add_argument('--weather', choices=list(PROFILES), default=DEFAULT,
                        help='storm (default): gray, rain, thunder and lightning, visuals only; '
                             'clear: fair weather. The air is calm in both.')
