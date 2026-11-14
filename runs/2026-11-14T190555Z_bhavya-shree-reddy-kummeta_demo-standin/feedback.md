# 2026-11-14T190555Z_bhavya-shree-reddy-kummeta_demo-standin

Run by Bhavya Shree Reddy Kummeta. Command: `python -m flight_simulator mission --route lax-burbank --brain standin --noise-seed 1 --vision-port 0 --log /tmp/lax-bur-noisy.csv`

| | |
|---|---|
| Outcome | landing_completed |
| Backend / brain | demo / standin |
| Elapsed | ? s |
| Min clearance | 335.3 m |
| Min altitude | ? m |
| Avoidance activations | ? |
| Code | 36c3b04c7 on main (+ uncommitted, see code.diff) |

## Who was flying

**NO FLY BRAIN: probe-table stand-in flying the full mission (takeoff, circuit, landing)**

- Neurons decide: nothing (no connectome is simulated in this run)
- Code decides: everything: a lookup table of DN rates measured earlier from the connectome
- Airplane autopilot: never: the fly does not use the airplane autopilot/autothrottle; AutopilotGuard forces it off and stops the run if it cannot (actual autopilot state over time is in the FlightGear session log)

## Notes


<!-- add feedback: python -m flight_simulator.runlog note "..." -->
