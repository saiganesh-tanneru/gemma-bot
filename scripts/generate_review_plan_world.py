#!/usr/bin/env python3
"""Generate the Chintu / GemaBot Webots world and PROTOs from the fitted CAD design.

Dimensions match cad/build_chintu_cad.py ("fitted" preset, mm -> m, Z up, face -Y):

  base     tapered frustum, bottom Ø86 mm, top Ø78 mm, height 50 mm, LED groove z=6.5 mm
  neck     tapered column (Ø36 mm -> Ø24 mm cup) + Ø32 mm gimbal ball (center z=72.5 mm)
  pogo     Ø24 mm gold pogo crown tucked inside head underside bay (0 mm pad slip)
  head     68 x 58 x 46 mm (W x H x D), 7 mm fillet, seated 15.5 mm above ball center
  screen   2.06" 502x410 landscape AMOLED (47.2 x 39.2 mm) inside 50.4 x 42.4 mm bezel
  crown    50 x 30 mm top solar cell acting as floating bumper for head_touch
  overall  146.0 mm from base bottom to head top
  dock     92 x 92 x 16 mm clock charger, base sits 3 mm into pocket

Device names match gemma_bot_controller:
oled_display, camera, head_yaw, head_pitch, yaw_sensor, pitch_sensor, head_touch.
"""

from __future__ import annotations

import math
import shutil
import struct
import zlib
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None

ROOT = Path(__file__).resolve().parents[1]
PROTO_DIR = ROOT / "protos"
TEX_DIR = PROTO_DIR / "textures"
WORLD_PATH = ROOT / "worlds" / "gemabot_review_plan.wbt"

# Source textures shipped with the concept (copied next to the PROTOs if present).
_UPLOADS = Path("/home/ubuntu/.cursor/projects/workspace/uploads")
FACE_HAPPY_SRC = _UPLOADS / "face_happy_e555.png"
FACE_JOY_SRC = _UPLOADS / "face_joy_71a0.png"
CLOCK_SRC = _UPLOADS / "clock_1042_d25a.png"

# Fitted CAD parameters (from cad/build_chintu_cad.py PRESETS["fitted"]), metres.
BASE_H = 0.050
BASE_R_BOT = 0.043
BASE_R_TOP = 0.039
RING_GROOVE_Z = 0.0065
NECK_BASE_Z = BASE_H - 0.0015  # 0.0485
NECK_R_BOT = 0.018
NECK_H = 0.024
BALL_R = 0.016  # Ø32 mm gimbal ball centered at BASE_H - 0.0015 + NECK_H = 0.0725 m
BALL_CENTER_Z = NECK_BASE_Z + NECK_H  # 0.0725
HEAD_SEAT_ABOVE_BALL = 0.0155
POGO_RING_R = 0.012
POGO_RING_H = 0.0042

HEAD_W = 0.068
HEAD_H = 0.058
HEAD_D = 0.046
HEAD_BEVEL = 0.007
HEAD_MASS_KG = 0.0906
HEAD_CENTER_LOCAL_Z = HEAD_SEAT_ABOVE_BALL + HEAD_H / 2  # 0.0445 above ball center
HEAD_CENTER_Z = BALL_CENTER_Z + HEAD_CENTER_LOCAL_Z  # 0.117; head top = 0.146 m
OVERALL_HEIGHT_M = BALL_CENTER_Z + HEAD_SEAT_ABOVE_BALL + HEAD_H  # 0.1460

# 2.06" 410x502 AMOLED mounted in landscape (47.2 x 39.2 mm active glass)
IMG_W = 0.0472
IMG_H = 0.0392
SCR_W = 0.0504
SCR_H = 0.0434
SCR_Z_OFFSET = -0.0010  # Leaves room for top-bezel camera pinhole inside flat front face
OLED_DISP_W = 502
OLED_DISP_H = 410

# Burnt-orange side ear rings (from cad/build_chintu_cad.py build_color_accents)
EAR_R = min(HEAD_H * 0.22, 0.013)  # 0.01276 m
EAR_THICK = 0.0024
EAR_DOT_R = 0.0036

# Top crown 50 x 30 mm monocrystalline solar panel / floating touch bumper
SOLAR_W = 0.050
SOLAR_D = 0.030
SOLAR_H = 0.0014

DOCK = 0.092
DOCK_H = 0.016

DESK_TOP = 0.740


def _r(v: float) -> str:
    if abs(v) < 5e-7:
        return "0"
    text = f"{v:.6f}".rstrip("0").rstrip(".")
    if text == "-0":
        return "0"
    return text


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _norm(a):
    length = math.sqrt(_dot(a, a))
    if length < 1e-12:
        return (0.0, 0.0, 0.0)
    return (a[0] / length, a[1] / length, a[2] / length)


class Mesh:
    def __init__(self):
        self.verts: list[tuple[float, float, float]] = []
        self.tris: list[tuple[int, int, int]] = []
        self.uvs: list[tuple[float, float]] | None = None

    def add(self, p) -> int:
        self.verts.append((float(p[0]), float(p[1]), float(p[2])))
        return len(self.verts) - 1

    def tri(self, a, b, c) -> None:
        if len({a, b, c}) == 3:
            self.tris.append((a, b, c))

    def bounds(self):
        xs = [v[0] for v in self.verts]
        ys = [v[1] for v in self.verts]
        zs = [v[2] for v in self.verts]
        return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))

    def extend(self, other: "Mesh") -> None:
        if self.uvs is not None or other.uvs is not None:
            raise RuntimeError("extend() does not carry UVs")
        base = len(self.verts)
        self.verts.extend(other.verts)
        self.tris.extend((a + base, b + base, c + base) for a, b, c in other.tris)

    def weld(self, tol: float = 1e-6) -> None:
        if self.uvs is not None:
            return
        buckets: dict[tuple[int, int, int], int] = {}
        remap: list[int] = []
        verts: list[tuple[float, float, float]] = []
        inv = 1.0 / tol
        for v in self.verts:
            key = (round(v[0] * inv), round(v[1] * inv), round(v[2] * inv))
            idx = buckets.get(key)
            if idx is None:
                idx = len(verts)
                buckets[key] = idx
                verts.append(v)
            remap.append(idx)
        tris = []
        for a, b, c in self.tris:
            ia, ib, ic = remap[a], remap[b], remap[c]
            if len({ia, ib, ic}) == 3:
                tris.append((ia, ib, ic))
        self.verts = verts
        self.tris = tris

    def orient_outward(self, interior=(0.0, 0.0, 0.0)) -> None:
        fixed = []
        origin = interior
        for a, b, c in self.tris:
            va, vb, vc = self.verts[a], self.verts[b], self.verts[c]
            n = _cross(_sub(vb, va), _sub(vc, va))
            center = _mul(_add(_add(va, vb), vc), 1.0 / 3.0)
            if _dot(n, _sub(center, origin)) < 0:
                fixed.append((a, c, b))
            else:
                fixed.append((a, b, c))
        self.tris = fixed

    def vrml(self, crease: float, indent: str = "        ") -> str:
        points = "\n".join(indent + "  " + " ".join(_r(c) for c in v) for v in self.verts)
        faces = "\n".join(indent + "  " + f"{a} {b} {c} -1" for a, b, c in self.tris)
        uv_block = ""
        if self.uvs is not None:
            uvs = "\n".join(indent + "  " + f"{_r(u)} {_r(v)}" for u, v in self.uvs)
            uv_block = (
                f"\n{indent}texCoord TextureCoordinate {{\n{indent}  point [\n{uvs}\n{indent}  ]\n{indent}}}"
            )
        return (
            f"IndexedFaceSet {{\n"
            f"{indent}coord Coordinate {{\n{indent}  point [\n{points}\n{indent}  ]\n{indent}}}"
            f"{uv_block}\n"
            f"{indent}coordIndex [\n{faces}\n{indent}]\n"
            f"{indent}creaseAngle { _r(crease) }\n"
            f"{indent}}}"
        )


