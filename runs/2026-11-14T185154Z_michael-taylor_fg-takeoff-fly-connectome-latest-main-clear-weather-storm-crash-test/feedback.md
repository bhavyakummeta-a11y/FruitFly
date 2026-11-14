# takeoff fly - CONNECTOME, latest main, clear weather (storm crash test)

`2026-11-14T185154Z_michael-taylor_fg-takeoff-fly-connectome-latest-main-clear-weather-storm-crash-test`, FlightGear session by Michael Taylor.

| | |
|---|---|
| Outcome | FlightGear crashed or was force-closed (exit 3221226356) |
| Duration | 2 min 35 s |
| FlightGear | 2024.1.4, 738-flies |
| Graphics / weather | light / clear |
| Airplane samples | 64 at 2 Hz |
| Max altitude / IAS | 21 ft / 160 kt |
| FlightGear warnings | 59 lines (fgfs_warnings.log) |
| Controller runs | [2026-11-14T185223Z_michael-taylor_flightgear-connectome](../2026-11-14T185223Z_michael-taylor_flightgear-connectome/feedback.md), [2026-11-14T185243Z_michael-taylor_flightgear-connectome](../2026-11-14T185243Z_michael-taylor_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| Nobody: no controller running and no control inputs | 1 min 38 s |
| FLY BRAIN (connectome) flying the takeoff | 0 min 50 s |
| UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain | 0 min 6 s |

Timeline (seconds from session start):

-      1 to     51: **Nobody: no controller running and no control inputs**
-     51 to    102: **FLY BRAIN (connectome) flying the takeoff** (run 2026-11-14T185243Z_michael-taylor_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover)
-    102 to    108: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**
-    108 to    155: **Nobody: no controller running and no control inputs**

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
