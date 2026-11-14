# Takeoff fly and Landing fly: three plans each, and the pick

Scope: the two **main** phases from the [project plan](PROJECT_PLAN.md): the **Takeoff fly** (milestone 4, the pivot deliverable) and the **Landing fly** (milestone 6). Cruise and the barrel roll are out of scope. The sim is FlightGear (the current MVP), and everything goes through the same interface MSFS will use later.

Rule we keep: **the connectome is the controller.** We use Shiu's LIF settings and `Connectivity_783` signs. Stimulators only turn sim state into sense rates (0–200 Hz, clipped at about 2σ), and decoders only turn firing rates into controls. Neither one does the flying.

---

## 1. The biology we're borrowing

A real fly has two opposite looming reflexes, and which one fires depends on what it is doing:

| Fly state | Stimulus | Descending neurons | Behaviour |
|---|---|---|---|
| **Standing** | looming (LC4, LPLC2) | Giant Fibre **DNp01** (fast) plus non-GF escape DNs **DNp02, DNp04, DNp11** (slower, controlled) | **jump into the air: takeoff** |
| **Flying** | looming (LC4, LPLC2) | **DNp07, DNp10** | **extend the legs: landing** |

That's Ache et al. 2019 (*Nat Neurosci*, "State-dependent decoupling of sensory and motor circuits…"). The state switch happens **downstream of the brain, in the nerve cord**. FlyWire has no nerve cord, so in our model **the decoder plays the nerve cord's state gate**. That's biologically honest, because the brain really does see both pathways light up.

That gives us our two brains:

- **Takeoff fly = a standing fly.** As the plane nears Vr, something looms, the fly jumps, and the plane rotates.
- **Landing fly = a flying fly.** The runway rushes up, the fly extends its legs, and the plane flares.

They get the same stimulus and do opposite things, depending on the brain's state. That's the headline of the demo.

Other circuits we use, all checked to exist in the FlyWire 783 annotations:

| Circuit | Cell types (count in FlyWire) | Senses / does |
|---|---|---|
| Lobula plate tangential cells | HSE/HSN/HSS (yaw), VS1–VS8 (roll and pitch) | self-rotation optic flow |
| Ocelli | ocellar + OCG/OCC interneurons | horizon and pitch attitude |
| Translational-flow columnar cells | LPC1 (164), LLPC1 (219) | front-to-back ground flow. Linked to speed regulation in walking (Isaacson et al. 2023), but this needs checking in our probes |
| Looming | LC4 (104), LPLC2 (210) | approaching object or surface |
| Steering DNs | DNa01, DNa02 (2 each, L/R) | turn left or right |
| Flight power DNs | DNg02_a–h (~27) | wingbeat amplitude, i.e. thrust |
| Walk DNs (current MVP) | DNp09 (forward), MDN (backward, 4) | advance or back off |
| Taste (validated in the handbook) | sugar LB3c (32), bitter | good / bad |

---

## 2. What "two different brains" means: three options

| | Option | Verdict |
|---|---|---|
| **B1** | **One connectome (FlyWire 783), two configured instances.** Each brain gets its own stimulator rig, its own readout, and its own nerve-cord state gate (standing vs flying). Both share the sparse `W` in memory. | ✅ **Pick.** It matches the biology (same brain, different state), keeps Shiu's validated signs, and reuses the MVP code. |
| B2 | Two connectomes: Takeoff on **BANC** (brain plus nerve cord, so we can read the real jump muscle TTMn), Landing on FlyWire. | ⏩ **Reach.** Port the Takeoff fly to BANC once B1 works, to show the "jump" reaching the body. Its signs aren't pre-applied like Shiu's, so it's a real risk for the main path. |
| B3 | Female (FlyWire) vs male (Male CNS). | ❌ No flight reason to do it, and its transmitters are predicted only. |

---

## 3. Takeoff fly: three plans

### T-A: Trigger fly (the brain decides *when*)

A conventional controller flies the takeoff. The brain only fires three switches: **go** (sugar → DNp09), **rotate** (looming → GF spike at Vr), and **reject** (bitter → MDN).

- ➕ Fastest to build. Each decision is a single yes/no, so latency hardly matters.
- ➖ The autopilot does the flying, which breaks "the encoder/decoder doesn't fly". This is option A from the concept notes.

