# Recording a fly-brain run (and keeping FlightGear alive)

How to get a video of a run that shows FlightGear and the fly's live panel side by side,
at a speed the fly brain can keep up with, plus the tools for when FlightGear crashes.

## One recorded takeoff to 2,000 ft

```sh
# 1. FlightGear on the runway (waits its turn in the sim queue)
python -m flight_simulator.launch_fg --phase takeoff --weather clear --name "takeoff to 2000 ft, recorded"

# 2. Once it has loaded: the fly brain flies, at half speed, recorded, stopping at 2,000 ft
#    (bash; in PowerShell use $env:FRUITFLY_SIM_SPEED = "0.5")
FRUITFLY_SIM_SPEED=0.5 python -m flight_simulator.takeoff_live takeoff --brain connectome \
    --backend flightgear --stop-at-ft 2000 --screen-record
```

Use the project venv for the connectome (`.venv\Scripts\python`). Keep the default decision
period (0.25 s). `launch_fg --fly` passes `--period 1.0`; at one decision per second the takeoff
fly's steering lags, it drifts more than 8 m off the centerline at ~120 kt and correctly rejects
the takeoff.

## What each piece does

| Piece | What it does |
|---|---|
| Panel layout (`dock.py`) | FlightGear takes the left 75% of the screen, full height; the Log / Fly brain panel sits to its right, so one capture shows both. |
| `--screen-record` (`screen_record.py`) | Records the desktop with the ffmpeg bundled by `imageio-ffmpeg` (`pip install imageio-ffmpeg`, no admin): H.264, 30 fps. Saved to `%LOCALAPPDATA%\FruitFly\videos\screen_<UTC>_<name>.mp4`, or `FRUITFLY_SCREEN_DIR`. Local only, never committed. |
| Sidecar `<video>.json` | `started_utc` (ms), `fps`, `width`, `height`, `region`, `session_id`, so `demo_cut.py` can line the video up with `events.log` / `airplane.csv`. |
| `FRUITFLY_SIM_SPEED` (`SpeedLock`) | Locks FlightGear's `/sim/speed-up`: 1x by default, `0.5` = half speed, so the brain gets twice the sim time per decision. Allowed 0.1–1, never faster than real time, never a pause per brain trial. The video then plays in slow motion. |
| `--stop-at-ft N` (`takeoff_live`) | Ends the run once airborne at N ft AGL, like Ctrl-C: the result is saved and FlightGear is paused with the surfaces centred. |
| Sim queue (`sim_queue.py`) | One FlightGear at a time. Launchers wait their turn; `python -m flight_simulator.sim_queue status`. |

FlightGear's own session video (session.py) films only the 3D view. For a screen-recorded
run, set `FRUITFLY_NO_VIDEO=1` for the session logger so it doesn't encode a second video.

## When FlightGear crashes

```sh
python -m flight_simulator.fg_crashes        # crashes grouped by fault site, matched to sessions
```

FlightGear writes a minidump for every crash (`%APPDATA%\flightgear.org\sentry_db\reports`).
The tool reads the faulting module and offset. The same offset across runs means the same bug.
Found so far (2026-11-14):

| Fault site | When | Notes |
|---|---|---|
| `fgfs.exe+0x5adea5`, access violation | mid-flight, **obstacle runs only**, 15–60 s after the handover | Suspect: the tornado threat-glow updates. Test with `python -m flight_simulator ... --no-threat-glow`. |
| `fgfs.exe+0x95b329`, access violation | during startup (takeoff launches) | Intermittent; no controller attached yet. |
| `ntdll.dll` heap corruption (0xC0000374) | when FlightGear closes | Harmless for data: the run has already been saved. |

To rule out the media recorder's FlightGear screenshots in a session, start FlightGear with
`--prop:bool:/fruitfly/no-screenshots=true` (`launch_fg ... -- --prop:bool:/fruitfly/no-screenshots=true`).
