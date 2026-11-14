# landing fly: connectome, 3 nm final KSFO 28R (with landing fix, run 3)

`2026-11-14T215615Z_kaden-vandine_fg-landing-fly-connectome-3-nm-final-ksfo-28r-with-landing-fix-run-3`, FlightGear session by Kaden VanDine.

| | |
|---|---|
| Outcome | closed normally (exit None) |
| Duration | 3 min 51 s |
| FlightGear | ?, ? |
| Graphics / weather | light / storm |
| Airplane samples | 73 at 2 Hz |
| Max altitude / IAS | 1000 ft / 151 kt |
| FlightGear warnings | 0 lines (fgfs_warnings.log) |
| Video (on the recording machine, not pushed) | off (opt in: --video / FRUITFLY_VIDEO=1) |
| Controller runs | [2026-11-14T215622Z_kaden-vandine_flightgear-connectome](../2026-11-14T215622Z_kaden-vandine_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| FLY BRAIN (connectome) flying the landing | 3 min 19 s |
| AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying | 0 min 25 s |
| Nobody: no controller running and no control inputs | 0 min 7 s |

Timeline (seconds from session start):

-      0 to      7: **Nobody: no controller running and no control inputs**
-      7 to     32: **AIRPLANE AUTOPILOT ENGAGED: the fly is NOT flying** (engaged: SPD; controller 2026-11-14T215622Z_kaden-vandine_flightgear-connectome is running)
-     32 to    231: **FLY BRAIN (connectome) flying the landing** (run 2026-11-14T215622Z_kaden-vandine_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope (no pitch-up once the sink is arrested), landing thrust to idle in the flare (MN9 sets approach power only above it), and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover)

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
