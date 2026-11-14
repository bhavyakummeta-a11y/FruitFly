# graphics benchmark: full profile, KSFO runway, no controller

`2026-11-14T181508Z_michael-taylor_fg-graphics-benchmark-full-profile-ksfo-runway-no-controller`, FlightGear session by Michael Taylor.

| | |
|---|---|
| Outcome | FlightGear crashed or was force-closed (exit 1073741845) |
| Duration | 2 min 15 s |
| FlightGear | 2024.1.4, 738-flies |
| Airplane samples | 41 at 2 Hz |
| Max altitude / IAS | 6 ft / 0 kt |
| FlightGear warnings | 48 lines (fgfs_warnings.log) |
| Controller runs | [2026-11-14T181613Z_michael-taylor_flightgear-connectome](../2026-11-14T181613Z_michael-taylor_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| Nobody: no controller running and no control inputs | 1 min 27 s |
| FLY BRAIN (connectome) flying the takeoff | 0 min 48 s |

Timeline (seconds from session start):

-      1 to     70: **Nobody: no controller running and no control inputs**
-     70 to    118: **FLY BRAIN (connectome) flying the takeoff** (run 2026-11-14T181613Z_michael-taylor_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover)
-    118 to    135: **Nobody: no controller running and no control inputs**

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
