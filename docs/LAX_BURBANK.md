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

## The storm story

The route tells one story (`flight_simulator/route_weather.py`):

| Stage | Where (route km from KLAX 25R) | Sky | Tornadoes |
|---|---|---|---|
| clear | takeoff and the westbound departure leg | clear, a few high clouds | hidden |
| darkening | after the turn north, 12 km before tornado 1 | lowering overcast, light rain | hidden |
| storm | 8 km before tornado 1 until 4 km past tornado 2 | thunderstorm, heavy rain, lightning, thunder, the roar | shown |
| clearing | past the tornadoes | rain easing, no lightning | behind you |
| burbank | start of the Burbank intercept leg | fair | behind you |

At the burbank stage the fly gets its **runway briefing**: KBUR 08 threshold,
true heading, length, width, threshold elevation, 3 deg glide path, calm wind.
It appears on FlightGear's screen as an ATC message and is logged.
`result.json` keeps it as `runway_briefing`, with the stages reached as
`sky_stages`. The landing never starts without the briefing. It is runway data
the code supplies, not something the fly perceives.

Stages follow the airplane's position along the route, not the clock, and only
move forward. The weather is looks only: every METAR has calm wind (00000KT),
turbulence stays 0, and cloud bases stay above the 5,000 ft cruise and the
tornado tops (about 7,300 ft MSL). The controller changes the sky live by
writing the METAR to `/environment/metar/data`, the same way FlightGear's
weather dialog does. A failed change is logged in `sky_applied` and the flight
goes on.

The route planner knows the tornado positions from the start (they are the
route's known obstacles). FlightGear shows them only from the storm stage. That
stage begins 8 km before the first tornado, beyond the planner's at most 70 s
look-ahead, so nothing is avoided before it can be seen.

`launch_fg --route lax-burbank` starts with a clear sky. Pass `--weather storm`
or `--weather clear` to fix the weather for the whole flight instead: the
launcher then starts the controller with `--sky fixed`, which leaves the
weather and the tornado models alone. The runway briefing is still given and
logged either way.

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

Local validation on 2026-11-14:

| Brain | Minimum obstacle clearance | Touchdown along KBUR 08 | Sink at touchdown | Stop along runway |
|---|---:|---:|---:|---:|
| Deterministic stand-in | 357 m | 553 m | 214 ft/min | 1,208 m |
| Noisy stand-in (seed 1) | 335 m | 543 m | 231 ft/min | 1,198 m |
| Real connectome (seed 0) | 348 m | 575 m | 263 ft/min | 1,250 m |

All three completed both avoidance events and a full-stop landing. The real
connectome run took about eight minutes of wall time in the offline model;
this is not a FlightGear real-time performance measurement. The full suite
passed 215 tests (five skipped), followed by a separate live-runner regression
verifying that touchdown and runway bounds use Burbank's frame. After the latest
teammate merge, 41 relevant launcher, logging, guard and route checks also passed.

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
