# obstacle avoidance - CONNECTOME, immediate takeover (4e85e94)

`2026-11-14T184545Z_michael-taylor_fg-obstacle-avoidance-connectome-immediate-takeover-4e85e94`, FlightGear session by Michael Taylor.

| | |
|---|---|
| Outcome | FlightGear crashed or was force-closed (exit 3221225477) |
| Duration | 3 min 4 s |
| FlightGear | 2024.1.4, 738-flies |
| Graphics / weather | light / storm |
| Airplane samples | 91 at 2 Hz |
| Max altitude / IAS | 2979 ft / 254 kt |
| FlightGear warnings | 79 lines (fgfs_warnings.log) |
| Controller runs | [2026-11-14T184606Z_michael-taylor_flightgear-connectome](../2026-11-14T184606Z_michael-taylor_flightgear-connectome/feedback.md), [2026-11-14T184733Z_michael-taylor_flightgear-connectome](../2026-11-14T184733Z_michael-taylor_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying | 1 min 44 s |
| FLY BRAIN (connectome) decides when to escape; code flies the airplane | 0 min 56 s |
| Nobody: no controller running and no control inputs | 0 min 23 s |

Timeline (seconds from session start):

-      1 to     24: **Nobody: no controller running and no control inputs**
-     24 to    129: **AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying** (engaged: CMDA, SPD; controller 2026-11-14T184733Z_michael-taylor_flightgear-connectome is running)
-    129 to    184: **FLY BRAIN (connectome) decides when to escape; code flies the airplane** (run 2026-11-14T184733Z_michael-taylor_flightgear-connectome. Neurons decide: escape request: Giant Fibre (DNp01) response to synthetic looming and path cues; training retains looming-only input. Code decides: synthetic visual encoding, turn direction (from obstacle geometry), holding altitude, speed and heading, and flying the avoidance turn (conventional FlightController))

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
