# Feedback: first live FlightGear test of the obstacle controller (2026-11-14)

Tester: MT (with Claude Code), Windows 11, Python 3.12, FlightGear 2024.1.4
(winget package `FlightGear.FlightGear`, base data 2024.1.4 in `D:\FlightGear\data`).
Code tested: `main` at `78e0f27` ("Commit Obstacle 1").

## Results

| Check | Result |
|---|---|
| `python -m unittest discover -s tests` | **10/10 pass** on Windows |
| Local demo, reflex, 180 s, seed 0 | **Matches the documented run**: no collision, 6 activations, min clearance 235.76 m, altitude held at 900 m |
| Protocol XMLs copied into `$FG_ROOT/Protocol` | FlightGear loads both `flybrain-state` and `flybrain-controls` generic channels without errors |
| HTTP (`--httpd=8080`) and telnet (`--telnet=5500`) property access | Read and write verified (position, flaps, heading, airspeed) |
| **Live closed-loop run (`--backend flightgear --brain reflex`)** | **Not reached.** The aircraft could not be brought to the controller's start conditions in time (details below). No live avoidance result yet. |

## Findings

1. **The air start doesn't produce the documented cruise state.**
   Start flags: `--in-air --altitude=3000 --heading=0 --vc=100` over water
   (`--lat=37.55 --lon=-122.75`), calm wind. The C172 starts with low throttle;
   within ~5 s airspeed fell to **~50 kt** (the controller requires >= 68 kt) and
   the aircraft rolled off to **-38°** bank with no input (the controller requires
   |bank| < 20°). So `__main__.py` rejects the start. In practice there is a short
   window between FlightGear starting and the controller connecting, and with no
   one on the controls the aircraft doesn't wait.
2. **`--state=cruise` does nothing for this c172p.** `fgfs.log` shows
   `initialstate.cxx: missing state node for:cruise`. Remove it. (The
   uncommitted `flight_simulator/launch_fg.py` currently has this flag too.)
3. **The course is fixed north, but the hold heading is whatever the start
   heading is.** Obstacles are in a fixed east/north frame and the controller
   holds the *initial* heading. If the aircraft isn't pointing north at handoff,
   it never meets the course and the run reports "no collision", which reads
   like a success. Suggestion: either rotate the course into the
   initial-heading frame, or refuse to start (or warn) when the initial heading
   is more than ~10° off the course axis.
4. **A pre-handoff stabilizer is needed.** A simple roll/pitch P–D loop over the
   HTTP API (throttle 0.9) got speed back to ~82 kt and heading to ~0°, but
   oscillated ±15° in roll at the ~2–3 Hz rate the HTTP property calls allow.
   It needs either lower roll gain with more damping, or to run over the UDP
   channel at 20 Hz. Better still, have `FlightController` own this
   "capture" phase: accept any start in a wider envelope (e.g. > 55 kt,
   |bank| < 45°) and level out before arming obstacle avoidance.
5. **The C172 tops out around 82 kt in level flight at throttle 0.9, with the
   mixture as started (0.46).** The doc targets 100 kt. Either lower the speed
   target or set mixture/throttle explicitly at handoff; otherwise the
   speed-hold gains are tuned for a target the aircraft can't reach.
6. **Docs are Unix-only.** On Windows: `python` (not `python3`),
   `.venv\Scripts\activate`, and FlightGear at `D:\FlightGear\bin\fgfs.exe`.
7. **Exposure:** both `--httpd` and `--telnet` listen on `0.0.0.0`, not
   localhost. Keep the firewall rule for `fgfs.exe` set to deny or private only.

## Suggested next steps

- Drop `--state=cruise`; set throttle/mixture explicitly (UDP throttle channel,
  or `--prop:/controls/engines/engine/throttle=0.9` at launch).
- Add a capture/level-off phase before obstacle arming (finding 4), then rerun
  `--backend flightgear --brain reflex --seconds 180 --log runs/fg-baseline.csv`.
- Add a heading-vs-course check (finding 3) so a missed course isn't reported as
  a clean pass.
