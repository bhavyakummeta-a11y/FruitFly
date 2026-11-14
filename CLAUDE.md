# FruitFly: rules for every agent and teammate

## FlightGear sessions: named, logged, pushed (mandatory)

1. **Every FlightGear session gets a name.** Launch only through the project
   launchers and always pass `--name "<what this session tests>"`:
   - `python flightgear/launch.py --name "..."`
   - `python -m flight_simulator.launch_fg --instance N --name "..."`
   - `flightgear_api/launch_fg.ps1 -Name "..."` (local helper)
   Never start `fgfs.exe` directly. If you must, include
   `--prop:string:/fruitfly/session/name=<name>` in its arguments.
2. **Logging is automatic; do not disable or bypass it.** A watchdog attaches a
   session logger to every `fgfs.exe`. Check with
   `python -m flight_simulator.session status`; if it says the watchdog is not
   running, run `python -m flight_simulator.session ensure-watchdog`.
   A running session that shows as UNNAMED must be named:
   `python -m flight_simulator.session attach --name "..."`.
3. **The session is pushed when FlightGear exits** (sim-logs branch, `runs/`).
   Close FlightGear normally when done so the log is complete; don't kill the
   session logger.
4. Controller runs (`python -m flight_simulator ...`) are logged and pushed
   automatically too. Add feedback with `python -m flight_simulator.runlog note "..."`.
5. When testing the logging code itself, set `FRUITFLY_NO_PUSH=1` so test logs
   are never committed to the shared `sim-logs` branch.
6. Ask the user before opening FlightGear windows; they take over the screen/GPU.

Details: `docs/FLIGHT_SIMULATOR.md` (section "FlightGear sessions").
