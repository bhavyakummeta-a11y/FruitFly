# LAX to Burbank simulation mission

The old launcher default is **KSFO 28R**, not LAX. The explicit route option
below starts at **KLAX 25R** and targets **KBUR 08**. It runs takeoff, transit with
known-obstacle avoidance, approach, landing and braking to a full stop. A rejected
takeoff, go-around, obstacle hit or runway excursion is not destination success.

## Run in FlightGear

Pull the latest code, then use the project Python environment:

```sh
git pull --rebase
python -m flight_simulator.launch_fg --route lax-burbank --fly connectome --name "LAX to Burbank route test"
```

Use `--fg "<FlightGear install directory or fgfs executable>"` if the default
installation path does not match your machine. For a bare executable or Mac app,
set `FG_ROOT` to FlightGear's data directory so the launcher can install the
updated telemetry protocol. Both airports' terrain/scenery must be installed
(or downloaded by your FlightGear scenery setup).

The launcher selects KLAX 25R, the 737, runway telemetry and the full mission
controller. It holds the parking brake during setup. The controller validates
position and heading before takeoff: a plane at KSFO or the wrong runway is
rejected rather than silently treating its location as LAX. Keep the default
calibration enabled for the connectome. The route launch has a 30-minute limit.

For the existing synthetic cockpit view and the path map on its right, run:

```sh
python -m flight_simulator.vision_view
```

Its map stays in one geographic frame throughout the flight, shows the full
planned route and obstacles, and switches the runway display from LAX to Burbank
at the landing handover. The FlightGear session brain/log pages still work.
Known obstacles are also published as visible tornado models in FlightGear.
These are deliberately placed simulation obstacles, not real-world objects.

For a controller started separately after the launcher has loaded:

```sh
python -m flight_simulator.mission --route lax-burbank --brain connectome --backend flightgear --seconds 1800
```

Do not start two controllers or two FlightGear instances together.

## Local test without opening FlightGear

```sh
python -m flight_simulator.mission --route lax-burbank --brain standin --vision-port 0 --log runs/lax-burbank.csv
```

`standin` is a deterministic lookup model, **not** the connectome. Use
`--brain connectome` for the actual neural model. During logging-code tests,
set `FRUITFLY_NO_PUSH=1` to save runs locally without publishing them.

## What drives the aircraft

The route goes west after departure, turns north, intercepts a long eastbound
final and descends to Burbank. Waypoints are an experimental simulation route,
not a published departure/arrival procedure. Cruise targets are in feet MSL;
landing height and lateral guidance use the destination runway reference.
The landing controller never reuses the departure centerline as Burbank's.

Neural readouts still drive pitch, bank, steering and throttle. Code supplies
waypoint/altitude sensory cues, predicts headings around the known obstacle
cylinders, limits bank, selects flight phases and applies rollout braking.
Obstacle looming reaches the brain without suppressing cruise appetite. A
blocked final requests a go-around, not a low-altitude avoidance turn. The
predictive planner is a code rule, not learned neural route planning.

The airplane's autopilot/autothrottle remain off. Brain trials run in the
background at 1x without pausing at phase changes. All phase calibrations finish
before flight. A failed avoidance prediction is logged while an escape turn and
climb are requested; it does not pause the simulator mid-flight.

The runway protocol now adds **MSL altitude** as a 14th field. Old 11/13-field
protocols still work for single-airport tests; this route explicitly requires
the new field. Live terrain clearance is separate and raises the transit
altitude target when clearance falls below 300 m. This is a reactive check,
not terrain-ahead sensing or a terrain-clearance guarantee. Arbitrary scenery
objects and camera detections are not automatically added to this route's
obstacle map.

`--vision-obstacles path.json` replaces the two default known obstacles. The
file uses the existing obstacle list format: `east` is **right of LAX 25R**,
`north` is **along LAX 25R**, and `bottom`/`top` are metres above the LAX runway
datum. Do not pass an unrelated KSFO scenery course. The controller converts
this geometry for rendering and for Burbank final.

## Results and limits

The local deterministic flight clears both obstacles, touches down at Burbank,
and brakes to a stop within the 1,768 m runway. Tests cover geographic frame
round trips, the altitude-datum change, wrong-start rejection, the launcher,
old/new telemetry, obstacle sensing, go-around and full-stop completion.

This reduced model has no intervening terrain mesh, wind or real 737 brake
model. Passing it does not validate the Windows FlightGear aircraft. Inspect
`result.json` for `departure`, `destination`, `outcome`, `success`,
`minimum_clearance_m`, `avoidance_count` and decision timing after a live run.
Actual go-arounds and failures remain visible; arrival is not guaranteed.

Runway endpoint coordinates, true bearings, elevations and lengths were checked
against FAA-derived [KLAX runway data](https://www.airnav.com/airport/KLAX) and
[KBUR runway data](https://www.airnav.com/airport/KBUR) on 2026-11-14. KBUR's runway
08 threshold elevation is 727.4 ft, distinct from the airport's 778 ft elevation.
The route uses the threshold value. Match the installed FlightGear scenery if
its runway data differs.
