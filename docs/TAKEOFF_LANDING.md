# Takeoff fly and Landing fly: how they work and how to run them

This is the implementation of the picks in [TAKEOFF_LANDING_PLAN.md](TAKEOFF_LANDING_PLAN.md): the **escape-jump Takeoff fly** (T-C) and the **flying-fly Landing fly** (L-C), flying the Boeing 737-800.

Both are the **same FlyWire 783 connectome** running Shiu's LIF model unchanged, configured as two brains in different behavioural states:

| | Takeoff fly | Landing fly |
|---|---|---|
| State | **standing** fly | **flying** fly |
| Looming means… | jump → **rotation** (DNp02/04/11, DNp01) | extend the legs → **flare** (DNp07) |
| Nerve-cord gate | escape DNs act only on the wheels; past V1 the throttle is committed | DNp07 acts only below 100 ft; DNp01 (jump) is decoupled and only logged |

## Quick start

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

1. **Stimulator rig** (`encode` in [flies.py](../flight_simulator/flies.py)): sim state → sense rates, always clipped to 0–200 Hz. VS and HS use push-pull around a **tonic 100 Hz** resting rate, so "no error" is 100/100 and the readout zero points come from the probe.
2. **Brain** (`ConnectomeBrain.run` in [brain.py](../flight_simulator/brain.py)): one fresh 200 ms trial from rest per decision, with all senses stimulated together.
3. **Nerve-cord layer** (`decode`, `haltere`): descending-neuron rates → commands, plus the state gates. A fixed-gain **pitch-rate reflex** executes the brain's pitch-rate command, the way a fly's halteres stabilise its wingbeat without the brain.

### Takeoff fly channels

| Sense | Encodes | → Readout | → Command |
|---|---|---|---|
| sugar 200 Hz | "go" | MN9 | throttle (before V1); TOGA after V1 (committed) |
| bitter 200 Hz | fault or > 8 m off centerline, below V1 only | suppresses MN9 | MN9 < 10 Hz for 2 trials → **reject**: idle + max brakes |
| looming 0→200 Hz | IAS from Vr−5 to Vr+5 kt, on the wheels | DNp02+DNp04+DNp11 | nose-up rate, up to 3°/s: **the jump** |
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

## FlightGear

1. Copy `flight_simulator/protocols/flybrain-runway-state.xml` and `flybrain-runway-controls.xml` into `$FG_ROOT/Protocol/`.
2. Start the 737 with the runway protocols. **Autopilot and autothrottle off.** Set flaps 5 for takeoff, or flaps 30 and gear down for landing.

   ```
   --generic=socket,out,20,127.0.0.1,5501,udp,flybrain-runway-state
   --generic=socket,in,20,127.0.0.1,5502,udp,flybrain-runway-controls
   ```

3. **Takeoff:** line up on the runway with the engines running, then:

   ```sh
   .venv/bin/python -m flight_simulator.takeoff_landing takeoff --brain connectome --backend flightgear
   ```

   The first packet's position and heading define the runway frame.

4. **Landing:** start on a stabilised 3° approach about 3 nm out at around 1,000 ft. You must give the threshold position and the runway's true heading:

   ```sh
   .venv/bin/python -m flight_simulator.takeoff_landing landing --brain connectome --backend flightgear \
       --runway LAT LON TRUE_HEADING --approach-throttle 0.55
   ```

FlightGear is frozen (`/sim/freeze/master`) during every brain trial and resumed afterwards. **The FlightGear path has not been flown live yet** (FlightGear isn't installed on the dev machine): the parsing and wire format are unit-tested, but the gains were tuned on the reduced local model. Expect to retune `--approach-throttle`, the VS pitch gain, and the rudder gains against the JSBSim 737. Also check that rudder steers the nosewheel on the ground in the 738-flies model.

## Honest limits

- The local `RunwaySim` is a **reduced point-mass model with rough 737 numbers**, not a validated flight model. Success there is not evidence of performance in FlightGear.
- The `standin` brain is a lookup of the probe table, labelled as not a fly everywhere. It exists for fast tests and as a baseline.
- The decoder gains and zero points are hand-set from the probe table, not fitted. The haltere reflex is a fixed PI loop on pitch rate. It executes the brain's commands but doesn't choose them.
- The brain only sees the world through 7 sensory channels, at 2–4 decisions per second.
