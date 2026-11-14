# Fruit Fly Hackday Handbook

Someone mapped every neuron and synapse in a fruit fly's brain. If you simulate each neuron as a simple spiking unit and wire them up exactly as the map says, the fly's circuits just work:

- Sugar on the mouth makes the feeding neuron fire.
- A looming shadow makes the escape neuron fire.

No training. **The wiring is the model.** Your job:

1. Turn your problem's signals into stimulation of the fly's senses.
2. Read the answer off neurons with known behaviours.

> **The rule:** if your problem can't be phrased as "this tastes good / bad / looms at me" → "eat / back off / flee", a fly brain is the wrong tool.

Let Claude write the code. This doc is the ideas, the gotchas, and where to get things.

## Files in this repo

| File | What |
|---|---|
| [`fly_brain_starter.ipynb`](fly_brain_starter.ipynb) | Hack-day starter notebook: load the brain, view a neuron, run the LIF simulator, poke it with sugar / bitter / looming. Opens in Colab. |
| [`docs/Fly-Brain Handbook + Resources.docx`](docs/) | Original Word version of this handbook |

---

## Resources

### Data

| What | Where | Notes |
|---|---|---|
| FlyWire, the whole female brain (139k neurons) | https://flywire.ai/ | The dataset the hack-day notebook uses (via fafbseg) |
| FlyWire Codex: search neurons, bulk downloads | https://codex.flywire.ai/ | Look up cell types (MN9, DNp01…) to get their IDs |
| FlyWire API token | https://global.daf-apis.com/auth/api/v1/create_token | Needed for fafbseg. **Keep it out of your repo.** |
| fafbseg docs | https://fafbseg-py.readthedocs.io/ | `search_annotations`, `get_connectivity`, `get_adjacency`, `get_transmitter_predictions` |
| Shiu's whole-brain model plus ready-to-simulate wiring | https://github.com/philshiu/Drosophila_brain_model | Easiest start. `Connectivity_783.parquet` holds every connection with +/− already applied. No token. |
| BANC: brain plus nerve cord (169k neurons) | https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/7WTH1N | Adds the body side: jump muscle, legs |
| Male CNS: whole male brain plus nerve cord | https://male-cns.janelia.org/ | Newest (v1.0, June 2026). Adds courtship circuits. Transmitters are predicted only. |
| MANC, Hemibrain, neuPrint browser | https://neuprint.janelia.org/ | Older or partial datasets |

### Papers

- Shiu et al. 2024, the brain model you're reproducing: https://www.nature.com/articles/s41586-024-07763-9
- FlyWire 2024, the connectome itself: https://www.nature.com/articles/s41586-024-07558-y

### Bodies and visuals

- **flybody**, a MuJoCo physics-simulated fly body (legs, wings) to animate what your brain decides: https://github.com/TuragaLab/flybody
- **navis + plotly** (already in the notebook) give 3D neuron renders

### Compute

- A laptop CPU is enough to run the model. One decision takes a few seconds on the full brain.
- Google Colab, with free T4 GPUs: https://colab.research.google.com/
- Modal: https://modal.com/. $30/month free credit once you add a card (it doesn't charge you), so any GPU you want.

You only need a GPU if you want decisions faster than about 1 per second, thousands of runs, or to train the synapses (which kind of defeats the point).

---

## The model in one paragraph

Each neuron is **leaky integrate-and-fire (LIF)**: voltage leaks toward rest, incoming spikes nudge it up or down, and crossing threshold fires a spike. Each connection's weight is its synapse count times +1 or −1.

- **Excitatory or inhibitory:** GABA, glutamate and histamine inhibit; acetylcholine excites.
- **Stimulating a sense:** drive its neurons with random spikes at a chosen rate (0–200 Hz).
- **Reading the output:** measure how fast the output neurons fire.
- **Settings:** use Shiu's exactly. Tell Claude "port Shiu's LIF model to numpy" and point it at his repo.

| Parameter | Value |
|---|---|
| Resting potential | −52 mV |
| Threshold | −45 mV |
| Membrane time constant | 20 ms |
| Synaptic time constant | 5 ms |
| Refractory period | 2.2 ms |
| Synaptic delay | 1.8 ms |
| Weight per synapse | 0.275 mV |
| Time step | 0.1 ms |

## Senses you can plug into

| Sense | Means | Status |
|---|---|---|
| Sugar taste (mouth) | good, approach | ✅ solid |
| Bitter taste (mouth) | bad, suppresses eating | ✅ solid |
| Leg taste (BANC only) | slower good/bad context | ✅ works |
| Looming vision (LC4, LPLC2) | threat, sudden change | ✅ solid, triggers escape |
| Smell, wind | — | ⚠️ tends to seize: everything fires forever. Skip at first. |

## Outputs you can read

| Neuron | Behaviour | Use as |
|---|---|---|
| MN9 | extend the mouth, eat | how much to go for it (rate) |
| Giant Fibre (DNp01) | escape jump | bail now (any spike, overrides everything) |
| MDN | walk backwards | back off |
| DNp09 | walk forward | advance |
| TTMn (BANC only) | jump muscle | proof the escape reached the body |
| ~1,300 descending neurons | every brain-to-body command | fit a decoder if you want something unbiased |

---

## Gotchas that will bite you

**Signs make or break it.** One inhibitory neuron mislabelled as excitatory and a whole region seizes. Use Shiu's file or human-verified transmitters, not raw predictions.

**Sanity-check before building anything:**

- [ ] No input → silence.
- [ ] Sugar → MN9 fires (~50 Hz).
- [ ] Sugar + bitter → MN9 drops a lot.
- [ ] Looming → Giant Fibre fires.
- [ ] Silence the Giant Fibre → no escape.
- [ ] Stop the input → activity dies out.

If any of these fail, your wiring is wrong, not your idea.

**Reset between decisions.** Run 100–200 ms of brain time from rest each time. If you need memory, feed it back in as an input.

**Clip your inputs** at about 2 standard deviations so one outlier doesn't max out a sense.

**Compare against a dumb baseline.** The fly is a weird fixed filter, not an optimiser.

---

## Project ideas

| Idea | In → Out |
|---|---|
| Trading bot (built: crypto) | 3-candle price momentum → sugar/bitter; crash → looming. MN9 = position size; Giant Fibre = sell all. Lost money, but less than holding. |
| Robot or drone dodging | expanding blob in the camera → looming → Giant Fibre → swerve |
| Game agent | food → sugar, hazard → bitter/looming. MN9 approach, Giant Fibre dodge, MDN retreat |
| Uptime / anomaly pager | metric spike → looming; Giant Fibre = page someone |
| Fly in a body | wire brain outputs into flybody and watch it walk, eat or jump in MuJoCo |
| Lesion lab | silence any cell type and see what breaks. This is the real science use. |
| Male vs female | same stimulus on FlyWire vs the Male CNS. What differs? |

*A **candle** in trading is one bar on a price chart: open, high, low and close over 5 minutes, an hour, and so on.*
