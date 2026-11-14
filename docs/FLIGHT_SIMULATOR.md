# Airborne obstacle avoidance

See [Synthetic fly sensory view](FLY_VISION.md) for live obstacle/runway projections, path-deviation cues and the inputs sent to the brain.

This experiment starts in flight, maintains a cruise target, turns away from
configured obstacles, and resumes the original heading. It has a local demo and
a FlightGear UDP adapter using the same controller. No takeoff/landing or MSFS
adapter is included.

## Visible obstacles inside FlightGear

The optional [scenery overlay](../flightgear/SCENERY.md) adds three tornadoes
inside FlightGear. Load `flightgear/obstacle-course` as an additional scenery
folder and pass `--obstacles flightgear/obstacle-course/course.json` to the
controller. Follow that guide for the matching airborne start location.
The course has a fixed geographic origin, so visual objects and collision
checks stay aligned even when Python connects after the aircraft has moved.
The ordinary default JSON remains a virtual-only course.

## Cruise rules and companion view (2026-11-14)

Mandatory rules now run alongside the brain. Every half second the controller
checks candidate turns against **all configured obstacles**, with a 150 m minimum predicted
clearance and a preference for 250 m to allow tracking error. It rejoins the original course after avoidance, including cross-track
correction. Neural escape activity can prefer a safe turn side; it cannot disable
obstacle protection. Silent mode also receives these rules.

Altitude hold uses damped vertical-speed feedback, slower integral trim and bank lift
compensation. Pitch demands slew at at most 2 degrees/second to avoid abrupt
up/down corrections. Pitch-rate damping remains active across telemetry gaps up
to 2 seconds. A sinking aircraft retains power even if its airspeed increases.
Bank targets are limited to 18 degrees, reduced to 10 degrees during altitude
recovery and 5 degrees at low speed. Surface and bank demands are rate-limited.
If no predicted route meets the constraints, the run stops and requests a
FlightGear pause instead of choosing an unsafe route. These are assisted autopilot
rules, not a learned ability of the fly to stabilize an aircraft.

The companion window has a **3D virtual obstacle view on the left** and **the
full flight path on the right**, including all configured obstacles, the predicted
route and the original cruise direction. An altitude chart below compares actual
altitude with the held target. It opens by
default with `--backend flightgear`; use `--no-plot` to disable it. For the local
demo, use `--plot --realtime`. It is a separate window/process, not embedded in FlightGear. Slow rendering drops
display frames instead of delaying aircraft controls.

```sh
.venv/bin/python -m flight_simulator --brain reflex --plot --realtime --seconds 180
```

FlightGear now reads the latest queued telemetry instead of replaying stale
states. It stops and sends a pause request if heading deviates by over 90 degrees,
bank exceeds 50 degrees, pitch exceeds 25 degrees, speed falls below 70% of the
starting speed, or altitude differs by more than 40 m from the starting altitude. These are test
abort conditions, not stall protection or a terrain-avoidance system.

For the supplied default course, FlightGear rotates the course ahead of the
starting heading, increases its forward spacing with the square of starting
speed relative to 50 m/s, and raises cylinder tops above the starting altitude.
Custom JSON obstacle files keep their exact local east/north positions and
heights. The controller also draws this course live in FlightGear as tornadoes
(see "Obstacles inside FlightGear" below); the fixed scenery course above is the
alternative that needs no telnet connection.

### Boeing / two-engine connection

The original protocol controls only one engine. For a two-engine aircraft, copy
`flight_simulator/protocols/flybrain-controls-twin.xml` into FlightGear's
`Protocol/` folder, and **replace** the old input argument with:

```text
--generic=socket,in,20,127.0.0.1,5502,udp,flybrain-controls-twin
```

Keep the existing state-output argument. Restart FlightGear after changing the
protocol configuration, start already airborne and trimmed, then run:

```sh
.venv/bin/python -m flight_simulator --backend flightgear --brain reflex --engines 2 --seconds 180 --log runs/fg-test.csv
```

Both throttle values are identical. `--engines 2` must be paired with the twin
protocol; the single-engine XML uses a different packet layout. This fixes the
missing second-engine command but does not establish Boeing flight-model tuning.
Disable conflicting autopilot, autothrottle, and joystick control before testing.
The shared controller still requires live validation with the selected aircraft.

## Watch the fly's body (3D)

