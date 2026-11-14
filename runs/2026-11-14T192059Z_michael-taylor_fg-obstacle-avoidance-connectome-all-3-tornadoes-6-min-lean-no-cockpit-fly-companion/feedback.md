# obstacle avoidance - CONNECTOME, all 3 tornadoes (6 min, lean: no cockpit fly/companion)

`2026-11-14T192059Z_michael-taylor_fg-obstacle-avoidance-connectome-all-3-tornadoes-6-min-lean-no-cockpit-fly-companion`, FlightGear session by Michael Taylor.

| | |
|---|---|
| Outcome | FlightGear crashed or was force-closed (exit 3221225477) |
| Duration | 1 min 15 s |
| FlightGear | 2024.1.4, 738-flies |
| Graphics / weather | light / clear |
| Airplane samples | 21 at 2 Hz |
| Max altitude / IAS | 2982 ft / 252 kt |
| FlightGear warnings | 43 lines (fgfs_warnings.log) |
| Video (on the recording machine, not pushed) | none |
| Controller runs | [2026-11-14T192127Z_michael-taylor_flightgear-connectome](../2026-11-14T192127Z_michael-taylor_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| FLY BRAIN (connectome) decides when to escape; code flies the airplane | 0 min 35 s |
| Nobody: no controller running and no control inputs | 0 min 29 s |
| AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying | 0 min 10 s |

Timeline (seconds from session start):

-      1 to     29: **Nobody: no controller running and no control inputs**
-     29 to     39: **AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying** (engaged: CMDA, SPD; controller 2026-11-14T192127Z_michael-taylor_flightgear-connectome is running)
-     39 to     75: **FLY BRAIN (connectome) decides when to escape; code flies the airplane** (run 2026-11-14T192127Z_michael-taylor_flightgear-connectome. Neurons decide: escape request: Giant Fibre (DNp01) response to synthetic looming and path cues; training retains looming-only input. Code decides: synthetic visual encoding, turn direction (from obstacle geometry), holding altitude, speed and heading, and flying the avoidance turn (conventional FlightController))

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
