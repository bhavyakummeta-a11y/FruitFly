# Synthetic fly sensory view

The controller now exposes what the fly is told about known obstacles, the
runway and the intended route. This is **synthetic geometry**, not camera image
recognition, ray tracing, or a biological compound-eye simulation. The cockpit
fly remains an animation; its rendered eyes do not collect these measurements.

## Open the view

Install the existing plotting dependencies (`requirements.txt`), then run
this in a separate terminal before starting the controller:

```sh
python -m flight_simulator.vision_view
```

The viewer listens on localhost UDP 5601. Cruise, takeoff/landing (including
`takeoff_live`) and mission controllers publish there automatically. It shows:

- An aircraft-facing projection of configured cylinders and the runway, with a
  path look-ahead marker. Pitch and roll change the projected view.
- A map of the runway, intended route, actual trajectory and (in cruise) planned
  avoidance route.
- Cross-track, heading and height errors; landing glideslope error; obstacle
  warnings and runway-centerline warnings.
- Encoded sensory rates, alongside the inputs whose brain response was last
  applied. Sample age matters: a background brain trial may finish seconds later.
  Loss of telemetry produces a stale-data banner rather than a moving fake plane.

Use `--vision-port 5611` on both viewer and controller for another simultaneous
run; `--vision-port 0` on a controller disables its display stream. The renderer
is a separate process and cannot block the controller. Closing it does not stop
the airplane. It has no controls and cannot enable the airplane autopilot.

For a local visual check without FlightGear:

```sh
python -m flight_simulator --brain reflex --seconds 180 --realtime
```

This is explicitly a non-neural baseline. For a saved example without opening a
window:

```sh
python -m flight_simulator.vision_view --snapshot landing --output runs/vision-landing.png
python -m flight_simulator.vision_view --snapshot obstacle --output runs/vision-obstacle.png
```

## What reaches the brain

In ordinary cruise connectome mode, obstacle geometry produces the existing
looming signal to LC4/LPLC2. Signed heading/cross-track error produces a left/right
HS input pair; height and bank error produce VS input rates. All are bounded to
0–200 Hz and passed to `ConnectomeBrain.run`. These are engineered proxies, not
measured optical flow. DNp01 remains the cruise escape readout; conventional code
still stabilizes the plane and selects safe routes. Extra sensory inputs do not
mean that neural steering or neural altitude control has been demonstrated.

Reflex/silent modes still use only looming and contain no connectome. Existing
reinforcement-learning/checkpoint cruise runs retain their looming-only pathway
to avoid silently changing the training input distribution. The display labels
these modes and shows the actual inputs used.

Takeoff/landing already encode runway centerline error through HS, pitch/roll
correction through VS, and phase-specific rotation/flare cues through looming.
The new view exposes those inputs and their runway/path geometry. Optional known
obstacles add an aversive `bitter` cue. They do **not** increase the runway looming
signal: otherwise an obstacle could mistakenly trigger rotation or landing flare.
The existing phase decoder determines reject/go-around/flight responses. This
input alone does not guarantee obstacle avoidance, especially past V1 or during
flare. Circuit views follow the currently active mission leg.

## Coordinates and configuration

Cruise uses its existing `--obstacles` file, local east/north coordinates and MSL
heights. Its airborne experiment has no runway configured, and the viewer says so.
Runway modes use the existing runway frame: `x` along the runway from the reference
origin, `y` right, heights above the runway datum. The displayed runway uses the
model's configured 3,600 m length and 60 m width. It is not discovered from scenery;
the launch/reference origin must match the physical runway. No airport database
or automatic runway identification is added.

To supply hazards for takeoff/landing or mission mode, pass
`--vision-obstacles path/to/runway-hazards.json`. The JSON uses the same obstacle
schema, but **east means right of centerline, north means along the runway, and
bottom/top are heights above the runway**. Do not reuse an MSL scenery file without
converting its coordinates and heights. For example:

```json
{"obstacles":[{"name":"Runway hazard","east":0,"north":1800,"radius":80,"bottom":0,"top":100}]}
```

Alerts are informational, not new stop conditions: cross-track over 100 m,
heading error over 15 degrees, fixed-target height error over 30 m, and runway
centerline/glideslope thresholds from the existing phase model. Deviation from
nominal cruise can be expected during an avoidance maneuver. Unknown obstacles,
terrain, weather, occlusion and runway markings are not detected.

## Validation

Geometry, signed cue encoding, heading wrap, behind-camera clipping, runway
datum/glideslope checks, phase separation of obstacle and flare inputs, delivery
to the neural interface, and UDP sample timestamps are covered by tests.
A real connectome probe received looming 89.44 Hz, HS 200/0 Hz and VS 84/84 Hz and
returned DNp01 222.5 Hz. This verifies input delivery, not flight performance.
The combined suite passed 143 tests (one skipped). A local connectome cruise
smoke test and the stand-in landing scenario completed successfully. Runway and
obstacle previews were rendered and inspected without opening FlightGear.
Live Windows FlightGear testing of the expanded sensory mix is still needed.
