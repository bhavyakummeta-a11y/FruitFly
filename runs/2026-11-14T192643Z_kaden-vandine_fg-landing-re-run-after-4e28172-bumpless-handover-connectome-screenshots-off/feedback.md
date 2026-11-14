# landing re-run after 4e28172 (bumpless handover), connectome, screenshots off

`2026-11-14T192643Z_kaden-vandine_fg-landing-re-run-after-4e28172-bumpless-handover-connectome-screenshots-off`, FlightGear session by Kaden VanDine.

| | |
|---|---|
| Outcome | closed normally (exit None) |
| Duration | 5 min 7 s |
| FlightGear | ?, ? |
| Graphics / weather | light / storm |
| Airplane samples | 69 at 2 Hz |
| Max altitude / IAS | 1435 ft / 236 kt |
| FlightGear warnings | 0 lines (fgfs_warnings.log) |
| Video (on the recording machine, not pushed) | none |
| Controller runs | [2026-11-14T192652Z_kaden-vandine_flightgear-connectome](../2026-11-14T192652Z_kaden-vandine_flightgear-connectome/feedback.md), [2026-11-14T192754Z_kaden-vandine_flightgear-connectome](../2026-11-14T192754Z_kaden-vandine_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| Nobody: no controller running and no control inputs | 2 min 13 s |
| AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying | 1 min 28 s |
| FLY BRAIN (connectome) flying the landing | 1 min 20 s |
| UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain | 0 min 6 s |

Timeline (seconds from session start):

-      0 to     10: **Nobody: no controller running and no control inputs**
-     10 to     98: **AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying** (engaged: SPD; controller 2026-11-14T192754Z_kaden-vandine_flightgear-connectome is running)
-     98 to    178: **FLY BRAIN (connectome) flying the landing** (run 2026-11-14T192754Z_kaden-vandine_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope, and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover)
-    178 to    184: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**
-    184 to    307: **Nobody: no controller running and no control inputs**

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
