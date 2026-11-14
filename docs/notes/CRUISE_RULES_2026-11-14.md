# Cruise altitude and obstacle recovery — 2026-11-14

## Evidence from the shared logs

The [controlled 737 reflex run](https://github.com/bhavyakummeta-a11y/FruitFly/tree/sim-logs/runs/2026-11-14T163037Z_michael-taylor_flightgear-reflex)
started at 613.74 m with a 4.67 m/s descent despite a nose-up pitch of 2.85°.
At 17.69 seconds it was at 492.89 m, sinking at 7.24 m/s. Elevator was only
-0.096 and throttle had fallen from 0.65 to 0.448 as descent increased airspeed.
The old pitch-only correction and speed-based power reduction were consistent
with this continuing descent. A numerical excerpt is preserved in
`tests/fixtures/github_descent.json`; its regression checks pitch-up demand and
retained power, not a counterfactual replay of aircraft dynamics.

Other same-day Boeing logs included zero throttle, gear down and controller
startup failures. The `2026-11-14T163949Z_kaden-vandine_fg-session` record did not
establish that our controller was active. These logs are not a reproduction of
the user's exact Cessna crash; they expose additional setup issues. The controller
requires an already airborne aircraft with its engine running.

## Implemented rules

- Correct vertical speed immediately, integrate trim, compensate for lift lost in
  bank, and retain power during a descent instead of cutting power on overspeed.
- Predict bounded turns against every configured cylinder, including the next
  obstacles, with a 150 m modeled margin. Replan twice per second.
- Reduce bank demands when altitude or airspeed needs recovery. Slew controls
  rather than abruptly switching bank direction.
- Recover both the original heading and cross-track position after passing an
  obstacle. Neural activity can prefer a safe side; rules remain active in silent
  mode. This is conventional assisted control, not learned neural stabilization.
- Stop and request a FlightGear pause if no candidate is safe or measured altitude
  differs from target by over 40 m. The pause requires a functioning simulator
  connection; these bounds are not a physical safety guarantee.

The companion has the obstacle scene left, actual/predicted route right, and an
altitude-versus-target graph below. Telemetry now includes controller targets,
vertical-speed demand, cross-track error, predicted clearance and decision source.
The macOS process watcher also now detects live PIDs without Linux's `/proc`.

## Validation

66 automated tests pass, including multiple obstacles with no neural escape,
route recovery, descending-log commands, neural safe-side preference and the
macOS/POSIX process watcher. Optional `requirements-validation.txt` pins JSBSim
1.3.3. Both aerodynamic runs use its bundled C172P at 3,000 ft / 100 KIAS, a running
engine, trimmed initial state and the three-obstacle course. Controls run at
20 Hz and dynamics at 100 Hz. The disturbance adds +0.10 elevator during seconds
45–47. Results:

| 240-second run | Maximum altitude error | Minimum obstacle clearance | Maximum bank |
|---|---:|---:|---:|
| Normal cruise | 1.453 m | 150.348 m | 14.63° |
| Elevator disturbance | 1.453 m | 150.191 m | 14.63° |

Both pass all three cylinders, use two avoidance episodes, and finish about
57.3 m from the original course with the initial heading recovered. The companion
was rendered from the trajectory and visually inspected. Commands to reproduce
are in [the setup guide](../FLIGHT_SIMULATOR.md#cruise-rule-validation).

This validates the controller against a headless aerodynamic Cessna model, not a
live FlightGear session or the team's Boeing. It assumes the configured obstacles
are known and calm air; it does not detect arbitrary scenery or follow terrain.
The existing optional connectome reinforcement-learning pathway remains separate
from these mandatory rules. No claim of improved learned flight performance is
made by these reflex-baseline tests.
