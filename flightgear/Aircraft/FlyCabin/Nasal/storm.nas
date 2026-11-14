# FruitFly storm: lightning, thunder and the roar of the tornadoes. VISUALS AND SOUND ONLY.
#
# The launchers' "storm" weather (flight_simulator/fg_weather.py) gives a gray
# overcast and rain with calm air. This file adds lightning flashes, thunder and
# a roar that grows as the airplane nears a tornado. Nothing here touches the
# air, the flight model or the controls: the fly flies in still air.
#
#   /fruitfly/storm/enabled   bool    set by the launcher; false = quiet, no lightning
#   /fruitfly/storm/bolt      int     index of the obstacle tornado a bolt is on, -1 = none
#                                     (Models/Obstacles/obstacle-N.xml shows its "Bolt")
#   /fruitfly/storm/light     0..1    how brightly lightning lights the funnels
#   /fruitfly/storm/strikes   int     how many strikes so far (for logs)
#   /fruitfly/storm/nearest-m double  distance to the nearest tornado's axis, -1 = none
#   /environment/lightning/*          FlightGear's own flash inputs: its cloud and rain
#                                     shaders light up when flash is 1

var storm = props.globals.getNode("/fruitfly/storm", 1);
var enabled = storm.getNode("enabled", 1);
if (enabled.getValue() == nil) enabled.setBoolValue(0);
var bolt = storm.getNode("bolt", 1);
bolt.setIntValue(-1);
var glow = storm.getNode("light", 1);
glow.setDoubleValue(0);
var strikes = storm.getNode("strikes", 1);
strikes.setIntValue(0);
var nearest = storm.getNode("nearest-m", 1);
nearest.setDoubleValue(-1);
var flash = props.globals.getNode("/environment/lightning/flash", 1);
flash.setDoubleValue(0);

var THUNDER = ["thunder.wav", "thunder1.wav", "thunder2.wav", "thunder3.wav"];
var ROAR = "wind1.wav";            # FlightGear's own 8.5 s sample
var ROAR_LEN = 8.0;                # restart just before it ends
var sounds = (getprop("/sim/fg-root") or "") ~ "/Sounds";
var play = func(file, volume, queue) {
    fgcommand("play-audio-sample", props.Node.new({path: sounds, file: file, volume: volume, queue: queue}));
};

var lit = 0;                       # 1 while a flash is on
var light = func(on, target) {
    lit = on;
    flash.setDoubleValue(on);
    bolt.setIntValue(on ? target : -1);
    glow.setDoubleValue(on ? 1.0 : 0.0);
};

# One strike = a flicker of two or three flashes, then thunder. `big` strikes are
# longer and louder.
var flicker = func(target, big) {
    var t = 0.0;
    var n = big ? 3 : 2;
    for (var i = 0; i < n; i += 1) {
        var on = 0.08 + 0.10 * rand();
        (func(at, len) {
            settimer(func { light(1, target); }, at);
            settimer(func { light(0, target); }, at + len);
        })(t, on);
        t += on + 0.05 + 0.08 * rand();
    }
    settimer(func { play(THUNDER[int(rand() * size(THUNDER))], big ? 1.0 : 0.5 + 0.3 * rand(),
                         "fruitfly-thunder"); }, 0.4 + 2.0 * rand());
};

var strike = func {
    settimer(strike, 3 + 7 * rand());             # next one in 3-10 s of sim time
    if (!enabled.getBoolValue()) return;
    var count = getprop("/fruitfly/obstacles/count") or 0;
    var target = count > 0 ? int(rand() * count) : -1;
    setprop("/environment/lightning/lightning-pos-x", (rand() - 0.5) * 6000);
    setprop("/environment/lightning/lightning-pos-y", (rand() - 0.5) * 6000);
    setprop("/environment/lightning/lightning-range", 6000);
    strikes.setIntValue(strikes.getValue() + 1);
    var big = rand() < 0.3;
    flicker(target, big);
    # sometimes a second bolt answers from another tornado
    if (count > 1 and rand() < 0.35)
        settimer(func { flicker(int(rand() * count), 0); }, 0.5 + 0.6 * rand());
};

# Between flashes the funnels pulse with a faint, uneasy light.
var pulse_t = 0.0;
var pulse = func {
    pulse_t += 0.1;
    if (!lit) glow.setDoubleValue(enabled.getBoolValue() ? 0.03 + 0.03 * math.sin(1.7 * pulse_t) * math.sin(0.31 * pulse_t) : 0);
};
var pulse_timer = maketimer(0.1, pulse);

# The roar: quiet in the distance, loud beside a tornado. Sound only.
var distance_to_nearest = func {
    var count = getprop("/fruitfly/obstacles/count") or 0;
    var here = geo.aircraft_position();
    var best = -1;
    for (var i = 0; i < count; i += 1) {
        var base = "/fruitfly/obstacles/obstacle[" ~ i ~ "]/";
        if (!getprop(base ~ "visible")) continue;
        var lat = getprop(base ~ "latitude-deg");
        var lon = getprop(base ~ "longitude-deg");
        if (lat == nil or lon == nil) continue;
        var d = here.distance_to(geo.Coord.new().set_latlon(lat, lon, here.alt()));
        d -= getprop(base ~ "radius-m") or 0;
        if (best < 0 or d < best) best = d;
    }
    return best;
};
var roar = func {
    settimer(roar, ROAR_LEN);
    if (!enabled.getBoolValue()) return;
    var d = distance_to_nearest();
    nearest.setDoubleValue(d);
    var near = d < 0 ? 0 : math.max(0, 1 - d / 5000);     # 0 beyond 5 km, 1 at the funnel
    play(ROAR, 0.12 + 0.88 * near * near, "fruitfly-roar");
};
# Nothing runs while FlightGear is still loading: the storm starts 5 s after the
# flight model is up (and only once, also after a reset).
var started = 0;
var start = func {
    if (started) return;
    started = 1;
    pulse_timer.start();
    settimer(roar, 3);
    settimer(strike, 6);
};
setlistener("/sim/signals/fdm-initialized", func { settimer(start, 5); }, 0, 0);

print("FruitFly: storm visuals loaded (lightning, thunder, tornado roar; the air stays calm)");
