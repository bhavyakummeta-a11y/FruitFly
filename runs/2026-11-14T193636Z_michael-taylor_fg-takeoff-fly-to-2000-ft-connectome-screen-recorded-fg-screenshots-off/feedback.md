# takeoff fly to 2000 ft - CONNECTOME, screen-recorded, FG screenshots off

`2026-11-14T193636Z_michael-taylor_fg-takeoff-fly-to-2000-ft-connectome-screen-recorded-fg-screenshots-off`, FlightGear session by Michael Taylor.

| | |
|---|---|
| Outcome | FlightGear crashed or was force-closed (exit 4294967295) |
| Duration | 2 min 45 s |
| FlightGear | 2024.1.4, 738-flies |
| Graphics / weather | light / clear |
| Airplane samples | 35 at 2 Hz |
| Max altitude / IAS | 15 ft / 119 kt |
| FlightGear warnings | 49 lines (fgfs_warnings.log) |
| Video (on the recording machine, not pushed) | none |
| Controller runs | [2026-11-14T193710Z_michael-taylor_flightgear-connectome](../2026-11-14T193710Z_michael-taylor_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| Nobody: no controller running and no control inputs | 1 min 51 s |
| FLY BRAIN (connectome) flying the takeoff | 0 min 49 s |
| UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain | 0 min 3 s |

Timeline (seconds from session start):

-      1 to     40: **Nobody: no controller running and no control inputs**
-     40 to     89: **FLY BRAIN (connectome) flying the takeoff** (run 2026-11-14T193710Z_michael-taylor_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope, and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover)
-     89 to     92: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**
-     92 to    165: **Nobody: no controller running and no control inputs**

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
