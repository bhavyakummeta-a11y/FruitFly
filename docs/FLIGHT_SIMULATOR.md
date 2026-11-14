# Airborne obstacle avoidance

This experiment starts in flight, maintains a cruise target, turns away from
configured obstacles, and resumes the original heading. It has a local demo and
a FlightGear UDP adapter using the same controller. No takeoff/landing or MSFS
adapter is included.

## Visible obstacles inside FlightGear

The optional [scenery overlay](../flightgear/SCENERY.md) adds three striped towers
inside FlightGear. Load `flightgear/obstacle-course` as an additional scenery
folder and pass `--obstacles flightgear/obstacle-course/course.json` to the
controller. Follow that guide for the matching airborne start location.
The course has a fixed geographic origin, so visual objects and collision
checks stay aligned even when Python connects after the aircraft has moved.
The ordinary default JSON remains a virtual-only course.

## Local update: bounded turns and companion view

Avoidance now latches one heading target at most 35 degrees from the initial
cruise heading. It holds that target until the triggering obstacle is behind the
airplane, then returns to cruise. Repeated escape spikes do not renew an endless
bank command. Bank targets are limited to 18 degrees, and bank/surface changes
are rate-limited. Roll and pitch damping are reduced from the first prototype.
The controller retains the initial trimmed pitch for FlightGear altitude hold.

The companion window has a **3D virtual obstacle view on the left** and **the
full flight path on the right**, including all configured obstacles. It opens by
default with `--backend flightgear`; use `--no-plot` to disable it. For the local
demo, use `--plot --realtime`. It is a separate window, not embedded in FlightGear.

```sh
.venv/bin/python -m flight_simulator --brain reflex --plot --realtime --seconds 180
```

FlightGear now reads the latest queued telemetry instead of replaying stale
states. It stops and sends a pause request if heading deviates by over 90 degrees,
bank exceeds 50 degrees, pitch exceeds 25 degrees, speed falls below 70% of the
starting speed, or altitude falls 150 m below the starting altitude. Avoidance
also stops if an obstacle has not been passed after 90 seconds. These are test
abort conditions, not stall protection or a terrain-avoidance system.

For the supplied default course, FlightGear rotates the course ahead of the
starting heading, increases its forward spacing with the square of starting
speed relative to 50 m/s, and raises cylinder tops above the starting altitude.
Custom JSON obstacle files keep their exact local east/north positions and
heights. The controller also draws this course live in FlightGear as towers
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

## What actually controls the airplane

- **Connectome mode:** the starter notebook's LIF equations run on the downloaded
  Shiu connectivity. A geometric looming proxy stimulates LC4/LPLC2. Measured
  DNp01 (Giant Fibre) spikes activate an avoidance turn.
- **Direction decoder:** obstacle bearing determines left/right. This is a design
  choice, not a learned lateralized neural response.
- **Conventional controller:** holds altitude, speed, and heading, and executes
  the requested bank. The fly does not independently stabilize the aircraft.
- **Reflex mode:** a deterministic threshold replaces the brain for integration
  tests. It is labeled as a non-neural baseline everywhere. It is never a silent
  fallback when the real data is missing.
- **Silent mode:** disables escape to test whether the escape channel affects
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
configuration/runtime error. A silent-brain collision is expected in the supplied
course. Success in one course is not a general collision-avoidance guarantee.

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
   (`fruitfly.nas`) switches it back off after about 7 s. Select calm weather. Disable
   any aircraft autopilot and conflicting joystick/mouse control inputs. In the
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
property server and places a red/white banded tower at every obstacle cylinder.
Each tower has the cylinder's exact position, radius, bottom and top, after the
default course has been rotated and scaled. The tower that the fly's looming
input currently comes from glows orange, more strongly as time-to-contact
shrinks. Re-running the controller in the same FlightGear session moves the
existing towers instead of adding more. This works for any course and any
aircraft, including custom `--obstacles` files. It is skipped for a fixed
scenery course (`"scenery"` in its JSON), whose towers are already in the scenery.

- FlightGear needs `--telnet` (port 5500, or telemetry port − 1 for
  `launch_fg --instance N`) and `--fg-aircraft=<repo>/flightgear/Aircraft`. Both
  launchers already pass them, for any aircraft.
- `--telnet-port N` overrides the port. `--no-scene` skips the towers.
- If telnet is not reachable, the run continues and prints a warning.
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

### FlightGear session log + live page

Opening FlightGear through any project launcher also starts a session log and
opens a **live log page** in your browser (`http://127.0.0.1:8765/`): airplane
charts, fly-activity charts, and a running log of session events, FlightGear
warnings/Nasal errors, and the output of any controller run started meanwhile.
When FlightGear closes (or crashes, which is flagged), the session folder
`runs/<time>_<who>_fg-session/` (`airplane.csv` at 2 Hz from the property API,
`fly_activity.csv` with the cabin flies' activity, `events.log`,
`fgfs_warnings.log`, `feedback.md` linking the controller runs) is pushed.

```sh
python flightgear/launch.py                       # 737 + fly cabin  (--no-log to skip)
python -m flight_simulator.launch_fg --instance 1 # extra instance   (--no-log to skip)
python -m flight_simulator.session attach         # FlightGear opened another way (desktop shortcut)
```

Airplane charts need the property API (`--httpd=8080`, which the launchers set);
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

## Bounded-turn regression results (2026-11-14)

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

## Original validation before the bounded-turn update (2026-11-14)

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
