---
tags:
  - devlog
  - cad
  - hardware
date: 2026-11-27
related:
  - "[[Architecture/System-Overview]]"
  - "[[DEMO_REVIEW_PLAN]]"
---

# Chintu 4-Part FreeCAD Model & Kinematics Check

## Context
Built a parametric FreeCAD + OpenCASCADE (`cadquery`) 4-part mechanical model of the Chintu ball-socket desk companion (`base + socket`, `ball + neck`, `head shell`, `pogo-pin + magnet ring`) to check real hardware fit (`2.06"` `410x502` AMOLED, `ESP32-S3`, `600 mAh` LiPo, `2x MG90S`) and verify collision, pogo-pin alignment, and CoM torque before ordering hardware.

## Findings / Changes
- Added [build_chintu_cad.py](../../cad/build_chintu_cad.py) generating both `fitted` (`Ø86 mm` base, `68x58x46 mm` head, `Ø32 mm` ball, `149.0 mm` tall) and `estimate` (`Ø96 mm` base, `95x80x75 mm` head, `Ø36 mm` ball, `195.5 mm` tall) comparisons and exporting STEP/STL files to `cad/out/`.
- Added native parametric [chintu_freecad.FCMacro](../../cad/chintu_freecad.FCMacro) with a live `Params` spreadsheet and `TestPanDeg` / `TestPitchDeg` / `TestRollDeg` preview placement.
- Verified that mounting the pogo-pin crown on top of the rotating ball keeps pad slip at `0.0 mm` at `+-26°` tilt (whereas a fixed-neck mount slips `2.36 mm` and opens an `8.33 mm` gap).
- Fitted head (`92.4 g`, rear LiPo counterbalancing front AMOLED) cuts `+26°` dynamic peak torque to `0.376 kg·cm` (`5.31x` `MG90S` headroom) vs. `0.912 kg·cm` (`1.76x` `SG90` marginal) on the `95x80x75 mm` estimate.

## Verification
- `uv run --with cadquery python cad/build_chintu_cad.py --preset both` — 0.0 mm³ boolean collision across Pan `+-80°` and Tilt `+-26°` poses; STEP/STL exports written to `cad/out/`.
- `.venv/bin/pytest -q` — 42 passed.
