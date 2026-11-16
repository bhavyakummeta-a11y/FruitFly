# takeoff run, connectome fly brain, 1x

`2026-11-16T015528Z_kaden-vandine_fg-takeoff-run-connectome-fly-brain-1x`, FlightGear session by Kaden VanDine.

| | |
|---|---|
| Outcome | closed normally (exit None) |
| Duration | 3 min 12 s |
| FlightGear | ?, ? |
| Graphics / weather | light / clear |
| Airplane samples | 97 at 2 Hz |
| Max altitude / IAS | 2088 ft / 189 kt |
| FlightGear warnings | 0 lines (fgfs_warnings.log) |
| Video (on the recording machine, not pushed) | off (opt in: --video / FRUITFLY_VIDEO=1) |
| Controller runs | [2026-11-16T015617Z_kaden-vandine_flightgear-connectome](../2026-11-16T015617Z_kaden-vandine_flightgear-connectome/feedback.md), [2026-11-16T015642Z_kaden-vandine_flightgear-connectome](../2026-11-16T015642Z_kaden-vandine_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| FLY BRAIN (connectome) flying the takeoff | 1 min 57 s |
| Nobody: no controller running and no control inputs | 1 min 6 s |
| UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain | 0 min 9 s |

Timeline (seconds from session start):

-      0 to     60: **Nobody: no controller running and no control inputs**
-     60 to     66: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**
-     66 to     72: **Nobody: no controller running and no control inputs**
-     72 to     76: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**
-     76 to    192: **FLY BRAIN (connectome) flying the takeoff** (run 2026-11-16T015642Z_kaden-vandine_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope (no pitch-up once the sink is arrested), landing thrust to idle in the flare (MN9 sets approach power only above it), and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover)

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
