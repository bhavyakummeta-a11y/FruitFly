# FruitFly cabin animation + helpers for the 737-800.
#
# Inputs (written by our Python bridge):
#   /fruitfly/passengers/activity  0..1  how agitated the passengers are
#   /fruitfly/autostart            bool  true -> run the 737's own autostart
#   /fruitfly/mirror-throttle      bool  (default true) copy engine[0] throttle
#                                        to engine[1], so bridges that only write
#                                        engine[0] (e.g. flybrain-controls.xml,
#                                        written for the single-engine C172) drive both
#
# Outputs (read by the fly models' animations):
#   /fruitfly/passengers/group[n]/flap-norm, head-turn-deg   n = 0..2
#
# This is display only. It never touches the flight controls.

var activity = props.globals.getNode("/fruitfly/passengers/activity", 1);
var groups = [];
var phase = [0.0, 2.1, 4.2];
for (var g = 0; g < 3; g += 1) {
    append(groups, props.globals.getNode("/fruitfly/passengers/group[" ~ g ~ "]", 1));
}

var t = 0.0;
var DT = 0.04;

var update = func {
    t += DT;
    var a = activity.getValue() or 0.0;
    a = (a < 0) ? 0 : ((a > 1) ? 1 : a);
    var hz = 1.0 + 7.0 * a;                  # wing beat speed rises with activity
    for (var g = 0; g < 3; g += 1) {
        var p = phase[g];
        var beat = 0.5 + 0.5 * math.sin(2 * math.pi * hz * t + p);
        groups[g].setDoubleValue("flap-norm", a * beat);
        # idle passengers glance around slowly; agitated ones look about more
        var look = (6 + 24 * a) * math.sin(0.4 * t + 1.7 * p) * math.sin(0.13 * t + p);
        groups[g].setDoubleValue("head-turn-deg", look);
    }
};

var timer = maketimer(DT, update);
timer.start();

setlistener("/fruitfly/autostart", func(n) {
    if (n.getBoolValue()) {
        print("FruitFly: running 737 autostart");
        boeing737.autostart();
        n.setBoolValue(0);
    }
}, 0, 0);

var mirror = props.globals.getNode("/fruitfly/mirror-throttle", 1);
if (mirror.getValue() == nil) mirror.setBoolValue(1);
var thr1 = props.globals.getNode("/controls/engines/engine[1]/throttle", 1);
setlistener("/controls/engines/engine[0]/throttle", func(n) {
    if (mirror.getBoolValue()) thr1.setDoubleValue(n.getValue() or 0);
}, 0, 0);

print("FruitFly: cabin loaded");
