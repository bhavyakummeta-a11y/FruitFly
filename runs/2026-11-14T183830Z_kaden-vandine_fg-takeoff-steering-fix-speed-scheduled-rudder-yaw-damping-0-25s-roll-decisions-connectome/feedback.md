# takeoff steering fix: speed-scheduled rudder, yaw damping, 0.25s roll decisions (connectome)

`2026-11-14T183830Z_kaden-vandine_fg-takeoff-steering-fix-speed-scheduled-rudder-yaw-damping-0-25s-roll-decisions-connectome`, FlightGear session by Kaden VanDine.

| | |
|---|---|
| Outcome | closed normally (exit None) |
| Duration | 2 min 3 s |
| FlightGear | ?, ? |
| Airplane samples | 61 at 2 Hz |
| Max altitude / IAS | 603 ft / 186 kt |
| FlightGear warnings | 0 lines (fgfs_warnings.log) |
| Controller runs | none |

## Who was flying

| Who | Time |
|---|---|
| UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain | 1 min 25 s |
| Nobody: no controller running and no control inputs | 0 min 38 s |

Timeline (seconds from session start):

-      0 to     38: **Nobody: no controller running and no control inputs**
-     38 to    123: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**

## Notes
- **Kaden VanDine** (2026-11-14 13:41): NOT a fly-brain flight and NOT a test of the steering fix: the mission controller (claude-run-check) never received UDP telemetry and exited. The takeoff to ~450 ft / 186 kt with pause/resume every 1-3 s was flown by an unidentified other program or person (UNATTRIBUTED). Disregard as steering-fix evidence.

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
