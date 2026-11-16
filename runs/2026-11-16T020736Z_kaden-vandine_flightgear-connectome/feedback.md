# 2026-11-16T020736Z_kaden-vandine_flightgear-connectome

Run by Kaden VanDine. Command: `python -m flight_simulator mission --route lax-burbank --brain connectome --seconds 1800 --backend flightgear --telemetry-port 5501 --control-port 5502`

| | |
|---|---|
| Outcome | error |
| Backend / brain | flightgear / connectome |
| Elapsed | ? s |
| Min clearance | ? m |
| Min altitude | ? m |
| Avoidance activations | ? |
| Code | ba9fab7e2 on main |

## Who was flying

**FLY BRAIN (connectome) flying the full mission (takeoff, circuit, landing)**

- Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9)
- Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope (no pitch-up once the sink is arrested), landing thrust to idle in the flare (MN9 sets approach power only above it), and phase handover (flies.py); airport waypoints, MSL/runway transforms, predictive obstacle heading selection, and destination rollout braking are code rules (airport_route.py)
- Airplane autopilot: never: the fly does not use the airplane autopilot/autothrottle; AutopilotGuard forces it off and stops the run if it cannot (actual autopilot state over time is in the FlightGear session log)

## Notes


<!-- add feedback: python -m flight_simulator.runlog note "..." -->
