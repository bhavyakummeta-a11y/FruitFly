# landing fly - CONNECTOME, paused through handover (26b50af), clear weather

`2026-11-14T191042Z_michael-taylor_fg-landing-fly-connectome-paused-through-handover-26b50af-clear-weather`, FlightGear session by Michael Taylor.

| | |
|---|---|
| Outcome | FlightGear crashed or was force-closed (exit 3221226356) |
| Duration | 2 min 3 s |
| FlightGear | 2024.1.4, 738-flies |
| Graphics / weather | light / clear |
| Airplane samples | 42 at 2 Hz |
| Max altitude / IAS | 1448 ft / 181 kt |
| FlightGear warnings | 503 lines (fgfs_warnings.log) |
| Controller runs | [2026-11-14T191114Z_michael-taylor_flightgear-connectome](../2026-11-14T191114Z_michael-taylor_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| FLY BRAIN (connectome) flying the landing | 1 min 3 s |
| Nobody: no controller running and no control inputs | 0 min 31 s |
| AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying | 0 min 29 s |

Timeline (seconds from session start):

-      1 to     32: **Nobody: no controller running and no control inputs**
-     32 to     61: **AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying** (engaged: SPD; controller 2026-11-14T191114Z_michael-taylor_flightgear-connectome is running)
-     61 to    123: **FLY BRAIN (connectome) flying the landing** (run 2026-11-14T191114Z_michael-taylor_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope, and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover)

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
