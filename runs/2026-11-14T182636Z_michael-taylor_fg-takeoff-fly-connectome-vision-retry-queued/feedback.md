# takeoff fly - CONNECTOME + vision, retry (queued)

`2026-11-14T182636Z_michael-taylor_fg-takeoff-fly-connectome-vision-retry-queued`, FlightGear session by Michael Taylor.

| | |
|---|---|
| Outcome | FlightGear crashed or was force-closed (exit 3221226356) |
| Duration | 1 min 59 s |
| FlightGear | 2024.1.4, 738-flies |
| Airplane samples | 53 at 2 Hz |
| Max altitude / IAS | 17 ft / 118 kt |
| FlightGear warnings | 55 lines (fgfs_warnings.log) |
| Controller runs | [2026-11-14T182703Z_michael-taylor_flightgear-connectome](../2026-11-14T182703Z_michael-taylor_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| Nobody: no controller running and no control inputs | 1 min 5 s |
| FLY BRAIN (connectome) flying the takeoff | 0 min 51 s |
| UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain | 0 min 3 s |

Timeline (seconds from session start):

-      1 to     31: **Nobody: no controller running and no control inputs**
-     31 to     82: **FLY BRAIN (connectome) flying the takeoff** (run 2026-11-14T182703Z_michael-taylor_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover)
-     82 to     85: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**
-     85 to    119: **Nobody: no controller running and no control inputs**

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
