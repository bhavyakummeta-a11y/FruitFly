# landing fly - CONNECTOME, latest main, clear weather (retry after stage-file fix)

`2026-11-14T190052Z_michael-taylor_fg-landing-fly-connectome-latest-main-clear-weather-retry-after-stage-file-fix`, FlightGear session by Michael Taylor.

| | |
|---|---|
| Outcome | FlightGear crashed or was force-closed (exit 3221226356) |
| Duration | 1 min 36 s |
| FlightGear | 2024.1.4, 738-flies |
| Graphics / weather | light / clear |
| Airplane samples | 33 at 2 Hz |
| Max altitude / IAS | 1346 ft / 164 kt |
| FlightGear warnings | 52 lines (fgfs_warnings.log) |
| Controller runs | [2026-11-14T190118Z_michael-taylor_flightgear-connectome](../2026-11-14T190118Z_michael-taylor_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| FLY BRAIN (connectome) flying the landing | 0 min 57 s |
| Nobody: no controller running and no control inputs | 0 min 29 s |
| AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying | 0 min 10 s |

Timeline (seconds from session start):

-      1 to     29: **Nobody: no controller running and no control inputs**
-     29 to     39: **AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying** (engaged: CMDA, SPD; controller 2026-11-14T190118Z_michael-taylor_flightgear-connectome is running)
-     39 to     96: **FLY BRAIN (connectome) flying the landing** (run 2026-11-14T190118Z_michael-taylor_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope, and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover)

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
