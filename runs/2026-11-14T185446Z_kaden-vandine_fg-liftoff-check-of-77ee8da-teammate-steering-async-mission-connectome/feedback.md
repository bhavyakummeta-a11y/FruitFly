# liftoff check of 77ee8da (teammate steering + async mission), connectome

`2026-11-14T185446Z_kaden-vandine_fg-liftoff-check-of-77ee8da-teammate-steering-async-mission-connectome`, FlightGear session by Kaden VanDine.

| | |
|---|---|
| Outcome | closed normally (exit None) |
| Duration | 6 min 39 s |
| FlightGear | ?, ? |
| Graphics / weather | light / storm |
| Airplane samples | 220 at 2 Hz |
| Max altitude / IAS | 3389 ft / 225 kt |
| FlightGear warnings | 0 lines (fgfs_warnings.log) |
| Controller runs | [2026-11-14T185508Z_kaden-vandine_flightgear-connectome](../2026-11-14T185508Z_kaden-vandine_flightgear-connectome/feedback.md), [2026-11-14T184958Z_bhavya-shree-reddy-kummeta_demo-standin](../2026-11-14T184958Z_bhavya-shree-reddy-kummeta_demo-standin/feedback.md), [2026-11-14T185223Z_michael-taylor_flightgear-connectome](../2026-11-14T185223Z_michael-taylor_flightgear-connectome/feedback.md), [2026-11-14T185243Z_michael-taylor_flightgear-connectome](../2026-11-14T185243Z_michael-taylor_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| FLY BRAIN (connectome) flying the full mission (takeoff, circuit, landing) | 5 min 57 s |
| Nobody: no controller running and no control inputs | 0 min 37 s |
| UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain | 0 min 4 s |

Timeline (seconds from session start):

-      0 to     24: **Nobody: no controller running and no control inputs**
-     24 to    381: **FLY BRAIN (connectome) flying the full mission (takeoff, circuit, landing)** (run 2026-11-14T185508Z_kaden-vandine_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope, and phase handover (flies.py))
-    381 to    386: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**
-    386 to    399: **Nobody: no controller running and no control inputs**

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