def shape(appearance: str, geometry: str, indent: str = "        ") -> str:
    geo = geometry.strip("\n")
    if "\n" in geo:
        geo = "\n".join((indent + "  " + line) if line else line for line in geo.splitlines())
    return (
        f"Shape {{\n"
        f"{indent}appearance {appearance}\n"
        f"{indent}geometry {geo}\n"
        f"{indent}}}"
    )


def _round_vertex(p, half, radius):
    inner = tuple(h - radius for h in half)
    clamped = tuple(max(-inner[i], min(inner[i], p[i])) for i in range(3))
    n = _norm(_sub(p, clamped))
    if _dot(n, n) < 1e-12:
        return p
    return _add(clamped, _mul(n, radius))


def rounded_box(half, radius: float, segments: int) -> Mesh:
    """Subdivided box projected onto a rounded box (three.js RoundedBoxGeometry)."""
    mesh = Mesh()
    hx, hy, hz = half
    n = segments

    def grid(point_at, quad):
        start = len(mesh.verts)
        for j in range(n + 1):
            v = -1.0 + 2.0 * j / n
            for i in range(n + 1):
                u = -1.0 + 2.0 * i / n
                mesh.add(point_at(u, v))
        for j in range(n):
            for i in range(n):
                a = start + j * (n + 1) + i
                b = a + 1
                c = a + (n + 1)
                d = c + 1
                i0, i1, i2, i3 = quad(a, b, c, d)
                mesh.tri(i0, i1, i2)
                mesh.tri(i0, i2, i3)

    # u right, v up, as seen from outside.
    grid(lambda u, v: (u * hx, -hy, v * hz), lambda a, b, c, d: (a, d, b, c))  # -Y front
    grid(lambda u, v: (-u * hx, hy, v * hz), lambda a, b, c, d: (a, d, b, c))  # +Y back
    grid(lambda u, v: (hx, -u * hy, v * hz), lambda a, b, c, d: (a, d, b, c))  # +X
    grid(lambda u, v: (-hx, u * hy, v * hz), lambda a, b, c, d: (a, d, b, c))  # -X
    grid(lambda u, v: (u * hx, v * hy, hz), lambda a, b, c, d: (a, b, d, c))  # +Z
    grid(lambda u, v: (u * hx, -v * hy, -hz), lambda a, b, c, d: (a, b, d, c))  # -Z
    mesh.verts = [_round_vertex(v, half, radius) for v in mesh.verts]
    mesh.weld()
    mesh.orient_outward((0.0, 0.0, 0.0))
    return mesh


def _inside_round_rect(x, z, hw, hh, rad) -> bool:
    ax, az = abs(x), abs(z)
    if ax > hw or az > hh:
        return False
    ix, iz = hw - rad, hh - rad
    if ax <= ix or az <= iz:
        return True
    dx, dz = ax - ix, az - iz
    return dx * dx + dz * dz <= rad * rad + 1e-12


def recess_front(mesh: Mesh, half, opening, depth: float) -> None:
    """Push the flat front face back to form the screen recess."""
    hy = half[1]
    hw, hh, rad = opening
    sunk = []
    for v in mesh.verts:
        if v[1] < -hy + 0.0012 and _inside_round_rect(v[0], v[2], hw, hh, rad):
            sunk.append((v[0], v[1] + depth, v[2]))
        else:
            sunk.append(v)
    mesh.verts = sunk


def clip_mesh(mesh: Mesh, axis: int, limit: float, keep_below: bool) -> Mesh:
    def keep(p):
        return (p[axis] <= limit) if keep_below else (p[axis] >= limit)

    def intersect(p, q):
        sp = p[axis] - limit
        sq = q[axis] - limit
        denom = sp - sq
        t = 0.0 if abs(denom) < 1e-12 else sp / denom
        return tuple(p[i] + (q[i] - p[i]) * t for i in range(3))

    def clip_poly(poly):
        if not poly:
            return []
        output = []
        prev = poly[-1]
        prev_in = keep(prev)
        for curr in poly:
            curr_in = keep(curr)
            if curr_in:
                if not prev_in:
                    output.append(intersect(prev, curr))
                output.append(curr)
            elif prev_in:
                output.append(intersect(prev, curr))
            prev = curr
            prev_in = curr_in
        return output

    out = Mesh()
    cache: dict[tuple[int, int, int], int] = {}

    def vid(p) -> int:
        key = (round(p[0] * 1e6), round(p[1] * 1e6), round(p[2] * 1e6))
        idx = cache.get(key)
        if idx is None:
            idx = out.add(p)
            cache[key] = idx
        return idx

    for a, b, c in mesh.tris:
        poly = clip_poly([mesh.verts[a], mesh.verts[b], mesh.verts[c]])
        if len(poly) < 3:
            continue
        i0 = vid(poly[0])
        for k in range(1, len(poly) - 1):
            out.tri(i0, vid(poly[k]), vid(poly[k + 1]))
    return out


def rounded_rect(width: float, height: float, radius: float, y: float, facing: int, segments: int = 8) -> Mesh:
    """Rounded rectangle in the XZ plane. facing -1 looks toward -Y, +1 toward +Y."""
    mesh = Mesh()
    hw, hh = width / 2.0, height / 2.0
    rad = min(radius, hw - 1e-6, hh - 1e-6)
    pts = []
    corners = (
        (hw - rad, hh - rad, 0.0),
        (-(hw - rad), hh - rad, math.pi / 2),
        (-(hw - rad), -(hh - rad), math.pi),
        (hw - rad, -(hh - rad), 3 * math.pi / 2),
    )
    # Walk CCW when viewed from +Y (x right? from +Y, +X is to the left).
    # Build the loop CCW in the standard XZ plane (x right, z up) which is CCW from -Y.
    loop_corners = (
        (-(hw - rad), -(hh - rad), math.pi),
        (hw - rad, -(hh - rad), 3 * math.pi / 2),
        (hw - rad, hh - rad, 0.0),
        (-(hw - rad), hh - rad, math.pi / 2),
    )
    for cx, cz, a0 in loop_corners:
        for i in range(segments + 1):
            a = a0 + (math.pi / 2) * i / segments
            pts.append((cx + rad * math.cos(a), cz + rad * math.sin(a)))
    # Drop the duplicated corner samples.
    cleaned = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - cleaned[-1][0]) > 1e-8 or abs(p[1] - cleaned[-1][1]) > 1e-8:
            cleaned.append(p)
    if abs(cleaned[0][0] - cleaned[-1][0]) < 1e-8 and abs(cleaned[0][1] - cleaned[-1][1]) < 1e-8:
        cleaned.pop()

    mesh.uvs = []
    center = mesh.add((0.0, y, 0.0))
    mesh.uvs.append((0.5, 0.5))
    ids = []
    for x, z in cleaned:
        ids.append(mesh.add((x, y, z)))
        mesh.uvs.append((x / width + 0.5, z / height + 0.5))
    n = len(ids)
    for i in range(n):
        j = (i + 1) % n
        if facing < 0:
            mesh.tri(center, ids[i], ids[j])
        else:
            mesh.tri(center, ids[j], ids[i])
    return mesh