A second window shows the [flybody](../models/flybody/) fruit fly reacting live to
its own brain while the controller flies. It banks and pitches with the airplane,
beats its wings harder with DNg02, beats one wing harder and leans into turns from
the left/right steering DNs (DNa01/DNa02), and flares its wings and kicks its mid
legs out when the Giant Fibre (DNp01) fires. It is display only: joint angles are
set from firing rates, nothing feeds back into the controls, and flybody's RL
policies are not used.

```sh
pip install -r requirements-body.txt
python -m flight_simulator.fly_body          # window 1: waits for the controller
python -m flight_simulator.launch_fg --instance 0 --name "fly body"   # FlightGear
python -m flight_simulator --backend flightgear --brain connectome --seconds 180
```

The controller streams to UDP 127.0.0.1:5600 by default (`--body-port`,
`--no-fly-body`).

**737 handover:** a 737 started in the air keeps its own autopilot on until the
controller connects. The controller then sets `/fruitfly/controller-connected`
over telnet, and `fruitfly.nas` switches the autopilot off (never sooner than 7 s
after spawn). Before this, the autopilot went off on a fixed 7 s timer and the
plane stalled while FlightGear was still loading.

**Taking over an in-air run:** the controller takes over as soon as the plane is
flying (speed at least 35 m/s, wings within 20 deg; `wait_until_flying`). It no
longer waits for the 737 autopilot to settle. It holds the spawn preset altitude
and airspeed from `/sim/presets` (for example 3,000 ft / 220 kt;
`takeover_targets`), so the fly climbs back from the in-air sag itself. A closed
or crashed companion window no longer stops a FlightGear run: it warns and keeps
flying. `python -m flight_simulator.launch_fg --fly --name "..."` (no `--phase`)
starts the connectome obstacle run automatically.

**No-autopilot rule (mandatory, every aircraft): the fly never uses the airplane's
autopilot or autothrottle.** It is enforced in three places:

- **In FlightGear (737):** from the handover on, `fruitfly.nas` forces CMD A,
  CMD B and the autothrottle off whenever anything engages them, and counts each
  attempt in `/fruitfly/autopilot/violations`. There is no override.
- **In the controllers (all aircraft):** `flight_simulator` and `takeoff_landing`
  open an `AutopilotGuard` (`flightgear.py`) over telnet. Without telnet they
  refuse to fly. After the handover they wait until the autopilot is confirmed
  off before the fly touches the controls, then check it every second. If it is
  on, they force it off and count it (`autopilot_violations` in the result). If
  it stays on, the run stops and FlightGear is paused. The guard watches the
  737 (CMD A/B, autothrottle), the C172's KAP140 and FlightGear's generic
  `/autopilot/locks`.
- **In the code:** `tests/test_no_autopilot.py` fails if repo code engages an
  autopilot, reintroduces an override, or weakens the guard.

## What actually controls the airplane

- **Connectome mode:** the starter notebook's LIF equations run on the downloaded
  Shiu connectivity. A geometric looming proxy stimulates LC4/LPLC2. Measured
  DNp01 (Giant Fibre) spikes request an avoidance turn, subject to cruise rules.
- **Direction decoder:** obstacle bearing determines left/right. This is a design
  choice, not a learned lateralized neural response.
- **Conventional controller:** holds altitude, speed, and heading, and executes
  the requested bank. The fly does not independently stabilize the aircraft.
- **Reflex mode:** a deterministic threshold replaces the brain for integration
  tests. It is labeled as a non-neural baseline everywhere. It is never a silent
  fallback when the real data is missing.
- **Silent mode:** disables escape while retaining mandatory cruise rules to test whether the escape channel affects
  obstacle avoidance.

This implements the assisted alternative in the reference notes. The direct
neural flight-control goal in [PROJECT_PLAN.md](PROJECT_PLAN.md) remains an
unproven research objective. Opt-in experimental dopamine learning is now available; see
[reinforcement learning](REINFORCEMENT_LEARNING.md). Flight improvement has not
been established.

## Run the local demo

