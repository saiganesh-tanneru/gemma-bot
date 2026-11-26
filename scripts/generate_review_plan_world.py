#!/usr/bin/env python3
"""Generate the GemaBot review-plan Webots world and PROTOs.

Dimensions follow gemabot_scene.py (millimetres, Z up, face toward -Y):

  base     tapered frustum, bottom diameter 96 mm, top diameter 84 mm, height 70 mm
  neck     40 mm, pan axis on the base top
  head     95 x 80 x 75 mm (W x H x D), 9 mm bevel, tilt axis through the head centre
  screen   65 x 49 mm (3.2 in) in a 74 x 58 mm recess
  overall  190 mm from base bottom to head top
  dock     99 x 99 x 16 mm, robot sits 3 mm into the top pocket

The controller is not touched. Device names match gemma_bot_controller:
oled_display, camera, head_yaw, head_pitch, yaw_sensor, pitch_sensor, head_touch.
"""

from __future__ import annotations

import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
PROTO_DIR = ROOT / "protos"
TEX_DIR = PROTO_DIR / "textures"
WORLD_PATH = ROOT / "worlds" / "gemabot_review_plan.wbt"

# Source textures shipped with the concept (copied next to the PROTOs).
_UPLOADS = Path("/home/ubuntu/.cursor/projects/workspace/uploads")
FACE_HAPPY_SRC = _UPLOADS / "face_happy_e555.png"
FACE_JOY_SRC = _UPLOADS / "face_joy_71a0.png"
CLOCK_SRC = _UPLOADS / "clock_1042_d25a.png"

