# 2026-11-14T192239Z_kaden-vandine_flightgear-connectome

Run by Kaden VanDine. Command: `python -m flight_simulator takeoff_live landing --brain connectome --backend flightgear --telemetry-port 5501 --control-port 5502 --period 0.25`

| | |
|---|---|
| Outcome | completed |
| Backend / brain | flightgear / connectome |
| Elapsed | ? s |
| Min clearance | ? m |
| Min altitude | ? m |
| Avoidance activations | ? |
| Code | fd4d653ea on main |

## Who was flying

**FLY BRAIN (connectome) flying the landing**

- Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9)
- Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope, and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover
- Airplane autopilot: never: the fly does not use the airplane autopilot/autothrottle; AutopilotGuard forces it off and stops the run if it cannot (actual autopilot state over time is in the FlightGear session log)

## Notes

- **Kaden VanDine** (2026-11-14 14:24): Landing test (Linux FG 2024.1.7, connectome, 3 nm final KSFO 28R): handover at ~990 ft / 144 kt (737 SPD autothrottle was still on and was forced off). The fly held ~1 deg nose-down, sank ~1,600 fpm (about 2x the glideslope rate) and sped up to 153 kt with throttle ~0.4-0.5; it drifted right. At 560 ft it was 53 m below the glideslope and 70 m right of the centreline -> unstable -> bitter -> MN9 to 0 -> GO-AROUND (the designed safe response, not a crash). Climbed away to ~1,100 ft; stopped by Ctrl-C (FG paused, acknowledged). No touchdown attempted. Next: the initial pitch/sink after handover (pitch zero / trim pitch) and the lateral drift.

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
