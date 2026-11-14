"""Generate the fruit-fly passenger cabin for the FlightGear Boeing 737-800.

Writes into flightgear/Aircraft/FlyCabin/Models/:
  cabin.ac         cabin shell (floor, walls with window holes, ceiling,
                   overhead bins, bulkheads) plus the 3+3 economy seats
  fly.ac           one low-poly Drosophila passenger (body, red eyes, wings)
  fly-group{0,1,2}.xml   the fly model with wing/head animations bound to
                   /fruitfly/passengers/group[n]/... (three groups so the
                   cabin doesn't move in lockstep)
  738-flies.xml    top-level aircraft model: the stock 737-800 + cabin + flies
  attendant.ac/.xml  the fly flight attendant + snack cart (running gag, no brain)
  ../Nasal/cabin_rows.nas  row positions for the attendant script (cabin_show.nas)

Run:  python flightgear/tools/make_cabin.py
Re-run after changing any constant below. The outputs are committed so
teammates don't need to run it.

Coordinates: everything is built in FlightGear model axes
(x = back, y = right, z = up, metres, same origin as 737-800.ac) and converted
to AC3D axes on write (ac = (x, z, -y)).
Fuselage numbers were measured from 737-800.ac: nose x=-19.8, tail x=18.3,
window band x=-14.0..10.6, fuselage circle centre z~0.68, outer radius ~1.88.
"""
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "Aircraft", "FlyCabin", "Models")

# ---- cabin geometry (FG model coords) ---------------------------------------
X_FRONT, X_REAR = -13.4, 11.2   # front / rear bulkheads (doors are outside)
Z_C, R_IN = 0.68, 1.72          # fuselage centre height, inner wall radius
Z_FLOOR = 0.10
Z_CEIL = 2.18
BIN_Y = 0.92                     # inner face of overhead bins
BIN_Z = 1.72                     # underside of overhead bins
WIN_Z = (0.88, 1.24)             # window holes, vertical extent
WIN_PITCH, WIN_W = 0.508, 0.24   # 20 in window pitch, like the real 737
WIN_X = (-13.0, 10.4)

ROW_FIRST, ROW_PITCH, N_ROWS = -12.6, 0.79, 29   # 31 in pitch
OVERWING_GAP_AFTER = 13          # extra legroom row at the overwing exits
SEAT_Y = (0.49, 0.95, 1.41)      # seat centres, mirrored to the left side
SEAT_W, SEAT_D = 0.43, 0.46
CUSHION_Z = Z_FLOOR + 0.42
BACK_H = 0.70
EMPTY_FRACTION = 0.06            # a few empty seats look more real
SEED = 1914                      # Morgan's fly room, roughly


def to_ac(p):
    x, y, z = p
    return (x, z, -y)


class Mesh:
    def __init__(self, name, mat):
        self.name, self.mat = name, mat
        self.verts, self.faces = [], []

    def quad(self, a, b, c, d):
        i = len(self.verts)
        self.verts += [a, b, c, d]
        self.faces.append([i, i + 1, i + 2, i + 3])

    def poly(self, pts):
        i = len(self.verts)
        self.verts += list(pts)
        self.faces.append(list(range(i, i + len(pts))))

    def box(self, cx, cy, cz, sx, sy, sz):
        x0, x1 = cx - sx / 2, cx + sx / 2
        y0, y1 = cy - sy / 2, cy + sy / 2
        z0, z1 = cz - sz / 2, cz + sz / 2
        v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                  (2, 3, 7, 6), (1, 2, 6, 5), (3, 0, 4, 7)):
            self.quad(*[v[k] for k in f])

    def segment(self, a, b, r):
        """Thin square tube from point a to point b."""
        d = [b[i] - a[i] for i in range(3)]
        n = math.sqrt(sum(c * c for c in d)) or 1.0
        d = [c / n for c in d]
        ref = (0, 0, 1) if abs(d[2]) < 0.9 else (1, 0, 0)
        u = [d[1] * ref[2] - d[2] * ref[1], d[2] * ref[0] - d[0] * ref[2], d[0] * ref[1] - d[1] * ref[0]]
        un = math.sqrt(sum(c * c for c in u))
        u = [c / un * r for c in u]
        v = [d[1] * u[2] - d[2] * u[1], d[2] * u[0] - d[0] * u[2], d[0] * u[1] - d[1] * u[0]]
        corners = [(1, 1), (-1, 1), (-1, -1), (1, -1)]
        ring = lambda p: [tuple(p[i] + cu * u[i] + cv * v[i] for i in range(3)) for cu, cv in corners]
        ra, rb = ring(a), ring(b)
        for k in range(4):
            self.quad(ra[k], ra[(k + 1) % 4], rb[(k + 1) % 4], rb[k])

    def ellipsoid(self, c, r, seg=10, rings=7, pitch_deg=0.0):
        """Ellipsoid with radii r=(rx,ry,rz), pitched about y (nose-down +)."""
        cp, sp = math.cos(math.radians(pitch_deg)), math.sin(math.radians(pitch_deg))
        base = len(self.verts)
        grid = []
        for i in range(rings + 1):
            th = math.pi * i / rings
            row = []
            for j in range(seg):
                ph = 2 * math.pi * j / seg
                x = r[0] * math.sin(th) * math.cos(ph)
                y = r[1] * math.sin(th) * math.sin(ph)
                z = r[2] * math.cos(th)
                x, z = x * cp + z * sp, -x * sp + z * cp
                row.append(len(self.verts))
                self.verts.append((c[0] + x, c[1] + y, c[2] + z))
            grid.append(row)
        for i in range(rings):
            for j in range(seg):
                a, b = grid[i][j], grid[i][(j + 1) % seg]
                c2, d = grid[i + 1][(j + 1) % seg], grid[i + 1][j]
                self.faces.append([a, d, c2, b])
        return base


