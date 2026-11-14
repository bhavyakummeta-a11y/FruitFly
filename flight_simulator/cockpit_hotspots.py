"""Capture FlightGear's yellow clickable-control highlights and locate them.

FlightGear draws every clickable cockpit control in yellow when
/sim/panel-hotspots is on (Ctrl-C in the sim). This tool, via the httpd
property server:

  1. pauses the sim and looks around the cockpit from a few view angles,
  2. screenshots each view with highlights off and on,
  3. finds the yellow regions (yellow in the "on" frame but not in "off",
     so painted yellow gauge arcs are ignored),
  4. writes one JSON with each region's pixel box and its direction from the
     pilot's eye as azimuth/elevation in degrees (+az = right, +el = up,
     relative to the aircraft nose).

Azimuth/elevation is the form a fly's visual system works in (receptive fields
over the eye), so the brain side can use it directly.

    python -m flight_simulator.cockpit_hotspots --port 8090 --out cockpit/c172p

Names are not attached yet: a region is "some clickable control at this
direction". Regions near a view's edge can be cut off; the same control can
appear in several views. Restores the view, hotspot setting and pause state
when done.
"""
import argparse
import io
import json
import math
from pathlib import Path
import time
import urllib.request

import numpy as np
from PIL import Image
from scipy import ndimage

# name, heading offset (deg, + = look left as FlightGear defines it), pitch offset (deg)
VIEWS = [('center', 0, -12), ('panel-low', 0, -30), ('left', 35, -20), ('right', -35, -20)]


class FG:
    def __init__(self, host, port):
        self.base = f'http://{host}:{port}'

    def get(self, path):
        with urllib.request.urlopen(f'{self.base}/json{path}', timeout=5) as r:
            return json.load(r).get('value')

    def set(self, path, value):
        req = urllib.request.Request(f'{self.base}/json{path}', json.dumps({'value': value}).encode(),
                                     method='POST')
        urllib.request.urlopen(req, timeout=5).read()

    def screenshot(self):
        with urllib.request.urlopen(f'{self.base}/screenshot?type=png', timeout=15) as r:
            return np.asarray(Image.open(io.BytesIO(r.read())).convert('RGB'))


def yellow(img):
    r, g, b = (img[..., i].astype(int) for i in range(3))
    return (r > 170) & (g > 150) & (b < 110) & (r - b > 90)


def regions(on, off, min_pixels=12):
    mask = yellow(on) & ~ndimage.binary_dilation(yellow(off), iterations=1)
    mask[:30] = False  # menubar
    grown = ndimage.binary_dilation(mask, iterations=3)  # hotspots are drawn as wireframe lines
    labels, n = ndimage.label(grown)
    out = []
    for i, sl in enumerate(ndimage.find_objects(labels), 1):
        hits = mask[sl] & (labels[sl] == i)
        if hits.sum() < min_pixels:
            continue
        ys, xs = np.nonzero(hits)
        out.append({'x0': int(sl[1].start), 'y0': int(sl[0].start), 'x1': int(sl[1].stop), 'y1': int(sl[0].stop),
                    'cx': float(xs.mean() + sl[1].start), 'cy': float(ys.mean() + sl[0].start),
                    'pixels': int(hits.sum())})
    return out


def direction(cx, cy, width, height, hfov_deg, heading_deg, pitch_deg):
    """Pixel -> (azimuth right, elevation up) in degrees relative to the aircraft nose."""
    f = (width / 2) / math.tan(math.radians(hfov_deg) / 2)
    right, up, fwd = cx - width / 2, height / 2 - cy, f
    p = math.radians(pitch_deg)
    up, fwd = up * math.cos(p) + fwd * math.sin(p), fwd * math.cos(p) - up * math.sin(p)
    az = math.degrees(math.atan2(right, fwd)) - heading_deg
    el = math.degrees(math.atan2(up, math.hypot(right, fwd)))
    return round(az, 2), round(el, 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--host', default='localhost')
    ap.add_argument('--port', type=int, default=8080, help='FlightGear --httpd port (instance N: 8080+10N)')
    ap.add_argument('--out', required=True, help='Output folder for PNGs and hotspots.json')
    ap.add_argument('--settle', type=float, default=1.0, help='Seconds to wait after moving the view')
    args = ap.parse_args()
    fg = FG(args.host, args.port)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    saved = {p: fg.get(p) for p in ['/sim/panel-hotspots', '/sim/freeze/master',
                                     '/sim/current-view/heading-offset-deg', '/sim/current-view/pitch-offset-deg']}
    aircraft = fg.get('/sim/aircraft')
    view_name = fg.get('/sim/current-view/name')
    if view_name != 'Cockpit View':
        raise SystemExit(f'Switch FlightGear to Cockpit View first (current: {view_name}).')
    hfov = float(fg.get('/sim/current-view/field-of-view'))
    result = {'aircraft': aircraft, 'captured': time.strftime('%Y-%m-%dT%H:%M:%S'),
              'field_of_view_deg': hfov,
              'eye_offset_m': {k: fg.get(f'/sim/current-view/{k}-offset-m') for k in 'xyz'},
              'conventions': 'az_deg + = right of nose, el_deg + = above horizon of aircraft body axes; '
                             'pixel boxes are x0,y0 inclusive / x1,y1 exclusive in the PNG',
              'views': []}
    try:
        fg.set('/sim/freeze/master', True)
        for name, heading, pitch in VIEWS:
            for k, v in (('heading', heading), ('pitch', pitch)):
                fg.set(f'/sim/current-view/{k}-offset-deg', v)
                fg.set(f'/sim/current-view/goal-{k}-offset-deg', v)
            fg.set('/sim/panel-hotspots', False)
            time.sleep(args.settle)
            off = fg.screenshot()
            fg.set('/sim/panel-hotspots', True)
            time.sleep(0.5)
            on = fg.screenshot()
            h, w = on.shape[:2]
            Image.fromarray(off).save(out / f'{name}.png')
            Image.fromarray(on).save(out / f'{name}-hotspots.png')
            spots = regions(on, off)
            for s in spots:
                s['az_deg'], s['el_deg'] = direction(s['cx'], s['cy'], w, h, hfov, heading, pitch)
                s['cx'], s['cy'] = round(s['cx'], 1), round(s['cy'], 1)
            result['views'].append({'name': name, 'heading_offset_deg': heading, 'pitch_offset_deg': pitch,
                                    'width': w, 'height': h, 'image': f'{name}.png',
                                    'hotspot_image': f'{name}-hotspots.png', 'hotspots': spots})
            print(f'{name:10} {len(spots):3} hotspots')
    finally:
        for p, v in saved.items():
            if v is not None:
                fg.set(p, v)
                if 'offset-deg' in p:
                    fg.set(p.replace('/sim/current-view/', '/sim/current-view/goal-'), v)
    (out / 'hotspots.json').write_text(json.dumps(result, indent=1))
    print(f'Wrote {out / "hotspots.json"}')


if __name__ == '__main__':
    main()
