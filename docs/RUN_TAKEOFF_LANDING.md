# How to run the Takeoff fly and the Landing fly

Step-by-step instructions. For how the flies work and why, see [TAKEOFF_LANDING.md](TAKEOFF_LANDING.md).

There are three ways to run them, from fastest to most real:

| | Brain | Airplane | Time per run | Use it to |
|---|---|---|---|---|
| **A. Offline check** | stand-in (probe table, **not** a fly) | reduced local 737 model | under 1 s | check the code works |
| **B. Real brain, local plane** | connectome (FlyWire 783) | reduced local 737 model | 8–15 min | test the fly brain without FlightGear |
| **C. Real brain in FlightGear** | connectome | FlightGear 737-800 | 10–20 min | the demo |
| **Full flight** (takeoff → circuit → landing) | either | local or FlightGear | 1.5–2 h with the connectome | the whole demo in one go |

Commands below use `python`. On Linux/WSL use `python3`. Once the venv exists, use `.venv\Scripts\python` (Windows) or `.venv/bin/python` (Linux).

---

## 1. One-time setup

From the repository root:

```sh
git pull
python -m venv .venv
```

Then install the brain's packages and download the connectome, about 140 MB:

```sh
# Windows
.venv\Scripts\pip install -r requirements-brain.txt
.venv\Scripts\python -m flight_simulator.download_data

# Linux / WSL
.venv/bin/pip install -r requirements-brain.txt
.venv/bin/python -m flight_simulator.download_data
```

The data goes into `data/brain/`, which git ignores.

For FlightGear (option C only): install **FlightGear 2024.1.4**, then install our 737 once:

```sh
python flightgear/setup_aircraft.py
```

If FlightGear isn't in `D:\FlightGear`, set `FG_INSTALL` to its folder, or pass `--fg <folder>` to the launcher.

---

## 2. Offline check (A)

```sh
python -m flight_simulator.takeoff_landing takeoff --brain standin
python -m flight_simulator.takeoff_landing landing --brain standin
python -m unittest discover -s tests
```

Each run ends with a JSON summary and `"success": true`. All tests should pass.

To include the connectome's noise (1–2 neurons per readout), add `--noise-seed 1`.

---

## 3. Real brain, local plane (B)

```sh
.venv/bin/python -m flight_simulator.takeoff_landing takeoff --brain connectome --log runs/takeoff.csv --plot runs/takeoff.png
.venv/bin/python -m flight_simulator.takeoff_landing landing --brain connectome --log runs/landing.csv --plot runs/landing.png
```

What you'll see:

1. `Adapting: measuring zero points ...`: 20 brain trials (about 70 s) of the fly's "nothing is wrong" stimulus.
2. A status line every 5 s of sim time: phase, distance, height, speed, pitch, throttle, and a few neuron rates.
3. The JSON summary. `--log` saves every step (inputs and neuron rates), and `--plot` saves a picture of the run.

Each brain trial takes about 3–4 s, so a takeoff takes about 8 minutes and a landing about 15.

### Experiments worth running

| Command (add to the line above) | What should happen |
|---|---|
| `takeoff ... --fault-at-kt 100` | Bitter suppresses MN9, the takeoff is **rejected** and the plane stops on the runway |
| `takeoff ... --silence looming` | **Lesion:** no jump, so no rotation, and the plane runs off the end (`success: false` is the expected result) |
| `landing ... --start-speed-kt 175` | Approach 30 kt fast, so the fly **goes around** |
| `landing ... --silence looming` | **Lesion:** no flare, so a harder touchdown than the intact fly |
| `--offset-m 15` | Start 15 m off the centerline |
| `--seed 1` | A different random seed for the brain's input spikes |

---

## 4. In FlightGear (C)

You need **two terminals**: one starts FlightGear, the other runs the fly.

### Takeoff

**Terminal 1:** start FlightGear on runway 28R at San Francisco (KSFO):

```sh
python -m flight_simulator.launch_fg --phase takeoff --name "takeoff fly test"
```

This copies the runway protocols into FlightGear, starts the 737 on the runway, and starts the session logger. **Wait until both engines are at idle**, about a minute (the 737 autostart runs by itself). Don't touch the controls, and leave the autopilot and autothrottle off.

**Terminal 2:** start the Takeoff fly:

```sh
.venv\Scripts\python -m flight_simulator.takeoff_landing takeoff --brain connectome --backend flightgear --log runs/fg-takeoff.csv --plot runs/fg-takeoff.png
```

(The launcher prints this command with `--brain standin`. Use `--brain connectome` for the real fly.)

What happens:

1. The fly adapts (about 70 s), then releases the brakes at full power.
2. FlightGear runs in **real time (1x) and is never paused** for a brain trial. Each trial runs in the background and the plane flies on the last decision until the next is ready, so decisions arrive a few seconds late. If that crashes the plane, the crash is data.
3. Near 145 kt the rig shows the fly a looming stimulus (presented, like a lab looming disk: nothing on the runway really looms), the fly "jumps", and the plane rotates and lifts off. Gear comes up when it's climbing.
4. At 1,000 ft the terminal prints **HANDOVER**. **The fly keeps flying** (wings level, 10° climb) because there's no Cruise fly yet.
5. **Press Ctrl-C** to stop. The fly centres the controls and pauses FlightGear. You should see `FlightGear paused (acknowledged)`.

> ⚠️ If you see **`WARNING: FlightGear did not acknowledge the pause`**, press **p** in FlightGear right away. FlightGear keeps the last controls it received, and that's how the first test crashed.

### Landing

**Terminal 1:**

```sh
python -m flight_simulator.launch_fg --phase landing --name "landing fly test"
```

