# obstacle avoidance - CONNECTOME, quiet cockpit (0224f28), clear weather

`2026-11-14T191738Z_michael-taylor_fg-obstacle-avoidance-connectome-quiet-cockpit-0224f28-clear-weather`, FlightGear session by Michael Taylor.

| | |
|---|---|
| Outcome | FlightGear crashed or was force-closed (exit 3221225477) |
| Duration | 0 min 59 s |
| FlightGear | 2024.1.4, 738-flies |
| Graphics / weather | light / clear |
| Airplane samples | 16 at 2 Hz |
| Max altitude / IAS | 3000 ft / 253 kt |
| FlightGear warnings | 46 lines (fgfs_warnings.log) |
| Video (on the recording machine, not pushed) | none |
| Controller runs | [2026-11-14T191800Z_michael-taylor_flightgear-connectome](../2026-11-14T191800Z_michael-taylor_flightgear-connectome/feedback.md), [2026-11-14T191139Z_kaden-vandine_flightgear-connectome](../2026-11-14T191139Z_kaden-vandine_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| Nobody: no controller running and no control inputs | 0 min 24 s |
| FLY BRAIN (connectome) decides when to escape; code flies the airplane | 0 min 24 s |
| AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying | 0 min 10 s |

Timeline (seconds from session start):

-      1 to     25: **Nobody: no controller running and no control inputs**
-     25 to     35: **AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying** (engaged: CMDA, SPD; controller 2026-11-14T191800Z_michael-taylor_flightgear-connectome is running)
-     35 to     59: **FLY BRAIN (connectome) decides when to escape; code flies the airplane** (run 2026-11-14T191800Z_michael-taylor_flightgear-connectome. Neurons decide: escape request: Giant Fibre (DNp01) response to synthetic looming and path cues; training retains looming-only input. Code decides: synthetic visual encoding, turn direction (from obstacle geometry), holding altitude, speed and heading, and flying the avoidance turn (conventional FlightController))

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