Python 3.10 or later. From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m flight_simulator --brain reflex --plot --realtime --seconds 0
```

Close the plot or press Ctrl-C to stop. `--seconds 0` continues cruising until
stopped; the configured obstacle course is finite. The companion shows a 3D obstacle scene and a full-course path map, with flight
phase, altitude, speed, bank angle, and escape activity. The local model uses reduced coordinated-turn dynamics, not a
complete aerodynamic model. It cannot establish performance in FlightGear.

Headless validation, requiring no third-party libraries:

```sh
python3 -m flight_simulator --brain reflex --seconds 180 --log runs/baseline.csv
python3 -m flight_simulator --brain silent --seconds 180 --log runs/silent.csv
python3 -m unittest discover -s tests -v
```

Exit status 0 means the requested run completed, 2 means collision, and 1 means
configuration/runtime error. Silent mode now avoids obstacles through the rules. Success in one course is not a general collision-avoidance guarantee.

## Run the actual connectome

```sh
pip install -r requirements-brain.txt
python -m flight_simulator.download_data
python -m flight_simulator --brain connectome --seconds 180 --plot --log runs/connectome.csv
```

The explicit downloader obtains the public datasets used by the notebook (over
100 MB). It resolves the current source commits and records URLs, SHA256 hashes,
and file sizes in `data/brain/manifest.json`. No FlyWire token is needed. The data,
virtual environment, and runtime logs are git-ignored. Missing files or empty
neuron groups fail with an error instead of substituting fake responses.

One 200 ms neural trial runs every 0.5 seconds of flight time. The model resets
between trials, as in the notebook, and advances its reproducible RNG seed each
trial. The local flight model waits during computation. FlightGear pauses and
requires a telemetry acknowledgement before each neural trial, then resumes.
Expect slower-than-real-time flight with the full brain. The notebook itself is
unchanged; this package reuses its model, not an independently validated
reproduction of every detail of the published model.

## Connect FlightGear

FlightGear must be installed separately. The project's default aircraft is the
**Boeing 737-800 with fly passengers** (`738-flies`): run
`python flightgear/setup_aircraft.py` once, see `flightgear/README.md`. The C172
(`c172p`) still works as a lighter fallback with `--aircraft c172p`. The steps target
an aircraft in calm air, already airborne and trimmed. The adapter and its UDP exchange
are tested locally; live FlightGear aircraft behavior still needs validation and
gain tuning on the teammate's machine.

1. Copy `flight_simulator/protocols/flybrain-state.xml` and
   `flight_simulator/protocols/flybrain-controls.xml` into the FlightGear data
   directory's `Protocol/` folder (`$FG_ROOT/Protocol`).
2. Start the 737 airborne, heading north, approximately 3,000 ft MSL and 220 kt
   (100 kt for the C172), with engines running over flat terrain or water.
   `python -m flight_simulator.launch_fg --instance 0` does this for you.
   The 737 auto-engages its own autopilot on an in-air start; our overlay
   (`fruitfly.nas`) switches it off at the handover and keeps it off (no-autopilot
   rule, above). Select calm weather. Disable conflicting joystick/mouse control
   inputs. In the
   launcher, add these additional arguments:

   ```text
   --generic=socket,out,20,127.0.0.1,5501,udp,flybrain-state
   --generic=socket,in,20,127.0.0.1,5502,udp,flybrain-controls
   ```

3. First test the baseline connection:

   ```sh
   python -m flight_simulator --backend flightgear --brain reflex --seconds 180 --plot --log runs/fg-baseline.csv
   ```

4. Once the aircraft holds stable flight and surface signs are verified, run:

   ```sh
   python -m flight_simulator --backend flightgear --brain connectome --seconds 0 --plot --log runs/fg-connectome.csv
   ```

The initial aircraft altitude, heading, and speed become hold targets. Obstacle
positions use a local east/north frame anchored at the first received aircraft
position. The default course is rotated ahead of the initial heading and spaced for the initial speed. **Obstacles are virtual cylinders: FlightGear does not
collide with them.** They are made visible either live by the controller (next section) or by the fixed scenery overlay. There is no automatic detection of terrain, buildings, or AI traffic.
For a real scene, provide obstacle coordinates/radii and MSL heights in JSON, or
add a sensor integration later. MSL altitude hold does not follow terrain.

### Obstacles inside FlightGear

With `--backend flightgear`, the controller connects to FlightGear's telnet
property server and places a tornado at every obstacle cylinder: a dark, slowly
turning funnel with a debris skirt and a cap cloud. The tornado is display only.
The fly avoids the cylinder, and the funnel stays inside it: it is as wide as the
cylinder at the top and narrows towards the ground, and the dark ring on the
ground is the cylinder's true footprint. Position, radius, bottom and top are the
cylinder's, after the default course has been rotated and scaled. The tornado
that the fly's looming input currently comes from glows pale blue, more strongly
as time-to-contact shrinks. Re-running the controller in the same FlightGear
session moves the existing tornadoes instead of adding more. This works for any course and any
aircraft, including custom `--obstacles` files. It is skipped for a fixed
scenery course (`"scenery"` in its JSON), whose tornadoes are already in the scenery.

- FlightGear needs `--telnet` (port 5500, or telemetry port − 1 for
  `launch_fg --instance N`) and `--fg-aircraft=<repo>/flightgear/Aircraft`. Both
  launchers already pass them, for any aircraft.
- `--telnet-port N` overrides the port. `--no-scene` skips the tornadoes.
- If telnet is not reachable, the run continues and prints a warning.

### Storm weather (looks only)

Both launchers start FlightGear in a thunderstorm by default (`--weather storm`):
gray overcast at 5,000 ft, heavy rain, and, with the 738-flies aircraft, lightning
flashes with thunder (`FlyCabin/Nasal/storm.nas`). A bolt appears beside one of the
tornadoes at each strike. `--weather clear` gives fair weather.

**The weather never acts on the airplane.** Wind is calm (METAR `00000KT`, plus
`--wind=0@0`), there are no gusts and turbulence is 0 in both profiles, and the
storm script touches nothing but the lightning flash, the bolt and the thunder
sound. `tests/test_storm.py` checks this. The fly's sensing is computed from
geometry, not from the picture, so rain and cloud don't change what it senses.
The [camera-vision prototype](CAMERA_VISION.md) does look at the picture. It now
looks for dark tornado funnels under a gray sky as well as the older red towers;
that detection is tuned on generated images and not yet checked on live frames.
- Code: `flight_simulator/fg_scene.py`. Models:
  `flightgear/Aircraft/FlyCabin/Models/Obstacles/`, generated by
  `flightgear/tools/make_obstacles.py` (up to 32 obstacles). Properties live
  under `/fruitfly/obstacles/obstacle[i]/`.

The adapter reads indicated airspeed and uses it as an approximate velocity for
obstacle sensing in calm air. It does not compensate for wind or high-altitude
true/indicated airspeed differences. The local tangent-plane coordinates are
intended for a small test area. Dense obstacles may trap this reactive controller.

On timeout, malformed telemetry, collision, Ctrl-C, or completion, the adapter
sends a pause request. UDP delivery is not guaranteed; verify pause in FlightGear.
No automatic resume occurs after exit. Resume manually when taking back control.
Pause/resume acknowledgements are required for connectome trials. A process crash
or broken socket cannot provide a reliable remote watchdog.

## Run logs and feedback (automatic)

Every `python -m flight_simulator ...` run is logged and pushed to the
[`sim-logs` branch](https://github.com/bhavyakummeta-a11y/FruitFly/tree/sim-logs)
with no extra steps. `main` and your working tree are never touched; the branch
is checked out separately at `.sim-logs/` (git-ignored).

Each run gets `runs/<UTC time>_<who>_<backend>-<brain>/` containing:

| File | What |
|---|---|
| `feedback.md` | Outcome table + notes. Start here. |
| `meta.json` | Exact command, args, code commit, dirty/untracked files, Python, FlightGear version |
| `code.diff` | Uncommitted changes at run time, so anyone can reproduce the run |
| `airplane.csv` | **Airplane log**: aircraft state + controls at every control step (gzipped if over 5 MB) |
| `fly_activity.csv` | **Fly-activity log**: every brain decision: looming input and escape output; in connectome mode also every stimulated input rate (`in_*_hz`) and every descending-neuron readout rate in `READOUTS` (DNp01 Giant Fibre, DNg02 flight power, DNa01/02 steering, ...) + trial time |
| `console.log`, `result.json` | Printed output and the summary |
| `fgfs_warnings.log` | FlightGear backend: WARN/ALERT/Nasal lines from `fgfs.log`, terrasync noise removed |

```sh
python -m flight_simulator --backend flightgear --brain reflex --note "first try with new gains"
python -m flight_simulator.runlog note "overshot heading after 2nd obstacle"   # feedback on latest run
python -m flight_simulator.runlog note --run <run id> "..."                    # feedback on any run
python -m flight_simulator.runlog list                                         # recent runs
python -m flight_simulator.runlog push                                         # retry if offline
```

`--no-push` logs and commits locally only (or set `FRUITFLY_NO_PUSH=1`);
`--no-runlog` skips logging. A failed push keeps the commit locally, and it goes
up with the next run. Passing `--log path.csv` still works; the airplane log then
goes there instead of the run folder.

### Graphics profile: light by default

The project launchers start FlightGear with a **light** graphics profile
(`flight_simulator/fg_graphics.py`): no trees, random objects, random buildings
or 3D clouds; cheapest fog; no specular/horizon effects; a shorter full-detail
range; and the frame rate capped at 30 fps. The fly's senses are computed from
geometry, not pixels, so experiments lose nothing, and the 30 fps cap keeps
FlightGear from taking CPU the fly brain and the loggers need.

```sh
python -m flight_simulator.launch_fg --phase takeoff --name "..."                 # light
python -m flight_simulator.launch_fg --phase takeoff --name "..." --graphics full # FlightGear defaults (demos, screenshots)
python flightgear/launch.py --name "..." --graphics full
```

The profile is on fgfs's command line (`/fruitfly/graphics`) and recorded as
`graphics` in each session's `meta.json`.

### FlightGear sessions: named, logged, pushed (mandatory)

**Every FlightGear session must have a name, is logged automatically, and is
pushed to the `sim-logs` branch when it ends.** This applies to people and AI agents.

```sh
python flightgear/launch.py --name "737 cabin smoke test"            # --name is required
python -m flight_simulator.launch_fg --instance 1 --name "obstacle course v2"
python -m flight_simulator.session attach --name "..."   # name (or rename) a running session
python -m flight_simulator.session status                # what is being logged right now
```

- The launchers refuse to start without `--name`. The name rides on fgfs's own
  command line (`--prop:string:/fruitfly/session/name=...`).
- A watchdog (`python -m flight_simulator.session watchdog`, started by the
  launchers; `install-autostart` runs it at every logon) attaches a logger to
  **any** `fgfs.exe`, however it was started. Sessions opened without a name are
  logged as `UNNAMED` and the live page asks for one.
- While FlightGear is open, a **live log page** (`http://127.0.0.1:8765/`, next
  free port per extra session) shows airplane charts, fly-activity charts and the
  running log: session events, FlightGear warnings/Nasal errors, and the output of
  controller runs.
