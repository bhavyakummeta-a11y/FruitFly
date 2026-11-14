"""Generate a separate FlightGear STG scenery overlay and matching fixed course.

Uses FlightGear's SGBucket tile layout and AC3D's Y-up model convention.
No changes to installed aircraft, terrain, or downloaded scenery are made.
"""
import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
from .core import Obstacle
from .tornado_shape import funnel_rings, is_dark_band

EARTH_RADIUS = 6371000.0


def validate_origin(origin):
    lat, lon = float(origin['latitude']), float(origin['longitude'])
    if not (math.isfinite(lat) and math.isfinite(lon) and -80 <= lat <= 80 and -180 <= lon < 180):
        raise ValueError('Course origin requires latitude in [-80,80] and longitude in [-180,180).')
    return lat, lon


def to_geographic(east, north, origin):
    lat, lon = validate_origin({'latitude': origin[0], 'longitude': origin[1]})
    latitude = lat + math.degrees(north / EARTH_RADIUS)
    longitude = (lon + math.degrees(east / (EARTH_RADIUS * math.cos(math.radians(lat)))) + 180) % 360 - 180
    if not -80 <= latitude <= 80:
        raise ValueError('Course extends outside supported latitude range')
    return latitude, longitude


def to_local(latitude, longitude, origin):
    lat, lon = origin
    delta_lon = (longitude - lon + 180) % 360 - 180
    return (EARTH_RADIUS * math.radians(delta_lon) * math.cos(math.radians(lat)),
            EARTH_RADIUS * math.radians(latitude-lat))


def tile_path(latitude, longitude):
    # SGBucket spans for the supported [-80,80] range. Boundaries are asymmetric
    # in the southern hemisphere, matching SimGear's sg_bucket_span.
    span = next(width for limit, width in [(76,1), (62,.5), (22,.25), (-22,.125), (-62,.25), (-76,.5), (-90,1)] if latitude >= limit)
    lon, lat = math.floor(longitude), math.floor(latitude)
    x, y = math.floor((longitude-lon)/span), math.floor((latitude-lat)*8)
    index = ((lon+180) << 14) + ((lat+90) << 6) + (y << 3) + x
    def directory(lon, lat):
        return f'{"e" if lon >= 0 else "w"}{abs(lon):03d}{"n" if lat >= 0 else "s"}{abs(lat):02d}'
    return Path('Objects') / directory(lon//10*10, lat//10*10) / directory(lon,lat) / f'{index}.stg'


def tornado_model(radius, height, segments=32, levels=24):
    """Static tornado inside the collision cylinder: a bent two-tone funnel, as wide as
    the cylinder at the top and narrow at the ground, closed by a flat cap cloud.
    Same shape as the live obstacle tornadoes (tornado_shape.py). AC3D is Y-up."""
    rings = funnel_rings(levels, segments)
    lines = ['AC3Db',
             'MATERIAL "dark" rgb 0.05 0.05 0.07 amb 0.05 0.05 0.07 emis 0 0 0 spec 0 0 0 shi 0 trans 0',
             'MATERIAL "mid" rgb 0.15 0.15 0.18 amb 0.15 0.15 0.18 emis 0 0 0 spec 0 0 0 shi 0 trans 0',
             'OBJECT world', 'kids 1', 'OBJECT poly', 'name "fly-obstacle-tornado"',
             f'numvert {(levels+1)*segments}']
    for ring in rings:
        for x, y, z in ring:
            lines.append(f'{radius*x:.6f} {height*z:.6f} {radius*y:.6f}')
    lines.append(f'numsurf {levels*segments+2}')
    def face(indices, material):
        lines.extend(['SURF 0x20', f'mat {material}', f'refs {len(indices)}'])
        lines.extend(f'{i} 0 0' for i in indices)
    for level in range(levels):
        for i in range(segments):
            j=(i+1)%segments
            face([level*segments+i, level*segments+j, (level+1)*segments+j, (level+1)*segments+i],
                 0 if is_dark_band(level, i) else 1)
    face(list(reversed(range(segments))), 0)
    face([levels*segments+i for i in range(segments)], 0)
    lines.append('kids 0')
    return '\n'.join(lines)+'\n'


def generate(output, origin=(37.60,-122.35), obstacles=None):
    validate_origin({'latitude':origin[0], 'longitude':origin[1]})
    obstacles = obstacles if obstacles is not None else [
        Obstacle('Tornado A',0,1300,150), Obstacle('Tornado B',500,3300,180), Obstacle('Tornado C',-150,5400,200)]
    for o in obstacles:
        if not all(math.isfinite(v) for v in [o.east,o.north,o.radius,o.bottom,o.top]) or o.radius <= 0 or o.top <= o.bottom:
            raise ValueError('Invalid obstacle geometry')
    output = Path(output)
    # Refuse an existing target to avoid mixing stale scenery tiles into a course.
    output.mkdir(parents=True, exist_ok=False)
    tiles = {}
    for i,o in enumerate(obstacles):
        lat,lon = to_geographic(o.east,o.north,origin)
        tile = output / tile_path(lat,lon)
        tile.parent.mkdir(parents=True,exist_ok=True)
        name=f'tornado-{i+1}.ac'
        (tile.parent/name).write_text(tornado_model(o.radius,o.top-o.bottom))
        tiles.setdefault(tile,[]).append(f'OBJECT_STATIC {name} {lon:.10f} {lat:.10f} {o.bottom:.3f} 0 0 0')
    for tile,lines in tiles.items():
        tile.write_text('\n'.join(lines)+'\n')
    course = {'description':'Fixed geographic obstacle course matching this FlightGear scenery overlay.',
              'origin':{'latitude':origin[0],'longitude':origin[1]},
              'scenery':True, 'obstacles':[asdict(o) for o in obstacles]}
    (output/'course.json').write_text(json.dumps(course,indent=2)+'\n')
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,help='New scenery directory (must not exist)')
    parser.add_argument('--latitude',type=float,default=37.60)
    parser.add_argument('--longitude',type=float,default=-122.35)
    args=parser.parse_args()
    path=generate(args.output,(args.latitude,args.longitude))
    print(f'Created scenery: {path.resolve()}\nController: --obstacles {path.resolve() / "course.json"}')


if __name__ == '__main__':
    main()
