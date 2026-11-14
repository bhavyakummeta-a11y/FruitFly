# Small camera-vision prototype

This standalone observer reads FlightGear screenshots and looks for **candidates**:
red or red/pale-banded towers, and pairs of converging white runway-edge lines.
It tracks expansion and lateral motion of the largest matched tower between
recent frames. It draws annotations and proposes looming and left/right sensory
rates for comparison. It never stimulates the brain, sends aircraft commands,
changes the view, pauses the sim, or replaces the synthetic controller inputs.

## Run it

```sh
python -m pip install -r requirements-camera.txt
python -m flight_simulator.camera_vision
```

Use an already running, named FlightGear session with HTTP enabled (the project
launcher uses port 8080). Select a **fixed, unobstructed forward view in daylight**.
Do not move the camera or change zoom during tracking. The observer requests at
most two screenshots per second; screenshot capture can still add simulator load.
Close it with Q or Ctrl-C. `--httpd 8090` selects another instance.

It receives the existing synthetic cue stream on UDP 5601 for a side-by-side
readout and saves annotations plus `observations.jsonl` under `runs/camera-<time>`.
Only one viewer can bind that port: close `vision_view` first, or use
`--synthetic-port 0` to run without comparison. For another port, set the same
value on the controller's `--vision-port` and this observer's `--synthetic-port`.
Synthetic telemetry older than two seconds is marked unavailable. Comparison is
approximate by receipt time, not frame-synchronized ground truth.

If the cockpit blocks the view, select a forward camera without the cockpit or
crop it using normalized `--roi X Y W H`, for example `--roi 0 0 1 0.6` to retain
the top 60%. Cropping cannot recover an occluded runway. Reported runway offset
is relative to the **crop's image center**, not a calibrated aircraft heading.

Analyze a saved screenshot without opening any windows:

```sh
python -m flight_simulator.camera_vision --image screenshot.jpg --headless --output runs/camera-check
```

Use `--headless --seconds 60` for a bounded live recording. The observer only
performs HTTP screenshot GETs and receives comparison UDP packets.

## Scope and limits

- Color/shape checks recognize the project's distinctive tower appearance, not
  arbitrary objects. Shadows, red scenery, occlusion and lighting can fool them.
- Runway candidates use white-line convergence, not an airport database or a
  trained recognizer. Roads, markings and cockpit edges can create false positives.
- Expansion requires a recent overlapping match; missing/old/new-object frames
  produce `null`/unknown, not a fabricated safe value. Apparent growth is not a
  calibrated distance or time-to-collision measurement. Camera motion can mimic it.
- Candidate neural inputs are logged/displayed only. Image processing performs
  recognition; this does not show that the fly recognizes pixels.
- No model training, downloads of detector weights, or control integration is added.

Validation covers blank frames, white-line runway geometry, round/elongated red
eye rejection, banded towers, matching and stale-frame rejection, and cropping.
A saved team screenshot (2026-11-14, `fg-172827-012.jpg`) marked the visible tower
at x=809, y=308, width=53, height=66 and rejected the cockpit fly's red eyes. No
runway was reported in that airborne frame. Runway checks use generated fixtures;
reliable runway detection in live FlightGear remains unverified. No FlightGear
window was opened during development.

Implementation uses OpenCV color masks and its
[probabilistic Hough line transform](https://docs.opencv.org/4.x/d9/db0/tutorial_hough_lines.html).
