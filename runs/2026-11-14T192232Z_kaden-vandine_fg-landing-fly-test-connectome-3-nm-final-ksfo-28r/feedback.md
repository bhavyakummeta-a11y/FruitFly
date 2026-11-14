# landing fly test: connectome, 3 nm final KSFO 28R

`2026-11-14T192232Z_kaden-vandine_fg-landing-fly-test-connectome-3-nm-final-ksfo-28r`, FlightGear session by Kaden VanDine.

| | |
|---|---|
| Outcome | closed normally (exit None) |
| Duration | 1 min 44 s |
| FlightGear | ?, ? |
| Graphics / weather | light / storm |
| Airplane samples | 36 at 2 Hz |
| Max altitude / IAS | 1294 ft / 163 kt |
| FlightGear warnings | 0 lines (fgfs_warnings.log) |
| Video (on the recording machine, not pushed) | none |
| Controller runs | [2026-11-14T192239Z_kaden-vandine_flightgear-connectome](../2026-11-14T192239Z_kaden-vandine_flightgear-connectome/feedback.md), [2026-11-14T191800Z_michael-taylor_flightgear-connectome](../2026-11-14T191800Z_michael-taylor_flightgear-connectome/feedback.md), [2026-11-14T192127Z_michael-taylor_flightgear-connectome](../2026-11-14T192127Z_michael-taylor_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| FLY BRAIN (connectome) flying the landing | 0 min 58 s |
| AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying | 0 min 22 s |
| UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain | 0 min 17 s |
| Nobody: no controller running and no control inputs | 0 min 7 s |

Timeline (seconds from session start):

-      0 to      7: **Nobody: no controller running and no control inputs**
-      7 to     29: **AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying** (engaged: SPD; controller 2026-11-14T192239Z_kaden-vandine_flightgear-connectome is running)
-     29 to     87: **FLY BRAIN (connectome) flying the landing** (run 2026-11-14T192239Z_kaden-vandine_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope, and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover)
-     87 to    104: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
