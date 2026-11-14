# takeoff fly: connectome, KSFO 28R (run 3)

`2026-11-14T215310Z_kaden-vandine_fg-takeoff-fly-connectome-ksfo-28r-run-3`, FlightGear session by Kaden VanDine.

| | |
|---|---|
| Outcome | closed normally (exit None) |
| Duration | 2 min 30 s |
| FlightGear | ?, ? |
| Graphics / weather | light / storm |
| Airplane samples | 83 at 2 Hz |
| Max altitude / IAS | 2410 ft / 190 kt |
| FlightGear warnings | 0 lines (fgfs_warnings.log) |
| Video (on the recording machine, not pushed) | off (opt in: --video / FRUITFLY_VIDEO=1) |
| Controller runs | [2026-11-14T215317Z_kaden-vandine_flightgear-connectome](../2026-11-14T215317Z_kaden-vandine_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| FLY BRAIN (connectome) flying the takeoff | 2 min 2 s |
| UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain | 0 min 17 s |
| Nobody: no controller running and no control inputs | 0 min 10 s |

Timeline (seconds from session start):

-      0 to     10: **Nobody: no controller running and no control inputs**
-     10 to    132: **FLY BRAIN (connectome) flying the takeoff** (run 2026-11-14T215317Z_kaden-vandine_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope (no pitch-up once the sink is arrested), landing thrust to idle in the flare (MN9 sets approach power only above it), and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover)
-    132 to    150: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