def lathe(profile: list[tuple[float, float]], segments: int, interior) -> Mesh:
    """Profile is (z, radius) from bottom to top, revolved around Z."""
    mesh = Mesh()
    rings = []
    for z, radius in profile:
        ring = []
        for s in range(segments):
            a = 2.0 * math.pi * s / segments
            ring.append(mesh.add((radius * math.cos(a), radius * math.sin(a), z)))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for s in range(segments):
            s2 = (s + 1) % segments
            a, b = rings[i][s], rings[i][s2]
            c, d = rings[i + 1][s], rings[i + 1][s2]
            mesh.tri(a, b, d)
            mesh.tri(a, d, c)
    bottom = mesh.add((0.0, 0.0, profile[0][0]))
    top = mesh.add((0.0, 0.0, profile[-1][0]))
    for s in range(segments):
        s2 = (s + 1) % segments
        mesh.tri(bottom, rings[0][s2], rings[0][s])
        mesh.tri(top, rings[-1][s], rings[-1][s2])
    mesh.orient_outward(interior)
    return mesh


def base_radius(z: float) -> float:
    return BASE_R_BOT + (BASE_R_TOP - BASE_R_BOT) * (z / BASE_H)


def base_profile() -> list[tuple[float, float]]:
    def lip(z, inset):
        return (z, max(0.004, base_radius(z) - inset))

    zg = RING_GROOVE_Z + 0.0011
    rg = base_radius(zg)
    return [
        lip(0.000, 0.0025),
        lip(0.0012, 0.0010),
        (0.0028, base_radius(0.0028)),
        (RING_GROOVE_Z - 0.0004, base_radius(RING_GROOVE_Z - 0.0004)),
        (RING_GROOVE_Z, rg - 0.0005),
        (RING_GROOVE_Z + 0.0003, rg - 0.0018),
        (RING_GROOVE_Z + 0.0019, rg - 0.0018),
        (RING_GROOVE_Z + 0.0022, base_radius(RING_GROOVE_Z + 0.0022) - 0.0005),
        (RING_GROOVE_Z + 0.0032, base_radius(RING_GROOVE_Z + 0.0032)),
        (0.0250, base_radius(0.0250)),
        (BASE_H - 0.0025, base_radius(BASE_H - 0.0025)),
        lip(BASE_H - 0.0012, 0.0010),
        lip(BASE_H, 0.0025),
    ]


def cylinder_z(height: float, radius: float, subdivision: int = 48) -> str:
    return (
        "Pose {\n"
        "          rotation 1 0 0 1.57079632679\n"
        "          children [\n"
        "            Shape {\n"
        "              appearance APPEARANCE\n"
        "              geometry Cylinder {\n"
        f"                height {_r(height)}\n"
        f"                radius {_r(radius)}\n"
        f"                subdivision {subdivision}\n"
        "              }\n"
        "            }\n"
        "          ]\n"
        "        }"
    )


def emit_indexed(name_comment: str, appearance: str, mesh: Mesh, crease: float) -> str:
    return shape(appearance, mesh.vrml(crease))


def smooth_rounded_box(half, radius, n=12):
    """Rounded box: one quad per flat face, a fillet only on edges and corners."""
    hx, hy, hz = half
    r = min(radius, hx - 1e-4, hy - 1e-4, hz - 1e-4)
    inner = (hx - r, hy - r, hz - r)
    mesh = Mesh()

    def quad(p00, p10, p11, p01):
        a, b = mesh.add(p00), mesh.add(p10)
        c, d = mesh.add(p11), mesh.add(p01)
        mesh.tri(a, b, c)
        mesh.tri(a, c, d)

    ix, iy, iz = inner
    # Flat faces. The fillet owns everything outside ±inner.
    quad((-ix, -hy, -iz), (ix, -hy, -iz), (ix, -hy, iz), (-ix, -hy, iz))
    quad((ix, hy, -iz), (-ix, hy, -iz), (-ix, hy, iz), (ix, hy, iz))
    quad((hx, -iy, -iz), (hx, iy, -iz), (hx, iy, iz), (hx, -iy, iz))
    quad((-hx, iy, -iz), (-hx, -iy, -iz), (-hx, -iy, iz), (-hx, iy, iz))
    quad((-ix, -iy, hz), (ix, -iy, hz), (ix, iy, hz), (-ix, iy, hz))
    quad((-ix, iy, -hz), (ix, iy, -hz), (ix, -iy, -hz), (-ix, -iy, -hz))

    def add_edge(free, sa, sb):
        others = [i for i in (0, 1, 2) if i != free]
        ia, ib = others

        def point(t, s_free):
            ang = (math.pi / 2.0) * t
            p = [0.0, 0.0, 0.0]
            p[free] = s_free * inner[free]
            p[ia] = sa * inner[ia] + sa * r * math.cos(ang)
            p[ib] = sb * inner[ib] + sb * r * math.sin(ang)
            return tuple(p)

        lo = [mesh.add(point(i / n, -1)) for i in range(n + 1)]
        hi = [mesh.add(point(i / n, 1)) for i in range(n + 1)]
        for i in range(n):
            mesh.tri(lo[i], hi[i], lo[i + 1])
            mesh.tri(lo[i + 1], hi[i], hi[i + 1])

    for free in (0, 1, 2):
        for sa in (-1, 1):
            for sb in (-1, 1):
                add_edge(free, sa, sb)

    def corner_point(sx, sy, sz, phi, theta):
        nx = math.cos(theta) * math.sin(phi)
        ny = math.sin(theta) * math.sin(phi)
        nz = math.cos(phi)
        return (
            sx * inner[0] + sx * r * nx,
            sy * inner[1] + sy * r * ny,
            sz * inner[2] + sz * r * nz,
        )

    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                ids = []
                for i in range(n + 1):
                    phi = (math.pi / 2) * i / n
                    row = []
                    for j in range(n + 1):
                        theta = (math.pi / 2) * j / n
                        row.append(mesh.add(corner_point(sx, sy, sz, phi, theta)))
                    ids.append(row)
                for i in range(n):
                    for j in range(n):
                        a, b = ids[i][j], ids[i][j + 1]
                        c, d = ids[i + 1][j], ids[i + 1][j + 1]
                        mesh.tri(a, c, b)
                        mesh.tri(b, c, d)
    mesh.weld(1e-5)
    mesh.orient_outward((0.0, 0.0, 0.0))
    return mesh


def build_head_mesh() -> Mesh:
    """Single seamless charcoal head shell matching cad/build_chintu_cad.py 03_head_shell."""
    half = (HEAD_W / 2, HEAD_D / 2, HEAD_H / 2)
    return smooth_rounded_box(half, HEAD_BEVEL, 16)


def build_screen() -> Mesh:
    # Glossy AMOLED glass panel flush inside the front bezel.
    m = rounded_rect(IMG_W - 0.0006, IMG_H - 0.0006, 0.005, -HEAD_D / 2 - 0.0011, facing=-1, segments=10)
    m.verts = [(x, y, z + SCR_Z_OFFSET) for (x, y, z) in m.verts]
    return m


def build_bezel() -> Mesh:
    m = rounded_rect(SCR_W, SCR_H, 0.006, -HEAD_D / 2 - 0.0005, facing=-1, segments=10)
    m.verts = [(x, y, z + SCR_Z_OFFSET * 0.4) for (x, y, z) in m.verts]
    return m


