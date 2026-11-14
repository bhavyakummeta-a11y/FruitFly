# Takeoff fly and Landing fly: how they work and how to run them

See [Synthetic fly sensory view](FLY_VISION.md) for live obstacle/runway projections, path-deviation cues and the inputs sent to the brain.

This is the implementation of the picks in [TAKEOFF_LANDING_PLAN.md](TAKEOFF_LANDING_PLAN.md): the **escape-jump Takeoff fly** (T-C) and the **flying-fly Landing fly** (L-C), flying the Boeing 737-800.

Both are the **same FlyWire 783 connectome** running Shiu's LIF model unchanged, configured as two brains in different behavioural states:

| | Takeoff fly | Landing fly |
|---|---|---|
| State | **standing** fly | **flying** fly |
| Looming means… | jump → **rotation** (DNp02/04/11, DNp01) | extend the legs → **flare** (DNp07) |
| Where the looming comes from | **a stimulus we present at Vr**, like the looming disk a lab shows a standing fly. Nothing on a runway actually looms at Vr | **real geometry:** the runway expanding in view, time-to-contact τ = height ÷ sink rate |
| Nerve-cord gate | escape DNs act only on the wheels; past V1 the throttle is committed | DNp07 acts only below 100 ft; DNp01 (jump) is decoupled and only logged |

## Quick start

Step-by-step instructions, including FlightGear: **[RUN_TAKEOFF_LANDING.md](RUN_TAKEOFF_LANDING.md)**.

```sh
# Fast and offline: the probe-table stand-in (NOT a fly brain), standard library only
python3 -m flight_simulator.takeoff_landing takeoff --brain standin
python3 -m flight_simulator.takeoff_landing landing --brain standin

# The real connectome (one-time setup)
python3 -m venv .venv && .venv/bin/pip install -r requirements-brain.txt
.venv/bin/python -m flight_simulator.download_data
.venv/bin/python -m flight_simulator.takeoff_landing takeoff --brain connectome --log runs/takeoff.csv
.venv/bin/python -m flight_simulator.takeoff_landing landing --brain connectome --log runs/landing.csv
```

Useful flags:

| Flag | What it does |
|---|---|
| `--silence looming` | Lesion control: cut the looming neurons' outgoing synapses |
| `--fault-at-kt 100` | Takeoff: inject a reject condition at 100 kt (bitter) |
| `--start-speed-kt 175` | Landing: start the approach 30 kt fast, which should cause a go-around |
| `--offset-m 15`, `--yaw-drift 0.004` | Start off the centerline / add a crosswind-like yaw drift |
| `--period 0.5` | Seconds of sim time between brain trials (Landing uses 0.25 s below 200 ft) |
| `--backend flightgear` | Fly the live FlightGear 737 instead of the reduced local model (below) |
| `--plot runs/x.png` | Save a plot of sugar input, brain activity, altitude and airspeed (needs matplotlib) |

### Plot: sugar input and brain activity

Add `--plot runs/landing.png` to any run (demo or FlightGear) to get a picture of the flight: the flight phases, the **sugar input** the brain receives (Hz), a **brain activity** heatmap with one row per descending neuron (darker blue = firing harder), altitude and airspeed, all on one time axis. To plot a run you already logged with `--log`:

```sh
python3 -m flight_simulator.plot_run runs/landing.csv          # writes runs/landing.png
```

Exit status: `0` means the plan's "done when" criteria were met, `2` means they weren't, `1` means an error. Every brain trial takes about 3–4 s on a laptop CPU with the connectome, so a takeoff takes about 8 minutes of wall time and a landing about 15.

To re-measure the channels, run the step-0 probe: `.venv/bin/python -m flight_simulator.probe`.

## Step-0 probe: what the connectome actually does

Each sensory group alone, 200 ms trials. Rates are the mean of each readout group (Hz). Full tables: `runs/probe.json`, `runs/probe_combos.json`.

