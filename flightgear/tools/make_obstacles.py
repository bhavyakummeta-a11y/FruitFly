"""Generate the FlightGear models that show the virtual obstacle cylinders as tornadoes.

The obstacle-avoidance controller (flight_simulator/, scenarios/obstacles.json)
treats obstacles as vertical cylinders that exist only in Python. To see them
in the sim, flight_simulator/fg_scene.py loads one tornado model per obstacle at
runtime over the telnet property server and drives it from properties:

    /fruitfly/obstacles/obstacle[i]/latitude-deg, longitude-deg   position
    /fruitfly/obstacles/obstacle[i]/elevation-ft                  cylinder bottom (MSL)
    /fruitfly/obstacles/obstacle[i]/radius-m, height-m            size
    /fruitfly/obstacles/obstacle[i]/visible                       bool
    /fruitfly/obstacles/obstacle[i]/threat                        0..1 blood-red glow while
                                                                  the fly is reacting to it
    /fruitfly/storm/bolt                                          index of the tornado a
                                                                  lightning bolt is on, or -1
                                                                  (FlyCabin/Nasal/storm.nas)
    /fruitfly/storm/light                                         0..1 lightning lighting up
                                                                  every funnel

The tornado is display only. The fly avoids the cylinder, and every part of the
funnel stays inside it: the funnel is as wide as the cylinder at the top and
narrows towards the ground. The dark ring on the ground is the cylinder's
true footprint.

Writes into flightgear/Aircraft/FlyCabin/Models/Obstacles/:
    tornado.ac          unit tornado (widest radius 1 m, height 1 m): a bent, ragged,
                        near-black funnel, a cap cloud with hanging scud, a debris
                        skirt, three suction vortices, flying wreckage, forked
                        lightning and the footprint "Ring"
    obstacle-{i}.xml    tornado.ac with select/scale/spin/glow animations bound to index i

Run:  python flightgear/tools/make_obstacles.py   (outputs are committed)
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_cabin import Mesh, write_ac  # noqa: E402  (same AC writer + FG->AC axes)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from flight_simulator.tornado_shape import (funnel_radius, funnel_centre,  # noqa: E402,F401
                                            funnel_rings, is_dark_band)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "Aircraft", "FlyCabin", "Models", "Obstacles")
MAX_OBSTACLES = 32   # keep in sync with flight_simulator/fg_scene.py
SIDES = 40
LEVELS = 28
SPIN_DEG_PER_S = 50  # visual spin of the funnel
PROP = "/fruitfly/obstacles/obstacle[{i}]/{name}"
BOLT_PROP = "/fruitfly/storm/bolt"
LIGHT_PROP = "/fruitfly/storm/light"           # 0..1: lightning lighting up the funnels
# Object -> spin in degrees per second about the vertical axis (not listed = fixed).
SPIN = {"Dark": SPIN_DEG_PER_S, "Mid": SPIN_DEG_PER_S, "Debris": SPIN_DEG_PER_S,
        "Vortices": 120, "Chunks": 85, "Scud": -6}
TALL = ("Dark", "Mid", "Cap", "Scud", "Debris", "Vortices", "Chunks", "Bolt")  # scaled by height
ALL = TALL + ("Ring",)
INSIDE = TALL                                   # everything that must stay inside the cylinder


def circle(z, r, centre=(0.0, 0.0), sides=SIDES):
    return [(centre[0] + r * math.cos(2 * math.pi * k / sides),
             centre[1] + r * math.sin(2 * math.pi * k / sides), z) for k in range(sides)]


def noise(i, salt=0.0):
    """Repeatable 0..1 pseudo-random number (the models are committed, so no RNG)."""
    x = math.sin(i * 12.9898 + salt * 78.233) * 43758.5453
    return x - math.floor(x)


def tornado_meshes():
    dark, mid = Mesh("Dark", "dark"), Mesh("Mid", "mid")
    rings = funnel_rings(LEVELS, SIDES)             # ragged, twisted; shared with the scenery course
    for L in range(LEVELS):
        for k in range(SIDES):
            m = dark if is_dark_band(L, k) else mid
            lo, hi = rings[L], rings[L + 1]
            m.quad(lo[k], lo[(k + 1) % SIDES], hi[(k + 1) % SIDES], hi[k])

    cap = Mesh("Cap", "cap")                         # black storm cloud closing the top
    cap.poly(circle(1.0, 1.0))

    # Scud: torn cloud hanging from the cap like teeth, an outer and an inner row.
    scud = Mesh("Scud", "scud")
    for rim, tip, salt in ((1.0, 0.90, 1.0), (0.74, 0.68, 2.0)):
        edge = circle(1.0, rim)
        for k in range(SIDES):
            drop = 0.03 + 0.10 * noise(k, salt)
            ang = 2 * math.pi * (k + 0.5) / SIDES
            scud.poly([edge[k], edge[(k + 1) % SIDES],
                       (tip * math.cos(ang), tip * math.sin(ang), 1.0 - drop)])

    debris = Mesh("Debris", "debris")                # dust skirt around the foot of the funnel
    foot = funnel_centre(0.0)
    inner, outer = circle(0.07, 0.16, foot), circle(0.0, 0.70)
    for k in range(SIDES):
        debris.quad(outer[k], outer[(k + 1) % SIDES], inner[(k + 1) % SIDES], inner[k])

    # Suction vortices: three thin ropes circling the foot of the main funnel.
    vortices = Mesh("Vortices", "vortex")
    for n in range(3):
        base = 2 * math.pi * n / 3
        levels, sides = 8, 8
        tube = []
        for L in range(levels + 1):
            f = L / levels
            ang = base + 1.3 * f                      # each rope twists as it rises
            orbit = 0.46 - 0.16 * f                   # and leans in towards the main funnel
            tube.append(circle(0.40 * f, 0.030 + 0.045 * f,
                               (orbit * math.cos(ang), orbit * math.sin(ang)), sides))
        for L in range(levels):
            for k in range(sides):
                vortices.quad(tube[L][k], tube[L][(k + 1) % sides], tube[L + 1][(k + 1) % sides], tube[L + 1][k])

    # Flying wreckage: dark chunks swept round the funnel. Heights are in units of the
    # tornado's height (far larger than its radius), so the boxes are flattened in z.
    chunks = Mesh("Chunks", "chunk")
    for n in range(56):
        z = 0.03 + 0.62 * noise(n, 3.0)
        size = 0.05 + 0.07 * noise(n, 4.0)
        r = min(funnel_radius(z) + 0.10 + 0.30 * noise(n, 5.0), 0.98 - size)
        ang = 2.399963 * n
        chunks.box(r * math.cos(ang), r * math.sin(ang), z, size, size * (0.5 + 0.5 * noise(n, 6.0)), size * 0.10)

    # Lightning: two forked bolts, shown only during a strike on this tornado.
    bolt = Mesh("Bolt", "bolt")
    strokes = [
        [(0.82, 0.10, 0.97), (0.70, 0.02, 0.84), (0.80, -0.06, 0.70), (0.66, 0.05, 0.52),
         (0.76, 0.12, 0.38), (0.64, 0.00, 0.22), (0.72, -0.05, 0.10), (0.66, 0.02, 0.03)],
        [(-0.60, -0.62, 0.97), (-0.70, -0.50, 0.80), (-0.58, -0.56, 0.66), (-0.66, -0.44, 0.50),
         (-0.54, -0.52, 0.34), (-0.62, -0.42, 0.18), (-0.56, -0.48, 0.03)],
    ]
    for points in strokes:
        for a, b in zip(points, points[1:]):
            bolt.segment(a, b, 0.016)
    for start, end in (((0.66, 0.05, 0.52), (0.50, -0.14, 0.36)), ((0.50, -0.14, 0.36), (0.56, -0.20, 0.24)),
                       ((0.76, 0.12, 0.38), (0.86, 0.22, 0.26)), ((-0.66, -0.44, 0.50), (-0.80, -0.34, 0.38)),
                       ((-0.54, -0.52, 0.34), (-0.44, -0.64, 0.22))):
        bolt.segment(start, end, 0.010)

    ring = Mesh("Ring", "ring")                      # the cylinder's true footprint
    inner, outer = circle(0.002, 1.0), circle(0.002, 1.15)
    for k in range(SIDES):
        ring.quad(inner[k], outer[k], outer[(k + 1) % SIDES], inner[(k + 1) % SIDES])
    return [dark, mid, cap, scud, debris, vortices, chunks, bolt, ring]


MATERIALS = [("dark", (0.05, 0.05, 0.07), 0), ("mid", (0.15, 0.15, 0.18), 0),
             ("cap", (0.06, 0.08, 0.07), 0), ("scud", (0.10, 0.12, 0.11), 0),
             ("debris", (0.22, 0.19, 0.16), 0.30), ("vortex", (0.10, 0.10, 0.12), 0),
             ("chunk", (0.03, 0.03, 0.03), 0), ("bolt", (1.00, 1.00, 0.85), 0),
             ("ring", (0.12, 0.12, 0.12), 0)]


def model_xml(i):
    p = lambda name: PROP.format(i=i, name=name)
    objs = lambda names: "".join(f"<object-name>{o}</object-name>" for o in names)
    spins = ""
    for rate in sorted(set(SPIN.values()), reverse=True):
        names = [o for o in ALL if SPIN.get(o) == rate]
        spins += f"""
  <!-- Turns with sim time ({rate} deg/s; stops when the sim is paused). -->
  <animation>
    <type>rotate</type>
    {objs(names)}
    <property>/sim/time/elapsed-sec</property>
    <factor>{rate}</factor>
    <center><x-m>0</x-m><y-m>0</y-m><z-m>0</z-m></center>
    <axis><x>0</x><y>0</y><z>1</z></axis>
  </animation>
