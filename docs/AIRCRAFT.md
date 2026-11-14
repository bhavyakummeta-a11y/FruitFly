# Aircraft: Boeing 737-800

**Decided 2026-11-14.** The project flies a **Boeing 737-800** in FlightGear. The Cessna 172 used for the first tests is now only a fallback for debugging.

## Why the 737-800

- **A big plane.** It is a real airliner with about 160–189 seats, not a 4-seat trainer.
- **Fly passengers.** We want to render the passenger cabin and seat fruit flies in it for the demo.
- **Flyable.** It is common, has a well-tested JSBSim flight model, and is easier to get off the ground than a wide-body like the 777 or 747.

Alternatives we considered: the CRJ700 (smaller and more forgiving), the Q400 (a slow, gentle propeller plane), and the 777, 747 and A380 (too heavy for a fly-brain takeoff).

## Getting it into FlightGear

Our install is FlightGear **2024.1.4**, and the 737-800 is not bundled. Install it from FGAddon:

1. Open the FlightGear launcher, then **Aircraft → Browse**.
2. Search for **737-800** and install the Boeing 737-800 (the `737-800YV` package).
3. Select it and start on a long runway, for example at KSFO.

From the command line:

```
fgfs --aircraft=737-800YV --airport=KSFO --telnet=5401 --httpd=8080
```

> TODO: confirm the exact aircraft ID after installing. Check the package's `*-set.xml` file names.

## What changes from the Cessna

| | Cessna 172 | 737-800 |
|---|---|---|
| Engines | 1 piston | 2 turbofans. Write **both** `/controls/engines/engine[0]/throttle` and `engine[1]/throttle`. |
| Spool-up | Instant | The engines take several seconds to respond, so the fly's throttle decisions show up late. |
| Takeoff | ~55 kt rotate | Rotate at roughly 140–150 kt, depending on weight. Takeoff needs flaps 5 and a much longer roll. |
| Systems | None | The engines may need to be started first (see the TODO below). The autopilot and autothrottle must be **off** so they don't fly the plane instead of the fly. |

The neuron-to-control decoder (DNp09 → throttle up, MDN → throttle down) stays the same. The gains and timing will need retuning for the slower engines and longer takeoff.

> TODO: decide how to start the engines, either with an auto-start menu option or by spawning in the "running" state.

## Fly passengers

Plan for rendering the cabin with fruit fly passengers:

1. **Check the cabin.** Confirm how much passenger cabin the 737-800 model actually renders. If the seats are missing, we add our own.
2. **Fly model.** Make a low-poly *Drosophila* model (`.ac` or glTF, a few hundred polygons).
3. **Seat the flies.** Add `<model>` entries to an overlay of the aircraft's `-set.xml` or model XML, placing a grid of flies at the seat positions.
4. **Cabin camera.** Add a "Cabin" view to `<sim><view>` so the demo can cut to the passengers.
5. **Stretch goal: live passengers.** Bind fly animations (wing flap, leg twitch) to properties that our Python bridge writes from the brain's firing rates. The passengers would then visibly react to what the brain is doing.

Put our overlay files in this repo under `flightgear/`. Don't edit the downloaded aircraft directly, so teammates can reproduce the setup.