# Concept parameters, metres.
BASE_H = 0.070
BASE_R_BOT = 0.048
BASE_R_TOP = 0.042
NECK_H = 0.040
NECK_R = 0.023
HEAD_W = 0.095
HEAD_H = 0.080
HEAD_D = 0.075
HEAD_BEVEL = 0.009
SCR_W = 0.074
SCR_H = 0.058
IMG_W = 0.065
IMG_H = 0.049
DOCK = 0.099
DOCK_H = 0.016
SEAM_FROM_FRONT = 0.013
SEAM_GAP = 0.0008
HEAD_CENTER_Z = BASE_H + NECK_H + HEAD_H / 2  # 0.150; top of head is 0.190

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

    zg = 0.010
    rg = base_radius(zg)
    zs = 0.060
    rs = base_radius(zs)
    return [
        lip(0.000, 0.0045),
        lip(0.0016, 0.0016),
        (0.0036, base_radius(0.0036)),
        (0.0076, base_radius(0.0076)),
        (0.0085, rg - 0.0005),
        (0.0089, rg - 0.0018),
        (0.0111, rg - 0.0018),
        (0.0115, base_radius(0.0115) - 0.0005),
        (0.0130, base_radius(0.0130)),
        (0.0300, base_radius(0.0300)),
        (0.0480, base_radius(0.0480)),
        (0.0588, base_radius(0.0588)),
        (0.0594, rs - 0.00035),
        (0.0597, rs - 0.00105),
        (0.0603, rs - 0.00105),
        (0.0606, base_radius(0.0606) - 0.00035),
        (0.0620, base_radius(0.0620)),
        (0.0662, base_radius(0.0662)),
        lip(0.0684, 0.0014),
        lip(0.0700, 0.0040),
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


def build_head_meshes():
    half = (HEAD_W / 2, HEAD_D / 2, HEAD_H / 2)
    # Few segments: a dense grid flat-shades into a chevron pattern in Webots' software renderer.
    head = rounded_box(half, HEAD_BEVEL, 5)
    seam = -HEAD_D / 2 + SEAM_FROM_FRONT
    front = clip_mesh(head, 1, seam, keep_below=True)
    back = clip_mesh(head, 1, seam + SEAM_GAP, keep_below=False)
    # Dark caps close each shell so the 0.8 mm gap reads as a seam.
    cap_front = rounded_rect(HEAD_W - 0.0012, HEAD_H - 0.0012, HEAD_BEVEL, seam, facing=+1, segments=6)
    cap_back = rounded_rect(HEAD_W - 0.0012, HEAD_H - 0.0012, HEAD_BEVEL, seam + SEAM_GAP, facing=-1, segments=6)
    return front, back, cap_front, cap_back, seam


def build_screen() -> Mesh:
    # Proud of the head's front face so the panel is not hidden inside the shell.
    return rounded_rect(IMG_W, IMG_H, 0.0065, -HEAD_D / 2 - 0.0008, facing=-1, segments=6)


def build_bezel() -> Mesh:
    return rounded_rect(SCR_W - 0.0012, SCR_H - 0.0012, 0.0075, -HEAD_D / 2 - 0.00035, facing=-1, segments=5)


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


def write_logo() -> None:
    TEX_DIR.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (512, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/macos/Inter-SemiBold.ttf", 78)
    letters = list("GEMA")
    widths = [draw.textlength(ch, font=font) for ch in letters]
    tracking = 18
    total = sum(widths) + tracking * (len(letters) - 1)
    x = (512 - total) / 2
    for ch, width in zip(letters, widths):
        draw.text((x, 22), ch, font=font, fill=(214, 214, 218, 255))
        x += width + tracking
    image.save(TEX_DIR / "logo_gema.png")


def copy_textures() -> tuple[float, float]:
    """Copy face art as-is. Pad the clock onto a 1024x512 sheet so Webots does not
    stretch the non-power-of-two source. Returns the V range of the digits."""
    TEX_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FACE_HAPPY_SRC, TEX_DIR / "face_happy.png")
    shutil.copyfile(FACE_JOY_SRC, TEX_DIR / "face_joy.png")
    src = Image.open(CLOCK_SRC).convert("RGBA")
    canvas_w, canvas_h = 1024, 512
    scaled_h = max(1, round(src.height * canvas_w / src.width))
    scaled = src.resize((canvas_w, scaled_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 255))
    top = (canvas_h - scaled_h) // 2
    canvas.paste(scaled, (0, top))
    canvas.save(TEX_DIR / "clock_1042.png")
    # OpenGL / Webots v=0 is the bottom of the image.
    v0 = (canvas_h - (top + scaled_h)) / canvas_h
    v1 = (canvas_h - top) / canvas_h
    return v0, v1


def robot_proto(base: Mesh, front: Mesh, back: Mesh, cap_f: Mesh, cap_b: Mesh, bezel: Mesh, screen: Mesh) -> str:
    # PBRAppearance is not a legal Robot child, so each material is DEF'd on first use.
    defined: set[str] = set()
    material_body = {
        "CHARCOAL": "baseColor 0.145 0.145 0.152 roughness 0.62 metalness 0.04",
        "CHARCOAL_DARK": "baseColor 0.035 0.035 0.038 roughness 0.55 metalness 0.02",
        "GRAPHITE": "baseColor 0.105 0.105 0.112 roughness 0.32 metalness 0.42",
        "ACCENT": "baseColor 0.86 0.45 0.32 roughness 0.38 metalness 0.02",
        "LED": "baseColor 0.95 0.40 0.18 roughness 0.35 emissiveColor 1 0.42 0.12 emissiveIntensity 3.5",
        "MIC": "baseColor 0.02 0.02 0.022 roughness 0.45 metalness 0.1",
        "BEZEL": "baseColor 0.012 0.012 0.014 roughness 0.25 metalness 0.05",
        "LOGO_MAT": (
            'baseColor 1 1 1 roughness 0.45 metalness 0 baseColorMap ImageTexture { '
            'url [ "textures/logo_gema.png" ] repeatS FALSE repeatT FALSE }'
        ),
        "SCREEN_MAT": (
            "baseColor 0 0 0 roughness 0.18 metalness 0 emissiveIntensity 1.6 "
            'baseColorMap DEF FACE_TEX ImageTexture { url [ "textures/face_happy.png" ] '
            "repeatS FALSE repeatT FALSE filtering 0 } emissiveColorMap USE FACE_TEX"
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

    led_r = base_radius(0.010) - 0.00055
    seam_r = base_radius(0.060) - 0.00045
    parts = [
        emit_indexed("base", app("CHARCOAL"), base, 0.7),
        cyl(app("LED"), led_r, 0.00215, "0 0 0.010", "1 0 0 1.57079632679", 64),
        cyl(app("CHARCOAL_DARK"), seam_r, 0.0007, "0 0 0.060", "1 0 0 1.57079632679", 64),
        cyl(app("ACCENT"), 0.0032, 0.0022, "0.014 -0.026 0.0702", "1 0 0 1.57079632679", 24),
    ]
    # Quad on the tapered front wall. Tilt matches atan((r_bot-r_top)/h).
    taper = math.atan((BASE_R_BOT - BASE_R_TOP) / BASE_H)
    lz = 0.034
    ly = -(base_radius(lz) + 0.0006)
    logo_w, logo_h = 0.030, 0.0072
    # Local quad in XZ, then the Pose below rotates it onto the wall.
    logo_block = (
        "Pose {\n"
        f"          translation 0 { _r(ly) } { _r(lz) }\n"
        f"          rotation 1 0 0 { _r(taper) }\n"
        "          children [\n"
        "            Shape {\n"
        f"              appearance {app('LOGO_MAT')}\n"
        "              geometry IndexedFaceSet {\n"
        "                coord Coordinate {\n"
        "                  point [\n"
        f"                    { _r(-logo_w/2) } 0 { _r(-logo_h/2) }\n"
        f"                    { _r(logo_w/2) } 0 { _r(-logo_h/2) }\n"
        f"                    { _r(logo_w/2) } 0 { _r(logo_h/2) }\n"
        f"                    { _r(-logo_w/2) } 0 { _r(logo_h/2) }\n"
        "                  ]\n"
        "                }\n"
        "                texCoord TextureCoordinate {\n"
        "                  point [ 0 0, 1 0, 1 1, 0 1 ]\n"
        "                }\n"
        "                coordIndex [ 0 1 2 -1, 0 2 3 -1 ]\n"
        "                texCoordIndex [ 0 1 2 -1, 0 2 3 -1 ]\n"
        "              }\n"
        "            }\n"
        "          ]\n"
        "        }"
    )
    parts.append(logo_block)

    neck_visuals = "\n".join(
        [
            cyl(app("GRAPHITE"), NECK_R + 0.006, 0.004, "0 0 0.002", "1 0 0 1.57079632679", 48),
            cyl(app("GRAPHITE"), NECK_R, 0.046, "0 0 0.023", "1 0 0 1.57079632679", 48),
        ]
    )
    head_bits = "\n".join(
        [
            emit_indexed("head front", app("CHARCOAL"), front, 1.4),
            emit_indexed("head back", app("CHARCOAL"), back, 1.4),
            emit_indexed("cap f", app("CHARCOAL_DARK"), cap_f, 0.4),
            emit_indexed("cap b", app("CHARCOAL_DARK"), cap_b, 0.4),
            emit_indexed("bezel", app("BEZEL"), bezel, 0.5),
            cyl(app("ACCENT"), 0.014, 0.004, f"{_r(HEAD_W/2 + 0.0012)} 0 0", "0 0 1 1.57079632679", 40),
            cyl(app("ACCENT"), 0.014, 0.004, f"{_r(-(HEAD_W/2 + 0.0012))} 0 0", "0 0 1 1.57079632679", 40),
            cyl(app("GRAPHITE"), 0.005, 0.0012, f"{_r(HEAD_W/2 + 0.0034)} 0 0", "0 0 1 1.57079632679", 32),
            cyl(app("GRAPHITE"), 0.005, 0.0012, f"{_r(-(HEAD_W/2 + 0.0034))} 0 0", "0 0 1 1.57079632679", 32),
        ]
    )
    # Mic dots sit on the crown and are the visible part of the touch sensor.
    mics = []
    for mx in (-0.006, 0.0, 0.006):
        mics.append(
            cyl(app("MIC"), 0.00115, 0.0014, f"{_r(mx)} 0 0", "1 0 0 1.57079632679", 16)
        )
    mic_block = "\n".join(mics)

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
          width 128
          height 64
        }}"""

    touch = f"""TouchSensor {{
          translation 0 0.008 { _r(HEAD_H/2 + 0.0004) }
          name "head_touch"
          type "bumper"
          children [
            {mic_block}
          ]
          boundingObject Sphere {{
            radius 0.014
          }}
        }}"""

    camera = """Camera {
          translation 0 -0.0392 0.026
          rotation 1 0 0 -1.57079632679
          children [
            Pose {
              rotation 0 0 1 1.57079632679
              children [
                Shape {
                  appearance USE MIC
                  geometry Cylinder {
                    height 0.0022
                    radius 0.0024
                    subdivision 24
                  }
                }
              ]
            }
          ]
          name "camera"
          fieldOfView 1
          width 160
          height 120
        }"""

    head_z = NECK_H + HEAD_H / 2
    return f"""#VRML_SIM R2025a utf8
# GemaBot review-plan body. Stationary (no wheels). Pan joint is head_yaw about Z,
# tilt joint is head_pitch about X through the head centre. Device names match
# controllers/gemma_bot_controller/gemma_bot_controller.py.

PROTO GemaBotReview [
  field SFVec3f    translation  0 0 0
  field SFRotation rotation     0 0 1 0
  field SFString   name         "Gemma-Bot"
  field SFString   controller   "gemma_bot_controller"
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
          anchor 0 0 { _r(BASE_H) }
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
          translation 0 0 { _r(BASE_H) }
          name "neck"
          children [
            {neck_visuals}
            HingeJoint {{
              jointParameters HingeJointParameters {{
                axis 1 0 0
                anchor 0 0 { _r(head_z) }
                minStop -0.45
                maxStop 0.45
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
                translation 0 0 { _r(head_z) }
                name "head"
                children [
                  {head_bits}
                  {display}
                  {touch}
                  {camera}
                ]
                boundingObject Box {{
                  size 0.108 0.078 0.084
                }}
                physics Physics {{
                  density -1
                  mass 0.15
                }}
              }}
            }}
          ]
          boundingObject Pose {{
            translation 0 0 0.017
            rotation 1 0 0 1.57079632679
            children [
              Cylinder {{
                height 0.034
                radius 0.024
              }}
            ]
          }}
          physics Physics {{
            density -1
            mass 0.05
          }}
        }}
      }}
    ]
    boundingObject Pose {{
      translation 0 0 0.034
      rotation 1 0 0 1.57079632679
      children [
        Cylinder {{
          height 0.068
          radius 0.048
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
      {emit_indexed("dock", "DEF DOCK_SHELL PBRAppearance { baseColor 0.145 0.145 0.152 roughness 0.62 metalness 0.04 }", body, 0.8)}
      {emit_indexed("clock", 'DEF CLOCK_MAT PBRAppearance { baseColor 0 0 0 roughness 0.2 metalness 0 emissiveIntensity 2.4 baseColorMap DEF CLOCK_TEX ImageTexture { url [ "textures/clock_1042.png" ] repeatS FALSE repeatT FALSE filtering 0 } emissiveColorMap USE CLOCK_TEX }', clock, 0.4)}
      Pose {{
        translation 0 { _r(-DOCK/2 - 0.0002) } 0.0018
        children [
          Shape {{
            appearance DEF DOCK_LED PBRAppearance {{
              baseColor 0.95 0.40 0.18
              roughness 0.35
              emissiveColor 1 0.42 0.12
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


def world_file(robot_xy, dock_z_note=True) -> str:
    rx, ry = robot_xy
    robot_z = DESK_TOP + (DOCK_H - 0.003)
    # Orientation taken from worlds/gemma_bot.wbt (it frames an upright Z-up robot).
    # Position is in front of this robot's head so the dock clock and desk stay in frame.
    ox, oy, oz, oa = (
        0.061059499569659864,
        -0.07047738381890405,
        -0.9956428455436946,
        4.851019190051961,
    )
    eye = (0.148, -0.971, 1.052)
    # Laptop hinge leans the lid back toward +Y so the panel faces the viewer.
    return f"""#VRML_SIM R2025a utf8
# GemaBot review-plan desk scene.
# Robot: 190 mm stationary companion, 96 mm tapered base, 95x80x75 mm head,
# 65x49 mm face, pan/tilt neck. Dock: 99x99x16 mm clock charger.
# Controller, device names, and the Sarvam voice pipeline are unchanged.

EXTERNPROTO "../protos/GemaBotReview.proto"
EXTERNPROTO "../protos/GemaClockDock.proto"

WorldInfo {{
  title "GemaBot Review Plan"
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

GemaClockDock {{
  translation { _r(rx) } { _r(ry) } { _r(DESK_TOP) }
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
    for token in ("GemaBotReview", "GemaClockDock", "Viewpoint", "WorldInfo"):
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
    base = lathe(base_profile(), 72, interior=(0.0, 0.0, 0.035))
    front, back, cap_f, cap_b, seam = build_head_meshes()
    bezel = build_bezel()
    screen = build_screen()
    dock = build_dock_mesh()
    clock = build_clock(clock_v0, clock_v1)

    # Dimension guards so a mesh change cannot silently leave the concept.
    bb = base.bounds()
    assert abs(bb[5] - BASE_H) < 1e-4, bb
    assert abs(max(abs(bb[0]), abs(bb[1])) - BASE_R_BOT) < 0.006, bb
    hb = front.bounds()
    assert hb[1] > 0.04 and hb[0] < -0.04, hb
    assert abs((back.bounds()[5] - front.bounds()[4]) - HEAD_H) < 0.004
    db = dock.bounds()
    assert abs(db[1] - db[0] - DOCK) < 0.004, db
    assert abs(db[5] - db[4] - DOCK_H) < 0.003, db
    assert abs(HEAD_CENTER_Z + HEAD_H / 2 - 0.190) < 1e-6
    screen_n = _mean_normal(screen)
    assert screen_n[1] < -0.5, screen_n
    clock_n = _mean_normal(clock)
    assert clock_n[1] < -0.5, clock_n

    PROTO_DIR.mkdir(parents=True, exist_ok=True)
    robot_path = PROTO_DIR / "GemaBotReview.proto"
    dock_path = PROTO_DIR / "GemaClockDock.proto"
    robot_path.write_text(
        robot_proto(base, front, back, cap_f, cap_b, bezel, screen),
        encoding="utf-8",
    )
    dock_path.write_text(dock_proto(dock, clock), encoding="utf-8")
    WORLD_PATH.write_text(world_file((0.30, 0.06)), encoding="utf-8")
    for path in (robot_path, dock_path, WORLD_PATH):
        check_vrml(path)
    proto_text = robot_path.read_text(encoding="utf-8")
    for name in ("oled_display", "camera", "head_yaw", "head_pitch", "yaw_sensor", "pitch_sensor", "head_touch"):
        if f'name "{name}"' not in proto_text:
            raise SystemExit(f"missing device {name}")
    if 'width 128' not in proto_text or "height 64" not in proto_text:
        raise SystemExit("OLED size is not 128x64")
    print(f"wrote {robot_path.relative_to(ROOT)} ({robot_path.stat().st_size} bytes)")
    print(f"wrote {dock_path.relative_to(ROOT)} ({dock_path.stat().st_size} bytes)")
    print(f"wrote {WORLD_PATH.relative_to(ROOT)}")
    print(f"head seam y={seam:.4f}  head-center z={HEAD_CENTER_Z:.3f}  total height 0.190")


if __name__ == "__main__":
    main()
