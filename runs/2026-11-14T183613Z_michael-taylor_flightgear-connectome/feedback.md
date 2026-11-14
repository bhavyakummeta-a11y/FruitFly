# 2026-11-14T183613Z_michael-taylor_flightgear-connectome

Run by Michael Taylor. Command: `python -m flight_simulator --backend flightgear --brain connectome --seconds 120 --no-plot --note 'obstacle avoidance, connectome, numba brain + vision; --no-plot (companion window died in the previous attempt); plane already level so handover is immediate'`

| | |
|---|---|
| Outcome | error |
| Backend / brain | flightgear / connectome |
| Elapsed | ? s |
| Min clearance | ? m |
| Min altitude | ? m |
| Avoidance activations | ? |
| Code | bcfa42e5a on main |
| FlightGear | 2024.1.4, 738-flies, 152 warning lines |

## Who was flying

**FLY BRAIN (connectome) decides when to escape; code flies the airplane**

- Neurons decide: escape request: Giant Fibre (DNp01) response to synthetic looming and path cues; training retains looming-only input
- Code decides: synthetic visual encoding, turn direction (from obstacle geometry), holding altitude, speed and heading, and flying the avoidance turn (conventional FlightController)
- Airplane autopilot: never: the fly does not use the airplane autopilot/autothrottle; AutopilotGuard forces it off and stops the run if it cannot (actual autopilot state over time is in the FlightGear session log)

## Notes

- obstacle avoidance, connectome, numba brain + vision; --no-plot (companion window died in the previous attempt); plane already level so handover is immediate

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