| Stimulus | Strong responses | Used for |
|---|---|---|
| looming (LC4 + LPLC2) | DNp01 165→292, DNp04 180→330, DNp02 52→202, DNp11 48→152 | **Takeoff: the jump (rotation)** |
| looming | DNp07 5→35 (DNp10 ≈ 0, unusable) | **Landing: the flare** |
| HS left / HS right | DNp15_L + DNa02_L / DNp15_R + DNa02_R | **Steering** (rudder, aileron) |
| VS left / VS right | DNp20_L / DNp20_R (DNOVS1) | **Pitch** (sum) and **roll** (difference) |
| sugar | MN9 10→100 only | **Throttle / "go for it"** |
| sugar + bitter | MN9 102 → 70 → 28 → 0 as bitter rises | **Reject takeoff / go-around** ("loses its appetite") |
| sugar + looming | MN9 → ~0 (escape overrides feeding) | Why the throttle needs the V1 commit gate, and why it idles itself in the flare |
| translational flow (LPC1/LLPC1) | MDN 26→72, DNa01/DNa02 on both sides, DNp07 | **Not used**: it hijacks the steering DNs |
| bitter alone | nothing | — |

Corrections to the plan that came out of the probe:

- **DNp09 never fires** for any of our stimuli, so the MVP mapping "sugar → DNp09 → throttle" doesn't exist in the model. MN9 carries the throttle instead.
- **Bitter doesn't drive MDN.** Reject and go-around come from bitter *suppressing* MN9 rather than from MDN.
- **DNp10 is silent** with looming. The flare uses DNp07 alone.

## The three layers

1. **Stimulator rig** (`encode` in [flies.py](../flight_simulator/flies.py)): sim state → sense rates, always clipped to 0–200 Hz. VS and HS use push-pull around a **tonic 100 Hz** resting rate, so "no error" is 100/100. The drive is strong (HS 16 Hz and VS pitch 12 Hz per degree of error, VS roll 8 Hz per degree) because steering and pitch are each read from **one neuron per side**: a 200 ms trial measures that rate only in 5 Hz steps, ±13–20 Hz from trial to trial.
   Before each phase the fly **adapts**: 20 trials of its own "nothing is wrong" stimulus mix set the steering zero point (`calibrate()`, about 70 s on the connectome; skip with `--no-calibrate`). The steering zero moves with context, from −37 Hz with HS probed alone to about −29 Hz with every sense on, and without adaptation both flies held a standing left offset. The pitch and roll zeros come from the probe, and the MN9 zero (65 Hz) from the connectome's in-flight approach average.
2. **Brain** (`ConnectomeBrain.run` in [brain.py](../flight_simulator/brain.py)): one fresh 200 ms trial from rest per decision, with all senses stimulated together.
3. **Nerve-cord layer** (`decode`, `haltere`): descending-neuron rates → commands, plus the state gates. A fixed-gain **pitch-rate reflex** executes the brain's pitch-rate command, the way a fly's halteres stabilise its wingbeat without the brain.

### Takeoff fly channels

| Sense | Encodes | → Readout | → Command |
|---|---|---|---|
| sugar 200 Hz | "go" | MN9 | throttle (before V1); TOGA after V1 (committed) |
| bitter 200 Hz | fault or > 8 m off centerline, below V1 only | suppresses MN9 | MN9 < 10 Hz for 2 trials → **reject**: idle + max brakes |
| looming 0→200 Hz | **presented stimulus, not seen:** ramps with IAS from Vr−5 to Vr+5 kt, on the wheels | DNp02+DNp04+DNp11 | nose-up rate, up to 3°/s: **the jump** |
| VS L/R | pitch error (target 0° on the wheels, 15° airborne), roll | DNp20 sum / difference | pitch rate / aileron |
| HS L/R | heading error + centerline offset + yaw rate | DNp15+DNa02, L−R | rudder and nosewheel (aileron in the air) |

### Landing fly channels