def write_ac(path, materials, meshes):
    with open(path, "w", newline="\n") as f:
        f.write("AC3Db\n")
        for name, rgb, trans in materials:
            r, g, b = rgb
            f.write(f'MATERIAL "{name}" rgb {r:.3f} {g:.3f} {b:.3f}  amb {r:.3f} {g:.3f} {b:.3f}  '
                    f"emis 0 0 0  spec 0.1 0.1 0.1  shi 10  trans {trans:.2f}\n")
        mats = [m[0] for m in materials]
        f.write(f"OBJECT world\nkids {len(meshes)}\n")
        for m in meshes:
            f.write(f'OBJECT poly\nname "{m.name}"\nnumvert {len(m.verts)}\n')
            for p in m.verts:
                f.write("%.4f %.4f %.4f\n" % to_ac(p))
            f.write(f"numsurf {len(m.faces)}\n")
            for face in m.faces:
                # 0x30 = smooth + two-sided, so winding never hides a face
                f.write(f"SURF 0x30\nmat {mats.index(m.mat)}\nrefs {len(face)}\n")
                for k in face:
                    f.write(f"{k} 0 0\n")
            f.write("kids 0\n")


# ---- cabin -----------------------------------------------------------------
def wall_y(z):
    return math.sqrt(max(R_IN ** 2 - (z - Z_C) ** 2, 0.0))


