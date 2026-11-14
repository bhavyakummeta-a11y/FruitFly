# 2026-11-14T184733Z_michael-taylor_flightgear-connectome

Run by Michael Taylor. Command: `python -m flight_simulator --backend flightgear --brain connectome --data C:/Users/micha/FruitFly/data/brain --seconds 120 --note 'obstacle avoidance, connectome, immediate takeover (ticket #1, 4e85e94), storm weather; run from clean origin/main worktree'`

| | |
|---|---|
| Outcome | error |
| Backend / brain | flightgear / connectome |
| Elapsed | ? s |
| Min clearance | ? m |
| Min altitude | ? m |
| Avoidance activations | ? |
| Code | 4e85e94cb on HEAD |
| FlightGear | 2024.1.4, 738-flies, 79 warning lines |

## Who was flying

**FLY BRAIN (connectome) decides when to escape; code flies the airplane**

- Neurons decide: escape request: Giant Fibre (DNp01) response to synthetic looming and path cues; training retains looming-only input
- Code decides: synthetic visual encoding, turn direction (from obstacle geometry), holding altitude, speed and heading, and flying the avoidance turn (conventional FlightController)
- Airplane autopilot: never: the fly does not use the airplane autopilot/autothrottle; AutopilotGuard forces it off and stops the run if it cannot (actual autopilot state over time is in the FlightGear session log)

## Notes

- obstacle avoidance, connectome, immediate takeover (ticket #1, 4e85e94), storm weather; run from clean origin/main worktree

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