| Sense | Encodes | → Readout | → Command |
|---|---|---|---|
| sugar 80–200 Hz | 100 + 4 Hz per kt below Vapp (145 kt) | MN9 | throttle around approach power |
| bitter 200 Hz | unstable below 1,000 ft: > 0.7° off glideslope, > 40 m off centerline, speed outside −8/+15 kt | suppresses MN9 | MN9 < 5 Hz for 2 trials above 100 ft → **go-around** |
| looming 0→200 Hz | time to contact τ = height / sink rate, from τ = 8 s | **DNp07** | below 100 ft: nose-up rate, the **flare**. Looming also suppresses MN9, so the brain idles the throttle itself |
| VS L/R | pitch error vs approach attitude − 1.5 × glideslope error | DNp20 sum / difference | pitch rate / aileron |
| HS L/R | localizer: heading + offset + yaw rate | DNp15+DNa02, L−R | aileron/rudder; rudder on rollout |

### What is scripted, not the fly

Flaps (5 for takeoff, 30 for landing), gear up at positive climb, and idle + autobrake after touchdown. The 737's autopilot and autothrottle must be **off**. The target attitudes (0° on the wheels, 15° climb, approach attitude), V-speeds and thresholds are fixed design choices, documented above.

## Results

See the table below (filled in from the connectome runs in `runs/connectome/`).

<!-- RESULTS -->

### What the first FlightGear test taught us (2026-11-14)

Michael's run "737 takeoff fly test" (sim-logs `ccc23d3`, code `161336b`):

| Seen | Cause | Fix |
|---|---|---|
| Good roll, lift-off, 15° climb to ~985 ft, then a spiral dive into the ground at 271 kt | At HANDOVER the controller **exited**. FlightGear keeps the last controls it received (rudder −0.2, aileron −0.08), and the single pause packet never took effect | The fly keeps flying after its phase ends (10° climb, wings level) until Ctrl-C. On exit it centres the ailerons and rudder and waits for a confirmed pause |
| Didn't follow the runway: drifted 5.5 m left on the roll, 11 m in the climb, rudder flipping sign every sample | Steering zero-point bias plus 1-neuron readout noise | Pre-flight adaptation (`calibrate()`), DN-rate low-pass, HS drive 8 → 16 Hz/deg |
| Lift-off at 10.9° (the tail strikes at 11°) | Rotation of 3°/s plus the FG 737's lag | Jump capped at 2.5°/s |
| AGL reads 7.95 ft parked | `altitude-agl-ft` is the CG height | Offset subtracted (it matters for the flare) |