- When fgfs exits, `runs/<time>_<who>_fg-<name>/` is committed and pushed:
  `airplane.csv` (2 Hz, property API), `fly_activity.csv`, `events.log`,
  `fgfs_warnings.log`, `meta.json`, `feedback.md` (exit code, crash/force-close
  flag, links to the controller runs).
- All checkouts/worktrees on a machine share one `sim-logs` checkout (the main
  checkout's `.sim-logs/`). Testing the logger itself? Set `FRUITFLY_NO_PUSH=1`:
  files are written but never committed, so they cannot ride along with someone
  else's push.

#### Who is flying: control attribution in every log

Every log states what is controlling the airplane, so a fly-brain flight can't
be confused with code, the autopilot or a person:

- **Controller runs** print and record (console, `meta.json` `control`,
  `feedback.md` "Who was flying") which kind of controller ran: `FLY_BRAIN`
  (connectome neurons decide, with what code still decides spelled out) or
  `NO_FLY_BRAIN` (reflex/silent baselines, the probe-table stand-in). The table
  is `control_attribution()` in `flight_simulator/runlog.py`.
- **FlightGear sessions** keep a control timeline (live "In control" line,
  `[control]` events, `in_control` + `autopilot` columns in `airplane.csv`,
  `control_timeline` in `meta.json`, and a time table in `feedback.md`):
  1. `AUTOPILOT`: the airplane's own autopilot is engaged (read every second from
     the same property list `AutopilotGuard` enforces); always wins.
  2. A running controller run: its `FLY_BRAIN` / `NO_FLY_BRAIN` attribution.
  3. A declared LLM agent / human / script: `python -m flight_simulator.session
     control llm --who "<name>" --note "..."` (then `control end`).
  4. `UNATTRIBUTED`: controls moving with nothing declared (human or external
     program, not the fly brain).
  5. `NOBODY`: no controller and no inputs.

