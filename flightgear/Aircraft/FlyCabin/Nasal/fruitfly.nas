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

# ---- the fly pilot (captain's seat) ------------------------------------------
# Inputs, written by the controller from the fly brain's descending neurons:
#   /fruitfly/pilot/active  bool   a fly-brain controller is connected
#   /fruitfly/pilot/power   0..1   DNg02 (wingbeat amplitude)
#   /fruitfly/pilot/steer  -1..1   steering DNs, right minus left
#   /fruitfly/pilot/escape  0..1   DNp01 Giant Fibre
# Outputs (fly-pilot.xml animations): flap-norm, head-turn-deg, lean-deg, hop-m.
var pilot = props.globals.getNode("/fruitfly/pilot", 1);
var pt = 0.0;
var hop_t = -10.0;
var was_escaping = 0;
var lean = 0.0;
var update_pilot = func {
    pt += DT;
    var active = pilot.getBoolValue("active");
    var power = active ? (pilot.getValue("power") or 0) : 0;
    var steer = active ? (pilot.getValue("steer") or 0) : 0;
    var escape = active ? (pilot.getValue("escape") or 0) : 0;
    if (escape > 0.5 and !was_escaping) hop_t = pt;   # Giant Fibre: hop + wing flare
    was_escaping = escape > 0.5;
    var hop = pt - hop_t < 0.8 ? 1 - (pt - hop_t) / 0.8 : 0;
    # Wings: idle twitch when no brain is connected; beat faster/wider with DNg02.
    var hz = active ? 2.0 + 8.0 * power : 0.3;
    var amp = active ? 0.25 + 0.6 * power : 0.08;
    var beat = 0.5 + 0.5 * math.sin(2 * math.pi * hz * pt);
    pilot.setDoubleValue("flap-norm", math.max(amp * beat, hop));
    pilot.setDoubleValue("head-turn-deg", 25 * steer + 4 * math.sin(0.5 * pt));
    lean += (12 * steer - lean) * 0.15;             # smoothed lean into the turn
    pilot.setDoubleValue("lean-deg", lean);
    pilot.setDoubleValue("hop-m", 0.12 * hop);
};
var pilot_timer = maketimer(DT, update_pilot);
pilot_timer.start();

# Clear view: in "Cockpit: fly pilot" the overhead panel and centre windshield post are
# hidden (select animation in 738-flies.xml) for a wide view outside.
var clear_view = func {
    var n = getprop("/sim/current-view/view-number");
    var name = "";
    if (n != nil and view.views != nil and n >= 0 and n < size(view.views))
        name = view.views[n].getNode("name", 1).getValue() or "";
    setprop("/fruitfly/pilot/clear-view", name == "Cockpit: fly pilot");
};
setlistener("/sim/current-view/view-number", clear_view, 1, 0);

var pilot_view = func {
    if (!getprop("/fruitfly/pilot/start-view")) return;
    var i = view.indexof("Cockpit: fly pilot");
    if (i != nil and i >= 0) setprop("/sim/current-view/view-number", i);
};
setlistener("/sim/signals/fdm-initialized", func { settimer(pilot_view, 1); }, 0, 0);

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

# The 737's in-air start (autostart.nas: inAirStart) engages its autopilot and
# autothrottle about 5 s after spawning above 400 ft AGL. The fly must be the
# one flying, but only once a controller is actually connected: switching the
# autopilot off on a fixed timer left the plane uncontrolled (and stalling)
# while FlightGear finished loading. So the autopilot holds the plane until the
# Python controller sets /fruitfly/controller-connected (flightgear.hand_over),
# then hands over - never sooner than 7 s after spawn, so the in-air start
# can't re-engage it afterwards.
#
# NO-AUTOPILOT RULE (project owner, 2026-11-14): the fly NEVER uses the
# airplane's autopilot or autothrottle. From the handover on, any attempt to
# engage CMD A / CMD B / the autothrottle (keyboard, panel click, script) is
# forced off at once and counted in /fruitfly/autopilot/violations. There is
# no override. The Python controller checks the same properties
# (flight_simulator/flightgear.py AutopilotGuard) and won't fly while they're on.
var spawn_time = 0;
var airborne_start = 0;
var ap_forbidden = props.globals.getNode("/fruitfly/autopilot/forbidden", 1);
var ap_violations = props.globals.getNode("/fruitfly/autopilot/violations", 1);
ap_forbidden.setBoolValue(0);
ap_violations.setIntValue(0);
var AP_ON = ["/autopilot/internal/CMDA", "/autopilot/internal/CMDB", "/autopilot/internal/SPD"];
var ap_off = func {
    autopilot737.ap_disengage();
    foreach (var p; ["SPD", "SPD-SPEED", "SPD-N1", "SPD-RETARD", "LVLCHG"])
        setprop("/autopilot/internal/" ~ p, 0);
};
var enforce_no_ap = func {
    if (!ap_forbidden.getBoolValue()) return;
    var on = [];
    foreach (var p; AP_ON) if (getprop(p)) append(on, p);
    if (!size(on)) return;
    ap_violations.setIntValue(ap_violations.getValue() + 1);
    print("FruitFly NO-AUTOPILOT RULE: " ~ string.join(", ", on) ~ " engaged while the fly is flying - forced off");
    settimer(ap_off, 0);  # outside the listener, so the 737's own listeners finish first
};
foreach (var p; AP_ON) setlistener(p, enforce_no_ap, 0, 0);
var release_ap = func {
    ap_off();
    ap_forbidden.setBoolValue(1);
    print("FruitFly: controller connected - 737 autopilot/autothrottle off and locked out, the fly is flying");
};
var hands_off = func {
    spawn_time = getprop("/sim/time/elapsed-sec") or 0;
    airborne_start = (getprop("/position/altitude-agl-ft") or 0) > 400;
    if (airborne_start)
        print("FruitFly: 737 autopilot holds the plane until the fly-brain controller connects");
};
setlistener("/sim/signals/fdm-initialized", hands_off, 0, 0);
setlistener("/fruitfly/controller-connected", func(n) {
    if (!n.getBoolValue()) return;
    if (!airborne_start) { release_ap(); return; }  # runway start: lock out at once
    var wait = spawn_time + 7 - (getprop("/sim/time/elapsed-sec") or 0);
    if (wait > 0) settimer(release_ap, wait) else release_ap();
}, 0, 0);

# launch_fg --phase takeoff sets /fruitfly/ground-autostart so the engines are
# running when the fly takes over on the runway.
var ground_autostart = func {
    if (!getprop("/fruitfly/ground-autostart")) return;
    if ((getprop("/position/altitude-agl-ft") or 0) > 400) return;
    settimer(func {
        print("FruitFly: ground start - running 737 autostart");
        boeing737.autostart();
        # The 737's controls.nas sets the parking brake at init, which held the plane on the
        # runway at full thrust. The fly brakes with the toe brakes, so release it.
        settimer(func {
            setprop("/controls/gear/brake-parking", 0);
            print("FruitFly: parking brake released for the takeoff");
        }, 1);
    }, 1);
};
setlistener("/sim/signals/fdm-initialized", ground_autostart, 0, 0);
setlistener("/sim/signals/reinit", hands_off, 0, 0);

print("FruitFly: cabin loaded");
