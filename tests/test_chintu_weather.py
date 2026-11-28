"""Verification tests for Chintu by Sarworks weather integration & creative face shows."""

import io
import json
from pathlib import Path
import sys
import time
import urllib.request
import wave

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from controllers.chintu_controller.audio_cues import NullAudioCuePlayer, synthesize_sfx_wav
from controllers.chintu_controller.face_renderer import FaceRenderer, RecordingDisplayTarget
from controllers.chintu_controller.hardware import LocalWakeWordDetector
from controllers.chintu_controller.registry import CHINTU_GESTURES, CHINTU_MOODS
from controllers.chintu_controller.run_playground import StandalonePlaygroundRuntime
from controllers.chintu_controller.server import CHINTU_COMMAND_QUEUE, CHINTU_STATUS, start_chintu_server
from controllers.chintu_controller.wake_engine import ChintuState, ChintuStateMachine
from controllers.chintu_controller.weather import (
    WEATHER_CONDITIONS,
    WeatherService,
    default_simulated_weather,
    fetch_live_weather,
    wmo_code_to_condition,
)


def _run_until_idle(machine: ChintuStateMachine, max_seconds: float = 20.0, dt: float = 0.02):
    for _ in range(int(round(max_seconds / dt))):
        machine.step(dt)
        if machine.state == ChintuState.IDLE_AWAKE:
            return
    raise AssertionError(f"Did not reach IDLE_AWAKE within {max_seconds}s")


def test_weather_wmo_mapping_and_live_fetch_with_mock_http():
    assert wmo_code_to_condition(0, is_day=True, wind_kmh=5.0)[0] == "sunny"
    assert wmo_code_to_condition(0, is_day=False, wind_kmh=5.0)[0] == "starry"
    assert wmo_code_to_condition(1, is_day=True, wind_kmh=35.0)[0] == "windy"
    assert wmo_code_to_condition(3, is_day=True, wind_kmh=10.0)[0] == "cloudy"
    assert wmo_code_to_condition(63, is_day=True, wind_kmh=15.0)[0] == "rainy"
    assert wmo_code_to_condition(73, is_day=True, wind_kmh=8.0)[0] == "snowy"
    assert wmo_code_to_condition(95, is_day=True, wind_kmh=42.0)[0] == "storm"

    def _fake_get(url: str, timeout_s: float) -> dict:
        if "geocoding-api" in url:
            return {
                "results": [
                    {
                        "name": "Tokyo",
                        "country_code": "JP",
                        "latitude": 35.6895,
                        "longitude": 139.6917,
                    }
                ]
            }
        return {
            "current": {
                "temperature_2m": 18.4,
                "apparent_temperature": 17.2,
                "is_day": 0,
                "weather_code": 0,
                "wind_speed_10m": 7.5,
            }
        }

    snap = fetch_live_weather("Tokyo", json_getter=_fake_get)
    assert snap.condition == "starry"
    assert snap.city == "Tokyo, JP"
    assert snap.temp_c == pytest.approx(18.4)
    assert snap.source == "live"
    assert snap.format_temp("C") == "18C"
    assert snap.format_temp("F") == "65F"


def test_weather_phrase_parsing():
    assert LocalWakeWordDetector.classify_text("what's the weather in Tokyo?") == "weather_live"
    assert LocalWakeWordDetector.extract_weather_city("what's the weather in Tokyo?") == "Tokyo"
    assert LocalWakeWordDetector.classify_text("weather") == "weather_live"
    assert LocalWakeWordDetector.classify_text("make it rain") == "weather_preset"
    assert LocalWakeWordDetector.extract_weather_preset("make it rain") == "rainy"
    assert LocalWakeWordDetector.extract_weather_preset("thunderstorm outside") == "storm"
    assert LocalWakeWordDetector.extract_weather_preset("starry night") == "starry"
    assert LocalWakeWordDetector.classify_text("clear weather") == "weather_clear"


