# 2026-11-14T165815Z_michael-taylor_flightgear-reflex

Run by Michael Taylor. Command: `python -m flight_simulator --backend flightgear --brain reflex --seconds 180 --note 'latest cruise rules f5c0ca0 + AP handover e8355dc; reflex baseline; 738-flies'`

| | |
|---|---|
| Outcome | error |
| Backend / brain | flightgear / reflex |
| Elapsed | ? s |
| Min clearance | ? m |
| Min altitude | ? m |
| Avoidance activations | ? |
| Code | e8355dc5d on main |
| FlightGear | 2024.1.4, 738-flies, 30 warning lines |

## Notes

- latest cruise rules f5c0ca0 + AP handover e8355dc; reflex baseline; 738-flies
- **Michael Taylor** (2026-11-14 11:59): Live 737 result for f5c0ca0 cruise rules: altitude hold much better than before (within +-15 m for 25 s, previously -150 m in 20 s) and AP handover worked. Aborted at ~30 s on the 40 m altitude limit, before reaching Tower A (~6.9 km ahead): the pitch loop oscillates with growing amplitude (pitch 5.5 -> 1 -> 7 -> 2 -> 9 -> -3.6 deg, elevator swinging -0.24..+0.27 with ~6 s period), i.e. underdamped/too much gain for the 737; reduce the altitude/pitch gains or add pitch-rate damping for the 737. No avoidance turn happened yet (heading drift only -3.5 deg). Note: connectome mode will also be affected by the freeze bug (see takeoff session note): /sim/freeze/master alone doesn't pause FG 2024, /sim/freeze/clock is needed.

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
