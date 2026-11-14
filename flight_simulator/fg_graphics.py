"""FlightGear graphics profiles for the project launchers.

The fly brain, FlightGear, the session logger and the media recorder share one
laptop. FlightGear's defaults (trees, random objects, 3D clouds, uncapped frame
rate) spend GPU *and* CPU on scenery the experiments don't use: the fly's
sensing is computed from geometry, not from rendered pixels.

    light (default)  no trees / random objects / random buildings, 3D clouds only
                     out to 8 km (the storm's visibility is 4 km), cheap fog, no
                     specular or horizon effects, shorter detail range, frame rate
                     capped at 30 fps (frees CPU for the brain)
    full             FlightGear's own settings (for screenshots and demos)

Launchers add `profile_args(name)` to the fgfs command. The profile name is also
put on fgfs's command line (/fruitfly/graphics) so session logs record it.
"""

PROFILES = {
    'light': [
        '--disable-random-vegetation',                      # trees
        '--prop:/sim/rendering/vegetation-density=0',
        '--disable-random-objects',                         # scattered houses, sheds, etc.
        '--disable-random-buildings',
        # 3D clouds stay on (the storm sky and its lightning need them), but only near.
        '--prop:/sim/rendering/clouds3d-vis-range=8000',    # default 10000
        '--prop:/sim/rendering/clouds3d-detail-range=4000', # default 10000
        '--fog-fastest',
        '--disable-specular-highlight',
        '--disable-horizon-effect',
        '--prop:/sim/rendering/static-lod/detailed=800',    # m; default 1500
        '--prop:/sim/rendering/static-lod/rough-delta=3000',  # default 7500
        '--prop:/sim/rendering/static-lod/bare-delta=10000',  # default 21000
        '--prop:/sim/frame-rate-throttle-hz=30',            # default 0 = uncapped
    ],
    'full': [],
}
DEFAULT = 'light'


def profile_args(name=DEFAULT):
    if name not in PROFILES:
        raise SystemExit(f'Unknown graphics profile {name!r}; choose from {", ".join(PROFILES)}')
    return [f'--prop:string:/fruitfly/graphics={name}', *PROFILES[name]]


def add_argument(parser):
    parser.add_argument('--graphics', choices=list(PROFILES), default=DEFAULT,
                        help='light (default): no trees/objects, near 3D clouds only, 30 fps cap; full: FlightGear defaults')