def build_cabin():
    floor, wall, ceil, bins, seats, cushions = (
        Mesh("CabinFloor", "carpet"), Mesh("CabinWall", "wall"),
        Mesh("CabinCeiling", "ceiling"), Mesh("OverheadBins", "bins"),
        Mesh("SeatFrames", "seatframe"), Mesh("SeatCushions", "seatcloth"))

    yf = wall_y(Z_FLOOR)
    floor.quad((X_FRONT, -yf, Z_FLOOR), (X_REAR, -yf, Z_FLOOR),
               (X_REAR, yf, Z_FLOOR), (X_FRONT, yf, Z_FLOOR))
    ceil.quad((X_FRONT, -BIN_Y, Z_CEIL), (X_REAR, -BIN_Y, Z_CEIL),
              (X_REAR, BIN_Y, Z_CEIL), (X_FRONT, BIN_Y, Z_CEIL))

    # wall: x-strips; inside the window band, leave a hole every WIN_PITCH
    z_levels = [Z_FLOOR, 0.40, 0.65, WIN_Z[0], WIN_Z[1], 1.45, BIN_Z]
    xs = [X_FRONT]
    x = WIN_X[0]
    while x + WIN_W <= WIN_X[1]:
        xs += [x, x + WIN_W]
        x += WIN_PITCH
    xs.append(X_REAR)
    for side in (-1, 1):
        for zi in range(len(z_levels) - 1):
            z0, z1 = z_levels[zi], z_levels[zi + 1]
            in_band = (z0, z1) == WIN_Z
            for xi in range(len(xs) - 1):
                xa, xb = xs[xi], xs[xi + 1]
                is_window = in_band and xi % 2 == 1
                if is_window:
                    continue
                wall.quad((xa, side * wall_y(z0), z0), (xb, side * wall_y(z0), z0),
                          (xb, side * wall_y(z1), z1), (xa, side * wall_y(z1), z1))
        # overhead bin: underside, face, and the curved wall above it
        yw = wall_y(BIN_Z)
        bins.quad((X_FRONT, side * BIN_Y, BIN_Z), (X_REAR, side * BIN_Y, BIN_Z),
                  (X_REAR, side * yw, BIN_Z), (X_FRONT, side * yw, BIN_Z))
        bins.quad((X_FRONT, side * BIN_Y, BIN_Z), (X_REAR, side * BIN_Y, BIN_Z),
                  (X_REAR, side * BIN_Y, Z_CEIL), (X_FRONT, side * BIN_Y, Z_CEIL))
        # bin door seams every ~1.6 m
        x = X_FRONT
        while x < X_REAR - 0.1:
            bins.box(x, side * (BIN_Y - 0.005), (BIN_Z + Z_CEIL) / 2, 0.02, 0.01, Z_CEIL - BIN_Z)
            x += 1.6

    # bulkheads (solid, so the cockpit and tail look closed from the cabin)
    for xb in (X_FRONT, X_REAR):
        pts = []
        for k in range(17):
            z = Z_FLOOR + (Z_CEIL - Z_FLOOR) * k / 16
            pts.append((xb, wall_y(z), z))
        for k in range(16, -1, -1):
            z = Z_FLOOR + (Z_CEIL - Z_FLOOR) * k / 16
            pts.append((xb, -wall_y(z), z))
        wall.poly(pts)

    # seats
    rows = []
    x = ROW_FIRST
    for r in range(N_ROWS):
        rows.append(x)
        x += ROW_PITCH + (0.35 if r == OVERWING_GAP_AFTER else 0.0)
    seat_pos = []
    for xr in rows:
        for side in (-1, 1):
            for yc in SEAT_Y:
                y = side * yc
                cushions.box(xr, y, CUSHION_Z - 0.05, SEAT_D, SEAT_W - 0.04, 0.10)
                # backrest, leaned back 12 deg via a sheared box
                bx = xr + SEAT_D / 2 + 0.03
                cushions.quad((bx, y - SEAT_W / 2 + 0.02, CUSHION_Z),
                              (bx, y + SEAT_W / 2 - 0.02, CUSHION_Z),
                              (bx + 0.15, y + SEAT_W / 2 - 0.02, CUSHION_Z + BACK_H),
                              (bx + 0.15, y - SEAT_W / 2 + 0.02, CUSHION_Z + BACK_H))
                seats.quad((bx + 0.06, y - SEAT_W / 2 + 0.02, CUSHION_Z),
                           (bx + 0.06, y + SEAT_W / 2 - 0.02, CUSHION_Z),
                           (bx + 0.21, y + SEAT_W / 2 - 0.02, CUSHION_Z + BACK_H),
                           (bx + 0.21, y - SEAT_W / 2 + 0.02, CUSHION_Z + BACK_H))
                seat_pos.append((xr, y, CUSHION_Z))
            # armrests + legs per triple
            for yc in (SEAT_Y[0] - SEAT_W / 2, SEAT_Y[0] + SEAT_W / 2,
                       SEAT_Y[1] + SEAT_W / 2, SEAT_Y[2] + SEAT_W / 2):
                seats.box(xr + 0.03, side * yc, CUSHION_Z + 0.18, SEAT_D - 0.06, 0.05, 0.05)
            for yc in (SEAT_Y[0], SEAT_Y[2]):
                seats.box(xr, side * yc, (Z_FLOOR + CUSHION_Z) / 2, 0.05, 0.05, CUSHION_Z - Z_FLOOR)

    materials = [("carpet", (0.20, 0.24, 0.38), 0), ("wall", (0.86, 0.85, 0.80), 0),
                 ("ceiling", (0.93, 0.93, 0.90), 0), ("bins", (0.80, 0.80, 0.77), 0),
                 ("seatframe", (0.25, 0.25, 0.27), 0), ("seatcloth", (0.10, 0.22, 0.55), 0)]
    write_ac(os.path.join(OUT, "cabin.ac"), materials,
             [floor, wall, ceil, bins, seats, cushions])
    return seat_pos, rows


# ---- fly -------------------------------------------------------------------
# Local frame: origin at the seat cushion top centre, fly faces -x (forward),
# sitting upright like a person: abdomen on the cushion, thorax above, head on top.
WING_ROOT_Y, WING_ROOT = 0.07, (0.13, 0.62)   # (x, z) of the wing hinge


