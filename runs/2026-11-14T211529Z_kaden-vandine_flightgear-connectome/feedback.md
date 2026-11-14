# 2026-11-14T211529Z_kaden-vandine_flightgear-connectome

Run by Kaden VanDine. Command: `python -m flight_simulator takeoff_live takeoff --brain connectome --backend flightgear --telemetry-port 5501 --control-port 5502 --period 0.25`

| | |
|---|---|
| Outcome | takeoff_achieved |
| Backend / brain | flightgear / connectome |
| Elapsed | ? s |
| Min clearance | ? m |
| Min altitude | ? m |
| Avoidance activations | ? |
| Code | feaefd52d on main |

## Who was flying

**FLY BRAIN (connectome) flying the takeoff**

- Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9)
- Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope, and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover
- Airplane autopilot: never: the fly does not use the airplane autopilot/autothrottle; AutopilotGuard forces it off and stops the run if it cannot (actual autopilot state over time is in the FlightGear session log)

## Notes

- **Kaden VanDine** (2026-11-14 16:19): Takeoff (Linux FG 2024.1.7 AppImage, connectome, KSFO 28R, main at feaefd5 with session video OFF by default): SUCCESS. Roll: heading within 1.1 deg, max 5.4 m off centreline, throttle >= 0.99. Liftoff t=34.5 s at 165 kt, 1,359 m down the runway, no tail strike; 1,000 ft handover reached (takeoff_achieved), then held a 10 deg climb to 3,577 ft until the 200 s time limit paused FG (acknowledged). 502 decisions, latency mean 0.26 s / max 2.6 s, 1x held (0 speed-up resets). FlightGear did not crash or hang this time (earlier today: 4 segfaults/1 hang with video recording on); one missed 5 s HTTP check at 16:19:25 UTC, recovered at once.

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
