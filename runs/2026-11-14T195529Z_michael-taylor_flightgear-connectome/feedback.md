# 2026-11-14T195529Z_michael-taylor_flightgear-connectome

Run by Michael Taylor. Command: `python -m flight_simulator --backend flightgear --brain connectome --seconds 180 --no-threat-glow --note 'tornado obstacle course, user request; --no-threat-glow to isolate the fgfs.exe+0x5adea5 mid-flight crash'`

| | |
|---|---|
| Outcome | error |
| Backend / brain | flightgear / connectome |
| Elapsed | ? s |
| Min clearance | ? m |
| Min altitude | ? m |
| Avoidance activations | ? |
| Code | 407c4ac1f on main (+ uncommitted, see code.diff) |
| FlightGear | 2024.1.4, 738-flies, 41 warning lines |

## Who was flying

**FLY BRAIN (connectome) decides when to escape; code flies the airplane**

- Neurons decide: escape request: Giant Fibre (DNp01) response to synthetic looming and path cues; training retains looming-only input
- Code decides: synthetic visual encoding, turn direction (from obstacle geometry), holding altitude, speed and heading, and flying the avoidance turn (conventional FlightController)
- Airplane autopilot: never: the fly does not use the airplane autopilot/autothrottle; AutopilotGuard forces it off and stops the run if it cannot (actual autopilot state over time is in the FlightGear session log)

## Notes

- tornado obstacle course, user request; --no-threat-glow to isolate the fgfs.exe+0x5adea5 mid-flight crash

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
