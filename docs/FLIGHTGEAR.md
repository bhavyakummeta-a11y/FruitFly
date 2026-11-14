# FlightGear 2024.1.4: setup and command reference

FlightGear is the free, open-source flight simulator we use for the [current MVP](PROJECT_PLAN.md#current-mvp-as-of-2026-11-14): get the plane on a runway, then let the fly brain drive the throttle from Python.

> **Aircraft:** the project's default is the **Boeing 737-800 with fly passengers** (`738-flies`). Install it once with `python flightgear/setup_aircraft.py`, then start it with `python flightgear/launch.py` or `python -m flight_simulator.launch_fg`. See [flightgear/README.md](../flightgear/README.md) and [AIRCRAFT.md](AIRCRAFT.md). The examples below use the bundled Cessna 172P (`c172p`), our fallback for debugging, because it works straight after install. For the 737, swap `--aircraft=c172p` for `--fg-aircraft=<repo>/flightgear/Aircraft --aircraft=738-flies`. Writing `engine[0]` throttle is enough, because the overlay mirrors it to `engine[1]`.
>
> **Related:** [FLIGHT_SIMULATOR.md](FLIGHT_SIMULATOR.md) covers the obstacle-avoidance experiment, which talks to FlightGear over `--generic` UDP rather than telnet.

**Version:** 2024.1.4, released 21 January 2026. It's a bug-fix release in the 2024.1 LTS series.
**Newer versions:** 2024.1.5, 2024.1.6 and 2024.1.7 have since shipped. Everything in this doc works the same on any 2024.1.x. Use 2024.1.4 when the whole team needs to match exactly; otherwise use the latest.

Contents:

1. [Download and install](#1-download-and-install), covering Windows, Linux and macOS
2. [First launch](#2-first-launch)
3. [Command-line options](#3-command-line-options)
4. [Telnet property server](#4-telnet-property-server), the Python ↔ FlightGear link
5. [HTTP server](#5-http-server-httpd)
6. [Useful properties](#6-useful-properties-for-this-project)
7. [Keyboard controls](#7-keyboard-controls)
8. [Python example](#8-python-example)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Download and install

All 2024.1.4 builds are in the official SourceForge release folder:
**https://sourceforge.net/projects/flightgear/files/release-2024.1/**

| OS | File | Requirement |
|---|---|---|
| Windows | `flightgear-2024.1.4-windows-amd64.exe` | Windows 10/11, x86-64 (no ARM64 build yet) |
| Linux | `flightgear-2024.1.4-linux-amd64.AppImage` | x86-64 |
| macOS | `flightgear-2024.1.4-macos-universal.dmg` | macOS 11 (Big Sur) or later, Intel or Apple Silicon |
| Data, optional | `FlightGear-2024.1.4-data.txz` | Only needed when building from source |

The latest release is always at https://www.flightgear.org/download/.

All three installers include the base data, which has the default Cessna 172P (`c172p`) and a few airports. Scenery for the rest of the world streams in while you fly through **TerraSync**, which is on by default. That needs internet access the first time you visit an area.

> **Hack-day tip:** download on good Wi-Fi before the event. The Linux AppImage is about 330 MB, and the first flight downloads scenery.

### Windows

1. Download `flightgear-2024.1.4-windows-amd64.exe`.
2. Run it. If SmartScreen warns you, click **More info**, then **Run anyway**.
3. Accept the defaults. FlightGear installs to `C:\Program Files\FlightGear 2024.1\` and adds a Start-menu shortcut that opens the launcher.
4. The simulator binary is `C:\Program Files\FlightGear 2024.1\bin\fgfs.exe`. Use it to start with command-line options:

   ```powershell
   & "C:\Program Files\FlightGear 2024.1\bin\fgfs.exe" --launcher
   ```

5. When FlightGear first opens a network port, Windows Firewall asks whether to allow it. Allow **private networks**, or the telnet server won't be reachable. Connections from the same PC (`localhost`) usually work either way.

**Optional, if you have winget:** `winget install FlightGear.FlightGear` installs the *latest* 2024.1.x, not necessarily 2024.1.4.

### Linux

The official build is an AppImage, a single self-contained executable with no install step.

```bash
mkdir -p ~/apps && cd ~/apps
# download flightgear-2024.1.4-linux-amd64.AppImage from the SourceForge folder above, then:
chmod +x flightgear-2024.1.4-linux-amd64.AppImage
./flightgear-2024.1.4-linux-amd64.AppImage --launcher
```

- **FUSE:** AppImages need FUSE 2. If you see `dlopen(): error loading libfuse.so.2`:
  - **Ubuntu 24.04 and later:** `sudo apt install libfuse2t64`
  - **Ubuntu 22.04 and Debian:** `sudo apt install libfuse2`
  - **Fedora:** `sudo dnf install fuse-libs`
  - Or run without FUSE: `./flightgear-...AppImage --appimage-extract-and-run --launcher`
- **Handy alias,** so the rest of this doc's `fgfs` commands work as written:
  ```bash
  echo 'alias fgfs="$HOME/apps/flightgear-2024.1.4-linux-amd64.AppImage"' >> ~/.bashrc && source ~/.bashrc
  ```
- **GPU:** use the proprietary NVIDIA driver, or Mesa for AMD/Intel. Software rendering (llvmpipe) is unusably slow. Check with `glxinfo -B | grep renderer`.
- **Distro packages** (`apt install flightgear`, Flatpak) exist, but they often ship a different version. Use the AppImage so everyone runs 2024.1.4.

### macOS

1. Download `flightgear-2024.1.4-macos-universal.dmg`. It's a single build for both Intel and Apple Silicon.
2. Open the DMG and drag **FlightGear** into **Applications**.
3. **The first open is blocked by Gatekeeper.** Right-click (Control-click) FlightGear.app, choose **Open**, then **Open** again. On macOS 15 and later, go to **System Settings → Privacy & Security** and click **Open Anyway**.
4. To start it with command-line options from Terminal, run the binary inside the app bundle:

   ```bash
   /Applications/FlightGear.app/Contents/MacOS/FlightGear --launcher
   # optional alias:
   echo 'alias fgfs="/Applications/FlightGear.app/Contents/MacOS/FlightGear"' >> ~/.zshrc && source ~/.zshrc
   ```

5. **Apple Silicon:** if the sky or terrain renders wrongly, see the notes in the [2024.1.2 release post](https://www.flightgear.org/blog/). Lowering the shader quality in the launcher's **Settings → Rendering** usually helps.

### Check the install

```bash
fgfs --version
```

It should print `FlightGear version: 2024.1.4` plus the SimGear and OpenSceneGraph versions.

---

## 2. First launch

There are two ways to start FlightGear:

- **The launcher (GUI),** via `fgfs --launcher` or the desktop shortcut. Pick an aircraft, airport and options, then click **Fly!** Settings typed under **Settings → Additional Settings** behave like command-line options.
- **Command line only,** `fgfs --aircraft=c172p --airport=KRDU ...`. This is the reproducible way to start, so use it for our scripts.

The first start takes a while: it builds caches and downloads scenery through TerraSync.

### Our standard start command (MVP)

This puts a Cessna 172P on the Raleigh-Durham runway in daytime, with no network weather, a telnet server on 5401 and a web server on 8080:

```bash
fgfs --aircraft=c172p \
     --airport=KRDU --runway=23R \
     --timeofday=noon \
     --disable-real-weather-fetch \
     --disable-ai-traffic \
     --telnet=5401 \
     --httpd=8080
```

On Windows PowerShell, put it on one line, or replace each `\` with a backtick `` ` ``.

---

## 3. Command-line options

Run `fgfs --help --verbose` to list every option. These are the useful ones.

### Aircraft and location

| Option | What it does |
|---|---|
| `--aircraft=c172p` | Aircraft to fly. `c172p` is the Cessna 172P, which is installed by default and forgiving. |
| `--show-aircraft` | List installed aircraft and exit |
| `--airport=KRDU` | Start at an airport, using its ICAO code. KRDU is Raleigh-Durham. |
| `--runway=23R` | Start on a specific runway |
| `--parkpos=<name>` | Start at a gate or parking spot instead of the runway |
| `--lat=35.87 --lon=-78.79` | Start at exact coordinates instead |
| `--heading=230` | Initial heading in degrees |
| `--in-air` | Start airborne. Combine with `--altitude` and `--vc`. |
| `--altitude=3000` | Starting altitude in feet |
| `--vc=100` | Starting calibrated airspeed in knots |
| `--offset-distance=5` | Start N nautical miles out from the runway, for approach practice |
| `--glideslope=3` | Starting flight-path angle in degrees, for approaches |
| `--state=<name>` | Start the aircraft in a named state, if the aircraft defines it (for example `take-off`, `cruise`) |

### Time, weather, world

| Option | What it does |
|---|---|
| `--timeofday=noon` | `dawn`, `morning`, `noon`, `afternoon`, `dusk`, `evening`, `midnight`, or `real` |
| `--disable-real-weather-fetch` | Don't download live METAR weather, so runs are repeatable |
| `--wind=270@10` | Fixed wind, here from 270° at 10 kt. Use `0@0` for calm. |
| `--visibility=10000` | Visibility in meters |
| `--disable-ai-traffic` | No AI planes |
| `--disable-terrasync` / `--enable-terrasync` | Turn scenery auto-download off or on |
| `--terrasync-dir=<path>` | Where downloaded scenery goes |

### Simulation control

| Option | What it does |
|---|---|
| `--enable-freeze` | Start paused. Unpause with `p` or the `/sim/freeze/master` property. |
| `--prop:<path>=<value>` | Set any property at startup, for example `--prop:/controls/gear/brake-parking=0`. The forms `--prop:double:/path=1.0` and `--prop:bool:/path=true` set the type explicitly. |
| `--config=<file.xml>` | Load extra property settings from an XML file |
| `--fdm=jsb` | Flight dynamics model. Normally set by the aircraft; leave it alone. |
| `--enable-auto-coordination` | Ailerons also move the rudder (coordinated turns). Useful when a controller doesn't output yaw. |
| `--ignore-autosave` | Ignore the settings saved from the last session, for a clean start |

### Networking and I/O, the important part for us

| Option | What it does |
|---|---|
| `--telnet=5401` | Start the **telnet property server** on TCP port 5401. See [§4](#4-telnet-property-server). |
| `--httpd=8080` | Start the **web server** on port 8080. See [§5](#5-http-server-httpd). |
| `--allow-nasal-from-sockets` | Allow the telnet `nasal` command to run code. Off by default. Only use it on a trusted network. |
| `--generic=socket,out,10,127.0.0.1,5500,udp,<protocol>` | Stream chosen properties at 10 Hz over UDP, using an XML protocol file in `$FG_ROOT/Protocol/`. Use `in` instead of `out` to receive. This is the fastest I/O option and worth trying if telnet is too slow. |
| `--native-fdm=socket,out,30,127.0.0.1,5502,udp` | Stream the binary flight-model state |
| `--native-ctrls=socket,in,30,,5503,udp` | Receive the binary control surfaces |

### Performance and display

| Option | What it does |
|---|---|
| `--geometry=1280x720` | Window size |
| `--enable-fullscreen` / `--disable-fullscreen` | Fullscreen on or off |
| `--max-fps=30` | Cap the frame rate to free CPU for the brain sim |
| `--fog-fastest` | Cheaper rendering |
| `--disable-sound` | No audio |
| `--disable-splash-screen` | Skip the splash screen |

### Paths and debugging

| Option | What it does |
|---|---|
| `--fg-root=<path>` | Base data directory. Usually found automatically. |
| `--fg-aircraft=<path>` | Extra folder of downloaded aircraft |
| `--log-level=info` | `bulk`, `debug`, `info`, `warn`, or `alert` |
| `--console` | **Windows only:** show a console window with log output |
| `--version` | Print the version and exit |
| `--help --verbose` | Print every option |

---

## 4. Telnet property server

Everything in FlightGear (position, speed, controls, engine state) lives in a **property tree**, a filesystem-like tree of named values such as `/velocities/groundspeed-kt`. `--telnet=5401` opens a text protocol on TCP port 5401 for reading and writing it. **This is how the fly brain talks to the plane.**

### Connecting by hand

```bash
# Linux / macOS
nc localhost 5401          # or: telnet localhost 5401
```

On Windows, use PuTTY (Connection type **Raw** or **Telnet**, host `localhost`, port `5401`). You can also enable the built-in client from an admin PowerShell (`Enable-WindowsOptionalFeature -Online -FeatureName TelnetClient`) and then run `telnet localhost 5401`.

Press Enter to get a prompt like `/> `.

### Commands

This is the full list from FlightGear 2024.1.4's own `help` output.

| Command | What it does |
|---|---|
| `help` | Show the command list |
| `about` | Print system and version info |
| `ls [<dir>]` | List a directory of properties with their values |
| `ls2 [<dir>]` | Machine-readable listing: `num_children name index type value` |
| `cd <dir>` | Change directory. `cd ..` goes up. |
| `pwd` | Print the current path |
| `get <var>` | Read a property. `show` does the same. |
| `set <var> <val>` | Write a property as a string. FlightGear converts it to the property's type. |
| `setd <var> <val>` | Write a double. `setf` is an alias. |
| `seti <var> <val>` | Write an int |
| `setb <var> <val>` | Write a bool: `0`, `1`, `true`, or `false` |
| `del <var> <node>` | Delete a child node |
| `dump [<dir>]` | Dump a subtree as XML |
| `run <command> [args]` | Run a built-in FlightGear command (fgcommand), for example `run pause` or `run exit` |
| `subscribe <var>` | Push a line `path=value` to you whenever the property changes |
| `unsubscribe <var>` | Stop that. Use the same path string as in `subscribe`. |
| `data` | Switch to **raw data mode** for scripts |
| `prompt` | Switch back to interactive mode (the default) |
| `nasal [EOF <marker>]` | Run Nasal script code. Needs `--allow-nasal-from-sockets`. |
| `quit` | Close the connection |

Commands that end in `\r\n` are fine; FlightGear accepts `\n` too.

### Prompt mode vs data mode

```text
/> get /velocities/groundspeed-kt
/velocities/groundspeed-kt = '12.34567' (double)
/> set /controls/engines/engine[0]/throttle 0.8
/controls/engines/engine[0]/throttle = '0.8' (double)
/> data
get /velocities/groundspeed-kt
12.34567
set /controls/engines/engine[0]/throttle 0.5
```

- **Prompt mode** echoes `path = 'value' (type)` and prints a `/> ` prompt after every command. It's good for poking around by hand.
- **Data mode** makes `get` return just the value plus `\r\n`, and `set` returns **nothing**. **Scripts should send `data` first.**
- Errors come back as `-ERR "message"`.

### Example session

```text
cd /controls/engines/engine[0]
ls
get throttle
set throttle 1.0
cd /
get /position/altitude-agl-ft
set /sim/freeze/master 1      # pause physics
set /sim/freeze/master 0      # resume
subscribe /velocities/groundspeed-kt
```

### Performance

The telnet server is serviced once per rendered frame, so each `get` costs roughly one frame (about 15–30 ms). That's fine for the MVP's few reads per decision. For tens of properties at 10 Hz or more, use `--generic` UDP or the HTTP `/json/` endpoint, which can read a whole subtree in one call.

---

## 5. HTTP server (`--httpd`)

`--httpd=8080` starts a web server.

| URL | What it does |
|---|---|
| `http://localhost:8080/` | Phi web interface: map, instruments and property browser in your browser |
| `http://localhost:8080/props/` | Browse the property tree as HTML |
| `GET /json/<path>?d=2&i=y` | Return a property subtree as JSON. `d` is the depth (default 1); `i=y` pretty-prints. |
| `POST /json/<path>` with body `{"value": 0.8}` | Set a property |
| `GET /run.cgi?value=<command>` | Run an fgcommand, for example `value=pause` |
| `GET /screenshot` | Take a screenshot |

Examples:

```bash
curl "http://localhost:8080/json/velocities/groundspeed-kt"
curl "http://localhost:8080/json/orientation?d=1&i=y"          # pitch, roll, heading in one call
curl -X POST -d '{"value":0.8}' "http://localhost:8080/json/controls/engines/engine[0]/throttle"
```

---

## 6. Useful properties for this project

### Read: aircraft state, the encoder inputs

| Property | Units | Notes |
|---|---|---|
| `/velocities/groundspeed-kt` | kt | **MVP read**: forward progress on the runway |
| `/velocities/airspeed-kt` | kt | Indicated airspeed. For the C172P, Vr ≈ 55 kt. |
| `/velocities/vertical-speed-fps` | ft/s | Climb or descent rate |
| `/orientation/pitch-deg` | deg | + nose up |
| `/orientation/roll-deg` | deg | + right wing down |
| `/orientation/heading-deg` | deg | True heading |
| `/orientation/roll-rate-degps`, `/orientation/pitch-rate-degps`, `/orientation/yaw-rate-degps` | deg/s | Rotation rates, the natural input for the VS/HS cells |
| `/position/altitude-ft` | ft | Above mean sea level |
| `/position/altitude-agl-ft` | ft | Above ground |
| `/position/latitude-deg`, `/position/longitude-deg` | deg | Position |
| `/gear/gear[0]/wow` | bool | Weight on wheels, so true while on the ground |
| `/engines/engine[0]/running` | bool | Engine running? |
| `/engines/engine[0]/rpm` | rpm | Engine RPM |
| `/sim/time/elapsed-sec` | s | Sim clock |

### Write: controls, the decoder outputs

| Property | Range | Notes |
|---|---|---|
| `/controls/engines/engine[0]/throttle` | 0 – 1 | **MVP write**. On the 737-800, also write `engine[1]`. |
| `/controls/engines/engine[0]/mixture` | 0 – 1 | Keep at 1 (rich) near sea level |
| `/controls/flight/elevator` | −1 – 1 | + is stick back, nose up |
| `/controls/flight/aileron` | −1 – 1 | + rolls right |
| `/controls/flight/rudder` | −1 – 1 | + yaws right |
| `/controls/flight/elevator-trim` | −1 – 1 | Trim |
| `/controls/flight/flaps` | 0 – 1 | C172P: 0, 0.33, 0.66, 1 |
| `/controls/gear/brake-parking` | 0 / 1 | **Release it (0) or the plane won't move** |
| `/controls/gear/brake-left`, `/controls/gear/brake-right` | 0 – 1 | Toe brakes |

### Sim control

| Property | Notes |
|---|---|
| `/sim/freeze/master` | 1 pauses physics, 0 resumes. Use this to **pause the sim while the brain thinks**. |
| `/sim/freeze/clock` | Freeze the sim clock |
| `/sim/speed-up` | Time multiplier, for example 0.5 for half speed. That buys the brain more wall-clock time per sim second. |

---

## 7. Keyboard controls

Click the FlightGear window first so it has keyboard focus.

| Key | Action |
|---|---|
| `p` | Pause / resume |
| `Page Up` / `Page Down` | Throttle up / down |
| Arrow keys, or numpad `8` `2` `4` `6` | Elevator and ailerons |
| Numpad `0` / `Enter` | Rudder left / right |
| Numpad `5` | Center the controls |
| `b` | Hold the brakes |
| `B` (Shift + b) | Toggle the parking brake |
| `]` / `[` | Flaps down / up |
| `}` / `{` | Magnetos up / down. Turn to **BOTH** before starting the engine. |
| `s` (hold) | Starter |
| `v` / `V` | Cycle the view forward / back |
| `Ctrl` + `v` | Back to the cockpit view |
| `x` / `X` | Zoom in / out |
| `Tab` | Open the quick menu |
| `?` | Show the key bindings for the current aircraft |

**Engine not running?** If `/engines/engine[0]/running` is false, either:

- set magnetos to BOTH (press `}` three times), then hold `s` until the engine catches, or
- use the C172P's menu entry **Cessna C172P → Autostart**.

---

## 8. Python example

This is a minimal telnet client using only the standard library. It's enough for the MVP loop.

```python
import socket

class FlightGear:
    """Tiny client for FlightGear's telnet property server (fgfs --telnet=5401)."""

    def __init__(self, host="localhost", port=5401):
        self.sock = socket.create_connection((host, port), timeout=5)
        self.buf = b""
        self._send("data")                      # raw mode: get -> value only, set -> no reply

    def _send(self, line):
        self.sock.sendall((line + "\r\n").encode())

    def _readline(self):
        while b"\n" not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("FlightGear closed the connection")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return line.decode().rstrip("\r")

    def get(self, path):
        self._send(f"get {path}")
        value = self._readline()
        if value.startswith("-ERR"):
            raise RuntimeError(value)
        return value

    def get_float(self, path):
        return float(self.get(path) or 0.0)

    def set(self, path, value):
        self._send(f"set {path} {value}")

    def pause(self, on=True):
        self.set("/sim/freeze/master", 1 if on else 0)

    def close(self):
        self._send("quit")
        self.sock.close()


if __name__ == "__main__":
    fg = FlightGear()
    fg.set("/controls/gear/brake-parking", 0)
    fg.set("/controls/engines/engine[0]/throttle", 0.6)
    print("groundspeed:", fg.get_float("/velocities/groundspeed-kt"), "kt")
    fg.close()
```

### MVP loop shape

The fly-brain side (`simulate`, `rate`, and the `dnp09` and `mdn` neuron groups) comes from [`fly_brain_starter.ipynb`](../fly_brain_starter.ipynb).

```python
ENGINES = [0, 1]                                    # 737-800; use [0] for the C172P
fg = FlightGear()
fg.set("/controls/gear/brake-parking", 0)
throttle = 0.0
while True:
    fg.pause(True)                                  # freeze the plane while the brain thinks
    counts = simulate([(stimulus_neurons, 150)])    # ~200 ms of brain time
    forward, backward = rate(counts, dnp09), rate(counts, mdn)
    throttle = min(1.0, max(0.0, throttle + 0.01 * (forward - backward)))
    for eng in ENGINES:                             # [0] for the C172P, [0, 1] for the 737-800
        fg.set(f"/controls/engines/engine[{eng}]/throttle", throttle)
    fg.pause(False)
    # let the sim run briefly, then log
    print(fg.get_float("/velocities/groundspeed-kt"), throttle)
```

The gain (`0.01`) is a placeholder. Keep the decoder this thin, per the project's [honor-the-fly-brain rule](PROJECT_PLAN.md#principle-honor-the-fly-brain).

---

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| `Connection refused` on port 5401 | FlightGear isn't running with `--telnet=5401`, or it's still loading. Wait for the cockpit to appear. On Windows, check the firewall prompt. |
| The plane doesn't move at full throttle | Parking brake is on (`set /controls/gear/brake-parking 0`), or the engine isn't running (§7). |
| `get` returns an empty string | Typo in the path. Paths are case-sensitive, and indexes are written `engine[0]`. Use `ls` to explore. |
| Script hangs after `set` | You're waiting for a reply. In data mode, `set` sends none. |
| Very low frame rate | Set `--max-fps=30`, `--fog-fastest`, and lower **Settings → Rendering** in the launcher. On Linux, check you're on the real GPU driver. |
| Linux: `libfuse.so.2` error | Install FUSE 2 (§1), or run with `--appimage-extract-and-run`. |
| macOS: "app is damaged / can't be opened" | Right-click → Open, or **System Settings → Privacy & Security → Open Anyway**. |
| Scenery is flat or missing | TerraSync is still downloading, or you're offline. Wait, or pick a different airport. |
| Settings from last time come back | Add `--ignore-autosave`. |

## Sources

- Release announcement: https://www.flightgear.org/blog/release-2024-1-4/
- 2024.1.4 changelog (macOS 11 minimum): https://flightgear.org/download/releases/2024-1-4
- Download files: https://sourceforge.net/projects/flightgear/files/release-2024.1/
- Telnet commands: `src/Network/propsProtocol.cxx`, and HTTP endpoints: `src/Network/http/`, both at tag `2024.1.4` on https://gitlab.com/flightgear/flightgear
- FlightGear wiki: https://wiki.flightgear.org/ (pages "Command line options", "Telnet usage", "Property tree")