### T-B: Taste fly (handbook-native valence)

Every control error becomes good or bad. On-profile maps to **sugar** and off-profile to **bitter**, one push-pull pair per axis, read from the validated outputs: MN9 means commit, DNp09 vs MDN gives throttle, and GF means abort.

- ➕ Uses only circuits that pass the handbook sanity checks. Lowest neural risk.
- ➖ The meaning is arbitrary: taste has nothing to do with pitch. There are only about 4 validated outputs, so the axes have to share them through separate sub-runs, which multiplies latency.

### T-C: Escape-jump fly (ethological) ⭐

The fly's real takeoff circuit does the plane's takeoff.

| Sim signal (FlightGear) | Stimulator | Why |
|---|---|---|
| Airspeed progress, `IAS / Vr` (Vr ≈ 55 KIAS) | **sugar** LB3c, 0–200 Hz | "good, keep going" (MVP path) |
| Centerline offset + yaw rate | **HS cells** L vs R, push-pull | yaw optic flow |
| Pitch error vs target attitude (0° on the ground, ~8° after liftoff) | **VS cells** (+ ocelli) | pitch optic flow / horizon |
| `IAS` from Vr−5 to Vr | **LC4/LPLC2 looming**, ramping rate | *the stimulus that makes a standing fly jump* |
| Reject conditions (off centerline > 5 m, low RPM, short runway) | **bitter** | bad, back off |

| Readout | Control |
|---|---|
| DNp09 − MDN | throttle (unchanged from the MVP) |
| DNa01/DNa02, L − R | rudder and nosewheel |
| DNp02 + DNp04 + DNp11 rate; a DNp01 spike means firm rotation | **elevator pitch-up: the rotation is the jump** |
| VS-driven DN, picked in the probe step | climb pitch hold after liftoff |
| MDN sustained on the ground | reject: idle and brakes |
| **Nerve-cord gate (standing)** | escape DNs drive rotation only while on the ground. After liftoff they're ignored, and the fly hands over at 500 ft AGL |

- ➕ The most faithful to the biology (rotating is jumping), it demos best, and it extends the MVP's throttle path.
- ➖ The DN directions for steering and pitch are still unproven (milestone 3), and the escape DNs might be too spiky to give a smooth rotation. Mitigation: low-pass the rate over 2–3 decisions.

### Takeoff scorecard (1–5, higher is better)

| | Bio fidelity | Brain really flies | Tech risk (5 = low) | Build time (5 = short) | Demo value | Total |
|---|---|---|---|---|---|---|
| T-A Trigger | 2 | 1 | 5 | 5 | 2 | 15 |
| T-B Taste | 3 | 4 | 4 | 3 | 3 | 17 |
| **T-C Escape-jump** | **5** | **4** | 3 | 3 | **5** | **20** |

