# 737 takeoff fly - connectome

`2026-11-14T165321Z_michael-taylor_fg-737-takeoff-fly-connectome`, FlightGear session by Michael Taylor.

| | |
|---|---|
| Outcome | FlightGear crashed or was force-closed (exit 3221226356) |
| Duration | 3 min 23 s |
| FlightGear | 2024.1.4, 738-flies |
| Airplane samples | 101 at 2 Hz |
| Max altitude / IAS | 14 ft / 93 kt |
| FlightGear warnings | 29 lines (fgfs_warnings.log) |
| Controller runs | none |

## Notes
- **Michael Taylor** (2026-11-14 11:57): Connectome takeoff (takeoff_landing --brain connectome --backend flightgear) failed: left runway 202 m off centerline after 1.3 s sim time, IAS 92 kt. Root cause: FlightGear did NOT pause during the ~6.5 s brain trials. Setting /sim/freeze/master alone (what all flybrain-*-controls.xml protocols do) does not stop the JSBSim 737 in FG 2024.1.4: master reads true, but position and elapsed-sec keep advancing. Setting /sim/freeze/clock=1 as well does stop it (that's what FG's own 'pause' command sets). Same bug explains the plane flying on uncontrolled after every controller exit. Fix: also drive /sim/freeze/clock from the controls protocols. The stand-in takeoff in the previous session succeeded only because its trials are fast.

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