def build_fly():
    body, abd_band, eyes, legs = (Mesh("Body", "chitin"), Mesh("AbdomenBands", "band"),
                                  Mesh("Eyes", "eye"), Mesh("Legs", "leg"))
    head = Mesh("Head", "chitin")
    body.ellipsoid((0.06, 0, 0.24), (0.17, 0.18, 0.26), pitch_deg=-15)    # abdomen
    for k, zb in enumerate((0.14, 0.24, 0.34)):                          # dark tergite stripes
        abd_band.ellipsoid((0.075 - 0.025 * k, 0, zb), (0.172, 0.183, 0.035), seg=10, rings=4)
    body.ellipsoid((0.00, 0, 0.55), (0.17, 0.17, 0.17))                 # thorax
    head.ellipsoid((-0.05, 0, 0.80), (0.11, 0.14, 0.11))                # head
    for s in (-1, 1):
        eyes.ellipsoid((-0.08, s * 0.11, 0.82), (0.08, 0.06, 0.09))     # compound eyes
        head.box(-0.15, s * 0.04, 0.88, 0.03, 0.02, 0.10)              # antennae
        # 3 legs a side, hanging over the seat edge like a person's legs
        for k, (hip_x, hip_z) in enumerate(((-0.10, 0.50), (-0.02, 0.44), (0.05, 0.36))):
            spread = 0.13 + 0.04 * k
            hip = (hip_x, s * 0.12, hip_z)
            knee = (-0.30 + 0.03 * k, s * spread, 0.22 + 0.04 * k)
            foot = (-0.38 + 0.03 * k, s * (spread + 0.02), -0.40)
            legs.segment(hip, knee, 0.025)
            legs.segment(knee, foot, 0.02)

    wings = []
    for s, name in ((1, "WingR"), (-1, "WingL")):
        w = Mesh(name, "wing")
        rx, rz = WING_ROOT
        pts = []
        for k in range(12):           # long ellipse, pointing up and slightly out/back
            t = 2 * math.pi * k / 12
            u = 0.24 + 0.24 * math.cos(t)    # along span 0..0.48
            v = 0.08 * math.sin(t)           # chord
            pts.append((rx + 0.10 * u / 0.48 + v, s * (WING_ROOT_Y + 0.10 * u), rz + u))
        w.poly(pts)
        wings.append(w)

    materials = [("chitin", (0.72, 0.55, 0.30), 0), ("band", (0.22, 0.15, 0.10), 0),
                 ("eye", (0.78, 0.06, 0.04), 0), ("leg", (0.30, 0.22, 0.14), 0),
                 ("wing", (0.85, 0.90, 0.95), 0.55)]
    write_ac(os.path.join(OUT, "fly.ac"), materials,
             [body, abd_band, eyes, legs, head] + wings)


# ---- flight attendant + snack cart (running gag, display only) ----------------
# A fly flight attendant walks the aisle pushing a cart and hands each row water,
# poop or a slice of rotten banana. No brain: cabin_show.nas scripts it. Local frame:
# origin on the cabin floor at the aisle centre, the attendant faces -x (forward)
# before cabin_show.nas turns her; the cart sits on her +x side.
ATT_START_X = X_FRONT + 0.30            # parked by the front galley between passes
ATT_SERVE_OFFSET = -0.05                # she stands this far (x) from a row's seat centre
CART_X, CART_LEN, CART_W, CART_H = 0.55, 0.60, 0.32, 0.86
HAND = (-0.34, 0.0, 1.08)               # where a handed-out item starts
HIP_Z = 0.72


