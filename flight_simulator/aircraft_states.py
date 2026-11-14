"""Check `--state=<name>` against the states an aircraft actually defines.

FlightGear only honours `--state=X` if the aircraft's -set.xml has a
`<sim><state><name>X</name>...</state></sim>` overlay. Otherwise it logs
"missing state node for:X" and silently starts in the default configuration
(issue #2: `--state=cruise` on 738-flies / c172p). This module lets launchers
refuse such a command before starting FlightGear, and lets tests lint for it.

    python -m flight_simulator.aircraft_states 738-flies   # list defined states
"""
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

REPO_AIRCRAFT = Path(__file__).resolve().parent.parent / 'flightgear' / 'Aircraft'


def find_set_xml(aircraft, aircraft_dirs):
    """Locate <aircraft>-set.xml the way FlightGear does: <dir>/<folder>/<id>-set.xml."""
    name = f'{aircraft}-set.xml'
    for d in aircraft_dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        if (d / name).is_file():
            return d / name
        for sub in sorted(p for p in d.iterdir() if p.is_dir()):
            if (sub / name).is_file():
                return sub / name
    return None


def _states_in(root, base, seen):
    """State names under a PropertyList root, following include= attributes."""
    names = set()
    inc = root.get('include')
    if inc:
        names |= defined_states(base / inc, seen)
    sim = root.find('sim')
    if sim is not None:
        if sim.get('include'):
            sim_file = base / sim.get('include')
            if sim_file.is_file() and sim_file not in seen:
                seen.add(sim_file)
                names |= {n.text.strip() for n in ET.parse(sim_file).getroot().findall('state/name') if n.text}
        names |= {n.text.strip() for n in sim.findall('state/name') if n.text}
    return names


def defined_states(set_xml, seen=None):
    """All `--state` names an aircraft -set.xml (plus its includes) defines."""
    set_xml = Path(set_xml)
    seen = set() if seen is None else seen
    if set_xml in seen or not set_xml.is_file():
        return set()
    seen.add(set_xml)
    return _states_in(ET.parse(set_xml).getroot(), set_xml.parent, seen)


def _flag(cmd, name):
    values = [a.split('=', 1)[1] for a in cmd if a.startswith(f'--{name}=')]
    return values[-1] if values else None


def aircraft_dirs_for(cmd):
    dirs = []
    for a in cmd:
        if a.startswith('--fg-aircraft='):
            dirs += [p for p in a.split('=', 1)[1].split(os.pathsep) if p]
    root = _flag(cmd, 'fg-root')
    if root:
        dirs.append(str(Path(root) / 'Aircraft'))
    return dirs


def check_command(cmd, extra_dirs=()):
    """Raise ValueError if cmd passes `--state=X` that its `--aircraft` doesn't define.

    Returns None when fine (or no --state), or a warning string when the
    aircraft's -set.xml can't be found to verify.
    """
    state = _flag(cmd, 'state')
    if not state:
        return None
    aircraft = _flag(cmd, 'aircraft') or 'c172p'
    set_xml = find_set_xml(aircraft, [*aircraft_dirs_for(cmd), *extra_dirs])
    if set_xml is None:
        return f'could not find {aircraft}-set.xml to verify --state={state}'
    states = defined_states(set_xml)
    if state not in states:
        have = ', '.join(sorted(states)) or 'none'
        raise ValueError(f"Aircraft '{aircraft}' does not define state '{state}' "
                         f'(defined: {have}). FlightGear would ignore it and start in the '
                         'default configuration. Remove --state or add the overlay to '
                         f'{set_xml.name}.')
    return None


if __name__ == '__main__':
    for ac in sys.argv[1:] or ['738-flies']:
        x = find_set_xml(ac, [REPO_AIRCRAFT, r'D:\FlightGear\data\Aircraft'])
        print(ac, '->', x, '->', sorted(defined_states(x)) if x else 'not found')
