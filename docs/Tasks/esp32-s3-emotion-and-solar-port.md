---
tags:
  - task
  - esp32-s3
  - emotion-engine
  - hardware
status: in-progress
---

# ESP32-S3 Emotion Engine & Solar Hardware Port

Back to [[Tasks/README]] | Related: [[Architecture/ADR-001-emotion-engine-and-solar-head]], [[DevLogs/2026-11-27-emotion-engine]]

## Goal
Port the verified Webots/Python Emotion Engine and fitted CAD mechanics onto the physical `ESP32-S3` + `2.06"` `502×410` AMOLED + `600 mAh` LiPo + `50×30 mm` solar bumper head.

## Checklist
- [x] Prototype 12-float `EyeConfig` morpher (`500 ms` lerp) & 29-emotion registry in MIT Python (`emotion_engine/`)
- [x] Add live `Energy / Boredom / Bond` weighted roulette + `head_touch` / `detach` / `shake` stimulus handlers
- [x] Pair `EmotionEngine` with `gestures.py` trajectories & synthesized WAV chirps (`synthesize_chirp_wav`)
- [x] Sync Webots `worlds/gemma_bot.wbt` and `worlds/gemabot_review_plan.wbt` to fitted CAD (`146 mm`, `502×410` AMOLED, `50×30 mm` solar `head_touch` bumper)
- [ ] Port `EyeConfig` + `EyeDrawer` primitives to ESP32-S3 C++ (`LovyanGFX` / `LVGL`) on `#000000` AMOLED background
- [ ] Implement ESP32-S3 I2S tone-sweep chirp synthesizer & `EXT0` Deep Sleep wake on floating solar `head_touch` bumper
- [ ] Wire MPPT solar LiPo charger + NTC thermistor + AMOLED/mic MOSFET power-gating on head PCB