def build_attendant():
    m = {k: Mesh(n, mat) for k, n, mat in (
        ("body", "AttBody", "chitin"), ("bands", "AttBands", "band"), ("eyes", "AttEyes", "eye"),
        ("head", "AttHead", "chitin"), ("uniform", "AttUniform", "uniform"),
        ("scarf", "AttScarf", "scarf"), ("apron", "AttApron", "apron"), ("hat", "AttHat", "uniform"),
        ("arms", "AttArms", "leg"), ("legsA", "AttLegsA", "leg"), ("legsB", "AttLegsB", "leg"),
        ("wingR", "AttWingR", "wing"), ("wingL", "AttWingL", "wing"),
        ("cup", "ItemWaterCup", "cup"), ("water", "ItemWater", "water"),
        ("poop", "ItemPoop", "poop"), ("banana", "ItemBanana", "banana"), ("rot", "ItemBananaRot", "poop"),
        ("cart", "Cart", "cart"), ("cartTrim", "CartTrim", "scarf"), ("wheels", "CartWheels", "leg"),
        ("stock", "CartStock", "cup"), ("stockWater", "CartStockWater", "water"),
        ("stockPoop", "CartStockPoop", "poop"), ("stockBanana", "CartStockBanana", "banana"))}

    # standing fly, upright like a person; navy jacket over the thorax, apron, red scarf, pillbox hat
    m["body"].ellipsoid((0.03, 0, 0.92), (0.15, 0.16, 0.24), pitch_deg=-8)          # abdomen
    for k, zb in enumerate((0.80, 0.90, 1.00)):
        m["bands"].ellipsoid((0.04, 0, zb), (0.152, 0.163, 0.03), seg=10, rings=4)
    m["apron"].box(-0.15, 0, 0.88, 0.03, 0.22, 0.32)
    m["uniform"].ellipsoid((0.0, 0, 1.25), (0.16, 0.17, 0.16))                       # jacket = thorax
    m["scarf"].ellipsoid((-0.02, 0, 1.39), (0.12, 0.13, 0.04), seg=10, rings=4)
    m["head"].ellipsoid((-0.04, 0, 1.51), (0.10, 0.13, 0.10))
    m["hat"].ellipsoid((0.0, 0, 1.63), (0.08, 0.08, 0.035), seg=10, rings=4)
    for s in (-1, 1):
        m["eyes"].ellipsoid((-0.07, s * 0.10, 1.53), (0.07, 0.055, 0.08))
        m["head"].box(-0.13, s * 0.04, 1.60, 0.03, 0.02, 0.09)                    # antennae
        # front legs = arms, reaching forward to hold the item
        shoulder, elbow, hand = (-0.06, s * 0.12, 1.22), (-0.22, s * 0.15, 1.02), (HAND[0] + 0.04, s * 0.06, HAND[2])
        m["arms"].segment(shoulder, elbow, 0.022)
        m["arms"].segment(elbow, hand, 0.018)
        # mid and hind legs stand on the floor; A/B alternate when she walks
        for k, (hx, kx, fx) in enumerate(((0.0, -0.12, -0.06), (0.06, 0.14, 0.10))):
            group = "legsA" if (s > 0) == (k == 0) else "legsB"
            hip, knee, foot = (hx, s * 0.10, HIP_Z), (kx, s * 0.18, 0.38), (fx, s * 0.16, 0.0)
            m[group].segment(hip, knee, 0.025)
            m[group].segment(knee, foot, 0.02)
    for s, key in ((1, "wingR"), (-1, "wingL")):                                    # folded down her back
        pts = []
        for k in range(12):
            t = 2 * math.pi * k / 12
            u = 0.22 + 0.22 * math.cos(t)
            v = 0.07 * math.sin(t)
            pts.append((0.14 + 0.05 * u / 0.44 + v, s * (0.07 + 0.08 * u), 1.32 - 0.9 * u))
        m[key].poly(pts)

    # the items she hands out (one shown at a time, at HAND)
    hx, hy, hz = HAND
    m["cup"].box(hx, hy, hz + 0.02, 0.07, 0.07, 0.10)
    m["water"].box(hx, hy, hz + 0.07, 0.072, 0.072, 0.01)
    for dz, r, h in ((0.0, 0.07, 0.035), (0.04, 0.05, 0.03), (0.075, 0.03, 0.025)):  # the classic swirl
        m["poop"].ellipsoid((hx, hy, hz + dz), (r, r, h), seg=10, rings=5)
    m["banana"].ellipsoid((hx, hy, hz + 0.02), (0.035, 0.12, 0.03), seg=10, rings=5)
    for dy in (-0.06, 0.0, 0.05):
        m["rot"].ellipsoid((hx - 0.03, hy + dy, hz + 0.03), (0.012, 0.018, 0.012), seg=6, rings=3)

    # the cart, stocked on top
    cx, ch = CART_X, CART_H
    m["cart"].box(cx, 0, 0.06 + ch / 2, CART_LEN, CART_W, ch)
    for z in (0.30, 0.55):
        m["cartTrim"].box(cx, 0, z, CART_LEN + 0.01, CART_W + 0.01, 0.03)
    for dx in (-0.24, 0.24):
        for dy in (-0.12, 0.12):
            m["wheels"].box(cx + dx, dy, 0.03, 0.07, 0.03, 0.06)
    top = 0.06 + ch
    for i, dx in enumerate((-0.22, -0.13, -0.04)):
        for dy in (-0.08, 0.08):
            m["stock"].box(cx + dx, dy, top + 0.05, 0.07, 0.07, 0.10)
            m["stockWater"].box(cx + dx, dy, top + 0.10, 0.072, 0.072, 0.01)
    for dx, dy in ((0.07, -0.08), (0.07, 0.08), (0.16, 0.0)):
        for dz, r, h in ((0.0, 0.06, 0.03), (0.035, 0.042, 0.025), (0.065, 0.025, 0.02)):
            m["stockPoop"].ellipsoid((cx + dx, dy, top + 0.03 + dz), (r, r, h), seg=8, rings=4)
    m["stockBanana"].ellipsoid((cx + 0.24, 0, top + 0.03), (0.03, 0.11, 0.03), seg=8, rings=4)

    materials = [("chitin", (0.72, 0.55, 0.30), 0), ("band", (0.22, 0.15, 0.10), 0),
                 ("eye", (0.78, 0.06, 0.04), 0), ("leg", (0.30, 0.22, 0.14), 0),
                 ("wing", (0.85, 0.90, 0.95), 0.55), ("uniform", (0.08, 0.12, 0.32), 0),
                 ("scarf", (0.80, 0.10, 0.12), 0), ("apron", (0.95, 0.95, 0.92), 0),
                 ("cup", (0.97, 0.97, 0.97), 0), ("water", (0.25, 0.55, 0.95), 0.25),
                 ("poop", (0.36, 0.22, 0.10), 0), ("banana", (0.85, 0.72, 0.20), 0),
                 ("cart", (0.72, 0.74, 0.76), 0)]
    write_ac(os.path.join(OUT, "attendant.ac"), materials, list(m.values()))
    return {k: v.name for k, v in m.items()}


