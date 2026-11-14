# 2026-11-14T175336Z_michael-taylor_flightgear-connectome

Run by Michael Taylor. Command: `python -m flight_simulator takeoff_live takeoff --brain connectome --backend flightgear --telemetry-port 5501 --control-port 5502 --period 1.0`

| | |
|---|---|
| Outcome | COLLISION |
| Backend / brain | flightgear / connectome |
| Elapsed | ? s |
| Min clearance | ? m |
| Min altitude | ? m |
| Avoidance activations | ? |
| Code | e2c92bced on main |
| FlightGear | 2024.1.4, 738-flies, 67 warning lines |

## Who was flying

**FLY BRAIN (connectome) flying the takeoff**

- Neurons decide: pitch (jump/rotation, flare), steering and roll through descending-neuron rates (DNp01/02/04/11, DNp07, DNp15, DNa02, DNp20, MN9)
- Code decides: sensory encoding of the aircraft state, the fixed decoder from DN rates to controls, the behavioural-state gate (standing/flying), a fixed-gain pitch-rate reflex (haltere stand-in), and phase handover (flies.py); takeoff_live holds the parking brake while the brain calibrates and releases it at the handover
- Airplane autopilot: never: the fly does not use the airplane autopilot/autothrottle; AutopilotGuard forces it off and stops the run if it cannot (actual autopilot state over time is in the FlightGear session log)

## Notes

- **Michael Taylor** (2026-11-14 12:56): Auto handoff worked (launch_fg --fly, parking brake held during calibration, released at handover, AP confirmed off). Fly accelerated to 129.8 kt, then left the runway at 32 m off the centerline before rotation. Cause is decision latency under the real-time rule (no pause per brain trial): connectome trials took 7.7 s mean / 9.6 s max on this laptop, so only 4 decisions were applied and 25 skipped in 34.6 s of roll. Steering at ~0.13 Hz can't hold a 737 on the centerline. Options for the brain/pilot team: faster brain trials (shorter trial ms / fewer neurons / GPU), or a slower sim rate for connectome runs.
- **Michael Taylor** (2026-11-14 13:03): fly_activity.csv in this run is missing the input/DN columns (takeoff_live header bug, fixed in 1c380a5). From airplane.csv: centerline offset -0.1 m @14 s, -5 m @23 s, -10 m @26 s (first right rudder +0.11), +14 m @33 s (rudder +0.51): corrections in the right direction but one decision (~8 s) late.

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
