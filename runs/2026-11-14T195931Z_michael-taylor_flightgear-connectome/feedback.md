# 2026-11-14T195931Z_michael-taylor_flightgear-connectome

Run by Michael Taylor. Command: `python -m flight_simulator --backend flightgear --brain connectome --seconds 180 --no-scene --note 'obstacle course, user request; --no-scene + session video off, retry after an unrelated startup abort'`

| | |
|---|---|
| Outcome | error |
| Backend / brain | flightgear / connectome |
| Elapsed | ? s |
| Min clearance | ? m |
| Min altitude | ? m |
| Avoidance activations | ? |
| Code | fbc99c318 on main |
| FlightGear | 2024.1.4, 738-flies, 36 warning lines |

## Who was flying

**FLY BRAIN (connectome) decides when to escape; code flies the airplane**

- Neurons decide: escape request: Giant Fibre (DNp01) response to synthetic looming and path cues; training retains looming-only input
- Code decides: synthetic visual encoding, turn direction (from obstacle geometry), holding altitude, speed and heading, and flying the avoidance turn (conventional FlightController)
- Airplane autopilot: never: the fly does not use the airplane autopilot/autothrottle; AutopilotGuard forces it off and stops the run if it cannot (actual autopilot state over time is in the FlightGear session log)

## Notes

- obstacle course, user request; --no-scene + session video off, retry after an unrelated startup abort

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
