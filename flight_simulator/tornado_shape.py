"""Shape of the tornado that stands for an obstacle cylinder. Display only.

One definition for both places a tornado is drawn: the live obstacle models
(flightgear/tools/make_obstacles.py) and the fixed scenery course (scenery.py).
Unit size: the obstacle cylinder has radius 1 and height 1; z is height, 0..1.

The funnel never leaves the cylinder the fly avoids. It is as wide as the
cylinder at the top and narrows towards the ground.
"""
import math


def funnel_radius(z):
    """Narrow at the ground, as wide as the obstacle cylinder (1.0) at the top."""
    return 0.16 + 0.84 * z ** 1.7


def funnel_centre(z):
    """Sideways bend of the funnel; zero at the top so it never leaves the cylinder."""
    slack = max(0.0, 1.0 - funnel_radius(z))        # room left inside the unit cylinder
    return (0.8 * slack * 0.45 * math.sin(2.4 * math.pi * z),
            0.8 * slack * 0.35 * math.sin(1.6 * math.pi * z + 1.0))


def funnel_rings(levels, sides):
    """levels+1 rings of `sides` (x, y, z) points from the ground (z=0) to the top (z=1)."""
    rings = []
    for level in range(levels + 1):
        z = level / levels
        r, (cx, cy) = funnel_radius(z), funnel_centre(z)
        rings.append([(cx + r * math.cos(2 * math.pi * k / sides),
                       cy + r * math.sin(2 * math.pi * k / sides), z) for k in range(sides)])
    return rings


def is_dark_band(level, k):
    """Two tones in a helix, so a turning funnel reads as turning."""
    return ((k + 3 * level) // 5) % 2 == 0