"""
    return f"""<?xml version="1.0"?>
<!-- Generated by flightgear/tools/make_obstacles.py; do not edit. Obstacle index {i}. -->
<PropertyList>
  <path>tornado.ac</path>

  <animation>
    <type>select</type>
    {objs(ALL)}
    <condition><property>{p("visible")}</property></condition>
  </animation>

  <!-- Lightning bolt beside this tornado: only while storm.nas points at index {i}. -->
  <animation>
    <type>select</type>
    <object-name>Bolt</object-name>
    <condition>
      <equals><property>{BOLT_PROP}</property><value>{i}</value></equals>
    </condition>
  </animation>
  <animation>
    <type>material</type>
    <object-name>Bolt</object-name>
    <emission><red>1.0</red><green>1.0</green><blue>0.85</blue></emission>
  </animation>

  <!-- radius: x and y; height: z. Unit tornado, so scale = metres. -->
  <animation>
    <type>scale</type>
    {objs(ALL)}
    <property>{p("radius-m")}</property>
    <x-factor>1</x-factor><x-offset>0</x-offset>
    <y-factor>1</y-factor><y-offset>0</y-offset>
    <z-factor>0</z-factor><z-offset>1</z-offset>
  </animation>
  <animation>
    <type>scale</type>
    {objs(TALL)}
    <property>{p("height-m")}</property>
    <x-factor>0</x-factor><x-offset>1</x-offset>
    <y-factor>0</y-factor><y-offset>1</y-offset>
    <z-factor>1</z-factor><z-offset>0</z-offset>
  </animation>

