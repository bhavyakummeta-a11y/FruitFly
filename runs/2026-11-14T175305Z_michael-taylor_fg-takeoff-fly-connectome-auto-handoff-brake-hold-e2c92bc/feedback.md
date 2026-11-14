# takeoff fly - CONNECTOME auto handoff + brake hold (e2c92bc)

`2026-11-14T175305Z_michael-taylor_fg-takeoff-fly-connectome-auto-handoff-brake-hold-e2c92bc`, FlightGear session by Michael Taylor.

| | |
|---|---|
| Outcome | FlightGear crashed or was force-closed (exit 3221226356) |
| Duration | 4 min 58 s |
| FlightGear | 2024.1.4, 738-flies |
| Airplane samples | 132 at 2 Hz |
| Max altitude / IAS | 12 ft / 130 kt |
| FlightGear warnings | 94 lines (fgfs_warnings.log) |
| Controller runs | [2026-11-14T175336Z_michael-taylor_flightgear-connectome](../2026-11-14T175336Z_michael-taylor_flightgear-connectome/feedback.md), [2026-11-14T175737Z_michael-taylor_demo-standin](../2026-11-14T175737Z_michael-taylor_demo-standin/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| FLY BRAIN (connectome) flying the takeoff | 2 min 58 s |
| Nobody: no controller running and no control inputs | 1 min 57 s |
| UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain | 0 min 3 s |

Timeline (seconds from session start):

-      1 to     34: **Nobody: no controller running and no control inputs**
-     34 to    212: **FLY BRAIN (connectome) flying the takeoff** (run 2026-11-14T175336Z_michael-taylor_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: sensory encoding of the aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover)
-    212 to    215: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**
-    215 to    298: **Nobody: no controller running and no control inputs**

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
