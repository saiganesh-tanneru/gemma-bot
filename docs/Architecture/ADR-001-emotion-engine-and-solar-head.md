---
tags:
  - adr
  - architecture
  - emotion-engine
  - hardware
date: 2026-11-27
status: accepted
related:
  - "[[Architecture/System-Overview]]"
  - "[[DevLogs/2026-11-27-chintu-freecad-model]]"
  - "[[DevLogs/2026-11-27-emotion-engine]]"
---

# ADR-001: MIT Emotion Engine & Popped-Off Solar/Touch Head Design

Back to [[00-Index]] | [[Architecture/System-Overview]]

## Decisions

### 1. Emotion Engine Architecture (MIT Clean-Room Implementation)
- **Chosen pattern:** Re-implement the `playfultechnology/esp32-eyes` parametric architecture (12-float `EyeConfig` with `500 ms` linear morphing, weighted roulette `FaceBehavior`, decoupled blink/gaze) in clean **MIT-licensed** code under `controllers/gemma_bot_controller/emotion_engine/` (avoiding `AGPL-3.0` copy-paste against the repo's MIT `LICENSE`).
- **Combinatorial expressions:** `29` emotions (`15` classic + `14` extended including `BORED`, `SULKING`, `WORRIED`, `SKEPTIC`, `AWE`, `GLEE`, `FRUSTRATED`) × `19` gestures (`gestures.py`) × synthesized chirp profiles (`ChirpSpec`).
- **Live drives:** `EmotionState` (`energy`, `boredom`, `bond`, `detached`, `battery_pct`, `thermal_hot`) dynamically shifts roulette weights and updates idle posture.
- **Display scaling:** `EyeConfig.scaled(disp_w, disp_h)` scales identically across `128×64` unit tests and Webots `502×410` (`2.06"` `47.2×39.2 mm` AMOLED).

### 2. Head Power, Outdoor Solar Top-Up, and `head_touch`
- **Desk power:** Keep the gimbal ball `6`-pin pogo crown + `600 mAh` LiPo (`2.22 Wh` at `3.7 V`) for normal indoor desk operation (indoor ambient light only yields `~0.5–1.5 mW`, `100×–1,000×` below active Wi-Fi + AMOLED load).
- **Popped-off outdoor solar (+20% top-up):** With Wi-Fi OFF outdoors, the `fitted` head top (`54×32 mm` flat inside `7 mm` fillets) fits a **`50×30 mm` (`15 cm²`)** monocrystalline panel (`~240 mW` direct sun / `~65 mW` shade). In **Deep Sleep** (`~30–100 µA`, AMOLED/mics power-gated OFF via load switch) or **Screen-OFF Light Sleep** (`~2–6 mA`), `+20%` (`~522 mWh` input at `85%` MPPT efficiency) takes **`~2.2–2.3 hrs`** in direct sun (`~8–10 hrs` in shade).
- **ESP32-S3 solar hardware rules:** Requires an MPPT solar LiPo charger (`CN3791` / `BQ25570` / `BQ24210`, never raw panel-to-GPIO or bare `TP4056`), load-switch power-gating for AMOLED/audio rails, and an NTC thermistor (`45 °C` LiPo charge cutoff).
- **Combined `head_touch` + solar:** Mount the `50×30 mm` solar panel as a **floating bumper** over tactile dome switches (`0 µA` Deep Sleep penalty via `EXT0`/`EXT1` GPIO wake, `100%` solar area retained, immune to outdoor moisture/solar ripple), matching `head_touch` in `GemaBotReview.proto`.
