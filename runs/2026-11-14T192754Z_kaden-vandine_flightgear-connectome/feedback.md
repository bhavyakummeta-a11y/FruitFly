# 2026-11-14T192754Z_kaden-vandine_flightgear-connectome

Run by Kaden VanDine. Command: `python -m flight_simulator takeoff_live landing --brain connectome --backend flightgear --telemetry-port 5501 --control-port 5502 --period 0.25`

| | |
|---|---|
| Outcome | runway_departure |
| Backend / brain | flightgear / connectome |
| Elapsed | ? s |
| Min clearance | ? m |
| Min altitude | ? m |
| Avoidance activations | ? |
| Code | c7865019e on main |

## Who was flying

**FLY BRAIN (connectome) flying the landing**

- Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9)
- Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope, and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover
- Airplane autopilot: never: the fly does not use the airplane autopilot/autothrottle; AutopilotGuard forces it off and stops the run if it cannot (actual autopilot state over time is in the FlightGear session log)

## Notes

- **Kaden VanDine** (2026-11-14 14:31): Landing re-run after 4e28172 (Linux FG 2024.1.7, screenshots OFF). First controller attempt died at SpeedLock: telnet 'get /sim/speed-up' timed out (FG busy ~10 s after start); restarted controller. Handover OK (throttle 0.55, elevator 0, ref attitude 1.5 deg); approach re-anchored at 2.7 deg from 667 ft. Then FlightGear itself stalled ~16 s (19:28:35-51 UTC; session sampler and controller both got nothing) and fast-forwarded 16 s of sim time on the last controls (aileron 0.35): 60 deg bank, -18 deg pitch, -7,500 fpm, ground contact ~1.7 ft, go-around, later dive and ground impact. Not a fly-brain or 4e28172 failure. FG then hung for good (0% CPU, no HTTP/telnet, threads in futex wait); terminated with SIGTERM. Screenshots off did not prevent the stall/hang.

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
