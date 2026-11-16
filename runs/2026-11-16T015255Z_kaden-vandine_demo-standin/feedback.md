# 2026-11-16T015255Z_kaden-vandine_demo-standin

Run by Kaden VanDine. Command: `python -m flight_simulator takeoff_live --help`

| | |
|---|---|
| Outcome | error |
| Backend / brain | demo / standin |
| Elapsed | ? s |
| Min clearance | ? m |
| Min altitude | ? m |
| Avoidance activations | ? |
| Code | 04784bb51 on main |

## Who was flying

**NO FLY BRAIN: probe-table stand-in flying the takeoff**

- Neurons decide: nothing (no connectome is simulated in this run)
- Code decides: everything: a lookup table of DN rates measured earlier from the connectome
- Airplane autopilot: never: the fly does not use the airplane autopilot/autothrottle; AutopilotGuard forces it off and stops the run if it cannot (actual autopilot state over time is in the FlightGear session log)

## Notes


<!-- add feedback: python -m flight_simulator.runlog note "..." -->