This starts the 737 in the air, 3 nm out on final for 28R. **Wait until it's flying steadily.** The autopilot switches off by itself once the controller connects.

**Terminal 2:**

```sh
.venv\Scripts\python -m flight_simulator.takeoff_landing landing --brain connectome --backend flightgear --log runs/fg-landing.csv --plot runs/fg-landing.png
```

The runway position comes from the launcher's start point (`--final-nm 3`). If you started somewhere else, give the threshold yourself: `--runway LAT LON TRUE_HEADING`. If the plane gains or loses speed on the approach, adjust `--approach-throttle` (default 0.55).

What happens: the plane follows the glideslope. Near 90 ft the runway looms, DNp07 fires and the plane **flares** (nose up, throttle to idle), then touches down and brakes. If the approach becomes unstable, the fly loses its appetite (bitter suppresses MN9) and **goes around**, and keeps flying until you press Ctrl-C.

### Full flight: takeoff, circuit, landing

One flight, three fly configurations of the same brain, handed over in the air:

| Fly | Brain state | Flies |
|---|---|---|
| Takeoff fly | standing | brake release → 1,000 ft |
| Circuit fly | cruising | right-hand traffic circuit at 2,000–3,000 ft (stays over the bay at KSFO 28R) |
| Landing fly | flying | 3 nm final → flare → touchdown → rollout |

**Terminal 1:** start on the runway, exactly as for takeoff:

```sh
python -m flight_simulator.launch_fg --phase takeoff --name "full flight test"
```

**Terminal 2:** once both engines are at idle:

```sh
.venv\Scripts\python -m flight_simulator.mission --brain connectome --backend flightgear --log runs/fg-mission.csv --plot runs/fg-mission.png
```

What happens:

1. The Takeoff fly takes off. At 1,000 ft the terminal prints `=== HANDOVER: Takeoff fly (standing) -> Circuit fly (cruising) ===`.
2. FlightGear freezes for about 70 s while the Circuit fly **adapts** (20 trials of its neutral stimulus), then the flight continues.
3. The Circuit fly flies upwind, crosswind, downwind, base and final. On final the checklist sets flaps 30 and gear down.
4. Once established about 3 nm out: `=== HANDOVER: Circuit fly (cruising) -> Landing fly (flying) ===`, then another adaptation pause, then the approach, flare and landing.

A full flight is about 10 minutes of flying, which is roughly 1,250 brain trials, so allow **1.5–2 hours** with the connectome. To check the whole sequence first, use the fast stand-in: `--brain standin`.

The plot marks each handover with a solid line and the fly's name. In the neuron heatmap you can see the brain switch: the escape neurons (DNp01/02/04/11) fire for the Takeoff fly's jump, the steering and pitch neurons carry the circuit, and DNp07 fires for the Landing fly's flare.

**Obstacle avoidance is not part of this flight.** It's a separate experiment with its own owner. `CircuitFly.obstacle_slot` is where it can plug in.

Local version (no FlightGear): `.venv/bin/python -m flight_simulator.mission --brain connectome --log runs/mission.csv --plot runs/mission.png`

### Running a second FlightGear at the same time

Add `--instance 1` to the launcher. It prints the ports to pass to the controller (`--telemetry-port 5511 --control-port 5512`).

---

## 5. Reading the result

The JSON summary at the end:

| Field | Meaning |
|---|---|
| `success` | The run met the plan's criteria (see below) |
| `phase` | Where it ended: `HANDOVER (1,000 ft)`, `REJECTED`, `ROLLOUT`, `GO-AROUND`… |
| `liftoff_x_m` | Takeoff: metres from brake release to lift-off |
| `touchdown_x_m`, `touchdown_sink_fpm` | Landing: where (metres past the threshold) and how hard |
| `max_centerline_m` | Largest distance from the centerline on the ground or below 100 ft |
| `tail_strike`, `left_runway`, `go_around`, `rejected` | What happened |
| `events` | The fly's key decisions: `JUMP`, `FLARE`, `REJECT`, `GO-AROUND` |

Success means:
- **Takeoff:** reached 1,000 ft, or rejected and stopped on the runway, with no tail strike and without leaving the runway.
- **Landing:** touched down 0–900 m past the threshold at under 500 fpm, or completed a go-around.

Exit codes: `0` success, `2` criteria not met, `1` error.

---

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| `No FlightGear telemetry` | FlightGear isn't running with the runway protocols, or the ports differ. Start it with `launch_fg --phase ...`, and match `--telemetry-port`/`--control-port` to what it printed |
| `Could not copy the protocols` | Copy `flight_simulator/protocols/flybrain-runway-*.xml` into `<FlightGear>/data/Protocol/` yourself (it may need an admin terminal) |
| `Start FlightGear on the runway ... for takeoff` | The main gear isn't on the ground yet; wait for the sim to settle |
| `Missing connectome data` | Run `python -m flight_simulator.download_data` (section 1) |
| `Install requirements-brain.txt` | You're using the system Python; use `.venv\Scripts\python` |
| Brain trials much slower than 4 s | Close other heavy programs. Each trial runs the whole 139k-neuron brain on the CPU |
| The plane drifts off the centerline | Make sure adaptation ran (don't pass `--no-calibrate`), then send us the `--log` CSV |
| `git push` hangs | Git Credential Manager is waiting for a sign-in window on your desktop |

---

## 7. Sharing a run

FlightGear sessions started with `launch_fg` are logged and pushed to the `sim-logs` branch automatically. **That log doesn't include the fly's brain activity**, so always run the controller with `--log runs/fg-<phase>.csv` (and `--plot`) and share those files too. Add notes to the latest session with:

```sh
python -m flight_simulator.runlog note "rotated late, drifted left"
```
