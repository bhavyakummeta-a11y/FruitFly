# Airborne obstacle avoidance

This experiment starts in flight, maintains a cruise target, turns away from
configured obstacles, and resumes the original heading. It has a local demo and
a FlightGear UDP adapter using the same controller. No takeoff/landing or MSFS
adapter is included.

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
unproven research objective. Dopamine learning is not implemented.

## Run the local demo

Python 3.10 or later. From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m flight_simulator --brain reflex --plot --realtime --seconds 0
```

Close the plot or press Ctrl-C to stop. `--seconds 0` continues cruising until
stopped; the configured obstacle course is finite. The plot follows the airplane
and shows its trail, obstacle footprints, flight phase, altitude, speed, and
escape activity. The local model uses reduced coordinated-turn dynamics, not a
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

FlightGear must be installed separately. These instructions target a conventional
C172 in calm air, already airborne and trimmed. The adapter and its UDP exchange
are tested locally; live FlightGear aircraft behavior still needs validation and
gain tuning on the teammate's machine.

1. Copy `flight_simulator/protocols/flybrain-state.xml` and
   `flight_simulator/protocols/flybrain-controls.xml` into the FlightGear data
   directory's `Protocol/` folder (`$FG_ROOT/Protocol`).
2. Start the C172 airborne, heading north, approximately 3,000 ft MSL and 100 kt,
   with a running engine over flat terrain or water. Select calm weather. Disable
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
position. The sample course is north of that point. **These obstacles are virtual
cylinders, shown in the Python plot; they are not inserted into FlightGear's 3D
scenery.** There is no automatic detection of terrain, buildings, or AI traffic.
For a real scene, provide obstacle coordinates/radii and MSL heights in JSON, or
add a sensor integration later. MSL altitude hold does not follow terrain.

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
| `telemetry.csv` | Every control step (gzipped if over 5 MB) |
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
up with the next run. Passing `--log path.csv` still works; the telemetry then
goes there instead of the run folder.

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

## Validation recorded on 2026-11-14

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
