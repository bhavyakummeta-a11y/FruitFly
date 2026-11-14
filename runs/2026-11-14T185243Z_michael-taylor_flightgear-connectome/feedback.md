# 2026-11-14T185243Z_michael-taylor_flightgear-connectome

Run by Michael Taylor. Command: `python -m flight_simulator takeoff_live takeoff --brain connectome --backend flightgear --telemetry-port 5501 --control-port 5502 --period 1.0`

| | |
|---|---|
| Outcome | COLLISION |
| Backend / brain | flightgear / connectome |
| Elapsed | ? s |
| Min clearance | ? m |
| Min altitude | ? m |
| Avoidance activations | ? |
| Code | 4e85e94cb on HEAD |
| FlightGear | 2024.1.4, 738-flies, 47 warning lines |

## Who was flying

**FLY BRAIN (connectome) flying the takeoff**

- Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9)
- Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover
- Airplane autopilot: never: the fly does not use the airplane autopilot/autothrottle; AutopilotGuard forces it off and stops the run if it cannot (actual autopilot state over time is in the FlightGear session log)

## Notes

- **Michael Taylor** (2026-11-14 13:54): Best takeoff yet (latest main, numba brain, clear weather). 37 decisions, 0.26 s mean latency. Centerline within +-9 m up to 151 kt (oscillation still present but bounded: +2.1@96, -4.3@111, +7.3@127, -6.4@131, +9.1@141 kt). Past V1, so no bitter reject. Rotation: looming -> JUMP, escape DNs 159 -> 378 -> 537 -> 615 Hz at 35.5-39.2 s, pitch -0.1 -> +4.7 deg, IAS 160 kt, agl 0.7-1 ft (nose up, mains about to leave). At rotation the lateral swing blew out: +2.7 m @151 kt -> +27 m @157 kt -> 37.9 m, left_runway at 40.3 s. Remaining blocker unchanged: high-speed steering gain/damping (issue #6), worst exactly when the nosewheel unloads at rotation.

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