def attendant_xml(names):
    obj = lambda keys: "".join(f"<object-name>{names[k]}</object-name>" for k in keys)
    cart = ["cart", "cartTrim", "wheels", "stock", "stockWater", "stockPoop", "stockBanana"]
    items = ["cup", "water", "poop", "banana", "rot"]
    fly = ["body", "bands", "eyes", "head", "uniform", "scarf", "apron", "hat", "arms",
           "legsA", "legsB", "wingR", "wingL"]
    p = "/fruitfly/cabin/attendant/"
    # FlightGear nests animations in the order listed: the first is the outermost transform.
    return f"""<?xml version="1.0"?>
<!-- Generated by flightgear/tools/make_cabin.py - edit the generator, not this file.
     Running gag: the fly flight attendant and her snack cart. No brain; cabin_show.nas
     scripts the properties under {p}. Display only. -->
<PropertyList>
  <path>attendant.ac</path>
  <animation><type>translate</type>{obj(fly + items + cart)}
    <property>{p}x-m</property><axis><x>1</x><y>0</y><z>0</z></axis></animation>
  <animation><type>translate</type>{obj(fly + items)}
    <property>{p}bob-m</property><axis><x>0</x><y>0</y><z>1</z></axis></animation>
  <animation><type>rotate</type>{obj(fly + items)}
    <property>{p}turn-deg</property>
    <center><x-m>0</x-m><y-m>0</y-m><z-m>0</z-m></center><axis><x>0</x><y>0</y><z>1</z></axis></animation>
  <animation><type>rotate</type>{obj(["legsA"])}
    <property>{p}stride-deg</property>
    <center><x-m>0</x-m><y-m>0</y-m><z-m>{HIP_Z}</z-m></center><axis><x>0</x><y>1</y><z>0</z></axis></animation>
  <animation><type>rotate</type>{obj(["legsB"])}
    <property>{p}stride-deg</property><factor>-1</factor>
    <center><x-m>0</x-m><y-m>0</y-m><z-m>{HIP_Z}</z-m></center><axis><x>0</x><y>1</y><z>0</z></axis></animation>
  <animation><type>rotate</type>{obj(["wingR"])}
    <property>{p}flap-norm</property><factor>-60</factor>
    <center><x-m>0.14</x-m><y-m>0.07</y-m><z-m>1.32</z-m></center><axis><x>1</x><y>0</y><z>0</z></axis></animation>
  <animation><type>rotate</type>{obj(["wingL"])}
    <property>{p}flap-norm</property><factor>60</factor>
    <center><x-m>0.14</x-m><y-m>-0.07</y-m><z-m>1.32</z-m></center><axis><x>1</x><y>0</y><z>0</z></axis></animation>
  <animation><type>translate</type>{obj(items)}
    <property>{p}serve-m</property><axis><x>-1</x><y>0</y><z>0</z></axis></animation>
  <!-- item: 0 hands empty, 1 water, 2 poop, 3 rotten banana -->
  <animation><type>select</type>{obj(["cup", "water"])}
    <condition><equals><property>{p}item</property><value>1</value></equals></condition></animation>
  <animation><type>select</type>{obj(["poop"])}
    <condition><equals><property>{p}item</property><value>2</value></equals></condition></animation>
  <animation><type>select</type>{obj(["banana", "rot"])}
    <condition><equals><property>{p}item</property><value>3</value></equals></condition></animation>
</PropertyList>
"""


ROWS_NAS = """# Generated by flightgear/tools/make_cabin.py - edit the generator, not this file.
# Cabin layout for cabin_show.nas (FlightGear model x, metres, + = toward the tail).
var ROWS = [{rows}];
var START_X = {start:.3f};
var SERVE_OFFSET = {offset:.3f};
"""


FLY_XML = """<?xml version="1.0"?>
<!-- Generated by flightgear/tools/make_cabin.py - edit the generator, not this file. -->
<PropertyList>
  <path>fly.ac</path>
  <!-- Wings spread with /fruitfly/passengers/group[{g}]/flap-norm (0 folded .. 1 spread).
       fruitfly.nas turns /fruitfly/passengers/activity into these per-group values. -->
  <animation>
    <type>rotate</type>
    <object-name>WingR</object-name>
    <property>/fruitfly/passengers/group[{g}]/flap-norm</property>
    <factor>-70</factor>
    <center><x-m>{rx}</x-m><y-m>{ry}</y-m><z-m>{rz}</z-m></center>
    <axis><x>1</x><y>0</y><z>0</z></axis>
  </animation>
  <animation>
    <type>rotate</type>
    <object-name>WingL</object-name>
    <property>/fruitfly/passengers/group[{g}]/flap-norm</property>
    <factor>70</factor>
    <center><x-m>{rx}</x-m><y-m>-{ry}</y-m><z-m>{rz}</z-m></center>
    <axis><x>1</x><y>0</y><z>0</z></axis>
  </animation>
  <animation>
    <type>rotate</type>
    <object-name>Head</object-name>
    <object-name>Eyes</object-name>
    <property>/fruitfly/passengers/group[{g}]/head-turn-deg</property>
    <center><x-m>0</x-m><y-m>0</y-m><z-m>0.70</z-m></center>
    <axis><x>0</x><y>0</y><z>1</z></axis>
  </animation>
</PropertyList>
"""