**Pick: T-C, with T-B as a per-channel fallback.** If a probe shows that a flight channel is weak (say, HS → DNa asymmetry doesn't separate cleanly), we swap only that axis to sugar/bitter → DNp09/MDN and write it up. T-A stays as the "dumb baseline" comparison, not a deliverable.

---

## 4. Landing fly: three plans

### L-A: Trigger fly

An autopilot flies the ILS. The brain only picks **flare now** (looming → DNp07/DNp10) and **go around** (bitter → MDN).

- ➕ Easiest, and latency barely matters.
- ➖ Same problem as T-A: the brain is just a timer.

### L-B: Taste fly ("land on the food")

Being on the glideslope and centerline maps to **sugar**, deviation to **bitter**. **MN9** means commit to touchdown (a fly lands, then extends its proboscis to eat), **MDN** means go around, and **GF** means abort.

- ➕ Validated circuits, and a cute story.
- ➖ The flare has no natural trigger: taste has no time-to-contact. Same output bottleneck as T-B.

### L-C: Flying-fly landing (ethological) ⭐

| Sim signal | Stimulator | Why |
|---|---|---|
| Glideslope deviation (dots) | **VS cells** push-pull | pitch optic flow |
| Localizer / centerline | **HS cells** L vs R | yaw optic flow |
| Speed vs Vref (≈ 65 KIAS) | **sugar** near Vref / **bitter** off it. *Stretch:* ventral flow `GS/AGL` → **LPC1/LLPC1** | speed regulation. LPC1 is the biological channel, but only if the probe confirms it |
| Time-to-contact `τ = AGL / sink rate`, below ~4 s | **LPLC2/LC4 looming**, rate ∝ 1/τ | *the runway rushing up: the cue that makes a flying fly land* |
| Unstable approach (>1 dot, sink >1000 fpm below 500 ft, speed ±10 kt) | **bitter** | bad |

| Readout | Control |
|---|---|
| DNp09 − MDN (or DNg02) | throttle |
| VS-driven DN, from the probe | elevator to track the glideslope |
| DNa01/DNa02, L − R | aileron and rudder |
| **DNp07 + DNp10** | **flare: pitch up, throttle to idle (the leg extension)** |
| MDN sustained + bitter high | **go around** (back off) |
| DNp01 (Giant Fibre) | **logged only.** *Nerve-cord gate (flying):* a flying fly decouples the jump, so the GF never acts here |

- ➕ The flare is a real fly reflex rather than a scripted height. It's a mirror of T-C: same looming, opposite behaviour. Using MDN for go-around matches what MDN does biologically.
- ➖ Flare timing is unforgiving, and per-decision latency hurts most here. Mitigation: freeze the sim per decision (`/sim/freeze/master`), start from long shallow approaches (3 nm, 1000 ft), and feed τ in early so DNp07/10 ramp rather than snap.

### Landing scorecard

| | Bio fidelity | Brain really flies | Tech risk (5 = low) | Build time (5 = short) | Demo value | Total |
|---|---|---|---|---|---|---|
| L-A Trigger | 2 | 1 | 5 | 5 | 2 | 15 |
| L-B Taste | 3 | 3 | 4 | 3 | 3 | 16 |
| **L-C Flying-fly** | **5** | **4** | 2 | 3 | **5** | **19** |

**Pick: L-C, with L-B as a per-channel fallback.** Speed starts on sugar/bitter, and LPC1 optic flow replaces it only if the probes back it up.

---

## 5. How we prove it's the fly flying (lesion controls)

These are cheap to run with the notebook's lesion trick (`keep[idx] = 0`), and each one should break exactly one behaviour:

| Lesion | Expected break |
|---|---|
| Silence LC4 + LPLC2 in the Takeoff fly | no rotation: the plane runs down the runway |
| Silence LPLC2 + LC4 in the Landing fly | no flare: the plane flies flat into the ground |
| Silence the HS cells | the plane drifts off the centerline |
| Shuffle `W` (keeping its degree distribution) | everything breaks |

We compare each fly against a **fixed-gain PID baseline** on the same scenario: touchdown point, centerline error and peak sink rate.

---

## 6. Build order

| # | Step | Done when |
|---|---|---|
| 0 | **Probe table** (milestone 3, open loop): drive each stimulator above at 0/50/100/200 Hz and record DNp01/02/04/07/09/10/11, MDN, DNa01/02 L/R and DNg02 | Looming → DNp02/04/11 and DNp07/10 respond. HS left vs right → opposite DNa sign. One VS → DN pick for pitch |
| 1 | **Speed:** prune to the sub-network within 3 hops of the stimulators and readouts, then time one 200 ms decision | ≤ 1 s per decision on CPU, or move to Colab/Modal |
| 2 | **Takeoff fly T-C** in FlightGear, frozen per decision | Repeatable takeoff to 500 ft AGL, ±5 m centerline, 5/5 runs. Lesion LC4/LPLC2 → no rotation |
| 3 | **Landing fly L-C** from 3 nm / 1000 ft | Touchdown in the zone, sink < 500 fpm, 3/5 runs. Go-around fires on a deliberately unstable approach. Lesion → no flare |
| 4 | Handover: Takeoff fly → (scripted cruise for now) → Landing fly | One full run, filmed with a neuron-activity panel |
| 5 | Reach: Takeoff fly on **BANC**, reading the TTMn jump muscle | TTMn spikes at rotation |

**Biggest risk:** step 0 finds no clean pitch DN. In that case pitch alone falls back to a **documented linear readout** over the ~1,300 DNs (a readout fit, not brain training), and everything else stays as above.
