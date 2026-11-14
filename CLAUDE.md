# FruitFly: rules for every agent and teammate

## No autopilot, ever (mandatory)

**The fly never uses the airplane's autopilot or autothrottle**, on any aircraft
(737 CMD A/B and A/T, C172 KAP140, FlightGear's generic `/autopilot/locks`).
- Never write code, launch flags or protocols that engage an autopilot, and
  never add an override. The 737's in-air start may hold the plane on its
  autopilot only until the handover; from then on it is locked out.
- It is enforced in the sim (`fruitfly.nas` forces it off and counts
  `/fruitfly/autopilot/violations`), in the controllers (`AutopilotGuard` in
  `flight_simulator/flightgear.py`: no telnet → no flying; autopilot on → forced
  off; can't turn off → run stops) and by `tests/test_no_autopilot.py`.
- Don't weaken or bypass any of the three. A design that needs the autopilot
  (e.g. "autopilot flies the ILS") is out: ask the user instead.

## Ticket board: claim work before you start (mandatory)

Several agents work in this repo at once, across checkouts and worktrees
(`FruitFly`, `FruitFly-obst`, ...). `tickets.py` keeps ONE machine-wide board
(`%LOCALAPPDATA%\FruitFly\board.db`, never committed) that makes sure two
agents never work on the same thing, or edit the same files, at the same time.
From a checkout whose branch predates `tickets.py`, run the main copy:
`python C:\Users\micha\FruitFly\tickets.py ...`.

1. **Name yourself** once per shell: `$env:FRUITFLY_AGENT = "<session name>"`
   (bash: `export FRUITFLY_AGENT=...`), or pass `--agent` on every call.
2. **Before starting a task:** `python tickets.py list`, then either
   `python tickets.py claim <id>` or
   `python tickets.py start "<task>" --paths <files/dirs you will edit>`.
   Exit code 3 (`BLOCKED`) means another agent holds it: pick other work or
   ask the user. Never work around a block, and never `--force` without the
   user's OK.
3. **Before editing a file outside your claimed paths:**
   `python tickets.py check <path>`; exit 1 means someone else holds it.
4. **While working:** `python tickets.py renew` at least every 30 min (claims
   go stale after 60 min without a renew, and another agent may take over).
5. **When finished:** `python tickets.py done <id> --note "<commit/result>"`,
   or `release <id>` if you stop without finishing.
6. Still commit with explicit pathspecs only: the board prevents overlap, it
   doesn't make `git add -A` safe.

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
