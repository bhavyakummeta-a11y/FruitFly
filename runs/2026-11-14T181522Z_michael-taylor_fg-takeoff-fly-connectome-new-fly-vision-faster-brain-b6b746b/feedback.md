# takeoff fly - CONNECTOME + new fly vision + faster brain (b6b746b)

`2026-11-14T181522Z_michael-taylor_fg-takeoff-fly-connectome-new-fly-vision-faster-brain-b6b746b`, FlightGear session by Michael Taylor.

| | |
|---|---|
| Outcome | FlightGear crashed or was force-closed (exit 3221226356) |
| Duration | 2 min 31 s |
| FlightGear | ?, ? |
| Airplane samples | 45 at 2 Hz |
| Max altitude / IAS | 9 ft / 104 kt |
| FlightGear warnings | 0 lines (fgfs_warnings.log) |
| Controller runs | [2026-11-14T181613Z_michael-taylor_flightgear-connectome](../2026-11-14T181613Z_michael-taylor_flightgear-connectome/feedback.md), [2026-11-14T181618Z_michael-taylor_demo-standin](../2026-11-14T181618Z_michael-taylor_demo-standin/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| Nobody: no controller running and no control inputs | 1 min 35 s |
| FLY BRAIN (connectome) flying the takeoff | 0 min 45 s |
| UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain | 0 min 8 s |

Timeline (seconds from session start):

-      2 to     53: **Nobody: no controller running and no control inputs**
-     53 to     56: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**
-     56 to    101: **FLY BRAIN (connectome) flying the takeoff** (run 2026-11-14T181613Z_michael-taylor_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover)
-    101 to    107: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**
-    107 to    151: **Nobody: no controller running and no control inputs**

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
