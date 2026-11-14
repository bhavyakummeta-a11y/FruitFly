# fly pilot holds the yoke: arms follow aileron/elevator (visual check + connectome takeoff)

`2026-11-14T190951Z_kaden-vandine_fg-fly-pilot-holds-the-yoke-arms-follow-aileron-elevator-visual-check-connectome-takeoff`, FlightGear session by Kaden VanDine.

| | |
|---|---|
| Outcome | closed normally (exit None) |
| Duration | 5 min 57 s |
| FlightGear | ?, ? |
| Graphics / weather | light / storm |
| Airplane samples | 154 at 2 Hz |
| Max altitude / IAS | 2101 ft / 189 kt |
| FlightGear warnings | 0 lines (fgfs_warnings.log) |
| Controller runs | [2026-11-14T191139Z_kaden-vandine_flightgear-connectome](../2026-11-14T191139Z_kaden-vandine_flightgear-connectome/feedback.md) |

## Who was flying

| Who | Time |
|---|---|
| FLY BRAIN (connectome) flying the full mission (takeoff, circuit, landing) | 4 min 8 s |
| LLM agent: claude-run-check | 1 min 2 s |
| Nobody: no controller running and no control inputs | 0 min 42 s |
| UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain | 0 min 5 s |

Timeline (seconds from session start):

-      0 to     39: **Nobody: no controller running and no control inputs**
-     39 to    101: **LLM agent: claude-run-check** (visual check of the fly pilot's arms on the yoke: sim paused on the runway, setting /controls/flight/aileron and /elevator by hand, screenshots; no flying)
-    101 to    106: **UNATTRIBUTED inputs: a human or an external program (e.g. an LLM agent) is moving the controls; not the fly brain**
-    106 to    109: **Nobody: no controller running and no control inputs**
-    109 to    357: **FLY BRAIN (connectome) flying the full mission (takeoff, circuit, landing)** (run 2026-11-14T191139Z_kaden-vandine_flightgear-connectome. Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9). Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope, and phase handover (flies.py))

## Notes

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
