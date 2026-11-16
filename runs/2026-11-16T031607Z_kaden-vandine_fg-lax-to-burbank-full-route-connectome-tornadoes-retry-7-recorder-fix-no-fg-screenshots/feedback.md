# LAX to Burbank full route, connectome, tornadoes (retry 7: recorder fix, no FG screenshots)

`2026-11-16T031607Z_kaden-vandine_fg-lax-to-burbank-full-route-connectome-tornadoes-retry-7-recorder-fix-no-fg-screenshots`, FlightGear session by Kaden VanDine.

| | |
|---|---|
| Outcome | closed normally (exit None) |
| Duration | 13 min 21 s |
| FlightGear | ?, ? |
| Graphics / weather | light / lax |
| Airplane samples | 497 at 2 Hz |
| Max altitude / IAS | 5022 ft / 193 kt |
| FlightGear warnings | 0 lines (fgfs_warnings.log) |
| Video (on the recording machine, not pushed) | off (opt in: --video / FRUITFLY_VIDEO=1) |
| Controller runs | [2026-11-16T031617Z_kaden-vandine_flightgear-connectome](../2026-11-16T031617Z_kaden-vandine_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| FLY BRAIN (connectome) flying the full mission (takeoff, circuit, landing) | 12 min 42 s |
| Nobody: no controller running and no control inputs | 0 min 33 s |
| UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain | 0 min 6 s |

Timeline (seconds from session start):

-      0 to     14: **Nobody: no controller running and no control inputs**
-     14 to    776: **FLY BRAIN (connectome) flying the full mission (takeoff, circuit, landing)** (run 2026-11-16T031617Z_kaden-vandine_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope (no pitch-up once the sink is arrested), landing thrust to idle in the flare (MN9 sets approach power only above it), and phase handover (flies.py); airport waypoints, MSL/runway transforms, predictive obstacle heading selection, and destination rollout braking are code rules (airport_route.py))
-    776 to    782: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**
-    782 to    801: **Nobody: no controller running and no control inputs**

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
