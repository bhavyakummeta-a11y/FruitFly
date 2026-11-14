# Cruise oscillation follow-up — 2026-11-14

The [Windows 737 reflex log](https://github.com/bhavyakummeta-a11y/FruitFly/tree/sim-logs/runs/2026-11-14T165815Z_michael-taylor_flightgear-reflex)
and its feedback report growing pitch oscillation, then an altitude-envelope
abort near 30 seconds, well before the first tower. This run used the conventional
reflex baseline, not the connectome. The teammate also reported that FlightGear
2024 needs `/sim/freeze/clock` to actually pause. These are distinct issues.

The CSV has 96 rows, a median control interval of 0.300 s, a first gap of 5.267 s,
and 18 gaps of at least 0.5 s. The old bridge discarded pitch/roll rate feedback
at those longer intervals; that removes damping precisely when timing is poor.
Synchronous Matplotlib rendering and scenery setup were in the control path.
The log alone does not prove that rendering caused every gap.

Changes:

- Move companion rendering into a bounded, nonblocking separate process. Keep
  only recent display frames; preserve the flight controls independently.
- Pause for scene setup and move autopilot handover afterward, avoiding a long
  initial uncontrolled gap. Place default towers ahead of the actual handover
  position, including when the autopilot has spent time settling.
- Reduce pitch/altitude and integral gains, double pitch-rate damping, and slew
  pitch targets at 2 degrees/s. Account for control intervals up to 0.5 s instead
  of clipping them to 0.2 s. Estimate attitude rates across gaps up to 2 s.
- Prefer 250 m predicted clearance while retaining the 150 m hard minimum;
  tracking error should not immediately exhaust all feasible routes.
- Use `/sim/freeze/clock` for cruise protocol commands and acknowledgements,
  install cruise protocols from the launcher, and diagnose stale installed
  protocols when the telnet clock check disagrees. Runway protocols are untouched.

Validation (JSBSim 1.3.3; +0.10 elevator disturbance at 45–47 s):

| Model | Duration | Control interval | Max altitude error | Min clearance |
|---|---:|---:|---:|---:|
| Bundled C172P | 240 s | 0.05 s | 7.74 m | 212.38 m |
| Bundled 737 | 360 s | 0.30 s | 6.23 m | 239.23 m |
| Bundled 737 | 360 s | 0.50 s | 6.92 m | 243.52 m |

All completed the three-obstacle course without an abort. The slower correction
trades tighter altitude tracking for gentler response; it does not hold altitude
exactly. 79 automated tests passed, including pitch slew/damping, rate estimation
with a 0.7 s gap, nonblocking display snapshots, and cruise pause XML. A 10-second
real-time demo smoke test exercised the spawned renderer with the headless Agg
backend and completed with no collision. No FlightGear window was opened.

The bundled JSBSim 737 is **not** the repository's 738-flies aircraft with its
FlightGear/Nasal systems. It also passed the old controller at a steady 0.3 s
interval without the disturbance, so it does not reproduce the reported live
oscillation. These are regression and slow-cadence checks, not proof that the
Windows problem is solved. Repeat the named live 737 session after restarting
with the updated protocols and inspect the next logs. Connectome mode continues
to pause for synchronous neural trials; aircraft stabilization remains
conventional control, and no learned flight-performance claim is made.
