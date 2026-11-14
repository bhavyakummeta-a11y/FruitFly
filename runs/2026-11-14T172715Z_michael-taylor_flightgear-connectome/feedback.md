# 2026-11-14T172715Z_michael-taylor_flightgear-connectome

Run by Michael Taylor. Command: `python -m flight_simulator --backend flightgear --brain connectome --seconds 90 --note 'latest a49150c; CONNECTOME fly brain; 738-flies in-air'`

| | |
|---|---|
| Outcome | error |
| Backend / brain | flightgear / connectome |
| Elapsed | ? s |
| Min clearance | ? m |
| Min altitude | ? m |
| Avoidance activations | ? |
| Code | a49150ccd on main |
| FlightGear | 2024.1.4, 738-flies, 771 warning lines |

## Notes

- latest a49150c; CONNECTOME fly brain; 738-flies in-air
- **Michael Taylor** (2026-11-14 12:29): CONNECTOME obstacle run, latest a49150c. Fly brain took over cleanly (737 AP handover OK, towers placed, pause/resume per trial working). At t=25.8 s escape DNs were at 47.5 Hz as Tower A loomed. Then fgfs crashed with 0xC0000005 (access violation) at 148 s sim-log time, mid pause/resume cycle; no Nasal error. ~10 HTTP req/s at the time (session logger + media recorder + cockpit fly pilot), /screenshot every 10-20 s (last 12 s before crash). Cause not determined.

<!-- add feedback: python -m flight_simulator.runlog note "..." -->
