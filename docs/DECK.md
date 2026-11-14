# Progress deck and project media

`deck/FruitFly_Progress.pptx` is built from what the project logs. Nobody
edits slides by hand: capture screenshots as you work, annotate them, rebuild.

```sh
python -m flight_simulator.media deck        # rebuild the deck (pulls sim-logs first)
```

## Capturing

| What | How |
|---|---|
| FlightGear, automatically | The media recorder screenshots every live session every 5 s, plus on events (pause/resume, controller start/exit, crash, takeoff, landing). The session's live log page is captured every 30 s. `python -m flight_simulator.media ensure-recorder` starts it; one per machine. |
| FlightGear, a moment you care about | `python -m flight_simulator.media snap --caption "737 rotates at 150 kt"` |
| The live log page | `python -m flight_simulator.media snap --page --caption "..."` |
| An agent at work | `python -m flight_simulator.media snap --window "<terminal title>" --caption "agent finds the freeze bug"` (captures that window even when covered) |
| Anything on screen | `python -m flight_simulator.media snap --screen --caption "..."` |

Images go to the sim-logs branch next to the run they belong to:
`runs/<session>/media/` (pushed when FlightGear exits), or for agent and desktop
snaps `runs/<hour>_<who>_media/` (pushed immediately). Set `FRUITFLY_NO_PUSH=1`
to keep test captures local. Intervals: `FRUITFLY_MEDIA_FG_S`, `FRUITFLY_MEDIA_PAGE_S`.

## Annotating

Raw images are never drawn on. Annotations are rows in `media/index.jsonl` and are
rendered at build time, so they can be added or corrected later:

```sh
python -m flight_simulator.media note latest --caption "Throttle hand-off to the fly" --box 680,640,760,740=throttle
python -m flight_simulator.media render latest      # preview the annotated image
python -m flight_simulator.media list               # recent media
```

Every rendered frame carries a banner with the session name, UTC time and the
telemetry at capture time (altitude, AGL, airspeed, heading, pitch, roll, paused).

## Deck structure

| Section | Slides | Source |
|---|---|---|
| Overview | Title (latest hero frame), pipeline + Rule #1 + goals, how we work (named/logged/pushed/filmed) | `deck/content.json`, counts from logs |
| Flight log | Timeline of every session and run per person; one slide per session with footage or notes (hero frame, stats, note), its GIF time-lapse; small-multiple grids for sessions without footage | sim-logs `runs/` |
| Results | Controller clearance by brain + failures; bugs found by flying (from run notes); cockpit hotspots | `result.json`, `feedback.md`, `cockpit/` |
| Agents along the way | Commits per half hour (Claude co-authored vs human), ticket board, agent snapshots, live page | git log, `tickets.py`, media |
| Next | Next steps | `deck/content.json` |
| Appendix | Run index | sim-logs `runs/` |

Story text lives in `deck/content.json`; layout and theme in `deck/build_deck.js`
(pptxgenjs, installed into `deck/node_modules` on first build). The deck favours
what the logs show: a session gets a full slide once it has screenshots or a note
(`python -m flight_simulator.runlog note "..."`).
