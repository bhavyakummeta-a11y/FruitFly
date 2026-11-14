# 2026-11-14T185909Z_bhavya-shree-reddy-kummeta_demo-connectome

Run by Bhavya Shree Reddy Kummeta. Command: `python -m flight_simulator mission --route lax-burbank --brain connectome --vision-port 0 --seconds 1500 --log /tmp/lax-bur-connectome.csv`

| | |
|---|---|
| Outcome | landing_completed |
| Backend / brain | demo / connectome |
| Elapsed | ? s |
| Min clearance | 348.4 m |
| Min altitude | ? m |
| Avoidance activations | ? |
| Code | 77ee8da3c on main (+ uncommitted, see code.diff) |

## Who was flying

**FLY BRAIN (connectome) flying the full mission (takeoff, circuit, landing)**

- Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9)
- Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope, and phase handover (flies.py); airport waypoints, MSL/runway transforms, predictive obstacle heading selection, and destination rollout braking are code rules (airport_route.py)
- Airplane autopilot: never: the fly does not use the airplane autopilot/autothrottle; AutopilotGuard forces it off and stops the run if it cannot (actual autopilot state over time is in the FlightGear session log)

## Notes


<!-- add feedback: python -m flight_simulator.runlog note "..." -->