#### Companion windows: log below, fly brain to the right (Windows)

When FlightGear's window appears, the session logger makes room on that monitor
and opens two chromeless windows glued to it (they follow when you move, resize,
minimise or raise FlightGear):

- **Log** (below): session name/status, altitude, speed, attitude, throttle, and
  the running log (session events, FlightGear warnings, controller output).
- **Fly brain** (right): all 138,639 FlyWire neurons drawn at their real positions
  (frontal view); neurons that fired in the latest 200 ms connectome trial light
  up (brightness = spike count), plus the descending-neuron rates. It states
  plainly when no fly brain is flying (no controller, or a reflex/silent baseline).

The brain data comes from the controller run's `fly_spikes.jsonl`, read
(read-only) from `ConnectomeBrain.last_counts`; the pilot code is not modified.
It needs the connectome data (`python -m flight_simulator.download_data`).
Parallel sessions each get their own windows, port and browser profile.

Airplane charts need the property API (`--httpd`, which the launchers set);
without it the session still records FlightGear's warnings and controller runs.

## Shared interface for teammates

`State` and `Controls` in `flight_simulator/core.py` are simulator independent.
State uses metres, m/s and radians, with clockwise heading from north and positive
right bank. Controls are aileron, elevator, rudder in [-1,1] and throttle in [0,1].
Positive elevator means nose down. FlightGear XML defines the exact wire order.
An MSFS teammate can supply the same state and consume these controls, adapting
units and signs to their API. Do not assume the FlightGear surface conventions
match a different aircraft or simulator.