PILOT_XML = """<?xml version="1.0"?>
<!-- Generated by flightgear/tools/make_cabin.py - edit the generator, not this file.
     The fly pilot in the captain's seat. Its brain is the controller flying the plane:
     the Python controller writes /fruitfly/pilot/{{active,power,steer,escape}} from the
     brain's descending-neuron rates, and fruitfly.nas turns them into the values below.
     Display only - nothing here touches the flight controls. -->
<PropertyList>
  <path>fly.ac</path>
  <!-- Hidden in the stock captain view (its eye point is inside the fly's head). -->
  <animation>
    <type>select</type>
    <object-name>Body</object-name><object-name>AbdomenBands</object-name><object-name>Eyes</object-name>
    <object-name>Legs</object-name><object-name>Head</object-name>
    <object-name>WingR</object-name><object-name>WingL</object-name>
    <condition><not><equals><property>/sim/current-view/view-number</property><value>0</value></equals></not></condition>
  </animation>
  <animation>
    <type>rotate</type>
    <object-name>WingR</object-name>
    <property>/fruitfly/pilot/flap-norm</property>
    <factor>-70</factor>
    <center><x-m>{rx}</x-m><y-m>{ry}</y-m><z-m>{rz}</z-m></center>
    <axis><x>1</x><y>0</y><z>0</z></axis>
  </animation>
  <animation>
    <type>rotate</type>
    <object-name>WingL</object-name>
    <property>/fruitfly/pilot/flap-norm</property>
    <factor>70</factor>
    <center><x-m>{rx}</x-m><y-m>-{ry}</y-m><z-m>{rz}</z-m></center>
    <axis><x>1</x><y>0</y><z>0</z></axis>
  </animation>
  <animation>
    <type>rotate</type>
    <object-name>Head</object-name>
    <object-name>Eyes</object-name>
    <property>/fruitfly/pilot/head-turn-deg</property>
    <center><x-m>0</x-m><y-m>0</y-m><z-m>0.70</z-m></center>
    <axis><x>0</x><y>0</y><z>1</z></axis>
  </animation>
  <!-- Whole fly: leans into turns (steering DNs) and hops on a Giant Fibre spike. -->
  <animation>
    <type>rotate</type>
    <object-name>Body</object-name><object-name>AbdomenBands</object-name><object-name>Eyes</object-name>
    <object-name>Legs</object-name><object-name>Head</object-name>
    <object-name>WingR</object-name><object-name>WingL</object-name>
    <property>/fruitfly/pilot/lean-deg</property>
    <center><x-m>0</x-m><y-m>0</y-m><z-m>0.10</z-m></center>
    <axis><x>-1</x><y>0</y><z>0</z></axis>
  </animation>
  <animation>
    <type>translate</type>
    <object-name>Body</object-name><object-name>AbdomenBands</object-name><object-name>Eyes</object-name>
    <object-name>Legs</object-name><object-name>Head</object-name>
    <object-name>WingR</object-name><object-name>WingL</object-name>
    <property>/fruitfly/pilot/hop-m</property>
    <axis><x>0</x><y>0</y><z>1</z></axis>
  </animation>
</PropertyList>
"""

# Stock cockpit objects (Models/cockpit.ac) hidden in the "Cockpit: fly pilot" view so the
# windshield is a clear, wide view outside: the overhead panel (Plane.004) with all its
# switches/knobs (everything above 1.38 m over the seats) and the centre windshield post
# (Cube), plus the cockpit shell (dorrhfront: roof, side walls and window frames) for an
# open, panoramic view. Found by bounding box; the stock captain view still shows them.
CLEAR_VIEW_HIDE = [
    'dorrhfront',
    'batt-cover', 'BatterySw', 'BusTransferSw', 'Circle.175', 'Circle.176', 'Circle.177',
    'Circle.178', 'Circle.179', 'Circle.180', 'Circle.181', 'Circle.182', 'Circle.183',
    'Circle.184', 'Circle.185', 'Circle.186', 'Circle.187', 'Circle.188', 'Circle.189',
    'Circle.190', 'Circle.191', 'Circle.192', 'Circle.193', 'Circle.194', 'Circle.195',
    'Circle.196', 'Circle.197', 'Circle.198', 'Circle.199', 'Circle.200', 'Circle.201',
    'Circle.202', 'Circle.203', 'Circle.204', 'Circle.205', 'Circle.206', 'Circle.207',
    'Circle.208', 'Circle.209', 'Circle.210', 'Circle.211', 'Circle.212', 'Circle.213',
    'Circle.214', 'Circle.215', 'Circle.216', 'Circle.223', 'Circle.224', 'Circle.225',
    'Circle.226', 'Drive1Sw', 'Drive2Sw', 'engNo1start', 'engNo2start', 'FuelPumpCL',
    'FuelPumpCR', 'FuelPumpLAft', 'FuelPumpLFwd', 'FuelPumpRAft', 'FuelPumpRFwd', 'GalleySw',
    'knob1.028', 'knob1.030', 'knob1.031', 'knob1.032', 'knob1.033', 'knob1.034',
    'knob1.035', 'knob1.036', 'knob1.037', 'knob1.038', 'knob1.039', 'knob1.040',
    'Plane.004', 'StbyPwSw', 'Cube',
]

