# Project: Fly Brains Fly a Plane

Use simulated fruit fly brains (connectome LIF model, see the [handbook](../README.md)) to control an aircraft in **Microsoft Flight Simulator**.

## Current MVP (as of 2026-11-14)

> **1. Get FlightGear working. 2. Have the fly make the airplane go forward.**

We start in **FlightGear** (free, scriptable) rather than waiting on MSFS access. MSFS stays the eventual target.

| Step | What | Done when |
|---|---|---|
| **A. FlightGear running** | Install FlightGear, load the **Boeing 737-800** (`python flightgear/setup_aircraft.py` then `python flightgear/launch.py`, see [Aircraft](AIRCRAFT.md)) on a runway, and talk to it from Python through FlightGear's property server (`--telnet` or `--httpd`). | Python can read `/velocities/groundspeed-kt` and set `/controls/engines/engine[0]/throttle` and `engine[1]/throttle`. |
| **B. Fly goes forward** | Run the fly brain and read **DNp09** (walk forward → more throttle) and **MDN** (walk backward → less throttle), as mapped in [the concept notes](notes/FLY_BRAIN_AIRPLANE_CONCEPT.md). Write the result to both engines' throttles. | Stimulating the fly makes the plane roll forward along the runway, and taking the stimulus away makes it slow down. |

Out of scope for the MVP: steering, rotation, takeoff, MSFS, and dopamine learning. Those follow in the milestones below.

## Goals

| Tier | Goal |
|---|---|
| **Pivot / minimum** | One fly that **takes off**. |
| **Main** | Three flies, one per flight phase: **Takeoff fly**, **Cruise fly** (normal flight), **Landing fly**. |
| **Reach** | A fly that does a **barrel roll** (probably the Cruise fly). |
| **Reach** | Learning through the fly's own **dopamine** system, with both positive and negative reinforcement. |

## Principle: honor the fly brain

The fly brain is the controller. We do not swap it for a standard neural net.

- Keep the connectome wiring and Shiu's LIF parameters. Do not train weights with backprop.
- Only change the brain the way a real fly's brain changes: dopamine-gated plasticity in the **mushroom body** (below).
- Any code outside the brain stays thin and inspectable. It encodes sim state into sensory input rates, and decodes neuron firing rates into stick, throttle and rudder. If the encoder or decoder starts doing the flying, we've broken the rule.
- Always compare against a dumb baseline, such as a fixed-gain autopilot or random inputs.

## Architecture

```
MSFS ──SimConnect──► state (pitch, roll, airspeed, altitude, VS, …)
                          │  encoder (clip ~2σ, map to rates 0–200 Hz)
                          ▼
              ┌───────────────────────┐
  phase ────► │ Takeoff / Cruise /    │  one brain sim per phase,
  selector    │ Landing fly (LIF)     │  100–200 ms brain time per decision,
              └───────────────────────┘  reset from rest each time
                          │  decoder (firing rates → controls)
                          ▼
MSFS ◄──SimConnect── elevator, ailerons, rudder, throttle, flaps, gear
                          ▲
       reward/punishment ─┘─► dopamine neurons (PAM = reward, PPL1 = punishment)
                              → adjust Kenyon cell → MBON weights between episodes
```

### Why flight is a reasonable fit (sensing)

The handbook rule says a problem must look like "tastes good / bad / looms" → "eat / back off / flee". Flight control stretches that, but the fly's own visual flight-stabilisation circuitry helps:

- **Roll and yaw sensing.** The lobula plate tangential cells already encode self-rotation: **VS cells** respond to roll and pitch, **HS cells** to yaw. We can drive them from the aircraft's attitude rates, which is the natural input for a barrel roll.
- **Threats.** Looming (LC4, LPLC2) maps to ground or obstacle approach, stall warning, or a hard landing. The Giant Fibre (DNp01) then acts as an abort or go-around trigger.
- **Good and bad.** Sugar and bitter map to "on profile" and "off profile" signals, such as being on the glideslope or at the target airspeed.

### Reading outputs (motor)

The FlyWire brain has no nerve cord, so we read **descending neurons**:

- Use the steering and flight-power descending neurons, for example the DNa/DNb steering types and DNg02, which is linked to wingbeat amplitude. These map naturally onto aileron or rudder and throttle.
- MN9, MDN and DNp09 are less natural for flight. We could still use them as abstract "go, back off, advance" channels, such as more or less throttle.
- Fallback: fit a small **linear** readout over the ~1,300 descending neurons. That's a readout fit, not brain training, so we should document it honestly.

## Learning with dopamine (reach goal)

Real flies learn in the mushroom body. Kenyon cells (KCs) represent the situation, mushroom body output neurons (MBONs) bias behaviour, and dopamine neurons (DANs) change the KC→MBON synapses:

- **PAM** DANs signal reward, for example climbing cleanly at the target pitch.
- **PPL1** DANs signal punishment, for example a stall, tail strike or bank overshoot.
- Rule: when a KC was active and its compartment's DAN fires, weaken that KC→MBON synapse. This is roughly how real fly learning depresses synapses.

Plan:

1. Score each episode or step with a reward and a punishment from the sim.
2. Drive PAM or PPL1 neurons at a rate proportional to the reward or punishment.
3. Apply the plasticity rule **only** to KC→MBON synapses, between decisions.
4. Leave everything else in the connectome fixed.

## Milestones

1. **Brain runs.** Port Shiu's LIF model to numpy and pass the handbook sanity checks: silence, sugar→MN9, sugar+bitter, looming→GF, GF silenced, input off.
2. **Sim I/O.** Read state and write controls through SimConnect. While waiting for MSFS access, develop against a stub or fallback sim (see below).
3. **Open-loop probes.** Drive VS and HS cells with fake roll and yaw. Find which descending neurons respond, and in which direction.
4. **Takeoff fly.** Close the loop for throttle-up, rotate at Vr, and hold a climb pitch. Compare against the baseline. *This is the pivot deliverable.*
5. **Cruise fly.** Wings level and altitude hold, then barrel roll.
6. **Landing fly.** Glideslope and flare, with looming → Giant Fibre as go-around.
7. **Dopamine learning** layered on top of whichever flies work.

## Integration notes

- **MSFS** exposes state and controls through **SimConnect**, Windows only. The Python `SimConnect` package wraps it.
- **Decision rate.** One full-brain decision takes a few seconds on a CPU (see the handbook). A plane needs control updates at roughly 5 Hz or faster, so we will likely need:
  - a GPU (Colab or Modal), or
  - a pruned sub-network containing only the relevant circuits, or
  - running the sim paused or slowed between decisions.
- **Pivot sims** if MSFS access is delayed: FlightGear (free), or X-Plane (with its UDP API).

## Open questions

- [ ] MSFS access: which version, and which machine runs it?
- [x] Which aircraft? **Boeing 737-800** (`738-flies`), decided 2026-11-14 and now the default everywhere. We want a big airliner with a cabin we can fill with fly passengers. See [Aircraft](AIRCRAFT.md).
- [ ] Phase switching: a simple rule-based selector based on altitude, airspeed and gear state?
- [ ] Which descending neurons give a clean left/right and up/down? This is answered in milestone 3.
- [ ] How do we show the result? A live MSFS view plus a neuron-activity panel?
