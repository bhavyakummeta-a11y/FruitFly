"""Generate the FlightGear models that show the virtual obstacle cylinders as tornadoes.

The obstacle-avoidance controller (flight_simulator/, scenarios/obstacles.json)
treats obstacles as vertical cylinders that exist only in Python. To see them
in the sim, flight_simulator/fg_scene.py loads one tornado model per obstacle at
runtime over the telnet property server and drives it from properties:

    /fruitfly/obstacles/obstacle[i]/latitude-deg, longitude-deg   position
    /fruitfly/obstacles/obstacle[i]/elevation-ft                  cylinder bottom (MSL)
    /fruitfly/obstacles/obstacle[i]/radius-m, height-m            size
    /fruitfly/obstacles/obstacle[i]/visible                       bool
    /fruitfly/obstacles/obstacle[i]/threat                        0..1 pale glow while
                                                                  the fly is reacting to it
    /fruitfly/storm/bolt                                          index of the tornado a
                                                                  lightning bolt is on, or -1
                                                                  (FlyCabin/Nasal/storm.nas)

The tornado is display only. The fly avoids the cylinder, and every part of the
funnel stays inside it: the funnel is as wide as the cylinder at the top and
narrows towards the ground. The dark ring on the ground is the cylinder's
true footprint.

Writes into flightgear/Aircraft/FlyCabin/Models/Obstacles/:
    tornado.ac          unit tornado (widest radius 1 m, height 1 m): a bent, two-tone
                        funnel, a cap cloud, a debris skirt, a lightning bolt and the
                        footprint "Ring"
    obstacle-{i}.xml    tornado.ac with select/scale/spin/glow animations bound to index i

Run:  python flightgear/tools/make_obstacles.py   (outputs are committed)
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_cabin import Mesh, write_ac  # noqa: E402  (same AC writer + FG->AC axes)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "Aircraft", "FlyCabin", "Models", "Obstacles")
MAX_OBSTACLES = 32   # keep in sync with flight_simulator/fg_scene.py
SIDES = 40
LEVELS = 28
SPIN_DEG_PER_S = 50  # visual spin of the funnel
PROP = "/fruitfly/obstacles/obstacle[{i}]/{name}"
BOLT_PROP = "/fruitfly/storm/bolt"
SPINNING = ("Dark", "Mid", "Debris")           # rotate about the vertical axis
TALL = ("Dark", "Mid", "Cap", "Debris", "Bolt")  # scaled by the obstacle's height
ALL = TALL + ("Ring",)


def funnel_radius(z):
    """Narrow at the ground, as wide as the obstacle cylinder (1.0) at the top."""
    return 0.16 + 0.84 * z ** 1.7


def funnel_centre(z):
    """Sideways bend of the funnel; zero at the top so it never leaves the cylinder."""
    slack = max(0.0, 1.0 - funnel_radius(z))        # room left inside the unit cylinder
    return (0.8 * slack * 0.45 * math.sin(2.4 * math.pi * z),
            0.8 * slack * 0.35 * math.sin(1.6 * math.pi * z + 1.0))


def circle(z, r, centre=(0.0, 0.0)):
    return [(centre[0] + r * math.cos(2 * math.pi * k / SIDES),
             centre[1] + r * math.sin(2 * math.pi * k / SIDES), z) for k in range(SIDES)]


def tornado_meshes():
    dark, mid = Mesh("Dark", "dark"), Mesh("Mid", "mid")
    rings = [circle(L / LEVELS, funnel_radius(L / LEVELS), funnel_centre(L / LEVELS))
             for L in range(LEVELS + 1)]
    for L in range(LEVELS):
        for k in range(SIDES):
            # Two tones in a helix, so the spin is visible.
            m = dark if ((k + 3 * L) // 5) % 2 == 0 else mid
            lo, hi = rings[L], rings[L + 1]
            m.quad(lo[k], lo[(k + 1) % SIDES], hi[(k + 1) % SIDES], hi[k])
    cap = Mesh("Cap", "cap")                         # flat storm cloud closing the top
    cap.poly(circle(1.0, 1.0))
    debris = Mesh("Debris", "debris")                # dust skirt around the foot of the funnel
    foot = funnel_centre(0.0)
    inner, outer = circle(0.045, 0.20, foot), circle(0.0, 0.62)
    for k in range(SIDES):
        debris.quad(outer[k], outer[(k + 1) % SIDES], inner[(k + 1) % SIDES], inner[k])
    bolt = Mesh("Bolt", "bolt")                      # shown only during a lightning strike
    points = [(0.82, 0.10, 0.97), (0.70, 0.02, 0.84), (0.80, -0.06, 0.70), (0.66, 0.05, 0.52),
              (0.76, 0.12, 0.38), (0.64, 0.00, 0.22), (0.72, -0.05, 0.10), (0.66, 0.02, 0.03)]
    for a, b in zip(points, points[1:]):
        bolt.segment(a, b, 0.012)
    bolt.segment(points[3], (0.52, -0.12, 0.36), 0.008)   # a side branch
    ring = Mesh("Ring", "ring")                      # the cylinder's true footprint
    inner, outer = circle(0.002, 1.0), circle(0.002, 1.15)
    for k in range(SIDES):
        ring.quad(inner[k], outer[k], outer[(k + 1) % SIDES], inner[(k + 1) % SIDES])
    return [dark, mid, cap, debris, bolt, ring]


MATERIALS = [("dark", (0.20, 0.21, 0.23), 0), ("mid", (0.38, 0.39, 0.42), 0),
             ("cap", (0.16, 0.17, 0.19), 0), ("debris", (0.36, 0.31, 0.26), 0.35),
             ("bolt", (1.00, 1.00, 0.85), 0), ("ring", (0.12, 0.12, 0.12), 0)]


def model_xml(i):
    p = lambda name: PROP.format(i=i, name=name)
    objs = lambda names: "".join(f"<object-name>{o}</object-name>" for o in names)
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

  <!-- The funnel turns with sim time (it stops when the sim is paused). -->
  <animation>
    <type>rotate</type>
    {objs(SPINNING)}
    <property>/sim/time/elapsed-sec</property>
    <factor>{SPIN_DEG_PER_S}</factor>
    <center><x-m>0</x-m><y-m>0</y-m><z-m>0</z-m></center>
    <axis><x>0</x><y>0</y><z>1</z></axis>
  </animation>

  <!-- Pale glow while the fly's looming input comes from this obstacle. -->
  <animation>
    <type>material</type>
    <object-name>Dark</object-name><object-name>Mid</object-name>
    <emission>
      <factor-prop>{p("threat")}</factor-prop>
      <red>0.55</red><green>0.65</green><blue>0.95</blue>
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