{spins}
  <!-- Blood-red glow while the fly's looming input comes from this obstacle. -->
  <animation>
    <type>material</type>
    <object-name>Dark</object-name><object-name>Vortices</object-name>
    <emission>
      <factor-prop>{p("threat")}</factor-prop>
      <red>1.0</red><green>0.10</green><blue>0.04</blue>
    </emission>
  </animation>

  <!-- Lightning lights the funnel and the cloud (storm.nas). -->
  <animation>
    <type>material</type>
    <object-name>Mid</object-name><object-name>Cap</object-name><object-name>Scud</object-name>
    <emission>
      <factor-prop>{LIGHT_PROP}</factor-prop>
      <red>0.75</red><green>0.80</green><blue>1.0</blue>
    </emission>
  </animation>
</PropertyList>
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    write_ac(os.path.join(OUT, "tornado.ac"), MATERIALS, tornado_meshes())
    old = os.path.join(OUT, "tower.ac")
    if os.path.exists(old):
        os.remove(old)
    for i in range(MAX_OBSTACLES):
        with open(os.path.join(OUT, f"obstacle-{i}.xml"), "w", newline="\n") as f:
            f.write(model_xml(i))
    print(f"Wrote tornado.ac and obstacle-0..{MAX_OBSTACLES - 1}.xml -> {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
