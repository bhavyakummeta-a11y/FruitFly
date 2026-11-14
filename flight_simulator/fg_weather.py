"""Weather for the project launchers. Looks only: the air the fly flies in is always calm.

    storm (default)  gray overcast, heavy rain, thunderstorm; lightning and thunder come
                     from FlyCabin/Nasal/storm.nas (738-flies aircraft)
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
STORM_METAR = 'XXXX 012345Z 00000KT 8000 +TSRA OVC050CB 14/13 Q0995'

CALM = ['--turbulence=0.0']
PROFILES = {
    'storm': [f'--metar={STORM_METAR}',
              '--prop:bool:/sim/rendering/precipitation-enable=true',
              '--prop:bool:/sim/rendering/precipitation-gui-enable=true',
              '--prop:bool:/fruitfly/storm/enabled=true',
              *CALM],
    'clear': ['--prop:bool:/fruitfly/storm/enabled=false', *CALM],
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
