# 2026-11-14T182703Z_michael-taylor_flightgear-connectome

Run by Michael Taylor. Command: `python -m flight_simulator takeoff_live takeoff --brain connectome --backend flightgear --telemetry-port 5501 --control-port 5502 --period 1.0`

| | |
|---|---|
| Outcome | completed |
| Backend / brain | flightgear / connectome |
| Elapsed | ? s |
| Min clearance | ? m |
| Min altitude | ? m |
| Avoidance activations | ? |
| Code | 4f63127e6 on main |
| FlightGear | 2024.1.4, 738-flies, 44 warning lines |

## Who was flying

**FLY BRAIN (connectome) flying the takeoff**

- Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9)
- Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover
- Airplane autopilot: never: the fly does not use the airplane autopilot/autothrottle; AutopilotGuard forces it off and stops the run if it cannot (actual autopilot state over time is in the FlightGear session log)

## Notes

- **Michael Taylor** (2026-11-14 13:28): Takeoff with numba brain (3d5a3c0) + vision (1f3063d), started via sim queue + launch_fg --fly. Decisions: 37 applied, 1 skipped, latency 0.22 s mean (2.8 s max). Held within +-3 m of centerline up to 104 kt (previous run had drifted 4 m by 86 kt). Lateral oscillation still grew above ~100 kt: -7.9 m @111 kt, -17.9 m @117 kt (max IAS 118, short of Vr), bitter at 24.4 s -> MN9 suppressed -> REJECT at 31.5 s, idle + max brakes, stopped at x=1213 m, 8.9 m off centerline, on the runway. Judged success (safe reject below V1) but no liftoff. Remaining blocker: steering gain at high speed (issue #6).

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
