# landing fix test: approach elevator -0.22 / pitch 3.7 (Paula's measured trim), connectome

`2026-11-14T212517Z_kaden-vandine_fg-landing-fix-test-approach-elevator-0-22-pitch-3-7-paula-s-measured-trim-connectome`, FlightGear session by Kaden VanDine.

| | |
|---|---|
| Outcome | closed normally (exit None) |
| Duration | 6 min 17 s |
| FlightGear | ?, ? |
| Graphics / weather | light / storm |
| Airplane samples | 208 at 2 Hz |
| Max altitude / IAS | 1000 ft / 152 kt |
| FlightGear warnings | 0 lines (fgfs_warnings.log) |
| Video (on the recording machine, not pushed) | off (opt in: --video / FRUITFLY_VIDEO=1) |
| Controller runs | [2026-11-14T212524Z_kaden-vandine_flightgear-connectome](../2026-11-14T212524Z_kaden-vandine_flightgear-connectome/feedback.md), [2026-11-14T212940Z_kaden-vandine_flightgear-standin](../2026-11-14T212940Z_kaden-vandine_flightgear-standin/feedback.md), [2026-11-14T213050Z_kaden-vandine_flightgear-standin](../2026-11-14T213050Z_kaden-vandine_flightgear-standin/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| Nobody: no controller running and no control inputs | 3 min 31 s |
| FLY BRAIN (connectome) flying the landing | 2 min 8 s |
| AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying | 0 min 25 s |
| UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain | 0 min 12 s |

Timeline (seconds from session start):

-      0 to      7: **Nobody: no controller running and no control inputs**
-      7 to     31: **AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying** (engaged: SPD; controller 2026-11-14T212524Z_kaden-vandine_flightgear-connectome is running)
-     31 to    160: **FLY BRAIN (connectome) flying the landing** (run 2026-11-14T212524Z_kaden-vandine_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope, and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover)
-    160 to    166: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**
-    166 to    253: **Nobody: no controller running and no control inputs**
-    253 to    259: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**
-    259 to    377: **Nobody: no controller running and no control inputs**

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