def test_all_7_creative_weather_shows_audio_and_renderer():
    audio = NullAudioCuePlayer()
    machine = ChintuStateMachine(audio_player=audio, cold_startup=False)

    # Weather never interrupts or wakes from SLEEP
    assert machine.trigger_weather("storm") is False
    assert machine.state == ChintuState.SLEEP

    assert machine.trigger_tap() is True
    _run_until_idle(machine)

    for cond in WEATHER_CONDITIONS:
        audio.events.clear()
        assert machine.trigger_weather(cond, city="Playground") is True
        frames = [machine.step(0.05) for _ in range(130)]  # 6.5 s covers entire show

        assert any(e.cue_name == f"reaction_weather_{cond}" for e in audio.events)
        assert any(f.weather_condition == cond and f.weather_intensity == 1.0 for f in frames)

        # Verify all emitted tags obey canonical 15 moods / 19 gestures
        for entry in machine.tag_log:
            if "mood=" in entry.tag:
                mood = entry.tag.split("mood=")[1].split(",")[0].rstrip("]")
                assert mood in CHINTU_MOODS
            if "gesture=" in entry.tag:
                gesture = entry.tag.split("gesture=")[1].rstrip("]")
                assert gesture in CHINTU_GESTURES

        # Never emit STAR_EYES in weather shows
        assert all(f.mood != "STAR_EYES" for f in frames)

        # Verify condition-specific creative signature beats
        if cond == "sunny":
            assert any(f.mood == "COOL" for f in frames)
        elif cond == "rainy":
            assert any(f.umbrella_alpha > 0.8 for f in frames)
            assert any(f.mood == "HAPPY" and f.umbrella_alpha > 0.5 for f in frames)
        elif cond == "storm":
            assert any(f.weather_flash > 0.5 for f in frames)
            assert any(f.alert_alpha > 0.5 for f in frames)
            assert {f.weather_bolt for f in frames if f.weather_flash > 0.2} == {0, 1, 2}
            assert sum(1 for e in audio.events if e.cue_name == "reaction_weather_thunder") == 2
        elif cond == "snowy":
            assert any(f.jacket_alpha > 0.8 for f in frames)
            assert any(f.mood == "HAPPY" and f.jacket_alpha > 0.5 for f in frames)
        elif cond == "windy":
            assert any(f.face_bob_x > 4.0 for f in frames)
            assert any(f.mood == "SMIRK" for f in frames)
        elif cond == "starry":
            assert any(f.mouth_open > 0.7 for f in frames)
            assert any(f.blanket_alpha > 0.8 for f in frames)
            assert any(f.face_mode == "sleep" and f.blanket_alpha > 0.8 for f in frames)
            assert any(e.cue_name == "baby_yawn" for e in audio.events)

        # Render peak weather frame onto 410x502 AMOLED without error
        peak_frame = max(frames, key=lambda f: f.weather_intensity + f.umbrella_alpha + f.blanket_alpha + f.jacket_alpha + f.weather_flash)
        tgt = RecordingDisplayTarget()
        FaceRenderer(target=tgt, disp_w=410, disp_h=502).render(peak_frame)
        assert len(tgt.ops) > 30

        # Audio WAV asset valid mono 44.1kHz
        wav_bytes = synthesize_sfx_wav(f"weather_{cond}")
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            assert wf.getframerate() == 44100
            assert wf.getnchannels() == 1
            assert wf.getnframes() > 1000

        # Ambient weather persists gently after show ends
        end_frame = machine.step(0.05)
        assert end_frame.weather_condition == cond
        assert 0.4 <= end_frame.weather_intensity <= 0.6

    # Clearing weather turns off ambient backdrop
    machine.clear_weather()
    cleared = machine.step(0.05)
    assert cleared.weather_condition == ""
    assert cleared.weather_intensity == 0.0


def test_async_live_weather_in_standalone_playground():
    while not CHINTU_COMMAND_QUEUE.empty():
        CHINTU_COMMAND_QUEUE.get_nowait()

    def _mock_open_meteo(url: str, timeout_s: float) -> dict:
        if "geocoding-api" in url:
            time.sleep(0.05)
            return {"results": [{"name": "Hyderabad", "country_code": "IN", "latitude": 17.385, "longitude": 78.4867}]}
        return {
            "current": {
                "temperature_2m": 31.2,
                "apparent_temperature": 33.0,
                "is_day": 1,
                "weather_code": 63,
                "wind_speed_10m": 16.0,
            }
        }

    rt = StandalonePlaygroundRuntime(
        port=0,
        start_server=False,
        audio_player=NullAudioCuePlayer(),
        cold_startup=False,
    )
    rt.machine.weather_service = WeatherService(json_getter=_mock_open_meteo)
    assert rt.machine.trigger_tap() is True
    _run_until_idle(rt.machine)

    CHINTU_COMMAND_QUEUE.put({"weather_city": "Hyderabad"})
    rt.step_once()
    assert rt.machine.current_mood == "THINKING"

    # Wait briefly for daemon fetch thread to resolve
    for _ in range(40):
        rt.step_once()
        if rt.machine.weather_snapshot is not None:
            break
        time.sleep(0.01)

    assert rt.machine.weather_snapshot is not None
    assert rt.machine.weather_snapshot.city == "Hyderabad, IN"
    assert rt.machine.weather_snapshot.condition == "rainy"
    assert CHINTU_STATUS["weather"]["condition"] == "rainy"
    assert CHINTU_STATUS["frame"]["weather_condition"] == "rainy"
    assert CHINTU_STATUS["frame"]["weather_temp_label"] == "31C"

    # HTTP Playground exposes Weather UI controls
    srv = start_chintu_server(port=0, host="127.0.0.1")
    assert srv is not None
    port = srv.server_address[1]
    try:
        html = urllib.request.urlopen(f"http://127.0.0.1:{port}/playground", timeout=2).read().decode("utf-8")
        assert "Weather &amp; Atmosphere" in html
        assert "Live Weather" in html
        assert "gemma" not in html.lower()
    finally:
        srv.shutdown()
        srv.server_close()