# Captain's seat: the stock captain eye point is (view axes) x -0.51, y 1.28, z -17.18,
# i.e. model x -17.18 (forward), y -0.51 (left), z 1.28 (up). Put the fly's eyes there.
PILOT_SEAT = (-17.10, -0.51, 0.46)

TOP_XML_HEAD = """<?xml version="1.0"?>
<!-- Generated by flightgear/tools/make_cabin.py - edit the generator, not this file.
     The stock FGAddon 737-800 model with our cabin and fly passengers added inside. -->
<PropertyList>
  <path>cabin.ac</path>

  <model>
    <name>Boeing737-800</name>
    <path>Aircraft/737-800/Models/738.xml</path>
  </model>

  <!-- The fly pilot (its brain flies the plane). -->
  <model><name>flypilot</name><path>Aircraft/FlyCabin/Models/fly-pilot.xml</path><offsets><x-m>{px:.3f}</x-m><y-m>{py:.3f}</y-m><z-m>{pz:.3f}</z-m></offsets></model>

  <!-- Clear view: hide the overhead panel and centre post while /fruitfly/pilot/clear-view
       is true (fruitfly.nas sets it in the "Cockpit: fly pilot" view). -->
  <animation>
    <type>select</type>
{hide}
    <condition><not><property>/fruitfly/pilot/clear-view</property></not></condition>
  </animation>

  <!-- One <model> per occupied seat. -->
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    seats, rows = build_cabin()
    build_fly()
    att_names = build_attendant()
    with open(os.path.join(OUT, "attendant.xml"), "w", newline="\n") as f:
        f.write(attendant_xml(att_names))
    nas_dir = os.path.join(OUT, "..", "Nasal")
    with open(os.path.join(nas_dir, "cabin_rows.nas"), "w", newline="\n") as f:
        f.write(ROWS_NAS.format(rows=", ".join(f"{x:.3f}" for x in rows),
                                start=ATT_START_X, offset=ATT_SERVE_OFFSET))
    for g in range(3):
        with open(os.path.join(OUT, f"fly-group{g}.xml"), "w", newline="\n") as f:
            f.write(FLY_XML.format(g=g, rx=WING_ROOT[0], ry=WING_ROOT_Y, rz=WING_ROOT[1]))
    with open(os.path.join(OUT, "fly-pilot.xml"), "w", newline="\n") as f:
        f.write(PILOT_XML.format(rx=WING_ROOT[0], ry=WING_ROOT_Y, rz=WING_ROOT[1]))
    rng = random.Random(SEED)
    hide = "\n".join(f"    <object-name>{n}</object-name>" for n in CLEAR_VIEW_HIDE)
    parts = [TOP_XML_HEAD.format(px=PILOT_SEAT[0], py=PILOT_SEAT[1], pz=PILOT_SEAT[2], hide=hide)]
    n = 0
    for i, (x, y, z) in enumerate(seats):
        if rng.random() < EMPTY_FRACTION:
            continue
        g = rng.randrange(3)
        parts.append(
            f"  <model><name>fly{n:03d}</name><path>Aircraft/FlyCabin/Models/fly-group{g}.xml</path>"
            f"<offsets><x-m>{x:.3f}</x-m><y-m>{y:.3f}</y-m><z-m>{z:.3f}</z-m>"
            f"<heading-deg>{rng.uniform(-6, 6):.1f}</heading-deg></offsets></model>\n")
        n += 1
    parts.append(
        "\n  <!-- Running gag: the fly flight attendant and her snack cart (cabin_show.nas). -->\n"
        f"  <model><name>attendant</name><path>Aircraft/FlyCabin/Models/attendant.xml</path>"
        f"<offsets><x-m>0</x-m><y-m>0</y-m><z-m>{Z_FLOOR:.3f}</z-m></offsets></model>\n")
    parts.append("</PropertyList>\n")
    with open(os.path.join(OUT, "738-flies.xml"), "w", newline="\n") as f:
        f.write("".join(parts))
    print(f"{len(seats)} seats, {n} fly passengers -> {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
