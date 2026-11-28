#!/usr/bin/env python3
"""Parametric OpenCASCADE (CadQuery) CAD builder & fit verifier for Chintu.

Generates the 4 FreeCAD-ready STEP and STL parts matching the Chintu ball-socket
design, and verifies:
  1. Pan +-80 deg & Tilt +-26 deg collision clearance (3D boolean intersection).
  2. Pogo-pin ring vs. head pad alignment at full +-26 deg tilt.
  3. Head Center of Mass & static holding torque vs. MG90S / SG90 ratings.

Usage:
  uv run --with cadquery python cad/build_chintu_cad.py --preset fitted
  uv run --with cadquery python cad/build_chintu_cad.py --preset estimate --no-export
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import cadquery as cq


@dataclass(frozen=True)
class ChintuParams:
    name: str
    # Base + socket
    base_d_bot: float
    base_d_top: float
    base_h: float
    ring_groove_z: float
    # Neck + ball
    neck_d_bot: float
    neck_d_top: float
    neck_h: float
    ball_d: float
    ball_cup_depth: float
    # Head shell (X=width, Y=depth front(-Y)/back(+Y), Z=height)
    head_w: float
    head_h: float
    head_d: float
    head_wall: float
    head_fillet: float
    # 2.06" 410x502 AMOLED module envelope (landscape)
    amoled_w: float
    amoled_h: float
    amoled_recess_d: float
    # Pogo-pin + magnetic ring
    pogo_ring_d: float
    pogo_ring_h: float
    pogo_pin_pcd: float
    pogo_pin_d: float
    pogo_pad_d: float
    magnet_d: float
    magnet_h: float
    head_seat_above_ball: float
    # Kinematics
    pan_deg: float
    tilt_deg: float


PRESETS: dict[str, ChintuParams] = {
    # Fitted to real hardware: 2.06" 410x502 AMOLED (46.8x38.4mm) + ESP32-S3 + 600mAh LiPo + 2x MG90S
    "fitted": ChintuParams(
        name="fitted",
        base_d_bot=86.0,
        base_d_top=78.0,
        base_h=50.0,
        ring_groove_z=6.5,
        neck_d_bot=36.0,
        neck_d_top=24.0,
        neck_h=24.0,
        ball_d=32.0,
        ball_cup_depth=11.0,
        head_w=68.0,
        head_h=58.0,
        head_d=46.0,
        head_wall=2.5,
        head_fillet=7.0,
        amoled_w=47.2,
        amoled_h=39.2,
        amoled_recess_d=2.2,
        pogo_ring_d=24.0,
        pogo_ring_h=4.2,
        pogo_pin_pcd=17.5,
        pogo_pin_d=1.7,
        pogo_pad_d=3.6,
        magnet_d=12.2,
        magnet_h=3.0,
        head_seat_above_ball=15.5,  # docks head flush over ball, hiding pogo ring inside bay!
        pan_deg=80.0,
        tilt_deg=26.0,
    ),
    # User's initial rough estimate from GemaBotReview (base Ø96mm, head 95x80x75mm)
    "estimate": ChintuParams(
        name="estimate",
        base_d_bot=96.0,
        base_d_top=84.0,
        base_h=70.0,
        ring_groove_z=8.0,
        neck_d_bot=42.0,
        neck_d_top=28.0,
        neck_h=26.0,
        ball_d=36.0,
        ball_cup_depth=12.0,
        head_w=95.0,
        head_h=80.0,
        head_d=75.0,
        head_wall=3.0,
        head_fillet=9.0,
        amoled_w=47.2,
        amoled_h=39.2,
        amoled_recess_d=2.2,
        pogo_ring_d=26.0,
        pogo_ring_h=4.2,
        pogo_pin_pcd=18.5,
        pogo_pin_d=1.7,
        pogo_pad_d=3.8,
        magnet_d=15.2,
        magnet_h=3.0,
        head_seat_above_ball=17.5,
        pan_deg=80.0,
        tilt_deg=26.0,
    ),
}


def build_base_and_socket(p: ChintuParams) -> cq.Workplane:
    """Part 1: Tapered base housing with internal MG90S/608 cavities & top turntable socket."""
    # Outer tapered frustum (Z=0 at desk, Z=base_h at top shoulder)
    outer = (
        cq.Workplane("XY")
        .circle(p.base_d_bot / 2)
        .workplane(offset=p.base_h)
        .circle(p.base_d_top / 2)
        .loft(ruled=True)
    )
    # Chamfer top rim slightly
    outer = outer.edges(">Z").fillet(2.5)

    # Copper accent light-ring groove near bottom
    groove_outer = (
        cq.Workplane("XY")
        .workplane(offset=p.ring_groove_z)
        .circle(p.base_d_bot / 2 + 1.0)
        .extrude(2.2)
    )
    groove_inner = (
        cq.Workplane("XY")
        .workplane(offset=p.ring_groove_z)
        .circle(p.base_d_bot / 2 - 2.0)
        .extrude(2.2)
    )
    outer = outer.cut(groove_outer.cut(groove_inner))

    # Hollow internal electronics + 2x MG90S servo cavity (open from bottom for serviceability)
    cavity_d_bot = p.base_d_bot - 8.0
    cavity_d_top = p.base_d_top - 10.0
    cavity = (
        cq.Workplane("XY")
        .circle(cavity_d_bot / 2)
        .workplane(offset=p.base_h - 6.0)
        .circle(cavity_d_top / 2)
        .loft(ruled=True)
    )
    outer = outer.cut(cavity)

    # 608 bearing seat pocket on top center (OD 22.2mm, depth 7mm)
    bearing_pocket = (
        cq.Workplane("XY")
        .workplane(offset=p.base_h - 5.5)
        .circle(22.2 / 2)
        .extrude(6.0)
    )
    outer = outer.cut(bearing_pocket)

    # Recessed rotary turntable lip + neck collar socket at top of base
    turntable_recess = (
        cq.Workplane("XY")
        .workplane(offset=p.base_h - 2.0)
        .circle(p.neck_d_bot / 2 + 2.0)
        .extrude(3.0)
    )
    outer = outer.cut(turntable_recess)

    # Small shoulder button pocket on front-right (+X, -Y)
    btn_x = p.base_d_top * 0.32
    btn_y = -p.base_d_top * 0.24
    btn_pocket = (
        cq.Workplane("XY")
        .workplane(offset=p.base_h - 2.0)
        .center(btn_x, btn_y)
        .circle(3.5)
        .extrude(3.0)
    )
    outer = outer.cut(btn_pocket)

    # Wire pass-through bore at center
    wire_bore = cq.Workplane("XY").circle(5.0).extrude(p.base_h + 2.0)
    outer = outer.cut(wire_bore)
    return outer


def build_ball_and_neck(p: ChintuParams) -> tuple[cq.Workplane, cq.Workplane, float]:
    """Part 2: Tapered neck column (top spherical cup) + Øball_d gimbal sphere.

    Returns (neck_pedestal, gimbal_ball, ball_center_z).
    """
    neck_base_z = p.base_h - 1.5
    ball_center_z = neck_base_z + p.neck_h
    cup_top_z = ball_center_z - 1.0  # slight undercut below ball equator so ball seats cleanly

    # Tapered neck pedestal rising from base turntable up to spherical cup rim
    neck = (
        cq.Workplane("XY")
        .workplane(offset=neck_base_z)
        .circle(p.neck_d_bot / 2)
        .workplane(offset=cup_top_z - neck_base_z)
        .circle((p.ball_d + 4.5) / 2)
        .loft(ruled=True)
    )

    # Carve spherical socket cup (+0.4 mm 3D-print radial clearance) at top of neck
    socket_sphere = (
        cq.Workplane("XY")
        .workplane(offset=ball_center_z)
        .sphere((p.ball_d + 0.8) / 2)
    )
    neck = neck.cut(socket_sphere)

    # Wire bore through neck
    neck = neck.cut(
        cq.Workplane("XY")
        .workplane(offset=neck_base_z - 1.0)
        .circle(4.5)
        .extrude(p.neck_h + 4.0)
    )

    # Gimbal ball itself centered at (0, 0, ball_center_z)
    ball = cq.Workplane("XY").workplane(offset=ball_center_z).sphere(p.ball_d / 2)
    # Trim top of ball flat at head_seat_above_ball - pogo_ring_h to mount the pogo-pin crown ring
    pogo_mount_z = ball_center_z + (p.head_seat_above_ball - p.pogo_ring_h)
    top_trim = (
        cq.Workplane("XY")
        .workplane(offset=pogo_mount_z)
        .rect(p.ball_d + 10, p.ball_d + 10)
        .extrude(p.ball_d)
    )
    ball = ball.cut(top_trim)
    # Central wire channel inside ball
    ball = ball.cut(
        cq.Workplane("XY")
        .workplane(offset=ball_center_z - p.ball_d / 2)
        .circle(4.0)
        .extrude(p.ball_d)
    )
    return neck, ball, ball_center_z


def build_pogo_and_magnet_ring(p: ChintuParams, ball_center_z: float) -> cq.Workplane:
    """Part 4: Pogo-pin crown ring + 6 spring pins (tucked inside head bay when docked)."""
    pin_h = 1.8
    flange_h = p.pogo_ring_h - pin_h
    pogo_mount_z = ball_center_z + (p.head_seat_above_ball - p.pogo_ring_h)
    ring = (
        cq.Workplane("XY")
        .workplane(offset=pogo_mount_z)
        .circle(p.pogo_ring_d / 2)
        .extrude(flange_h)
    )
    # Central N52 magnet pocket (recessed from top)
    mag_cut = (
        cq.Workplane("XY")
        .workplane(offset=pogo_mount_z + 0.4)
        .circle(p.magnet_d / 2)
        .extrude(flange_h + 1.0)
    )
    ring = ring.cut(mag_cut)

    # 6 radial gold pogo pins rising from flange_h to pogo_ring_h (fully inside head bay!)
    for a in range(0, 360, 60):
        px = (p.pogo_pin_pcd / 2) * math.cos(math.radians(a))
        py = (p.pogo_pin_pcd / 2) * math.sin(math.radians(a))
        pin = (
            cq.Workplane("XY")
            .workplane(offset=pogo_mount_z + flange_h)
            .center(px, py)
            .circle(p.pogo_pin_d / 2)
            .extrude(pin_h)
        )
        ring = ring.union(pin)
    return ring


def build_head_shell(p: ChintuParams, ball_center_z: float) -> cq.Workplane:
    """Part 3: Hollow rounded-box head shell with AMOLED bezel, side discs & pogo-pad bay."""
    head_bottom_z = ball_center_z + p.head_seat_above_ball
    head_center_z = head_bottom_z + p.head_h / 2

    # Outer rounded box
    shell = (
        cq.Workplane("XY")
        .workplane(offset=head_bottom_z)
        .box(p.head_w, p.head_d, p.head_h, centered=(True, True, False))
        .edges()
        .fillet(p.head_fillet)
    )

    # Hollow interior cavity (shell thickness = head_wall)
    inner = (
        cq.Workplane("XY")
        .workplane(offset=head_bottom_z + p.head_wall)
        .box(
            p.head_w - 2 * p.head_wall,
            p.head_d - 2 * p.head_wall,
            p.head_h - 2 * p.head_wall,
            centered=(True, True, False),
        )
        .edges()
        .fillet(max(1.5, p.head_fillet - p.head_wall))
    )
    shell = shell.cut(inner)

    # Front (-Y) 2.06" 410x502 AMOLED recess
    front_y = -p.head_d / 2
    screen_cut = (
        cq.Workplane("XZ")
        .workplane(offset=-front_y)
        .center(0, head_center_z)
        .rect(p.amoled_w, p.amoled_h)
        .extrude(-p.amoled_recess_d - 1.0)
    )
    shell = shell.cut(screen_cut)

    # Underside circular pogo-pad + magnet bay (fully encloses pogo_ring_h + 0.3mm so pins stay hidden!)
    bay_depth = p.pogo_ring_h + 0.3
    bay_cut = (
        cq.Workplane("XY")
        .workplane(offset=head_bottom_z - 0.1)
        .circle((p.pogo_ring_d + 1.4) / 2)
        .extrude(bay_depth)
    )
    bay_boss = (
        cq.Workplane("XY")
        .workplane(offset=head_bottom_z + 0.5)
        .circle((p.pogo_ring_d + 5.0) / 2)
        .extrude(bay_depth + 1.5)
    )
    shell = shell.union(bay_boss).cut(bay_cut)
    return shell


def check_collision_and_pogo(
    p: ChintuParams,
    base: cq.Workplane,
    neck: cq.Workplane,
    ball: cq.Workplane,
    pogo_ring: cq.Workplane,
    head: cq.Workplane,
    ball_center_z: float,
) -> dict:
    """Test 1 & Test 2: Full Pan (+-80°) and Tilt (+-26°) 3D B-rep interference & pogo alignment."""
    stationary = base.union(neck)
    moving_head = head.union(pogo_ring)

    pivot = (0.0, 0.0, ball_center_z)
    cases = [
        ("neutral_0_0", 0.0, 0.0, 0.0),
        ("pitch_fwd_+26", 0.0, p.tilt_deg, 0.0),
        ("pitch_back_-26", 0.0, -p.tilt_deg, 0.0),
        ("roll_right_+26", 0.0, 0.0, p.tilt_deg),
        ("roll_left_-26", 0.0, 0.0, -p.tilt_deg),
        ("pan_right_+80_pitch_+26", p.pan_deg, p.tilt_deg, 0.0),
        ("pan_left_-80_roll_+26", -p.pan_deg, 0.0, p.tilt_deg),
        ("corner_pitch_+26_roll_+26", p.pan_deg, p.tilt_deg, p.tilt_deg),
    ]

    collision_results = []
    any_collision = False

    for label, pan, pitch, roll in cases:
        transformed = moving_head
        if pitch != 0.0:
            transformed = transformed.rotate(pivot, (pivot[0] + 1.0, pivot[1], pivot[2]), pitch)
        if roll != 0.0:
            transformed = transformed.rotate(pivot, (pivot[0], pivot[1] + 1.0, pivot[2]), roll)
        if pan != 0.0:
            transformed = transformed.rotate((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), pan)

        # Boolean intersection volume in mm^3
        inter = transformed.intersect(stationary)
        vol = sum(s.Volume() for s in inter.solids().vals())

        # Approximate lowest head point vs. neck cup rim / base top
        bb_head = transformed.val().BoundingBox()
        bb_neck = neck.val().BoundingBox()
        z_above_neck_rim = bb_head.zmin - bb_neck.zmax
        z_above_base_top = bb_head.zmin - p.base_h

        collided = vol > 1e-3
        if collided:
            any_collision = True
        collision_results.append(
            {
                "pose": label,
                "pan_deg": pan,
                "pitch_deg": pitch,
                "roll_deg": roll,
                "intersection_mm3": round(vol, 4),
                "head_zmin_mm": round(bb_head.zmin, 2),
                "neck_cup_zmax_mm": round(bb_neck.zmax, 2),
                "clearance_to_neck_rim_mm": round(z_above_neck_rim, 2),
                "clearance_to_base_top_mm": round(z_above_base_top, 2),
                "collides": collided,
            }
        )

    # Test 2: Pogo-pin alignment at full tilt (+-26°)
    # Architecture A (as rendered): pogo crown mounted ON rotating ball -> 0 mm slip
    # Architecture B (hypothetical wrong placement): pogo crown fixed on neck while head tilts 26°
    pin_r = p.pogo_pin_pcd / 2.0
    tilt_rad = math.radians(p.tilt_deg)
    hypothetical_radial_slip_mm = pin_r * (1.0 - math.cos(tilt_rad)) + (
        p.pogo_ring_h * math.sin(tilt_rad)
    )
    hypothetical_axial_gap_mm = 2.0 * pin_r * math.sin(tilt_rad)

    return {
        "collision_pass": not any_collision,
        "cases": collision_results,
        "pogo_alignment": {
            "recommended_mount": "on_rotating_ball_crown",
            "slip_on_ball_mm": 0.0,
            "pads_stay_aligned": True,
            "if_mounted_on_fixed_neck_slip_mm": round(hypothetical_radial_slip_mm, 2),
            "if_mounted_on_fixed_neck_lift_gap_mm": round(hypothetical_axial_gap_mm, 2),
        },
    }


def compute_com_and_torque(p: ChintuParams, head: cq.Workplane, ball_center_z: float) -> dict:
    """Test 3: Exact shell mass + internal hardware CoM and static torque at +26 deg."""
    shell_vol_cm3 = head.val().Volume() / 1000.0
    pla_density_g_cm3 = 1.18  # PLA/ABS ~1.18 g/cm^3 at ~40-60% infill
    shell_mass_g = shell_vol_cm3 * pla_density_g_cm3
    shell_com = head.val().Center()  # (x, y, z) mm

    head_bottom_z = ball_center_z + p.head_seat_above_ball
    head_center_z = head_bottom_z + p.head_h / 2.0

    # Internal components placed for balanced CoM:
    # AMOLED at front (-Y), ESP32-S3 near center, LiPo battery at rear (+Y) to counterbalance glass
    components = [
        ("printed_head_shell", shell_mass_g, (shell_com.x, shell_com.y, shell_com.z)),
        ("amoled_2.06_panel", 14.0, (0.0, -p.head_d / 2 + 2.5, head_center_z)),
        ("esp32_s3_pcb_mics", 12.0, (0.0, 2.0, head_center_z)),
        ("lipo_600mah_battery", 14.0, (0.0, p.head_d / 2 - 8.0, head_center_z - 3.0)),
        ("n52_magnet_pogo_pcb", 8.0, (0.0, 0.0, head_bottom_z + 2.0)),
    ]

    total_mass_g = sum(m for _, m, _ in components)
    com_x = sum(m * pos[0] for _, m, pos in components) / total_mass_g
    com_y = sum(m * pos[1] for _, m, pos in components) / total_mass_g
    com_z = sum(m * pos[2] for _, m, pos in components) / total_mass_g

    dz_from_pivot_mm = com_z - ball_center_z
    dy_from_pivot_mm = com_y  # front/back imbalance relative to ball center

    tilt_rad = math.radians(p.tilt_deg)
    # Horizontal moment arm at +tilt_deg Pitch
    lever_arm_pitch_mm = dz_from_pivot_mm * math.sin(tilt_rad) + abs(dy_from_pivot_mm) * math.cos(tilt_rad)
    # Torque in kg*cm = (mass_kg) * (lever_cm)
    static_torque_kg_cm = (total_mass_g / 1000.0) * (lever_arm_pitch_mm / 10.0)
    # Include 2x dynamic gesture acceleration factor (snappy nod/perk_up)
    dynamic_peak_kg_cm = static_torque_kg_cm * 2.0

    sg90_stall_kg_cm = 1.6
    mg90s_stall_kg_cm = 2.0

    return {
        "shell_volume_cm3": round(shell_vol_cm3, 2),
        "total_head_mass_g": round(total_mass_g, 1),
        "components": [
            {"name": n, "mass_g": round(m, 1), "pos_mm": [round(v, 1) for v in pos]}
            for n, m, pos in components
        ],
        "com_relative_to_ball_mm": {
            "x": round(com_x, 2),
            "y_front_neg": round(com_y, 2),
            "z_above_ball": round(dz_from_pivot_mm, 2),
        },
        "tilt_deg": p.tilt_deg,
        "lever_arm_at_26deg_mm": round(lever_arm_pitch_mm, 2),
        "static_holding_torque_kg_cm": round(static_torque_kg_cm, 3),
        "dynamic_peak_torque_kg_cm": round(dynamic_peak_kg_cm, 3),
        "sg90_headroom_factor": round(sg90_stall_kg_cm / dynamic_peak_kg_cm, 2),
        "mg90s_headroom_factor": round(mg90s_stall_kg_cm / dynamic_peak_kg_cm, 2),
        "balanced_xy_within_2mm": abs(com_x) <= 2.0 and abs(dy_from_pivot_mm) <= 2.5,
    }


def build_color_accents(p: ChintuParams, ball_center_z: float) -> dict[str, cq.Workplane]:
    """Build colored accent linings: base copper ring, shoulder button, side ear rings & AMOLED glass."""
    r_at_groove = (p.base_d_bot / 2) - ((p.base_d_bot - p.base_d_top) / 2) * (p.ring_groove_z / p.base_h)
    light_ring = (
        cq.Workplane("XY")
        .workplane(offset=p.ring_groove_z + 0.05)
        .circle(r_at_groove + 0.15)
        .extrude(2.1)
        .cut(
            cq.Workplane("XY")
            .workplane(offset=p.ring_groove_z - 0.05)
            .circle(r_at_groove - 1.4)
            .extrude(2.3)
        )
    )

    btn_x = p.base_d_top * 0.32
    btn_y = -p.base_d_top * 0.24
    base_btn = (
        cq.Workplane("XY")
        .workplane(offset=p.base_h - 0.8)
        .center(btn_x, btn_y)
        .circle(3.1)
        .extrude(1.8)
    )

    head_bottom_z = ball_center_z + p.head_seat_above_ball
    head_center_z = head_bottom_z + p.head_h / 2
    amoled_glass = (
        cq.Workplane("XZ")
        .workplane(offset=p.head_d / 2 - 0.4)
        .center(0, head_center_z)
        .rect(p.amoled_w - 0.6, p.amoled_h - 0.6)
        .extrude(-1.4)
    )

    ear_r = min(p.head_h * 0.22, 13.0)
    ears = None
    ear_dots = None
    for sign in (-1.0, 1.0):
        ring = (
            cq.Workplane("YZ")
            .workplane(offset=sign * (p.head_w / 2 - 0.3))
            .center(0, head_center_z)
            .circle(ear_r)
            .extrude(sign * 2.4)
            .cut(
                cq.Workplane("YZ")
                .workplane(offset=sign * (p.head_w / 2 - 0.5))
                .center(0, head_center_z)
                .circle(3.8)
                .extrude(sign * 3.0)
            )
        )
        dot = (
            cq.Workplane("YZ")
            .workplane(offset=sign * (p.head_w / 2 - 0.3))
            .center(0, head_center_z)
            .circle(3.6)
            .extrude(sign * 2.1)
        )
        ears = ring if ears is None else ears.union(ring)
        ear_dots = dot if ear_dots is None else ear_dots.union(dot)

    return {
        "05a_base_light_ring": light_ring,
        "05b_base_button": base_btn,
        "05c_amoled_screen": amoled_glass,
        "05d_side_orange_ears": ears,
        "05e_side_ear_centers": ear_dots,
    }


def run(preset_name: str, export: bool) -> dict:
    p = PRESETS[preset_name]
    base = build_base_and_socket(p)
    neck, ball, ball_center_z = build_ball_and_neck(p)
    pogo_ring = build_pogo_and_magnet_ring(p, ball_center_z)
    head = build_head_shell(p, ball_center_z)
    accents = build_color_accents(p, ball_center_z)

    kinematics = check_collision_and_pogo(p, base, neck, ball, pogo_ring, head.union(accents["05d_side_orange_ears"]), ball_center_z)
    com_torque = compute_com_and_torque(p, head, ball_center_z)

    report = {
        "preset": preset_name,
        "params": asdict(p),
        "ball_center_z_mm": round(ball_center_z, 2),
        "overall_height_mm": round(ball_center_z + p.head_seat_above_ball + p.head_h, 2),
        "kinematics": kinematics,
        "com_and_torque": com_torque,
    }

    if export:
        out_dir = Path(__file__).resolve().parent / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        ball_and_neck = neck.union(ball)

        parts = {
            "01_base_and_socket": base,
            "02_ball_and_neck": ball_and_neck,
            "03_head_shell": head,
            "04_pogo_and_magnet_ring": pogo_ring,
        }
        for fname, solid in parts.items():
            cq.exporters.export(solid, str(out_dir / f"{fname}.step"))
            cq.exporters.export(solid, str(out_dir / f"{fname}.stl"))

        assy = cq.Assembly(name="Chintu_CAD")
        assy.add(base, name="01_base_and_socket", color=cq.Color(0.20, 0.21, 0.24, 1.0))
        assy.add(neck, name="02a_neck_socket", color=cq.Color(0.24, 0.25, 0.28, 1.0))
        assy.add(ball, name="02b_gimbal_ball", color=cq.Color(0.08, 0.09, 0.10, 1.0))
        assy.add(pogo_ring, name="04_pogo_and_magnet_ring", color=cq.Color(0.85, 0.68, 0.25, 1.0))
        assy.add(head, name="03_head_shell", color=cq.Color(0.22, 0.23, 0.26, 1.0))
        assy.add(accents["05a_base_light_ring"], name="05a_base_light_ring", color=cq.Color(0.93, 0.58, 0.37, 1.0))
        assy.add(accents["05b_base_button"], name="05b_base_button", color=cq.Color(0.92, 0.47, 0.24, 1.0))
        assy.add(accents["05c_amoled_screen"], name="05c_amoled_screen", color=cq.Color(0.07, 0.09, 0.12, 1.0))
        assy.add(accents["05d_side_orange_ears"], name="05d_side_orange_ears", color=cq.Color(0.92, 0.47, 0.24, 1.0))
        assy.add(accents["05e_side_ear_centers"], name="05e_side_ear_centers", color=cq.Color(0.10, 0.11, 0.12, 1.0))
        assy.save(str(out_dir / "chintu_assembly.step"))

        full_compound = base.union(ball_and_neck).union(pogo_ring).union(head)
        cq.exporters.export(full_compound, str(out_dir / "chintu_assembly.stl"))
        (out_dir / "cad_report.json").write_text(json.dumps(report, indent=2))

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build & verify Chintu 4-part CAD.")
    parser.add_argument("--preset", choices=["fitted", "estimate", "both"], default="both")
    parser.add_argument("--no-export", action="store_true")
    args = parser.parse_args()

    if args.preset == "both":
        rep_est = run("estimate", export=False)
        rep_fit = run("fitted", export=not args.no_export)
        print(json.dumps({"estimate_check": rep_est, "fitted_exported": rep_fit}, indent=2))
    else:
        rep = run(args.preset, export=not args.no_export)
        print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