The connectome landing went around for the same reasons: first the pitch noise sank it below the glideslope, then the steering bias carried it 40 m left. With all of the above, the noisy stand-in (spike-count noise plus a steering bias like the connectome's) takes off 40/40 times (median 3 m off centerline) and lands 37/40 (median 157–203 fpm).

## Full flight: three flies, one brain

`python -m flight_simulator.mission` ([mission.py](../flight_simulator/mission.py)) flies takeoff, a right-hand traffic circuit and landing as one flight. The connectome stays loaded throughout, and at each handover the next **fly configuration** takes over:

| Handover | When | Brain change |
|---|---|---|
| Takeoff fly → **Circuit fly** | 1,000 ft after takeoff | standing → cruising: looming no longer means "jump" (unused, reserved for obstacle avoidance); HS steering now sets a **bank target** (up to 25°) instead of rudder |
| Circuit fly → **Landing fly** | established ~3 nm out (< 30 m off the centerline, < 5° bank, on the glideslope) | cruising → flying: looming means "extend the legs" (DNp07 = flare), bitter can call a go-around |

At every handover the new fly re-adapts its steering zero point. The haltere-reflex integrator and throttle carry over, and the Landing fly starts from the attitude that flies the 3° glideslope at the current angle of attack.

The Circuit fly uses the same senses as the others:
- **HS:** track error (heading + cross-track over 1.5 km + 1 s × turn rate).
- **VS:** climb-angle error (both sides) and bank error (left vs right).
- **Sugar:** speed error.
- **Readouts:** the steering readout sets the bank target, the VS roll readout flies it, the VS pitch readout drives the haltere pitch-rate reflex, and MN9 sets the throttle around a slow, fixed-rate trim.
- **Scripted (never the fly):** the legs, altitudes and speeds of the circuit, gear up after takeoff, and flaps 30 + gear down + extra power at the start of final.

Results with the noisy stand-in (spike-count noise ± a steering bias like the connectome's): **16/20 full flights land** (61–266 fpm, within 6 m of the centerline); 3 of the other 4 go around.

Two bugs found on the way, both now covered by tests: the runway-relative heading wasn't wrapped, so after a 360° circuit the Landing fly thought it was 360° off and steered one way; and the glideslope check measured the error only as an angle, which near the runway is stricter than any real criterion.

## FlightGear

**Always pull first** (`git pull`), so you have the latest launcher, protocols and aircraft. Run `python flightgear/setup_aircraft.py` once.

The launcher does the setup for you: it copies `flybrain-runway-state.xml` and `flybrain-runway-controls.xml` into `$FG_ROOT/Protocol/`, starts the 737 at **KSFO 28R** with the runway data links, and prints the controller command. Use two terminals.

**Takeoff:** the 737 starts on the runway with flaps 5, parking brake off, and the engines starting by themselves (737 autostart).

```sh
python -m flight_simulator.launch_fg --phase takeoff --name "takeoff test"   # terminal 1
# wait ~1 min until both engines are at idle, then:
python -m flight_simulator.takeoff_landing takeoff --brain standin --backend flightgear    # terminal 2
```

**Landing:** the 737 starts 3 nm out on final at 1,000 ft and 145 kt with flaps 30 and gear down. The autopilot switches itself off a few seconds after spawning.

```sh
python -m flight_simulator.launch_fg --phase landing --name "landing test"   # terminal 1
python -m flight_simulator.takeoff_landing landing --brain standin --backend flightgear    # terminal 2
```

For the real fly brain, replace `python` with `.venv/bin/python` (Windows: `.venv\Scripts\python`) and `--brain standin` with `--brain connectome`.

Notes:

- Landing works out the threshold from where FlightGear spawns the plane: 3 nm (`--final-nm`) ahead along its heading. For an exact threshold, pass `--runway LAT LON TRUE_HEADING` instead.
- If FlightGear is installed somewhere unusual, add `--fg <install dir>` or set `FG_INSTALL`. If the protocols can't be copied (for example under `C:\Program Files` without admin rights, or with the Linux AppImage), the launcher prints a warning and the copy has to be done by hand.
- `--instance 1` runs a second FlightGear on other ports. The launcher prints the matching `--telemetry-port/--control-port` flags.

FlightGear is frozen (`/sim/freeze/master`) during every brain trial and resumed afterwards. The FlightGear path has been flown live once, for takeoff (see above). The fixes from that run haven't been flown yet, and the gains were tuned on the reduced local model. Run with `--log runs/fg-<phase>.csv` so the brain's inputs and DN rates are captured; a FlightGear session log alone doesn't include them. Expect to retune `--approach-throttle`, the VS pitch gain, and the rudder gains against the JSBSim 737. Also check that rudder steers the nosewheel on the ground in the 738-flies model.

## Honest limits

- The local `RunwaySim` is a **reduced point-mass model with rough 737 numbers**, not a validated flight model. Success there is not evidence of performance in FlightGear.
- The `standin` brain is a lookup of the probe table, labelled as not a fly everywhere. It exists for fast tests and as a baseline.
- The decoder gains and zero points are hand-set from the probe table, not fitted. The haltere reflex is a fixed PI loop on pitch rate. It executes the brain's commands but doesn't choose them.
- The brain only sees the world through 7 sensory channels, at 2–4 decisions per second.
- **The takeoff fly's rotation cue is presented, not seen.** On a runway nothing looms at Vr, so the stimulator rig shows the fly a looming stimulus timed by airspeed, the way lab experiments trigger the escape jump with a looming disk. The rig decides *when* to rotate; the connectome's escape circuit decides *how hard*. Real visual cues don't work here: the runway end does loom, but at Vr it is about 2 km away (τ ≈ 28 s), and escape only fires near τ ≈ 8 s, about 600 m before the end. Translational optic flow (LPC1/LLPC1) grows with speed, but in the probe it drives DNp07 and MDN, not the escape neurons. The Landing fly is different: its looming is the real runway expanding as the plane descends.
