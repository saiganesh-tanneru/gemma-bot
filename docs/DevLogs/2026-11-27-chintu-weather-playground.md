---
tags:
  - devlog
  - chintu
  - weather
  - playground
date: 2026-11-27
status: complete
related:
  - "[[DevLogs/2026-11-27-chintu-wake-ritual]]"
  - "[[00-Index]]"
---

# Chintu Weather & Creative Representation (Playground First)

Back to [[DevLogs/README]] | [[00-Index]]

## Summary
Added live Open-Meteo weather fetching + 7 expressive multi-beat animated weather shows (`sunny`, `cloudy`, `rainy`, `storm`, `snowy`, `windy`, `starry`) to Chintu's Face Playground and shared controller stack (`controllers/chintu_controller/`).

## Key Additions
- `controllers/chintu_controller/weather.py`:
  - `WeatherSnapshot`, WMO code mapper (`wmo_code_to_condition`), simulated presets (`default_simulated_weather`), zero-key Open-Meteo `fetch_live_weather`, and thread-safe non-blocking `WeatherService`.
- `controllers/chintu_controller/audio_cues.py`:
  - Added 8 deterministic procedural weather SFX (`weather_sunny`, `weather_cloudy`, `weather_rainy`, `weather_storm`, `weather_thunder`, `weather_snowy`, `weather_windy`, `weather_starry`) served via `/assets/sfx/<kind>.wav`.
- `controllers/chintu_controller/face_renderer.py` & `playground.html`:
  - Added `weather_*`, `face_scale`, `umbrella_alpha`, `blanket_alpha`, and `jacket_alpha` to `FaceFrameState` + weather backdrops, corner temperature badge, tilted sky-blue umbrella with center shaft & paw grip (`rainy`), quilted winter parka with scarf/hood & zipper (`snowy`), yawn + pull-up starry blanket (`starry`), and layered storm clouds with 3 tapered lightning bolt positions (`storm`).
  - Removed `STAR_EYES` emoji rendering and added mood parity (`COOL`, `LOVE`, `WINK`, `SMIRK`, `ANGRY`, `CRYING`, `TONGUE`) in `playground.html`.
  - Added the **Weather & Atmosphere** card (city lookup, 7 one-click presets, `Ambient` & `°C/°F` toggles, and live telemetry strip).
- `controllers/chintu_controller/wake_engine.py`, `hardware.py`, `runtime_helpers.py`, `server.py`:
  - Added multi-beat weather choreography strictly using canonical 15 moods / 19 gestures (with 3 thunder strikes on `storm`), offline weather phrase detection (`LocalWakeWordDetector`), and `/command` + `/status` wiring.
- `tests/test_chintu_weather.py`:
  - Covers WMO mapping, mocked Open-Meteo fetch, phrase parsing, all 7 weather shows (including 3 storm thunder strikes, umbrella, parka, and starry yawn+blanket) + SFX + 410×502 rendering, and async Playground runtime integration.