def build_curved_logo_mesh(z_center: float = 0.024, height: float = 0.0095, arc_deg: float = 42.0, segs: int = 16) -> Mesh:
    """Curved conical decal hugging the front (-Y) tapered base wall with zero floating edges."""
    mesh = Mesh()
    mesh.uvs = []
    z0 = z_center - height / 2.0
    z1 = z_center + height / 2.0
    r0 = base_radius(z0) + 0.0004
    r1 = base_radius(z1) + 0.0004
    half_rad = math.radians(arc_deg / 2.0)

    for i in range(segs + 1):
        u = i / segs
        # Sweep from left (-X, angle=-half_rad from -Y) to right (+X, angle=+half_rad from -Y)
        ang = -half_rad + 2.0 * half_rad * u
        sx = math.sin(ang)
        cy = -math.cos(ang)
        mesh.add((r0 * sx, r0 * cy, z0))
        mesh.uvs.append((u, 0.0))
        mesh.add((r1 * sx, r1 * cy, z1))
        mesh.uvs.append((u, 1.0))

    for i in range(segs):
        a = 2 * i
        b = a + 1
        c = a + 2
        d = a + 3
        mesh.tri(a, c, d)
        mesh.tri(a, d, b)
    return mesh


def build_dock_mesh() -> Mesh:
    half = (DOCK / 2, DOCK / 2, DOCK_H / 2)
    # Build centered, then shift so the bottom sits on z = 0.
    mesh = rounded_box(half, 0.006, 3)
    pocket_r = BASE_R_BOT + 0.0008
    moved = []
    for v in mesh.verts:
        x, y, z = v
        if z > half[2] - 0.0014 and x * x + y * y <= pocket_r * pocket_r:
            moved.append((x, y, z - 0.0036))
        else:
            moved.append(v)
    mesh.verts = moved
    mesh.verts = [(v[0], v[1], v[2] + half[2]) for v in mesh.verts]
    return mesh


def build_clock(v0: float, v1: float) -> Mesh:
    # Wide short display on the dock front. Width/height matches the 1000x280 art.
    width, height = 0.046, 0.0129
    y = -DOCK / 2 - 0.00035
    z = 0.0074
    mesh = rounded_rect(width, height, 0.0014, 0.0, facing=-1, segments=4)
    mesh.verts = [(v[0], y, v[2] + z) for v in mesh.verts]
    if mesh.uvs is not None:
        mesh.uvs = [(u, v0 + v * (v1 - v0)) for u, v in mesh.uvs]
    return mesh


def mat(name: str, **fields) -> str:
    lines = [f"DEF {name} PBRAppearance {{"]
    for key, value in fields.items():
        lines.append(f"  {key} {value}")
    lines.append("}")
    return "\n".join(lines)


def _dist_seg(px: float, py: float, x0: float, y0: float, x1: float, y1: float) -> float:
    vx, vy = x1 - x0, y1 - y0
    wx, wy = px - x0, py - y0
    denom = vx * vx + vy * vy
    t = 0.0 if denom < 1e-12 else max(0.0, min(1.0, (wx * vx + wy * vy) / denom))
    dx = px - (x0 + t * vx)
    dy = py - (y0 + t * vy)
    return math.hypot(dx, dy)


def _dist_arc(px: float, py: float, cx: float, cy: float, r: float, a0: float, a1: float) -> float:
    ang = math.atan2(py - cy, px - cx)
    if ang < 0.0:
        ang += 2.0 * math.pi
    if a0 <= ang <= a1:
        return abs(math.hypot(px - cx, py - cy) - r)
    p0 = (cx + r * math.cos(a0), cy + r * math.sin(a0))
    p1 = (cx + r * math.cos(a1), cy + r * math.sin(a1))
    return min(math.hypot(px - p0[0], py - p0[1]), math.hypot(px - p1[0], py - p1[1]))


def _write_rgba_png(path: Path, w: int, h: int, rows: list[bytes]) -> None:
    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    raw = b"".join(b"\x00" + r for r in rows)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    path.write_bytes(png)


def write_logo() -> None:
    """Renders crisp anti-aliased 'CHINTU' RGBA logo PNG using pure Python (no Pillow required)."""
    TEX_DIR.mkdir(parents=True, exist_ok=True)
    logo_path = TEX_DIR / "logo_chintu.png"
    w, h = 512, 128
    glyph_w = 56.0
    glyph_h = 84.0
    gap = 18.0
    # Per-glyph (advance_scale, segments, arcs) in normalized [0..1]x[0..1]
    c_arc_pts = [
        (
            0.55 + 0.42 * math.cos(a),
            0.50 + 0.42 * math.sin(a),
        )
        for a in [
            0.22 * math.pi + (1.56 * math.pi) * k / 16
            for k in range(17)
        ]
    ]
    c_segs = [(c_arc_pts[k][0], c_arc_pts[k][1], c_arc_pts[k + 1][0], c_arc_pts[k + 1][1]) for k in range(16)]
    u_arc_pts = [
        (
            0.50 + 0.34 * math.cos(a),
            0.58 + 0.34 * math.sin(a),
        )
        for a in [math.pi * k / 12 for k in range(13)]
    ]
    u_segs = [(0.16, 0.08, 0.16, 0.58), (0.84, 0.58, 0.84, 0.08)] + [
        (u_arc_pts[k][0], u_arc_pts[k][1], u_arc_pts[k + 1][0], u_arc_pts[k + 1][1]) for k in range(12)
    ]
    glyphs = {
        "C": (0.96, c_segs, []),
        "H": (1.0, [(0.16, 0.08, 0.16, 0.92), (0.84, 0.08, 0.84, 0.92), (0.16, 0.50, 0.84, 0.50)], []),
        "I": (0.42, [(0.50, 0.08, 0.50, 0.92)], []),
        "N": (1.0, [(0.16, 0.92, 0.16, 0.08), (0.16, 0.08, 0.84, 0.92), (0.84, 0.92, 0.84, 0.08)], []),
        "T": (0.96, [(0.06, 0.08, 0.94, 0.08), (0.50, 0.08, 0.50, 0.92)], []),
        "U": (1.0, u_segs, []),
    }
    word = "CHINTU"
    total_w = sum(glyph_w * glyphs[ch][0] for ch in word) + gap * (len(word) - 1)
    boxes = []
    cur_x = (w - total_w) / 2.0
    y0 = (h - glyph_h) / 2.0
    for ch in word:
        scale, segs, arcs = glyphs[ch]
        gw = glyph_w * scale
        boxes.append((cur_x, gw, y0, glyph_h, segs, arcs))
        cur_x += gw + gap

    stroke_r = 5.4
    aa = 1.6
    rows: list[bytes] = []
    for py in range(h):
        row = bytearray(w * 4)
        for px in range(w):
            best = 1e9
            for bx, bw, by, bh, segs, arcs in boxes:
                if px < bx - stroke_r - 4 or px > bx + bw + stroke_r + 4 or py < by - stroke_r - 4 or py > by + bh + stroke_r + 4:
                    continue
                for x0, ya, x1, yb in segs:
                    d = _dist_seg(px, py, bx + x0 * bw, by + ya * bh, bx + x1 * bw, by + yb * bh)
                    if d < best:
                        best = d
                for cx, cy, rad, a0, a1 in arcs:
                    # Keep uniform pixel radius using gw~glyph_h
                    r_px = rad * min(bw, bh)
                    d = _dist_arc(px, py, bx + cx * bw, by + cy * bh, r_px, a0, a1)
                    if d < best:
                        best = d
            if best < stroke_r + aa:
                alpha = int(max(0.0, min(1.0, (stroke_r + aa - best) / (2.0 * aa))) * 255)
                idx = px * 4
                row[idx] = 0xEE
                row[idx + 1] = 0xEE
                row[idx + 2] = 0xF2
                row[idx + 3] = alpha
        rows.append(bytes(row))
    _write_rgba_png(logo_path, w, h, rows)


