# LAX to Burbank full route, connectome, tornado obstacles

`2026-11-16T020654Z_kaden-vandine_fg-lax-to-burbank-full-route-connectome-tornado-obstacles`, FlightGear session by Kaden VanDine.

| | |
|---|---|
| Outcome | closed normally (exit None) |
| Duration | 3 min 24 s |
| FlightGear | ?, ? |
| Graphics / weather | light / lax |
| Airplane samples | 27 at 2 Hz |
| Max altitude / IAS | 100 ft / 0 kt |
| FlightGear warnings | 0 lines (fgfs_warnings.log) |
| Video (on the recording machine, not pushed) | off (opt in: --video / FRUITFLY_VIDEO=1) |
| Controller runs | [2026-11-16T020736Z_kaden-vandine_flightgear-connectome](../2026-11-16T020736Z_kaden-vandine_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| Nobody: no controller running and no control inputs | 3 min 16 s |
| FLY BRAIN (connectome) flying the full mission (takeoff, circuit, landing) | 0 min 8 s |

Timeline (seconds from session start):

-      0 to     44: **Nobody: no controller running and no control inputs**
-     44 to     52: **FLY BRAIN (connectome) flying the full mission (takeoff, circuit, landing)** (run 2026-11-16T020736Z_kaden-vandine_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope (no pitch-up once the sink is arrested), landing thrust to idle in the flare (MN9 sets approach power only above it), and phase handover (flies.py); airport waypoints, MSL/runway transforms, predictive obstacle heading selection, and destination rollout braking are code rules (airport_route.py))
-     52 to    204: **Nobody: no controller running and no control inputs**

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
