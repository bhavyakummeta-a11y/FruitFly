# FruitFly storm: lightning and thunder. VISUALS AND SOUND ONLY.
#
# The launchers' "storm" weather (flight_simulator/fg_weather.py) gives a gray
# overcast and rain with calm air. This file adds lightning flashes and thunder
# on top. Nothing here touches wind, turbulence, the flight model or the
# controls: the fly flies in still air.
#
#   /fruitfly/storm/enabled   bool   set by the launcher; false = no lightning
#   /fruitfly/storm/bolt      int    index of the obstacle tornado a bolt is on, -1 = none
#                                    (Models/Obstacles/obstacle-N.xml shows its "Bolt")
#   /fruitfly/storm/strikes   int    how many strikes so far (for logs)
#   /environment/lightning/*         FlightGear's own flash inputs: its cloud and rain
#                                    shaders light up when flash is 1

var storm = props.globals.getNode("/fruitfly/storm", 1);
var enabled = storm.getNode("enabled", 1);
if (enabled.getValue() == nil) enabled.setBoolValue(0);
var bolt = storm.getNode("bolt", 1);
bolt.setIntValue(-1);
var strikes = storm.getNode("strikes", 1);
strikes.setIntValue(0);
var flash = props.globals.getNode("/environment/lightning/flash", 1);
flash.setDoubleValue(0);

var THUNDER = ["thunder.wav", "thunder1.wav", "thunder2.wav", "thunder3.wav"];
var sounds = (getprop("/sim/fg-root") or "") ~ "/Sounds";

var light = func(on, target) {
    flash.setDoubleValue(on);
    bolt.setIntValue(on ? target : -1);
};

var strike = func {
    settimer(strike, 6 + 14 * rand());            # next one in 6-20 s of sim time
    if (!enabled.getBoolValue()) return;
    var count = getprop("/fruitfly/obstacles/count") or 0;
    var target = count > 0 ? int(rand() * count) : -1;
    setprop("/environment/lightning/lightning-pos-x", (rand() - 0.5) * 6000);
    setprop("/environment/lightning/lightning-pos-y", (rand() - 0.5) * 6000);
    setprop("/environment/lightning/lightning-range", 6000);
    strikes.setIntValue(strikes.getValue() + 1);
    # flicker: on, off, on, off
    light(1, target);
    settimer(func { light(0, target); }, 0.12);
    settimer(func { light(1, target); }, 0.20);
    settimer(func { light(0, target); }, 0.34);
    # thunder follows the flash
    settimer(func {
        fgcommand("play-audio-sample", props.Node.new({
            path: sounds, file: THUNDER[int(rand() * size(THUNDER))],
            volume: 0.5 + 0.4 * rand(), queue: "fruitfly-thunder"}));
    }, 0.6 + 2.4 * rand());
};
settimer(strike, 8);

print("FruitFly: storm visuals loaded (lightning + thunder; the air stays calm)");
