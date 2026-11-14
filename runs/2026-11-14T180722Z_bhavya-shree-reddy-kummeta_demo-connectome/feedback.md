# 2026-11-14T180722Z_bhavya-shree-reddy-kummeta_demo-connectome

Run by Bhavya Shree Reddy Kummeta. Command: `python -m flight_simulator --brain connectome --seconds 1 --vision-port 0 --no-fly-body --log runs/vision-connectome.csv --note 'Synthetic visual-input integration check, local demo'`

| | |
|---|---|
| Outcome | completed |
| Backend / brain | demo / connectome |
| Elapsed | 1.0 s |
| Min clearance | 1102.5 m |
| Min altitude | 900.0 m |
| Avoidance activations | 1 |
| Code | 4f2ea9664 on main (+ uncommitted, see code.diff) |

## Who was flying

**FLY BRAIN (connectome) decides when to escape; code flies the airplane**

- Neurons decide: escape request: Giant Fibre (DNp01) response to synthetic looming and path cues; training retains looming-only input
- Code decides: synthetic visual encoding, turn direction (from obstacle geometry), holding altitude, speed and heading, and flying the avoidance turn (conventional FlightController)
- Airplane autopilot: never: the fly does not use the airplane autopilot/autothrottle; AutopilotGuard forces it off and stops the run if it cannot (actual autopilot state over time is in the FlightGear session log)

## Notes

- Synthetic visual-input integration check, local demo

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
