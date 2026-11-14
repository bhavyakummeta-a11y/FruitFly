# Aircraft: Boeing 737-800

**Decided 2026-11-14.** The project flies a **Boeing 737-800** in FlightGear. The Cessna 172 used for the first tests is now only a fallback for debugging.

## Why the 737-800

- **A big plane.** It is a real airliner with about 160–189 seats, not a 4-seat trainer.
- **Fly passengers.** We want to render the passenger cabin and seat fruit flies in it for the demo.
- **Flyable.** It is common, has a well-tested JSBSim flight model, and is easier to get off the ground than a wide-body like the 777 or 747.

Alternatives we considered: the CRJ700 (smaller and more forgiving), the Q400 (a slow, gentle propeller plane), and the 777, 747 and A380 (too heavy for a fly-brain takeoff).

## Getting it into FlightGear

Everything lives in [`flightgear/`](../flightgear/README.md):

```
python flightgear/setup_aircraft.py   # downloads the stock FGAddon 737-800 (package id 738) + installs our overlay
python flightgear/launch.py           # KSFO 28R, telnet 5500, httpd 8080
```

Aircraft IDs: `738-flies` is ours, with the cabin and fly passengers. `738` is the stock plane.

## What changes from the Cessna

| | Cessna 172 | 737-800 |
|---|---|---|
| Engines | 1 piston | 2 turbofans. Write **both** `/controls/engines/engine[0]/throttle` and `engine[1]/throttle`. |
| Spool-up | Instant | The engines take several seconds to respond, so the fly's throttle decisions show up late. |
| Takeoff | ~55 kt rotate | Rotate at roughly 140–150 kt, depending on weight. Takeoff needs flaps 5 and a much longer roll. |
| Systems | None | The plane spawns cold and dark. Set `/fruitfly/autostart` to `true` to run the 737's own autostart. The parking brake is on. The autopilot and autothrottle must stay **off** so they don't fly the plane instead of the fly. |

The neuron-to-control decoder (DNp09 → throttle up, MDN → throttle down) stays the same. The gains and timing will need retuning for the slower engines and longer takeoff.

## Fly passengers

**Built (2026-11-14).** The stock 737-800 has a cockpit but no passenger cabin, so we made one with [`flightgear/tools/make_cabin.py`](../flightgear/tools/make_cabin.py):

- **Cabin shell:** floor, walls with window holes, ceiling and overhead bins.
- **Seats:** 29 rows of 3+3, 174 seats in all, with 166 occupied by low-poly *Drosophila*. The flies have tan bodies, dark abdomen stripes, red compound eyes and translucent wings.
- **Live passengers:** Their wings and heads move with `/fruitfly/passengers/activity` (0..1). Drive it from the brain's firing rates so the passengers visibly react to what the brain is doing. This is display only.
- **Cabin views:** Two cabin views are added to the sim. Cycle with **v**.

Still to do: check it in the running sim and tune the look. See the TODOs in [flightgear/README.md](../flightgear/README.md).