def write_face() -> None:
    """Soft light-blue face, drawn large and scaled so the panel is not a pixel grid."""
    face_path = TEX_DIR / "face_screen.png"
    if Image is None:
        if face_path.is_file():
            return
        raise RuntimeError("Pillow is required to generate missing face_screen.png")
    w, h = 1024, 788
    image = Image.new("RGB", (w, h), (6, 7, 10))
    draw = ImageDraw.Draw(image)
    eye = (0x8E, 0xC9, 0xDB)
    for cx in (int(w * 0.31), int(w * 0.69)):
        ew, eh = 300, 360
        box = [cx - ew // 2, 150, cx + ew // 2, 150 + eh]
        draw.rounded_rectangle(box, radius=140, fill=eye)
        draw.ellipse([cx - ew // 2 + 48, 210, cx - ew // 2 + 128, 290], fill=(255, 255, 255))
    draw.arc([w // 2 - 110, 560, w // 2 + 110, 700], start=15, end=165, fill=eye, width=18)
    image.save(face_path)


def copy_textures() -> tuple[float, float]:
    """Copy face art when source uploads exist; otherwise reuse pre-generated textures."""
    TEX_DIR.mkdir(parents=True, exist_ok=True)
    if FACE_HAPPY_SRC.is_file():
        shutil.copyfile(FACE_HAPPY_SRC, TEX_DIR / "face_happy.png")
    if FACE_JOY_SRC.is_file():
        shutil.copyfile(FACE_JOY_SRC, TEX_DIR / "face_joy.png")
    if CLOCK_SRC.is_file() and Image is not None:
        src = Image.open(CLOCK_SRC).convert("RGBA")
        canvas_w, canvas_h = 1024, 512
        scaled_h = max(1, round(src.height * canvas_w / src.width))
        scaled = src.resize((canvas_w, scaled_h), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 255))
        top = (canvas_h - scaled_h) // 2
        canvas.paste(scaled, (0, top))
        canvas.save(TEX_DIR / "clock_1042.png")
        v0 = (canvas_h - (top + scaled_h)) / canvas_h
        v1 = (canvas_h - top) / canvas_h
        return v0, v1
    # Pre-padded 1024x512 clock_1042.png V bounds (rows 112..399 of 512)
    return 113.0 / 512.0, 400.0 / 512.0


def robot_proto(base: Mesh, head_shell: Mesh, logo_mesh: Mesh, bezel: Mesh, screen: Mesh) -> str:
    # PBRAppearance is not a legal Robot child, so each material is DEF'd on first use.
    defined: set[str] = set()
    material_body = {
        "CHARCOAL": "baseColor 0.20 0.21 0.24 roughness 0.58 metalness 0",
        "HEAD_CHARCOAL": "baseColor 0.22 0.23 0.26 roughness 0.55 metalness 0",
        "NECK_CHARCOAL": "baseColor 0.24 0.25 0.28 roughness 0.55 metalness 0",
        "EAR_CENTER": "baseColor 0.10 0.11 0.12 roughness 0.45 metalness 0.05",
        "GRAPHITE": "baseColor 0.08 0.09 0.10 roughness 0.28 metalness 0.35",
        "ACCENT": "baseColor 0.92 0.47 0.24 roughness 0.40 metalness 0",
        "GOLD": "baseColor 0.85 0.68 0.25 roughness 0.25 metalness 0.85",
        "SOLAR_CELL": "baseColor 0.035 0.055 0.135 roughness 0.14 metalness 0.35",
        "LED": "baseColor 0.93 0.58 0.37 roughness 0.38 emissiveColor 0.93 0.58 0.37 emissiveIntensity 1.4",
        "MIC": "baseColor 0.02 0.02 0.022 roughness 0.45 metalness 0.1",
        "BEZEL": "baseColor 0.012 0.012 0.014 roughness 0.22 metalness 0.05",
        "LOGO_MAT": (
            'baseColor 1 1 1 roughness 0.45 metalness 0 baseColorMap ImageTexture { '
            'url [ "textures/logo_chintu.png" ] repeatS FALSE repeatT FALSE }'
        ),
        "SCREEN_MAT": (
            "baseColor 0.02 0.02 0.025 roughness 0.08 metalness 0.12 emissiveIntensity 0.55 "
            'baseColorMap DEF FACE_TEX ImageTexture { url [ "textures/face_screen.png" ] '
            "repeatS FALSE repeatT FALSE filtering 4 } emissiveColorMap USE FACE_TEX"
        ),
    }

    def app(name: str) -> str:
        if name in defined:
            return f"USE {name}"
        defined.add(name)
        return f"DEF {name} PBRAppearance {{ {material_body[name]} }}"

    def cyl(appearance, radius, height, translation, rotation, subdivision=48):
        return (
            "Pose {\n"
            f"          translation {translation}\n"
            f"          rotation {rotation}\n"
            "          children [\n"
            "            Shape {\n"
            f"              appearance {appearance}\n"
            "              geometry Cylinder {\n"
            f"                height {_r(height)}\n"
            f"                radius {_r(radius)}\n"
            f"                subdivision {subdivision}\n"
            "              }\n"
            "            }\n"
            "          ]\n"
            "        }"
        )

    led_r = base_radius(RING_GROOVE_Z + 0.0011) - 0.0005
    btn_x = (BASE_R_TOP * 2) * 0.32
    btn_y = -(BASE_R_TOP * 2) * 0.24
    parts = [
        emit_indexed("base", app("CHARCOAL"), base, 0.7),
        cyl(app("LED"), led_r, 0.0020, f"0 0 {_r(RING_GROOVE_Z + 0.0011)}", "1 0 0 1.57079632679", 64),
        cyl(app("ACCENT"), 0.0031, 0.0018, f"{_r(btn_x)} {_r(btn_y)} {_r(BASE_H + 0.0002)}", "1 0 0 1.57079632679", 24),
        emit_indexed("chintu logo", app("LOGO_MAT"), logo_mesh, 0.6),
    ]

    # Tapered neck socket column + Ø32 mm gimbal ball centered at z_local = NECK_H (0.024 m)
    neck_cup = lathe(
        [
            (0.0, NECK_R_BOT),
            (NECK_H - 0.001, BALL_R + 0.00225),
        ],
        48,
        interior=(0.0, 0.0, NECK_H * 0.5),
    )
    neck_visuals = "\n".join(
        [
            cyl(app("NECK_CHARCOAL"), NECK_R_BOT + 0.0015, 0.0025, "0 0 0.00125", "1 0 0 1.57079632679", 48),
            emit_indexed("neck pedestal", app("NECK_CHARCOAL"), neck_cup, 0.7),
            f"""Pose {{
          translation 0 0 {_r(NECK_H)}
          children [
            Shape {{
              appearance {app("GRAPHITE")}
              geometry Sphere {{
                radius {_r(BALL_R)}
                subdivision 3
              }}
            }}
          ]
        }}""",
        ]
    )

    head_bits = "\n".join(
        [
            emit_indexed("head shell", app("HEAD_CHARCOAL"), head_shell, 1.0),
            emit_indexed("bezel", app("BEZEL"), bezel, 0.5),
            # Burnt-orange side ear rings + dark center dots matching build_color_accents()
            cyl(app("ACCENT"), EAR_R, EAR_THICK, f"{_r(HEAD_W/2 + EAR_THICK/2 - 0.0003)} 0 0", "0 1 0 1.57079632679", 48),
            cyl(app("ACCENT"), EAR_R, EAR_THICK, f"{_r(-(HEAD_W/2 + EAR_THICK/2 - 0.0003))} 0 0", "0 1 0 1.57079632679", 48),
            cyl(app("EAR_CENTER"), EAR_DOT_R, EAR_THICK + 0.0003, f"{_r(HEAD_W/2 + EAR_THICK/2 - 0.0001)} 0 0", "0 1 0 1.57079632679", 32),
            cyl(app("EAR_CENTER"), EAR_DOT_R, EAR_THICK + 0.0003, f"{_r(-(HEAD_W/2 + EAR_THICK/2 - 0.0001))} 0 0", "0 1 0 1.57079632679", 32),
        ]
    )

    # Gold pogo-pin crown collar seated between ball top and head underside bay
    pogo_collar = cyl(
        app("GOLD"),
        POGO_RING_R,
        POGO_RING_H,
        f"0 0 {_r(HEAD_SEAT_ABOVE_BALL - POGO_RING_H / 2)}",
        "1 0 0 1.57079632679",
        36,
    )

    screen_geom = screen.vrml(0.4, indent="              ")
    display = f"""DEF OLED_DISPLAY Display {{
          translation 0 0 0
          children [
            Shape {{
              appearance {app("SCREEN_MAT")}
              geometry {screen_geom}
            }}
          ]
          name "oled_display"
          width {OLED_DISP_W}
          height {OLED_DISP_H}
        }}"""

    # Top crown 50x30 mm solar panel acting as floating bumper for head_touch
    solar_crown = f"""Pose {{
          translation 0 0 0
          children [
            Shape {{
              appearance USE BEZEL
              geometry Box {{
                size {_r(SOLAR_W + 0.002)} {_r(SOLAR_D + 0.002)} {_r(SOLAR_H)}
              }}
            }}
            Pose {{
              translation 0 0 0.0002
              children [
                Shape {{
                  appearance {app("SOLAR_CELL")}
                  geometry Box {{
                    size {_r(SOLAR_W)} {_r(SOLAR_D)} {_r(SOLAR_H)}
                  }}
                }}
              ]
            }}
          ]
        }}"""

    touch = f"""TouchSensor {{
          translation 0 0 { _r(HEAD_H/2 + SOLAR_H / 2) }
          name "head_touch"
          type "bumper"
          children [
            {solar_crown}
          ]
          boundingObject Box {{
            size {_r(SOLAR_W + 0.002)} {_r(SOLAR_D + 0.002)} {_r(SOLAR_H + 0.002)}
          }}
        }}"""

    # Camera pinhole tucked cleanly inside top bezel strip above the AMOLED glass
    camera = f"""Camera {{
          translation 0 {_r(-HEAD_D/2 - 0.0005)} {_r(IMG_H/2 + SCR_Z_OFFSET + 0.0014)}
          rotation 0 0 1 -1.57079632679
          children [
            Pose {{
              translation -0.0008 0 0
              rotation 0 0 1 1.57079632679
              children [
                Shape {{
                  appearance {app("MIC")}
                  geometry Cylinder {{
                    height 0.0014
                    radius 0.0015
                    subdivision 20
                  }}
                }}
              ]
            }}
          ]
          name "camera"
          fieldOfView 1.40
          near 0.05
          width 160
          height 120
        }}"""

    return f"""#VRML_SIM R2025a utf8
# Chintu fitted-CAD body (146 mm tall, Ø86 mm base, Ø32 mm ball socket,
# 68x58x46 mm seamless head, 2.06" 502x410 AMOLED, 50x30 mm solar crown bumper).
# Pan joint is head_yaw about Z (±80 deg); tilt joint is head_pitch about X through
# the gimbal ball center (±26 deg). Device names match gemma_bot_controller.py.

PROTO GemaBotReview [
  field SFVec3f    translation  0 0 0
  field SFRotation rotation     0 0 1 0
  field SFString   name         "Chintu"
  field SFString   controller   "chintu_controller"
  field SFBool     supervisor   TRUE
]
{{
  Robot {{
    translation IS translation
    rotation IS rotation
    name IS name
    controller IS controller
    supervisor IS supervisor
    children [
      {chr(10).join(parts)}
      HingeJoint {{
        jointParameters HingeJointParameters {{
          axis 0 0 1
          anchor 0 0 { _r(NECK_BASE_Z) }
          minStop -1.4
          maxStop 1.4
        }}
        device [
          RotationalMotor {{
            name "head_yaw"
            maxVelocity 4
            maxTorque 1.5
            sound ""
          }}
          PositionSensor {{
            name "yaw_sensor"
          }}
        ]
        endPoint Solid {{
          translation 0 0 { _r(NECK_BASE_Z) }
          name "neck"
          children [
            {neck_visuals}
            HingeJoint {{
              jointParameters HingeJointParameters {{
                axis 1 0 0
                anchor 0 0 { _r(NECK_H) }
                minStop -0.454
                maxStop 0.454
              }}
              device [
                RotationalMotor {{
                  name "head_pitch"
                  maxVelocity 3.5
                  maxTorque 1.5
                  sound ""
                }}
                PositionSensor {{
                  name "pitch_sensor"
                }}
              ]
              endPoint Solid {{
                translation 0 0 { _r(NECK_H) }
                name "head"
                children [
                  {pogo_collar}
                  Pose {{
                    translation 0 0 { _r(HEAD_CENTER_LOCAL_Z) }
                    children [
                      {head_bits}
                      {display}
                      {touch}
                      {camera}
                    ]
                  }}
                ]
                boundingObject Pose {{
                  translation 0 0 { _r(HEAD_CENTER_LOCAL_Z) }
                  children [
                    Box {{
                      size { _r(HEAD_W) } { _r(HEAD_D) } { _r(HEAD_H) }
                    }}
                  ]
                }}
                physics Physics {{
                  density -1
                  mass { _r(HEAD_MASS_KG) }
                }}
              }}
            }}
          ]
          boundingObject Pose {{
            translation 0 0 { _r(NECK_H / 2) }
            rotation 1 0 0 1.57079632679
            children [
              Cylinder {{
                height { _r(NECK_H) }
                radius { _r(NECK_R_BOT) }
              }}
            ]
          }}
          physics Physics {{
            density -1
            mass 0.04
          }}
        }}
      }}
    ]
    boundingObject Pose {{
      translation 0 0 { _r(BASE_H / 2) }
      rotation 1 0 0 1.57079632679
      children [
        Cylinder {{
          height { _r(BASE_H) }
          radius { _r(BASE_R_BOT) }
        }}
      ]
    }}
  }}
}}
"""


def dock_proto(body: Mesh, clock: Mesh) -> str:
    return f"""#VRML_SIM R2025a utf8
# 99 x 99 x 16 mm clock charging dock. The robot base sits 3 mm into the top pocket.
# Clock face is the attached 10:42 texture.

PROTO GemaClockDock [
  field SFVec3f    translation  0 0 0
  field SFRotation rotation     0 0 1 0
  field SFString   name         "clock dock"
]
{{
  Solid {{
    translation IS translation
    rotation IS rotation
    name IS name
    children [
      {emit_indexed("dock", "DEF DOCK_SHELL PBRAppearance { baseColor 0.18 0.18 0.19 roughness 0.6 metalness 0 }", body, 0.8)}
      {emit_indexed("clock", 'DEF CLOCK_MAT PBRAppearance { baseColor 0 0 0 roughness 0.2 metalness 0 emissiveIntensity 2.4 baseColorMap DEF CLOCK_TEX ImageTexture { url [ "textures/clock_1042.png" ] repeatS FALSE repeatT FALSE filtering 0 } emissiveColorMap USE CLOCK_TEX }', clock, 0.4)}
      Pose {{
        translation 0 { _r(-DOCK/2 - 0.0002) } 0.0018
        children [
          Shape {{
            appearance DEF DOCK_LED PBRAppearance {{
              baseColor 0.9 0.25 0.03
              roughness 0.35
              emissiveColor 1 0.32 0.04
              emissiveIntensity 3.2
            }}
            geometry Box {{
              size 0.084 0.0006 0.0013
            }}
          }}
        ]
      }}
    ]
    boundingObject Pose {{
      translation 0 0 { _r(DOCK_H / 2) }
      children [
        Box {{
          size { _r(DOCK) } { _r(DOCK) } { _r(DOCK_H) }
        }}
      ]
    }}
  }}
}}
"""


def look_at(eye, target, up=(0.0, 0.0, 1.0)):
    """Webots viewpoint: local -Z looks at the target, local +Y is up."""
    forward = _norm(_sub(target, eye))
    z_axis = _mul(forward, -1.0)
    x_axis = _norm(_cross(forward, up))
    y_axis = _norm(_cross(z_axis, x_axis))
    # Columns are the images of the local axes.
    r = (
        (x_axis[0], y_axis[0], z_axis[0]),
        (x_axis[1], y_axis[1], z_axis[1]),
        (x_axis[2], y_axis[2], z_axis[2]),
    )
    trace = r[0][0] + r[1][1] + r[2][2]
    angle = math.acos(max(-1.0, min(1.0, (trace - 1.0) / 2.0)))
    if angle < 1e-8:
        return (0.0, 0.0, 1.0, 0.0)
    axis = (
        r[2][1] - r[1][2],
        r[0][2] - r[2][0],
        r[1][0] - r[0][1],
    )
    axis = _norm(axis)
    return (axis[0], axis[1], axis[2], angle)


def world_file(robot_xy, dock_z_note=False) -> str:
    rx, ry = robot_xy
    robot_z = DESK_TOP
    # Orientation taken from worlds/gemma_bot.wbt (it frames an upright Z-up robot).
    ox, oy, oz, oa = (
        0.061059499569659864,
        -0.07047738381890405,
        -0.9956428455436946,
        4.851019190051961,
    )
    eye = (0.148, -0.971, 1.052)
    # Laptop hinge leans the lid back toward +Y so the panel faces the viewer.
    return f"""#VRML_SIM R2025a utf8
# Chintu fitted-CAD desk scene.
# Robot: 146 mm stationary companion, Ø86 mm tapered base, Ø32 mm ball socket,
# 68x58x46 mm seamless head, 47.2x39.2 mm (502x410) AMOLED, 50x30 mm solar crown bumper.
# Controller, device names, and the Sarvam voice pipeline are unchanged.

EXTERNPROTO "../protos/GemaBotReview.proto"

WorldInfo {{
  title "Chintu Desktop Companion"
  info [
    "Review-plan concept: stationary GemaBot on a clock charging dock, WFH desk."
    "Reuses gemma_bot_controller (head_yaw, head_pitch, oled_display, camera, head_touch)."
    "Open this world in Webots R2025a. See docs/DEMO_REVIEW_PLAN.md."
  ]
  basicTimeStep 16
  coordinateSystem "ENU"
  FPS 60
}}
Viewpoint {{
  fieldOfView 0.52
  orientation { _r(ox) } { _r(oy) } { _r(oz) } { _r(oa) }
  position { _r(eye[0]) } { _r(eye[1]) } { _r(eye[2]) }
  near 0.02
  far 30
  exposure 1.0
  followType "None"
  description "Review-plan three-quarter"
}}
Background {{
  skyColor [ 0.78 0.80 0.82 ]
  luminosity 1.05
}}
DirectionalLight {{
  direction 0.28 0.72 -0.55
  intensity 1.15
  color 1 0.97 0.93
  ambientIntensity 0.35
  castShadows TRUE
}}
DirectionalLight {{
  direction -0.45 0.55 -0.25
  intensity 0.45
  color 0.86 0.90 1
  ambientIntensity 0.2
  castShadows FALSE
}}
DirectionalLight {{
  direction -0.1 -0.8 -0.35
  intensity 0.55
  color 1 0.96 0.9
  castShadows FALSE
}}
PointLight {{
  location { _r(rx - 0.25) } { _r(ry - 0.35) } { _r(DESK_TOP + 0.55) }
  intensity 2.2
  color 1 0.95 0.88
  attenuation 0 0 0.8
  radius 3
  castShadows FALSE
}}

Solid {{
  translation 0 0.15 -0.02
  name "floor"
  children [
    Shape {{
      appearance PBRAppearance {{
        baseColor 0.70 0.64 0.56
        roughness 0.78
        metalness 0
      }}
      geometry Box {{
        size 4.6 3.6 0.04
      }}
    }}
  ]
  boundingObject Box {{
    size 4.6 3.6 0.04
  }}
}}
Solid {{
  translation 0.08 0.02 { _r(DESK_TOP - 0.004) }
  name "rug"
  children [
    Shape {{
      appearance PBRAppearance {{
        baseColor 0.55 0.57 0.58
        roughness 0.9
      }}
      geometry Box {{
        size 1.85 1.15 0.008
      }}
    }}
  ]
}}
Solid {{
  translation 0 1.20 1.15
  name "wall back"
  children [
    Shape {{
      appearance PBRAppearance {{
        baseColor 0.86 0.84 0.80
        roughness 0.85
      }}
      geometry Box {{
        size 3.4 0.08 2.30
      }}
    }}
    Pose {{
      translation -0.72 -0.045 0.28
      children [
        Shape {{
          appearance PBRAppearance {{
            baseColor 0.93 0.90 0.84
            roughness 0.4
            emissiveColor 1 0.90 0.72
            emissiveIntensity 1.4
          }}
          geometry Box {{
            size 0.78 0.02 0.62
          }}
        }}
      ]
    }}
  ]
}}
Solid {{
  translation -1.55 0.15 1.15
  name "wall left"
  children [
    Shape {{
      appearance PBRAppearance {{
        baseColor 0.84 0.82 0.78
        roughness 0.85
      }}
      geometry Box {{
        size 0.08 2.2 2.30
      }}
    }}
  ]
}}

Solid {{
  translation 0.06 0.04 { _r(DESK_TOP - 0.014) }
  name "desk"
  children [
    Shape {{
      appearance DEF WOOD PBRAppearance {{
        baseColor 0.46 0.32 0.22
        roughness 0.52
        metalness 0.02
      }}
      geometry Box {{
        size 1.38 0.70 0.028
      }}
    }}
    Pose {{
      translation -0.62 0.28 -0.370
      children [
        Shape {{
          appearance USE WOOD
          geometry Box {{ size 0.045 0.045 0.712 }}
        }}
      ]
    }}
    Pose {{
      translation 0.62 0.28 -0.370
      children [
        Shape {{
          appearance USE WOOD
          geometry Box {{ size 0.045 0.045 0.712 }}
        }}
      ]
    }}
    Pose {{
      translation -0.62 -0.28 -0.370
      children [
        Shape {{
          appearance USE WOOD
          geometry Box {{ size 0.045 0.045 0.712 }}
        }}
      ]
    }}
    Pose {{
      translation 0.62 -0.28 -0.370
      children [
        Shape {{
          appearance USE WOOD
          geometry Box {{ size 0.045 0.045 0.712 }}
        }}
      ]
    }}
  ]
  boundingObject Box {{
    size 1.38 0.70 0.028
  }}
}}

# Laptop, screen facing -Y (toward the person at the desk).
Solid {{
  translation -0.02 -0.08 { _r(DESK_TOP + 0.005) }
  name "laptop"
  children [
    Shape {{
      appearance DEF ALUMINUM PBRAppearance {{
        baseColor 0.72 0.73 0.75
        roughness 0.32
        metalness 0.65
      }}
      geometry Box {{
        size 0.305 0.214 0.010
      }}
    }}
    Pose {{
      translation 0 0.012 0.0056
      children [
        Shape {{
          appearance PBRAppearance {{
            baseColor 0.16 0.16 0.17
            roughness 0.55
          }}
          geometry Box {{
            size 0.27 0.15 0.001
          }}
        }}
      ]
    }}
    Pose {{
      translation 0 -0.045 0.0056
      children [
        Shape {{
          appearance PBRAppearance {{
            baseColor 0.22 0.22 0.23
            roughness 0.4
          }}
          geometry Box {{
            size 0.09 0.055 0.001
          }}
        }}
      ]
    }}
    Pose {{
      translation 0 0.107 0.006
      rotation 1 0 0 -0.42
      children [
        Pose {{
          translation 0 -0.003 0.098
          children [
            Shape {{
              appearance USE ALUMINUM
              geometry Box {{
                size 0.305 0.005 0.196
              }}
            }}
            Pose {{
              translation 0 -0.0028 0.004
              children [
                Shape {{
                  appearance PBRAppearance {{
                    baseColor 0.05 0.07 0.09
                    roughness 0.2
                    emissiveColor 0.25 0.40 0.55
                    emissiveIntensity 0.35
                  }}
                  geometry Box {{
                    size 0.278 0.001 0.168
                  }}
                }}
              ]
            }}
          ]
        }}
      ]
    }}
  ]
}}

Solid {{
  translation 0.55 -0.18 { _r(DESK_TOP + 0.032) }
  name "cup"
  children [
    Pose {{
      rotation 1 0 0 1.57079632679
      children [
        Shape {{
          appearance PBRAppearance {{
            baseColor 0.90 0.88 0.84
            roughness 0.4
          }}
          geometry Cylinder {{
            height 0.064
            radius 0.034
            subdivision 40
          }}
        }}
      ]
    }}
    Pose {{
      translation 0 0 0.033
      rotation 1 0 0 1.57079632679
      children [
        Shape {{
          appearance PBRAppearance {{
            baseColor 0.55 0.36 0.18
            roughness 0.35
          }}
          geometry Cylinder {{
            height 0.002
            radius 0.026
            subdivision 32
          }}
        }}
      ]
    }}
  ]
}}

Solid {{
  translation -0.22 0.16 { _r(DESK_TOP) }
  name "plant"
  children [
    Pose {{
      translation 0 0 0.022
      rotation 1 0 0 1.57079632679
      children [
        Shape {{
          appearance PBRAppearance {{
            baseColor 0.42 0.28 0.18
            roughness 0.6
          }}
          geometry Cylinder {{
            height 0.044
            radius 0.038
            subdivision 32
          }}
        }}
      ]
    }}
    Pose {{
      translation 0 0 0.07
      children [
        Shape {{
          appearance DEF LEAF PBRAppearance {{
            baseColor 0.22 0.40 0.20
            roughness 0.55
          }}
          geometry Sphere {{
            radius 0.038
            subdivision 3
          }}
        }}
      ]
    }}
    Pose {{
      translation 0.02 -0.01 0.105
      children [
        Shape {{
          appearance USE LEAF
          geometry Sphere {{
            radius 0.028
            subdivision 3
          }}
        }}
      ]
    }}
    Pose {{
      translation -0.018 0.012 0.098
      children [
        Shape {{
          appearance PBRAppearance {{
            baseColor 0.28 0.48 0.24
            roughness 0.5
          }}
          geometry Sphere {{
            radius 0.026
            subdivision 3
          }}
        }}
      ]
    }}
  ]
}}

GemaBotReview {{
  translation { _r(rx) } { _r(ry) } { _r(robot_z) }
}}
"""


def check_vrml(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    first = text.splitlines()[0]
    if first != "#VRML_SIM R2025a utf8":
        raise SystemExit(f"{path} header is {first!r}")
    depth = 0
    for i, ch in enumerate(text):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                raise SystemExit(f"{path} extra closing brace near character {i}")
    if depth != 0:
        raise SystemExit(f"{path} unbalanced braces ({depth})")
    if "PROTO" in path.name or path.suffix == ".proto":
        return
    for token in ("GemaBotReview", "Viewpoint", "WorldInfo"):
        if token not in text:
            raise SystemExit(f"{path} missing {token}")


def _mean_normal(mesh: Mesh):
    acc = (0.0, 0.0, 0.0)
    for a, b, c in mesh.tris:
        va, vb, vc = mesh.verts[a], mesh.verts[b], mesh.verts[c]
        n = _cross(_sub(vb, va), _sub(vc, va))
        acc = _add(acc, n)
    return _norm(acc)


def main() -> None:
    clock_v0, clock_v1 = copy_textures()
    write_logo()
    write_face()
    base = lathe(base_profile(), 72, interior=(0.0, 0.0, 0.025))
    head_shell = build_head_mesh()
    logo_mesh = build_curved_logo_mesh()
    bezel = build_bezel()
    screen = build_screen()
    dock = build_dock_mesh()
    clock = build_clock(clock_v0, clock_v1)

    # Dimension guards so a mesh change cannot silently leave the fitted CAD spec.
    bb = base.bounds()
    assert abs(bb[5] - BASE_H) < 1e-4, bb
    assert abs(max(abs(bb[0]), abs(bb[1])) - BASE_R_BOT) < 0.006, bb
    hb = head_shell.bounds()
    assert abs((hb[1] - hb[0]) - HEAD_W) < 0.002, hb
    assert abs((hb[5] - hb[4]) - HEAD_H) < 0.002, hb
    db = dock.bounds()
    assert abs(db[1] - db[0] - DOCK) < 0.004, db
    assert abs(db[5] - db[4] - DOCK_H) < 0.003, db
    assert abs(OVERALL_HEIGHT_M - 0.146) < 1e-6
    screen_n = _mean_normal(screen)
    assert screen_n[1] < -0.5, screen_n
    clock_n = _mean_normal(clock)
    assert clock_n[1] < -0.5, clock_n

    PROTO_DIR.mkdir(parents=True, exist_ok=True)
    robot_path = PROTO_DIR / "GemaBotReview.proto"
    robot_path.write_text(
        robot_proto(base, head_shell, logo_mesh, bezel, screen),
        encoding="utf-8",
    )
    WORLD_PATH.write_text(world_file((0.30, 0.06)), encoding="utf-8")
    for path in (robot_path, WORLD_PATH):
        check_vrml(path)
    proto_text = robot_path.read_text(encoding="utf-8")
    for name in ("oled_display", "camera", "head_yaw", "head_pitch", "yaw_sensor", "pitch_sensor", "head_touch"):
        if f'name "{name}"' not in proto_text:
            raise SystemExit(f"missing device {name}")
    if f"width {OLED_DISP_W}" not in proto_text or f"height {OLED_DISP_H}" not in proto_text:
        raise SystemExit(f"OLED size is not {OLED_DISP_W}x{OLED_DISP_H}")
    print(f"wrote {robot_path.relative_to(ROOT)} ({robot_path.stat().st_size} bytes)")
    print(f"wrote {WORLD_PATH.relative_to(ROOT)}")
    print(f"ball-center z={BALL_CENTER_Z:.4f}  head-center z={HEAD_CENTER_Z:.3f}  total height {OVERALL_HEIGHT_M:.3f}")


if __name__ == "__main__":
    main()
