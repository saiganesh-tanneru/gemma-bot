---
tags:
  - devlog
  - chintu
  - wake-ritual
  - esp32-s3
date: 2026-11-27
status: complete
related:
  - "[[Architecture/System-Overview]]"
  - "[[Architecture/ADR-001-emotion-engine-and-solar-head]]"
---

# Chintu Wakes Up — Startup Ritual, Audio Trim, & Charging Sleep

Back to [[DevLogs/README]] | [[00-Index]]

## Summary
Implemented the wordless **Chintu Wakes Up** 5-act startup and wake ritual under `controllers/chintu_controller/` and set `chintu_controller` as the default startup controller in `protos/GemaBotReview.proto`.

## Key Artifacts
- `assets/chintu-baby-yawn.wav`: Trimmed directly from Sai's uploaded reference clip (`44.1 kHz` mono 16-bit PCM WAV, peak `-1.00 dB`, measured duration `1.6105 s`). Act 3 stretches/syncs to the exact measured file duration (`0.4 s` uneven scrunch + `1.6105 s` bloom/wobble/0.3 s pop + `0.2 s` settle), shifting Acts 4–5 cleanly so total wake duration is `~12.56–12.58 s` (within `12.9 s ± 1 s`).
- `controllers/chintu_controller/`:
  - `chintu_controller.py`: Webots startup controller (`ChintuCompanion`) running Act 0 sleep face (`~1.0 s`) + safe servo centering before automatically executing the wake ritual on cold startup.
  - `face_renderer.py`: Uniform `128×64 -> 410×502` (`×3.203125`, `410×205` centered band on `#000000`) renderer across all 7 storyboard states (`sleep`, `stir`, `flutter`, `yawn`, `look`, `found-you`, `content_idle`).
  - `wake_engine.py`: Full state machine (`SLEEP`, `CHARGING_SLEEP`, `STIR`, `FLUTTER`, `YAWN`, `LOOK_AROUND`, `FOUND_YOU`, `IDLE_AWAKE`, `DROWSY`), 6 wake triggers, mid-ritual lock, `Energy`/`Boredom`/`Bond` meters, mood decay, idle gesture picker, and reaction table.
  - `audio_cues.py`: `E5 -> G5` (`659.25 -> 783.99 Hz`, `2 × 0.11 s`, `-14 dB`) sine stir chirp + real WAV file playback for `assets/chintu-baby-yawn.wav` (no synthesized yawn, no TTS/Sarvam in wake).
  - `hardware.py`: Single-flag `ChargingSensor.is_charging()` stub + manual hook, `DockDetector` keychain mode, `ServoRig` (`±50°` pan / `-12..+14°` tilt during wake, `≤ 90°/s`, detaches `20 s` after sleep), `TouchDebouncer`, and offline `LocalWakeWordDetector`.
  - `server.py` & `playground.html`: Local-first Face Playground (`/playground`) and `/status` + `/command` server.
- `tests/test_chintu_wake_ritual.py`: Covers Checks 1–9 and rehearsals (a)–(e).
