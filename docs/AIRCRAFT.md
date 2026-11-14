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
python flightgear/setup_aircraft.py   # stock FGAddon 737-800 (package id 738) is committed in flightgear/Aircraft/737-800; this installs our overlay
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
- **Flight attendant (running gag, no brain):** a fly flight attendant in a navy jacket, red scarf and pillbox hat pushes a snack cart down the aisle. She stops at every row and hands each side a cup of water, a swirl of poop or a slice of rotten banana. Then she pulls the cart back to the galley and starts again. [`cabin_show.nas`](../flightgear/Aircraft/FlyCabin/Nasal/cabin_show.nas) scripts her, and the totals are counted under `/fruitfly/cabin/served/`. The **Cabin: follow the snack cart** view rides along with her cart. It's display only and never touches the controls or the fly pilot.
- **Crying baby (running gag, no brain):** a baby fruit fly is a larva, so it's a little white maggot in a pink bonnet. It lies on a parent's lap in an aisle seat in row 10. In fits it wriggles, opens its mouth, sheds tears and cries out loud. You hear it only from a cabin view; the sound is a real newborn cry, a CC0 recording (credit in [`Sounds/CREDITS.md`](../flightgear/Aircraft/FlyCabin/Sounds/CREDITS.md)) prepared by [`fetch_baby_cry.py`](../flightgear/tools/fetch_baby_cry.py). When the flight attendant serves its row, it gets a pacifier and goes quiet for a while.
- **Camera buttons:** the docked session log page has buttons for Fly pilot, Captain seat, Snack cart, Cabin aisle, Cabin front and Outside. They change only what the person watching sees, through `/fruitfly/view-request`. The fly pilot doesn't use the camera.

Still to do: check it in the running sim and tune the look. See the TODOs in [flightgear/README.md](../flightgear/README.md).
