# LAX to Burbank full route, connectome, tornadoes (retry 5: same as retry 4)

`2026-11-16T031106Z_kaden-vandine_fg-lax-to-burbank-full-route-connectome-tornadoes-retry-5-same-as-retry-4`, FlightGear session by Kaden VanDine.

| | |
|---|---|
| Outcome | closed normally (exit None) |
| Duration | 0 min 58 s |
| FlightGear | ?, ? |
| Graphics / weather | light / lax |
| Airplane samples | 23 at 2 Hz |
| Max altitude / IAS | 106 ft / 111 kt |
| FlightGear warnings | 0 lines (fgfs_warnings.log) |
| Video (on the recording machine, not pushed) | off (opt in: --video / FRUITFLY_VIDEO=1) |
| Controller runs | [2026-11-16T031113Z_kaden-vandine_flightgear-connectome](../2026-11-16T031113Z_kaden-vandine_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| FLY BRAIN (connectome) flying the full mission (takeoff, circuit, landing) | 0 min 48 s |
| Nobody: no controller running and no control inputs | 0 min 10 s |

Timeline (seconds from session start):

-      0 to     10: **Nobody: no controller running and no control inputs**
-     10 to     58: **FLY BRAIN (connectome) flying the full mission (takeoff, circuit, landing)** (run 2026-11-16T031113Z_kaden-vandine_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope (no pitch-up once the sink is arrested), landing thrust to idle in the flare (MN9 sets approach power only above it), and phase handover (flies.py); airport waypoints, MSL/runway transforms, predictive obstacle heading selection, and destination rollout braking are code rules (airport_route.py))

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
