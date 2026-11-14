var altAlertModeSwitch = func {
	var warning_b = getprop("/b737/warnings/altitude-alert-b-conditions");
	var diff_0 = getprop("/b737/helpers/alt-diff-ft[0]");
	var diff_1 = getprop("/b737/helpers/alt-diff-ft[1]");

	if (warning_b) {
		var diff = diff_1;
	} else {
		var diff = diff_0;
	}

	if (diff < 600) {
		setprop("/b737/warnings/altitude-alert-mode", 1);
	} else {
		setprop("/b737/warnings/altitude-alert-mode", 0);
	}
}
setlistener( "/b737/warnings/altitude-alert", altAlertModeSwitch, 0, 0);

var gearLeverControl_node = props.globals.getNode("/b737/controls/gear/lever"); # 0 = down, 1 = up, 2 = middle
var gearDownControl_node = props.globals.getNode("/controls/gear/gear-down");
var rightGearWOW_node = props.globals.getNode("/gear/gear[1]/wow");
var gearlvr = nil;
var wow = nil;

setlistener("/b737/controls/gear/lever", func {
	gearlvr = gearLeverControl_node.getValue();
	wow = rightGearWOW_node.getValue();
	if (wow) {
		if (gearlvr != 0) {
			gearDownControl_node.setValue(1);   # force gear down
			gearLeverControl_node.setValue(0);  # inhibit gear lever movement
		}
	} else {
		if (gearlvr == 0) {
			gearDownControl_node.setValue(1);   # gear down
		} elsif (gearlvr == 1) {
			gearDownControl_node.setValue(0);   # gear up
		}
	}
}, 1, 0);


setlistener("/sim/signals/fdm-initialized", func {
	boeing737.hyd_init();
});