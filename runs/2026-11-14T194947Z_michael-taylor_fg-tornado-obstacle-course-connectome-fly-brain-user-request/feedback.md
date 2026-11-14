# tornado obstacle course - CONNECTOME fly brain (user request)

`2026-11-14T194947Z_michael-taylor_fg-tornado-obstacle-course-connectome-fly-brain-user-request`, FlightGear session by Michael Taylor.

| | |
|---|---|
| Outcome | FlightGear crashed or was force-closed (exit 3221225477) |
| Duration | 1 min 14 s |
| FlightGear | 2024.1.4, 738-flies |
| Graphics / weather | light / storm |
| Airplane samples | 19 at 2 Hz |
| Max altitude / IAS | 3204 ft / 246 kt |
| FlightGear warnings | 44 lines (fgfs_warnings.log) |
| Video (on the recording machine, not pushed) | none |
| Controller runs | [2026-11-14T195024Z_michael-taylor_flightgear-connectome](../2026-11-14T195024Z_michael-taylor_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| Nobody: no controller running and no control inputs | 0 min 27 s |
| FLY BRAIN (connectome) decides when to escape; code flies the airplane | 0 min 25 s |
| AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying | 0 min 22 s |

Timeline (seconds from session start):

-      1 to     27: **Nobody: no controller running and no control inputs**
-     27 to     50: **AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying** (engaged: CMDA, SPD; controller 2026-11-14T195024Z_michael-taylor_flightgear-connectome is running)
-     50 to     74: **FLY BRAIN (connectome) decides when to escape; code flies the airplane** (run 2026-11-14T195024Z_michael-taylor_flightgear-connectome. Neurons decide: escape request: Giant Fibre (DNp01) response to synthetic looming and path cues; training retains looming-only input. Code decides: synthetic visual encoding, turn direction (from obstacle geometry), holding altitude, speed and heading, and flying the avoidance turn (conventional FlightController))

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
