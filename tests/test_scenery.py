import json
import math
from pathlib import Path
import tempfile
import unittest
from flight_simulator.scenery import generate, to_local, to_geographic, tile_path, validate_origin
from flight_simulator.__main__ import load_obstacles
from flight_simulator.flightgear import FlightGear


class SceneryTests(unittest.TestCase):
    def test_known_flightgear_tile(self):
        # Example object coordinates/tile from FlightGear's UFO placement guide.
        self.assertEqual(str(tile_path(50.03667992,8.57928135)), 'Objects/e000n50/e008n50/3089154.stg')

    def test_coordinate_roundtrip_and_dateline(self):
        for origin in [(37.6,-122.35),(-35.2,149.1),(40,179.999)]:
            for east,north in [(500,3300),(-150,5400),(0,0)]:
                lat,lon=to_geographic(east,north,origin)
                actual=to_local(lat,lon,origin)
                self.assertAlmostEqual(actual[0],east,places=6)
                self.assertAlmostEqual(actual[1],north,places=6)

    def test_models_and_placements_match_controller(self):
        with tempfile.TemporaryDirectory() as directory:
            root=generate(Path(directory)/'Scenery')
            course=json.loads((root/'course.json').read_text())
            origin=validate_origin(course['origin'])
            obstacles=load_obstacles(root/'course.json')
            placements=[]
            for tile in root.rglob('*.stg'):
                for line in tile.read_text().splitlines():
                    token,model,lon,lat,alt,*angles=line.split()
                    self.assertEqual(token,'OBJECT_STATIC')
                    self.assertEqual(tile.relative_to(root),tile_path(float(lat),float(lon)))
                    placements.append((tile.parent/model,float(lat),float(lon),float(alt)))
            self.assertEqual(len(placements),len(obstacles))
            for model,lat,lon,alt in placements:
                i=int(model.stem.split('-')[1])-1
                o=obstacles[i]
                east,north=to_local(lat,lon,origin)
                self.assertAlmostEqual(east,o.east,places=4)
                self.assertAlmostEqual(north,o.north,places=4)
                self.assertEqual(alt,o.bottom)
                lines=model.read_text().splitlines()
                index=next(j for j,l in enumerate(lines) if l.startswith('numvert '))
                count=int(lines[index].split()[1])
                vertices=[tuple(map(float,l.split())) for l in lines[index+1:index+1+count]]
                self.assertEqual(min(v[1] for v in vertices),0)
                self.assertEqual(max(v[1] for v in vertices),o.top-o.bottom)
                for x,y,z in vertices:
                    self.assertAlmostEqual(math.hypot(x,z),o.radius,places=5)
                for j,line in enumerate(lines):
                    if line.startswith('refs '):
                        for ref in lines[j+1:j+1+int(line.split()[1])]:
                            self.assertTrue(0 <= int(ref.split()[0]) < count)
            with self.assertRaises(FileExistsError):
                generate(root)

    def test_fixed_origin_survives_first_telemetry(self):
        bridge=FlightGear(telemetry_port=0)
        try:
            bridge.origin=(37.6,-122.35)
            lat,lon=to_geographic(400,700,bridge.origin)
            state=bridge.parse(f'1,{lat},{lon},3000,0,0,0,100,0,1'.encode())
            self.assertAlmostEqual(state.east,400,places=6)
            self.assertAlmostEqual(state.north,700,places=6)
            self.assertEqual(bridge.origin,(37.6,-122.35))
        finally:
            bridge.close()

    def test_invalid_origins_rejected(self):
        for lat,lon in [(math.nan,0),(89,0),(0,181)]:
            with self.assertRaises(ValueError):
                validate_origin({'latitude':lat,'longitude':lon})


if __name__ == '__main__':
    unittest.main()
