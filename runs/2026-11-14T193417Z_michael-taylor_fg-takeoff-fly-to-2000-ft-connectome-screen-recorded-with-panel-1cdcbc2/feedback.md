# takeoff fly to 2000 ft - CONNECTOME, screen-recorded with panel (1cdcbc2)

`2026-11-14T193417Z_michael-taylor_fg-takeoff-fly-to-2000-ft-connectome-screen-recorded-with-panel-1cdcbc2`, FlightGear session by Michael Taylor.

| | |
|---|---|
| Outcome | FlightGear crashed or was force-closed (exit 1073741845) |
| Duration | 1 min 28 s |
| FlightGear | 2024.1.4, 738-flies |
| Graphics / weather | light / clear |
| Airplane samples | 20 at 2 Hz |
| Max altitude / IAS | 10 ft / 114 kt |
| FlightGear warnings | 41 lines (fgfs_warnings.log) |
| Video (on the recording machine, not pushed) | none |
| Controller runs | [2026-11-14T193453Z_michael-taylor_flightgear-connectome](../2026-11-14T193453Z_michael-taylor_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| FLY BRAIN (connectome) flying the takeoff | 0 min 49 s |
| Nobody: no controller running and no control inputs | 0 min 38 s |

Timeline (seconds from session start):

-      1 to     39: **Nobody: no controller running and no control inputs**
-     39 to     88: **FLY BRAIN (connectome) flying the takeoff** (run 2026-11-14T193453Z_michael-taylor_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope, and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover)

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
