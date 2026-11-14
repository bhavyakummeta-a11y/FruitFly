# Experimental reinforcement learning

Reinforcement learning is opt-in. Ordinary `--brain connectome` remains frozen.
The new learning mode updates existing KC→MBON synapses in the actual connectome;
it does not train a replacement network or tune the conventional flight controller.
This implements an experimental learning mechanism, not demonstrated improvement
in flying. Run the offline experiment before trying learning in FlightGear.

## Local conditioning experiment

```sh
.venv/bin/python -m flight_simulator.train --episodes 4 --trials 3 --output runs/my-conditioning
```

The output directory must be new. The command saves `checkpoint.npz`,
`training.json`, and `results.json` locally, and never pushes logs.

Two artificial cues directly stimulate different sets of 64 KCs at 150 Hz.
The sets are selected for strong existing connectivity to the measured MBON
channels, not inferred from a camera or learned from flight data. After each cue,
a separate reward or punishment pulse stimulates the selected DANs. KC eligibility
comes from the cue trial **before** reinforcement, so dopamine-induced KC spikes
cannot be mistaken for the activity being credited.

Baseline and post-training evaluation disable weight updates, omit reinforcement,
and use identical held-out Poisson RNG seeds on the same two cues. Results include
both MBON rates and Giant Fibre escape rates. A changed weight is not sufficient
evidence of a learned response, and a changed MBON response is not sufficient
evidence of better aircraft control. Zero response changes are reported as zeros.

## Learn during local flight

```sh
.venv/bin/python -m flight_simulator --brain connectome --learn --seconds 180 --save-learning runs/flight-learning.npz --log runs/flight-learning.csv --no-runlog
```

Flight reinforcement rewards forward progress and penalizes close obstacles,
excessive bank, descent, loss of speed, and collision. This is an engineering
reward definition, not a biological measurement. Feedback credits the KC activity
of the preceding neural decision. A new neural decision then uses the updated
weights. No learning happens when eligible KCs or the stimulated DANs are silent.

For FlightGear, append `--backend flightgear`, and retain your existing aircraft
and obstacle-course options. The simulator pauses during both the feedback trial
and the next sensory trial. This is slower than frozen connectome mode. The same
flight-envelope aborts and conventional stabilization still apply. A FlightGear
rendering or stabilization problem is not fixed by switching on learning.

`--no-runlog` keeps these experiments local and bypasses the separately added
automatic run-log publishing feature. CSV logs contain the most recent reward,
measured dopamine firing rate, and count of edges changed by that feedback event.
The checkpoint is saved on normal exit and handled interruption/error. It does
not preserve an interrupted neural trial or protect against abrupt process kills.

## Resume or evaluate learned weights

Resume learning:

```sh
.venv/bin/python -m flight_simulator --brain connectome --learn --load-learning runs/flight-learning.npz --save-learning runs/flight-learning-continued.npz --seconds 180 --no-runlog
```

Evaluate with weight updates disabled:

```sh
.venv/bin/python -m flight_simulator --brain connectome --load-learning runs/flight-learning.npz --seconds 180 --seed 100 --log runs/learned-evaluation.csv --no-runlog
.venv/bin/python -m flight_simulator --brain connectome --seconds 180 --seed 100 --log runs/frozen-evaluation.csv --no-runlog
```

Use identical initial states, obstacle courses, and seeds for the comparison.
Repeat across seeds and unseen courses before concluding performance improved.
Do not compare the training reward alone with an unrelated frozen run.

## Plasticity rule and scope

The initial experimental channel mapping is:

| Reinforcement | Stimulated DAN types | Plastic destination |
|---|---|---|
| Positive | PAM01 | MBON01 |
| Negative | PPL101 | MBON11 |

Only existing connections from annotated `KC*` neurons to those MBONs can change.
The current dataset contains 6,836 such sparse-matrix entries. This is a
cell-type-level compartment approximation. It does not reconstruct dopamine
concentrations at individual synapses, timing-dependent plasticity, or all
mushroom-body compartments. It is not a claim that every PAM/PPL1 neuron has the
same valence in every biological context.

For an eligible KC→MBON connection:

```text
eligibility = clip(KC spikes in preceding decision / 5, 0, 1)
gate = clip(measured DAN Hz / 200, 0, 1) * abs(reinforcement)
factor = max(0.2, factor * (1 - learning_rate * eligibility * gate))
weight = original_weight * factor
```

Default learning rate is 0.1. Both reinforcement types cause depression in their
respective channels, rather than positive reinforcement increasing every weight.
Non-KC→selected-MBON weights, weight signs, topology, and LIF settings remain
unchanged. The 20% floor prevents deletion of trained edges. There is no recovery
rule, so weights can saturate after repeated training. These parameter choices
are experimental and not fitted to physiological measurements.

Checkpoints use non-pickle NPZ files. They store weight factors, sparse indices,
learning parameters, and a SHA256 fingerprint of the initial matrix. Loading a
checkpoint from a different connectome/mask fails before applying weights.
Training resumes weights and learning rate, but restarts the neural RNG sequence
from the requested seed; it is not an exact continuation of the previous flight.

## Why flight improvement is uncertain

The obstacle controller still reads Giant Fibre activity, while the learned
connections are in the mushroom body. Whether those connections influence Giant
Fibre activity enough to affect avoidance is an experimental question. The
flight input encoder also does not guarantee that relevant KCs become active.
The offline synthetic cue assay helps test plasticity separately from these
unresolved sensory and motor connections.

There is no trained steering policy, autonomous takeoff/landing learner, or
validated live FlightGear learning result in this implementation.

## Validation in this checkout

A two-episode targeted-cue experiment with two held-out Poisson seeds changed
3,806 of the 6,836 eligible edges. Weight factors stayed between 0.81 and 1.
Measured mean responses across those two evaluation seeds were:

| Cue and measured channel | Frozen | After training |
|---|---|---|
| Reward cue, MBON01 | 58.75 Hz | 30.00 Hz |
| Punishment cue, MBON11 | 152.50 Hz | 127.50 Hz |

Giant Fibre output stayed at 0 Hz in these cue tests. These results demonstrate
changed mushroom-body responses, not improved flight control. The first random
cue assay had silent readouts, motivating the explicitly targeted synthetic cues.
A two-second local flight integration check successfully ran feedback and saved
a checkpoint, but changed **zero** synapses because eligible KC activity did not
coincide with the selected reinforcement channel. That is reported rather than
substituting fabricated updates.

The eight plasticity/reward/checkpoint unit tests pass. The wider test suite
reported an unrelated existing process-watcher test failure (`watch.code` was
`None` after its subprocess had already been reaped); no learning assertion failed.
Live FlightGear learning has not been tested here.

## Sources

The learning hypothesis follows dopamine-modulated KC→MBON plasticity described
in [Learning with reinforcement prediction errors in a model of the Drosophila
mushroom body](https://www.nature.com/articles/s41467-021-22592-4).
Compartment/type references include the [adult mushroom-body connectome](https://elifesciences.org/articles/62576)
and [FlyBase PAM01 definition](https://flybase.org/cgi-bin/cvreport.pl?childdepth=2&cvterm=FBbt%3A00049932).
These motivate the experimental design, not a claim of a full reproduction.