Custom obstacles use the schema in `scenarios/obstacles.json` and are selected
with `--obstacles path.json`. Logs include aircraft state, input rate, measured
escape rate, phase, controls, and obstacle clearance. Use matched scenarios and
seeds for baseline/connectome comparisons.

## Windows 737 oscillation and pause update

See [the shared-log diagnosis and damping tests](notes/CRUISE_DAMPING_2026-11-14.md).
After pulling this update, **restart FlightGear through the updated launcher** so
it installs the new cruise protocols. For the default Windows installation:

```sh
python -m flight_simulator.launch_fg --instance 0 --name "737 damped cruise check"
python -m flight_simulator --backend flightgear --brain reflex --seconds 360 --note "damped cruise and independent companion"
```

Use `--fg` or `FG_INSTALL` if FlightGear is installed elsewhere. Existing manual
launches must copy `flybrain-state.xml` and the chosen `flybrain-controls*.xml`
from `flight_simulator/protocols` to FlightGear's `Protocol` directory and restart.
The shared pause fix sends both `/sim/freeze/master` and `/sim/freeze/clock`;
cruise acknowledgements now read the actual clock freeze, because the
shared FlightGear 2024 report found `/sim/freeze/master` insufficient. Control
packets now have one additional clock-freeze field, so reinstalling is required. The startup check reports an outdated protocol when
telnet confirms that a purported pause did not freeze the clock. The teammate’s pause fix also updates takeoff/landing control packets; the
launcher refreshes all protocols together.

