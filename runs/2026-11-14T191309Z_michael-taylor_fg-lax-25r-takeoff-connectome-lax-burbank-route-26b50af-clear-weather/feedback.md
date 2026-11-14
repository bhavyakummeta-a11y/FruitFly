# LAX 25R takeoff - CONNECTOME, LAX-Burbank route (26b50af), clear weather

`2026-11-14T191309Z_michael-taylor_fg-lax-25r-takeoff-connectome-lax-burbank-route-26b50af-clear-weather`, FlightGear session by Michael Taylor.

| | |
|---|---|
| Outcome | FlightGear crashed or was force-closed (exit 1073741845) |
| Duration | 2 min 31 s |
| FlightGear | 2024.1.4, 738-flies |
| Graphics / weather | light / clear |
| Airplane samples | 54 at 2 Hz |
| Max altitude / IAS | 1206 ft / 207 kt |
| FlightGear warnings | 59 lines (fgfs_warnings.log) |
| Video (on the recording machine, not pushed) | none |
| Controller runs | [2026-11-14T191408Z_michael-taylor_flightgear-connectome](../2026-11-14T191408Z_michael-taylor_flightgear-connectome/feedback.md), [2026-11-14T191437Z_michael-taylor_demo-standin](../2026-11-14T191437Z_michael-taylor_demo-standin/feedback.md), [2026-11-14T191437Z_michael-taylor_flightgear-standin](../2026-11-14T191437Z_michael-taylor_flightgear-standin/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| FLY BRAIN (connectome) flying the full mission (takeoff, circuit, landing) | 1 min 28 s |
| Nobody: no controller running and no control inputs | 1 min 2 s |

Timeline (seconds from session start):

-      1 to     63: **Nobody: no controller running and no control inputs**
-     63 to    151: **FLY BRAIN (connectome) flying the full mission (takeoff, circuit, landing)** (run 2026-11-14T191408Z_michael-taylor_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope, and phase handover (flies.py); airport waypoints, MSL/runway transforms, predictive obstacle heading selection, and destination rollout braking are code rules (airport_route.py))

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
