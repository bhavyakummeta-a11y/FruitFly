# obstacle avoidance - CONNECTOME (numba brain + vision, bcfa42e)

`2026-11-14T183145Z_michael-taylor_fg-obstacle-avoidance-connectome-numba-brain-vision-bcfa42e`, FlightGear session by Michael Taylor.

| | |
|---|---|
| Outcome | FlightGear crashed or was force-closed (exit 4294967295) |
| Duration | 7 min 47 s |
| FlightGear | 2024.1.4, 738-flies |
| Airplane samples | 243 at 2 Hz |
| Max altitude / IAS | 3346 ft / 340 kt |
| FlightGear warnings | 156 lines (fgfs_warnings.log) |
| Controller runs | [2026-11-14T183208Z_michael-taylor_flightgear-connectome](../2026-11-14T183208Z_michael-taylor_flightgear-connectome/feedback.md), [2026-11-14T183529Z_michael-taylor_flightgear-connectome](../2026-11-14T183529Z_michael-taylor_flightgear-connectome/feedback.md), [2026-11-14T183613Z_michael-taylor_flightgear-connectome](../2026-11-14T183613Z_michael-taylor_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying | 3 min 31 s |
| FLY BRAIN (connectome) decides when to escape; code flies the airplane | 2 min 12 s |
| Nobody: no controller running and no control inputs | 1 min 56 s |
| UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain | 0 min 8 s |

Timeline (seconds from session start):

-      1 to     26: **Nobody: no controller running and no control inputs**
-     26 to    237: **AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying** (engaged: CMDA, SPD; controller 2026-11-14T183529Z_michael-taylor_flightgear-connectome is running)
-    237 to    244: **FLY BRAIN (connectome) decides when to escape; code flies the airplane** (run 2026-11-14T183529Z_michael-taylor_flightgear-connectome. Neurons decide: escape request: Giant Fibre (DNp01) response to synthetic looming and path cues; training retains looming-only input. Code decides: synthetic visual encoding, turn direction (from obstacle geometry), holding altitude, speed and heading, and flying the avoidance turn (conventional FlightController))
-    244 to    247: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**
-    247 to    272: **Nobody: no controller running and no control inputs**
-    272 to    398: **FLY BRAIN (connectome) decides when to escape; code flies the airplane** (run 2026-11-14T183613Z_michael-taylor_flightgear-connectome. Neurons decide: escape request: Giant Fibre (DNp01) response to synthetic looming and path cues; training retains looming-only input. Code decides: synthetic visual encoding, turn direction (from obstacle geometry), holding altitude, speed and heading, and flying the avoidance turn (conventional FlightController))
-    398 to    402: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**
-    402 to    467: **Nobody: no controller running and no control inputs**

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
