# takeoff fly: connectome, KSFO 28R

`2026-11-14T211450Z_kaden-vandine_fg-takeoff-fly-connectome-ksfo-28r`, FlightGear session by Kaden VanDine.

| | |
|---|---|
| Outcome | closed normally (exit None) |
| Duration | 6 min 49 s |
| FlightGear | ?, ? |
| Graphics / weather | light / storm |
| Airplane samples | 192 at 2 Hz |
| Max altitude / IAS | 3573 ft / 191 kt |
| FlightGear warnings | 0 lines (fgfs_warnings.log) |
| Video (on the recording machine, not pushed) | off (opt in: --video / FRUITFLY_VIDEO=1) |
| Controller runs | [2026-11-14T211529Z_kaden-vandine_flightgear-connectome](../2026-11-14T211529Z_kaden-vandine_flightgear-connectome/feedback.md), [2026-11-14T195529Z_michael-taylor_flightgear-connectome](../2026-11-14T195529Z_michael-taylor_flightgear-connectome/feedback.md), [2026-11-14T200455Z_michael-taylor_flightgear-connectome](../2026-11-14T200455Z_michael-taylor_flightgear-connectome/feedback.md), [2026-11-14T193710Z_michael-taylor_flightgear-connectome](../2026-11-14T193710Z_michael-taylor_flightgear-connectome/feedback.md), [2026-11-14T195024Z_michael-taylor_flightgear-connectome](../2026-11-14T195024Z_michael-taylor_flightgear-connectome/feedback.md), [2026-11-14T195736Z_michael-taylor_flightgear-connectome](../2026-11-14T195736Z_michael-taylor_flightgear-connectome/feedback.md), [2026-11-14T195931Z_michael-taylor_flightgear-connectome](../2026-11-14T195931Z_michael-taylor_flightgear-connectome/feedback.md), [2026-11-14T193453Z_michael-taylor_flightgear-connectome](../2026-11-14T193453Z_michael-taylor_flightgear-connectome/feedback.md), [2026-11-14T193142Z_paula-sof-a-contreras-villavicencio_flightgear-connectome](../2026-11-14T193142Z_paula-sof-a-contreras-villavicencio_flightgear-connectome/feedback.md), [2026-11-14T195535Z_paula-sof-a-contreras-villavicencio_flightgear-connectome](../2026-11-14T195535Z_paula-sof-a-contreras-villavicencio_flightgear-connectome/feedback.md), [2026-11-14T194009Z_paula-sof-a-contreras-villavicencio_flightgear-connectome](../2026-11-14T194009Z_paula-sof-a-contreras-villavicencio_flightgear-connectome/feedback.md), [2026-11-14T194814Z_paula-sof-a-contreras-villavicencio_flightgear-connectome](../2026-11-14T194814Z_paula-sof-a-contreras-villavicencio_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| FLY BRAIN (connectome) flying the takeoff | 3 min 27 s |
| Nobody: no controller running and no control inputs | 3 min 17 s |
| UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain | 0 min 5 s |

Timeline (seconds from session start):

-      0 to     42: **Nobody: no controller running and no control inputs**
-     42 to    249: **FLY BRAIN (connectome) flying the takeoff** (run 2026-11-14T211529Z_kaden-vandine_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope, and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover)
-    249 to    254: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**
-    254 to    409: **Nobody: no controller running and no control inputs**

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
