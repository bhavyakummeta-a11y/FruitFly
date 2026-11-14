# 2026-11-14T181613Z_michael-taylor_flightgear-connectome

Run by Michael Taylor. Command: `python -m flight_simulator takeoff_live takeoff --brain connectome --backend flightgear --telemetry-port 5501 --control-port 5502 --period 1.0`

| | |
|---|---|
| Outcome | COLLISION |
| Backend / brain | flightgear / connectome |
| Elapsed | ? s |
| Min clearance | ? m |
| Min altitude | ? m |
| Avoidance activations | ? |
| Code | b6b746b50 on main (+ uncommitted, see code.diff) |

## Who was flying

**FLY BRAIN (connectome) flying the takeoff**

- Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9)
- Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover
- Airplane autopilot: never: the fly does not use the airplane autopilot/autothrottle; AutopilotGuard forces it off and stops the run if it cannot (actual autopilot state over time is in the FlightGear session log)

## Notes

- **Michael Taylor** (2026-11-14 13:18): Takeoff with new synthetic vision (1f3063d) + faster brain (caaa108), launch_fg --fly. Decisions: 20 applied, 1 skipped, latency 0.73 s mean (was 7.7 s). Vision inputs reached the brain and steering went the right way every time (HS asymmetry -> DNp15/DNa02 on the correcting side -> rudder). But the steering loop oscillated with growing amplitude: offset +2.1 m @14 s (rudder -0.30), -4.1 m @19.5 s (rudder +0.59), +2.4 m @21.6 s, then +11/+18/+29 m @22.6-24.3 s at 99-105 kt with rudder -0.60..-0.97 (HS saturated 200/0). Centerline >8 m -> bitter 200 Hz -> MN9 0 -> throttle cut (reject behaviour), but the run ended left_runway at 24.5 s / 104.6 kt before the stop. Likely the fixed DN->rudder gain is too high at speed (rudder/nosewheel authority grows with v^2) plus ~0.7 s delay; needs speed-scheduled steering gain or more yaw-rate damping. Other session's full-graphics benchmark FG was running concurrently.

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
