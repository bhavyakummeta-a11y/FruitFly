# 2026-11-14T213143Z_kaden-vandine_flightgear-connectome

Run by Kaden VanDine. Command: `python -m flight_simulator takeoff_live landing --brain connectome --backend flightgear --telemetry-port 5501 --control-port 5502 --period 0.25`

| | |
|---|---|
| Outcome | landed |
| Backend / brain | flightgear / connectome |
| Elapsed | ? s |
| Min clearance | ? m |
| Min altitude | ? m |
| Avoidance activations | ? |
| Code | feaefd52d on main (+ uncommitted, see code.diff) |

## Who was flying

**FLY BRAIN (connectome) flying the landing**

- Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9)
- Code decides: synthetic runway/path and known-obstacle sensory encoding of aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), speed-dependent ground steering limits/yaw damping, stale-decision rejection, a fixed flare pitch envelope (no pitch-up once the sink is arrested), landing thrust to idle in the flare (MN9 sets approach power only above it), and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover
- Airplane autopilot: never: the fly does not use the airplane autopilot/autothrottle; AutopilotGuard forces it off and stops the run if it cannot (actual autopilot state over time is in the FlightGear session log)

## Notes

- **Kaden VanDine** (2026-11-14 16:35): LANDING SUCCESS on live FlightGear (Linux 2024.1.7, connectome, 3 nm final KSFO 28R) with the landing fix: handover at the measured approach trim (elevator -0.22, pitch 3.7 deg; Paula's KLAX numbers) -> stable approach 3.6 deg nose-up, -640..-990 fpm, max 11.8 m off centreline; flare from ~100 ft with thrust latched at idle and no pitch-up once the sink was arrested (levelled ~17 ft, max +2 fpm, no balloon); touchdown 630 m past the threshold at 488 fpm, pitch 4.3 deg, no tail strike; rollout on the runway (max 16.5 m off centre) to 14 kt. Earlier run 2026-11-14T2125 (without the flare fix) ballooned to 28 ft with power back on and touched down at 651 fpm. FG stalls of 2-4 s during the rollout only.

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