Scenery setup happens while paused, before autopilot handover. After that the
run is **real time** (project rules, gh #3–#5):

- **1x:** the controller sets `/sim/speed-up` to 1 at the start, re-checks it
  every 3 s, resets any change and counts it (`speed_up_resets` in the result).
  It refuses to run if it can't.
- **No pause per brain trial:** connectome trials run in a background worker.
  The plane keeps flying on the last decision until the next is ready. Each
  applied decision is logged with the sim time it started from and its latency
  (`decision_started`, `decision_latency_s` in `fly_activity.csv`;
  `decision_latency_s`, `decisions_skipped` in `airplane.csv`; a `decisions`
  summary in the result). Training runs (`--learn` / `--load-learning`) are the
  exception: they still pause for each trial.
- **Crashes are data:** leaving the envelope (heading off >90°, bank >50°,
  pitch >25°, speed <70 % of target, altitude more than 40 m off) prints
  `ENVELOPE BREACH (logged, run continues)` and is recorded in the result
  (`envelope`: first breach, breach count, worst bank/pitch/altitude error). The
  run ends only on collision/ground contact or the time limit.
The brain requests avoidance; conventional rules still stabilize the airplane.

## Cruise-rule validation

See [the original log analysis](notes/CRUISE_RULES_2026-11-14.md) and
[the current damped-control results](notes/CRUISE_DAMPING_2026-11-14.md).
To reproduce the aerodynamic checks without opening FlightGear:

```sh
.venv/bin/pip install -r requirements-validation.txt
.venv/bin/python -m flight_simulator.validate_cruise --seconds 240
.venv/bin/python -m flight_simulator.validate_cruise --seconds 240 --disturbance --output runs/jsbsim-disturbance.csv
.venv/bin/python -m flight_simulator.validate_cruise --model 737 --control-period .3 --seconds 360 --disturbance --output runs/737-damped.csv
```

The companion opens by default on a FlightGear controller run. Start with an
already airborne aircraft, running engine, sufficient speed and the matching
project launcher/protocol. Target altitude is captured when the controller starts;
it is MSL hold, not terrain following. These checks use JSBSim's bundled C172P and 737 models, not
the installed FlightGear aircraft or the team's custom 738-flies model. Wind, engine failure and
unmapped scenery obstacles are not covered. No exact-altitude or universal
collision-avoidance guarantee follows from these results.

## Historical bounded-turn results, superseded by cruise rules (2026-11-14)

Both modes completed 180 seconds in the reduced local model without collision,
with one avoidance activation followed by a return to the original heading.

| Brain mode | Minimum clearance | Maximum heading deviation | Maximum bank |
|---|---|---|---|
| reflex | 234.12 m | 34.80° | 16.98° |
| connectome | 320.47 m | 34.89° | 16.98° |

All 14 automated checks pass, including a permanently active escape signal,
no-forward-progress abort, latest-packet selection, and twin-engine commands.
The updated companion was rendered and visually inspected. These results do not
verify live FlightGear aircraft behavior; no FlightGear installation is available
on the development machine.

## Historical original validation before the bounded-turn update (2026-11-14)

Using the supplied three-obstacle course, 180 seconds of local simulated flight,
and seed 0:

| Backend | Result | Minimum obstacle clearance |
|---|---|---|
| Actual connectome LIF | Completed; 6 avoidance activations | 209.18 m |
| Non-neural reflex baseline | Completed; 6 avoidance activations | 235.76 m |
| Escape output silenced | Collision at 23 seconds | 0 m at stop |

Both completed runs held 900 m altitude in the reduced local dynamics. This
idealized model decouples pitch from bank and does not model stalls, wind, or
terrain; altitude hold here is not evidence of real aircraft performance. The
connectome did not outperform the reflex baseline on minimum clearance in this
run. No reinforcement learning or broader performance claim follows from it.

The dataset loaded 138,639 neurons, including 314 looming input neurons and two
Giant Fibre neurons. Separate probes produced 0 Hz escape with no input and
167.5 Hz with 50 Hz looming input. Nonzero-input trials took approximately
3.3 seconds on this machine. Zero input uses an exact silence shortcut because
each trial starts below threshold with zero synaptic current and no other drive.

Ten automated tests pass, covering sustained local avoidance, disturbance
recovery, escape suppression, obstacle filtering, bounded controls, UDP exchange,
pause acknowledgements, telemetry validation, and protocol field ordering.
**FlightGear itself was not installed, so no live FlightGear flight was tested.**

Dataset provenance for this run:

- `Completeness_783.csv`: commit `91bdd1e7dcf193f3e7ca5a8933497fcef63b7960`, SHA256 `bbb847a4cc2caaa7a16349722d220c087317b946d148d4d592d94d250617a311`.
- `Connectivity_783.parquet`: commit `91bdd1e7dcf193f3e7ca5a8933497fcef63b7960`, SHA256 `efeb23fb99098e9c390f6869969b2a121a2ee92c833cfc45ecb2c1d8e1af0347`.
- `annotations.tsv`: commit `a83b2776d60d5764cef36b927f5f9679c16c47a2`, SHA256 `b214970b55d2fbe0853bba536fdcb9e28730f4eb7ab06f600491df795da683cd`.

## Protocol sources

The adapter follows FlightGear's [generic protocol documentation](https://github.com/FlightGear/flightgear/blob/next/docs-mini/README.protocol)
and [generic I/O usage](https://github.com/FlightGear/flightgear/blob/next/docs-mini/README.IO).
FlightGear documents its elapsed-time property in [Time](https://wiki.flightgear.org/Time).
Neural data sources are the [Shiu model repository](https://github.com/philshiu/Drosophila_brain_model)
and [FlyWire annotations](https://github.com/flyconnectome/flywire_annotations).
