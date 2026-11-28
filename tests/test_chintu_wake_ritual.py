"""End-to-end verification & rehearsals (a)-(e) for Chintu Wakes Up."""

import importlib
import io
import json
import math
from pathlib import Path
import random
import re
import sys
import types
import urllib.request
import wave
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from controllers.chintu_controller.audio_cues import (
    BABY_YAWN_WAV_PATH,
    SFX_KINDS,
    NullAudioCuePlayer,
    measure_wav_duration,
    synthesize_sfx_wav,
    synthesize_stir_chirp_wav,
)
from controllers.chintu_controller.face_renderer import (
    DESIGN_H,
    DESIGN_W,
    EYE_CY,
    LEFT_EYE_CX,
    RIGHT_EYE_CX,
    FaceRenderer,
    RecordingDisplayTarget,
    build_storyboard_frame,
    compute_uniform_band,
)
from controllers.chintu_controller.hardware import (
    ChargingSensor,
    DockDetector,
    LocalWakeWordDetector,
    ServoRig,
)
from controllers.chintu_controller.registry import CHINTU_GESTURES, CHINTU_MOODS, format_bot_tag
from controllers.chintu_controller.server import CHINTU_COMMAND_QUEUE, CHINTU_STATUS, start_chintu_server
from controllers.chintu_controller.wake_engine import (
    ACT3_POP_S,
    ACT3_SCRUNCH_S,
    ChintuState,
    ChintuStateMachine,
    WAKE_STATES,
)


def _advance_seconds(machine: ChintuStateMachine, seconds: float, dt: float = 0.02):
    steps = int(round(seconds / dt))
    frames = []
    for _ in range(steps):
        frames.append(machine.step(dt))
    return frames


def _run_until_idle(machine: ChintuStateMachine, max_seconds: float = 20.0, dt: float = 0.02):
    seen_states = [machine.state]
    steps = int(round(max_seconds / dt))
    for _ in range(steps):
        machine.step(dt)
        if machine.state != seen_states[-1]:
            seen_states.append(machine.state)
        if machine.state == ChintuState.IDLE_AWAKE:
            return seen_states
    raise AssertionError(f"Did not reach IDLE_AWAKE within {max_seconds}s (stuck in {machine.state})")


def test_hard_rules_naming_and_registry_and_no_synth_yawn():
    # 1. Registry counts exact: 15 moods, 19 gestures
    assert len(CHINTU_MOODS) == 15
    assert len(CHINTU_GESTURES) == 19
    assert format_bot_tag(mood="HAPPY", gesture="nod") == "[BOT: mood=HAPPY, gesture=nod]"

    # 2. Zero mentions of forbidden names anywhere in controllers/chintu_controller/
    chintu_dir = REPO_ROOT / "controllers" / "chintu_controller"
    for path in chintu_dir.rglob("*"):
        if path.is_file() and path.suffix in (".py", ".html", ".md", ".json"):
            assert "gemma" not in path.name.lower(), f"Forbidden filename: {path}"
            txt = path.read_text(encoding="utf-8")
            assert not re.search(r"gemma[\s_-]*bot|\bgemma\b", txt, re.IGNORECASE), (
                f"Forbidden name found in {path}"
            )

    # 3. Audio asset exists, 44.1 kHz mono, ~2s range, peak ~ -1 dB, and no yawn synth code path
    assert BABY_YAWN_WAV_PATH.is_file()
    with wave.open(str(BABY_YAWN_WAV_PATH), "rb") as wf:
        assert wf.getframerate() == 44100
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        dur = wf.getnframes() / 44100.0
    assert 1.2 <= dur <= 2.6
    assert abs(measure_wav_duration(BABY_YAWN_WAV_PATH) - dur) < 1e-6

    audio_src = (chintu_dir / "audio_cues.py").read_text(encoding="utf-8").lower()
    for forbidden in ("formant", "vibrato", "glissando", "yawn_osc", "yawn_synth"):
        assert forbidden not in audio_src

    # Stir chirp: 2 x 0.11s = 0.22s mono 44.1kHz WAV at ~ -14 dB
    stir_wav = synthesize_stir_chirp_wav(44100)
    with wave.open(io.BytesIO(stir_wav), "rb") as wf:
        assert wf.getframerate() == 44100
        assert wf.getnchannels() == 1
        assert abs((wf.getnframes() / 44100.0) - 0.22) < 0.01


def test_check1_face_renderer_uniform_scale_and_7_storyboard_states():
    scale, bx, by = compute_uniform_band(410, 502)
    assert scale == pytest.approx(410 / 128.0, abs=1e-4)
    assert bx == pytest.approx(0.0, abs=1e-4)
    assert by == pytest.approx((502 - 64 * scale) / 2.0, abs=1e-4)

    target = RecordingDisplayTarget()
    renderer = FaceRenderer(target=target, disp_w=410, disp_h=502)
    lx, ly = renderer.to_screen(LEFT_EYE_CX, EYE_CY)
    rx, ry = renderer.to_screen(RIGHT_EYE_CX, EYE_CY)
    assert round(lx) == 128
    assert round(rx) == 282
    assert round(ly - by) == 90
    assert round(ry - by) == 90

    # Render all 7 storyboard states + charging glyph
    for state_name in ("sleep", "stir", "flutter", "yawn", "look", "found-you", "content_idle"):
        target.clear()
        frame = build_storyboard_frame(state_name, progress=0.5, is_charging=(state_name == "sleep"))
        renderer.render(frame)
        # First op clears entire 410x502 to pure black #000000
        assert target.ops[0] == ("rect", 0, 0, 410, 502, 0x000000)
        assert len(target.ops) > 5

        if state_name == "yawn":
            # Mouth pixels stay within 115x90 scaled bounds
            mouth_rects = [op for op in target.ops[1:] if op[2] > by + 35 * scale]
            assert mouth_rects
            min_x = min(op[1] for op in mouth_rects)
            max_x = max(op[1] + op[3] for op in mouth_rects)
            min_y = min(op[2] for op in mouth_rects)
            max_y = max(op[2] + op[4] for op in mouth_rects)
            assert (max_x - min_x) <= 118
            assert (max_y - min_y) <= 92


def test_check2_blink_and_breathing_engine_two_minutes_awake():
    machine = ChintuStateMachine(cold_startup=False, rng=random.Random(123))
    machine.trigger_tap()
    _run_until_idle(machine)

    blink_starts = []
    was_blinking = False
    for _ in range(int(120.0 / 0.04)):  # 25 fps (>= 20 fps) for 120 seconds
        machine.step(0.04)
        blinking = machine.blink_engine.blink_progress > 0.1
        if blinking and not was_blinking:
            blink_starts.append(machine.now_s)
        was_blinking = blinking

    intervals = [b - a for a, b in zip(blink_starts, blink_starts[1:])]
    assert len(intervals) >= 20
    assert all(2.2 <= iv <= 5.8 for iv in intervals)
    # Random, never metronomic (std > 0.2s)
    mean = sum(intervals) / len(intervals)
    std = math.sqrt(sum((iv - mean) ** 2 for iv in intervals) / len(intervals))
    assert std > 0.2


def test_check3_and_check6_and_check7_wake_triggers_mid_ritual_lock_and_tags():
    # Wake phrase classification local-first
    assert LocalWakeWordDetector.classify_text("wake Chintu up") == "wake_phrase"
    assert LocalWakeWordDetector.classify_text("Hey Chintu") == "wake_word"
    assert LocalWakeWordDetector.classify_text("Chintu, go to sleep") == "go_to_sleep"

    # Three wakes in a row -> 0 TTS calls, Bond +1 each time, exact tag order
    machine = ChintuStateMachine(cold_startup=False, rng=random.Random(7))
    for wake_idx in range(1, 4):
        if wake_idx == 1:
            assert machine.trigger_wake_phrase("wake Chintu up")
        elif wake_idx == 2:
            assert machine.trigger_wake_phrase("Hey Chintu")
        else:
            assert machine.trigger_alarm()

        assert machine.state == ChintuState.STIR

        # Mid-ritual tap / phrase is ignored!
        _advance_seconds(machine, 4.2)  # Inside YAWN
        assert machine.state == ChintuState.YAWN
        assert machine.trigger_tap() is False
        assert machine.trigger_wake_phrase("wake Chintu up") is False

        states = _run_until_idle(machine)
        assert ChintuState.STIR in states or machine.wake_count == wake_idx
        assert machine.tts_call_count_during_wake == 0
        assert machine.meters.bond == pytest.approx(float(wake_idx), abs=1e-3)
        assert machine.meters.energy == 100.0
        assert machine.meters.boredom == 0.0
        assert 11.9 <= machine.last_wake_duration_s <= 13.9

        # Go back down to sleep cleanly for next wake
        if wake_idx < 3:
            assert machine.trigger_wake_phrase("Chintu, go to sleep")
            assert machine.state == ChintuState.DROWSY
            _advance_seconds(machine, machine.yawn_duration_s + 3.5)
            assert machine.state == ChintuState.SLEEP

    # Typing "wake Chintu up" while IDLE_AWAKE also replays the full wake ritual
    assert machine.state == ChintuState.IDLE_AWAKE
    assert machine.trigger_wake_phrase("wake Chintu up") is True
    assert machine.state == ChintuState.STIR
    _run_until_idle(machine)
    assert machine.meters.bond == pytest.approx(4.0, abs=1e-3)

    # Verify [BOT: ...] wake tag sequence on first wake
    tags = [e.tag for e in machine.tag_log[:5]]
    assert tags == [
        "[BOT: mood=SLEEPY]",
        "[BOT: mood=SLEEPY]",
        "[BOT: mood=SLEEPY, gesture=yawn]",
        "[BOT: mood=SURPRISED, gesture=scan]",
        "[BOT: mood=HAPPY, gesture=nod]",
    ]
    assert machine.tag_log[5].tag == "[BOT: mood=NEUTRAL]"


def test_check4_and_check5_servos_detach_keychain_and_yawn_sync():
    dock = DockDetector()
    audio = NullAudioCuePlayer()
    servos = ServoRig(dock_detector=dock)
    machine = ChintuStateMachine(audio_player=audio, dock_detector=dock, servo_rig=servos, cold_startup=False)

    # Sleep -> detach 20 s later
    assert servos.attached is True
    _advance_seconds(machine, 20.5)
    assert servos.attached is False

    # Tap starts STIR immediately (< 200 ms) and re-attaches servos
    assert machine.trigger_tap() is True
    assert machine.state == ChintuState.STIR
    assert servos.attached is True

    # Track servo speed & limits and yawn mouth/sound exact end alignment
    prev_pan, prev_tilt = servos.pan_deg, servos.tilt_deg
    dt = 0.02
    yawn_start_t = None
    mouth_zero_after_yawn_t = None
    in_yawn_seen = False
    while machine.state != ChintuState.IDLE_AWAKE:
        frame = machine.step(dt)
        dp = abs(servos.pan_deg - prev_pan) / dt
        dtilt = abs(servos.tilt_deg - prev_tilt) / dt
        assert dp <= 95.0
        assert dtilt <= 95.0
        assert -50.1 <= servos.pan_deg <= 50.1
        assert -12.1 <= servos.tilt_deg <= 14.1
        prev_pan, prev_tilt = servos.pan_deg, servos.tilt_deg

        if machine.state == ChintuState.YAWN:
            if frame.mouth_open > 0.0 and yawn_start_t is None:
                yawn_start_t = machine.now_s
                in_yawn_seen = True
            elif in_yawn_seen and frame.mouth_open == 0.0 and mouth_zero_after_yawn_t is None:
                mouth_zero_after_yawn_t = machine.now_s

    assert yawn_start_t is not None and mouth_zero_after_yawn_t is not None
    # Mouth opens with audio and closes in pop exactly at end of BABY_YAWN_WAV_PATH
    assert abs((mouth_zero_after_yawn_t - yawn_start_t) - audio.yawn_duration_s) <= 0.06
    assert [ev.cue_name for ev in audio.events] == ["stir_chirp", "baby_yawn"]

    # Detached keychain mode: runs face + audio with zero servo errors
    dock.set_manual_override(False)
    machine2 = ChintuStateMachine(audio_player=NullAudioCuePlayer(), dock_detector=dock, cold_startup=True)
    _run_until_idle(machine2)
    assert machine2.servos.attached is False
    assert machine2.wake_count == 1


def test_check8_meters_decay_idle_picker_and_reactions():
    audio = NullAudioCuePlayer()
    machine = ChintuStateMachine(audio_player=audio, cold_startup=False, rng=random.Random(99))

    # Clap while sleeping NEVER wakes Chintu
    assert machine.handle_loud_sound(25.0) is False
    assert machine.state == ChintuState.SLEEP

    assert machine.trigger_tap() is True
    _run_until_idle(machine)

    # 15 minutes alone -> >= 3 different idle gestures, no back-to-back repeats, mood drifts sleepier
    machine.meters.energy = 24.0
    idle_gestures = []
    seen_log_len = len(machine.tag_log)
    for _ in range(int(900.0 / 0.1)):
        machine.step(0.1)
        while seen_log_len < len(machine.tag_log):
            entry = machine.tag_log[seen_log_len]
            seen_log_len += 1
            if entry.state == "IDLE_AWAKE" and "gesture=" in entry.tag:
                idle_gestures.append(entry.tag.split("gesture=")[1].rstrip("]"))

    assert len(set(idle_gestures)) >= 3
    for a, b in zip(idle_gestures, idle_gestures[1:]):
        assert a != b
    assert machine.current_mood == "SLEEPY"

    # Reactions: pet -> double pat -> 4 rapid pats dizzy gag -> face appears
    machine.meters.energy = 100.0
    machine.current_mood = "NEUTRAL"
    bond_before = machine.meters.bond
    assert machine.trigger_tap() is True
    assert machine.meters.bond == pytest.approx(bond_before + 1.0, abs=1e-3)
    _advance_seconds(machine, 2.0)
    assert machine.trigger_tap() is True  # second pat within 10 s -> wiggle + sparkles
    assert "gesture=wiggle" in machine.tag_log[-1].tag

    # 4 rapid pats in 3 s -> DIZZY
    for _ in range(4):
        machine.step(0.1)
        machine.handle_raw_touch(True)
        machine.step(0.1)
        machine.handle_raw_touch(False)
    assert machine.current_mood == "DIZZY"

    _advance_seconds(machine, 2.5)
    assert machine.handle_face_spotted(15.0) is True
    assert machine.tts_call_count_during_wake == 0


def test_check9_rehearsals_a_through_e():
    results = {}

    # (a) Cold power-on wake (auto after ~1s sleep face + center)
    a_audio = NullAudioCuePlayer()
    m_a = ChintuStateMachine(audio_player=a_audio, cold_startup=True)
    _run_until_idle(m_a)
    results["a_cold_startup_s"] = round(m_a.last_wake_duration_s, 3)
    assert 11.9 <= m_a.last_wake_duration_s <= 13.9
    assert [e.cue_name for e in a_audio.events] == ["stir_chirp", "baby_yawn"]

    # (b) Tap wake from ordinary sleep
    m_b = ChintuStateMachine(cold_startup=False)
    _advance_seconds(m_b, 20.5)
    assert m_b.servos.attached is False
    assert m_b.handle_raw_touch(True) is True
    assert m_b.state == ChintuState.STIR
    _run_until_idle(m_b)
    results["b_tap_sleep_s"] = round(m_b.last_wake_duration_s, 3)
    assert 11.9 <= m_b.last_wake_duration_s <= 13.9

    # (c) Wake from CHARGING_SLEEP via tap, wake phrase, and unplug (all three)
    for mode in ("tap", "phrase", "unplug"):
        chg = ChargingSensor()
        chg.set_manual_override(True)
        m_c = ChintuStateMachine(charging_sensor=chg, cold_startup=False)
        assert m_c.state == ChintuState.CHARGING_SLEEP
        if mode == "tap":
            assert m_c.trigger_tap() is True
        elif mode == "phrase":
            assert m_c.trigger_wake_phrase("wake Chintu up") is True
        else:
            chg.set_manual_override(False)
            m_c.step(0.02)
        assert m_c.state == ChintuState.STIR
        _run_until_idle(m_c)
        results[f"c_charging_{mode}_s"] = round(m_c.last_wake_duration_s, 3)
        assert 11.9 <= m_c.last_wake_duration_s <= 13.9

    # (d) Plug charger in while drowsy -> goes to CHARGING_SLEEP WITHOUT waking or speaking
    chg_d = ChargingSensor()
    aud_d = NullAudioCuePlayer()
    m_d = ChintuStateMachine(audio_player=aud_d, charging_sensor=chg_d, cold_startup=False)
    m_d.trigger_tap()
    _run_until_idle(m_d)
    assert m_d.start_drowsy() is True
    chg_d.set_manual_override(True)
    _advance_seconds(m_d, m_d.yawn_duration_s + 4.0)
    assert m_d.state == ChintuState.CHARGING_SLEEP
    assert m_d.wake_count == 1  # Never triggered a second wake!
    assert m_d.tts_call_count_during_wake == 0

    # (e) Full day cycle down to Drowsy -> SLEEP -> servo detach
    m_e = ChintuStateMachine(cold_startup=False)
    m_e.trigger_tap()
    _run_until_idle(m_e)
    m_e.meters.energy = 0.01
    _advance_seconds(m_e, 15.0)
    assert m_e.state == ChintuState.SLEEP
    _advance_seconds(m_e, 20.5)
    assert m_e.servos.attached is False

    print("REHEARSAL_TIMINGS:", json.dumps(results))


def test_playground_http_server_and_webots_controller_startup():
    while not CHINTU_COMMAND_QUEUE.empty():
        CHINTU_COMMAND_QUEUE.get_nowait()

    srv = start_chintu_server(port=0, host="127.0.0.1")
    assert srv is not None
    port = srv.server_address[1]
    try:
        html = urllib.request.urlopen(f"http://127.0.0.1:{port}/playground", timeout=2).read().decode("utf-8")
        assert "Chintu by Sarworks" in html
        assert "wake Chintu up" in html
        assert "gemma" not in html.lower()

        wav = urllib.request.urlopen(f"http://127.0.0.1:{port}/assets/chintu-baby-yawn.wav", timeout=2).read()
        assert wav[:4] == b"RIFF"

        for kind in SFX_KINDS:
            sfx = urllib.request.urlopen(f"http://127.0.0.1:{port}/assets/sfx/{kind}.wav", timeout=2).read()
            assert sfx[:4] == b"RIFF"
            with wave.open(io.BytesIO(sfx), "rb") as wf:
                assert wf.getframerate() == 44100
                assert wf.getnchannels() == 1
                assert wf.getnframes() > 1000

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/command",
            data=json.dumps({"phrase": "wake Chintu up"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=2).read().decode("utf-8"))
        assert resp["status"] == "received"
    finally:
        srv.shutdown()
        srv.server_close()

    # Stub Webots controller and verify cold startup runs automatically
    c = types.ModuleType("controller")

    class _Motor:
        def setPosition(self, p):
            pass

        def setVelocity(self, v):
            pass

    class _Display:
        def getWidth(self):
            return 410

        def getHeight(self):
            return 502

        def setOpacity(self, v):
            pass

        def setColor(self, col):
            pass

        def fillRectangle(self, x, y, w, h):
            pass

        def drawText(self, t, x, y):
            pass

    class _Keyboard:
        def enable(self, t):
            pass

        def getKey(self):
            return -1

    class _Touch:
        def enable(self, t):
            pass

        def getValue(self):
            return 0.0

    class _Supervisor:
        def getBasicTimeStep(self):
            return 20

        def getDevice(self, n):
            if n == "oled_display":
                return _Display()
            if n in ("head_yaw", "head_pitch"):
                return _Motor()
            if n == "head_touch":
                return _Touch()
            return MagicMock()

        def getKeyboard(self):
            return _Keyboard()

        def step(self, t):
            return -1

    c.Robot = c.Supervisor = _Supervisor
    c.Keyboard = _Keyboard
    sys.modules["controller"] = c

    import controllers.chintu_controller.chintu_controller as cc
    cc = importlib.reload(cc)
    bot = cc.ChintuCompanion(start_server=False, audio_player=NullAudioCuePlayer(), cold_startup=True)
    for _ in range(int(14.5 / 0.02)):
        bot.step_once()
    assert bot.machine.state == ChintuState.IDLE_AWAKE
    assert bot.machine.wake_count == 1
    assert CHINTU_STATUS["product"] == "Chintu"


def test_standalone_playground_runs_without_webots():
    sys.modules.pop("controller", None)
    from controllers.chintu_controller.run_playground import StandalonePlaygroundRuntime

    rt = StandalonePlaygroundRuntime(
        port=0,
        start_server=False,
        audio_player=NullAudioCuePlayer(),
        cold_startup=True,
    )
    for _ in range(int(14.5 / 0.02)):
        rt.step_once()
    assert rt.machine.state == ChintuState.IDLE_AWAKE
    assert rt.machine.wake_count == 1
    assert CHINTU_STATUS["product"] == "Chintu"


def test_kicked_off_dock_sudden_surprise_and_scared_reaction():
    chg = ChargingSensor()
    dock = DockDetector()
    audio = NullAudioCuePlayer()
    machine = ChintuStateMachine(
        audio_player=audio,
        charging_sensor=chg,
        dock_detector=dock,
        cold_startup=False,
    )
    assert machine.trigger_tap() is True
    _run_until_idle(machine)
    assert machine.state == ChintuState.IDLE_AWAKE

    # Detaching dock while charging is off triggers 4-beat mid-air dangle:
    # 1) SURPRISED + shiver ('!') -> 2) DIZZY + dizzy_spin (sweat) -> 3) PLEADING (whimper) -> 4) NEUTRAL
    dock.set_manual_override(False)
    frame_startle = machine.step(0.05)
    assert frame_startle.mood == "SURPRISED"
    assert frame_startle.eye_scale > 1.2
    assert frame_startle.alert_alpha == 1.0
    assert any(e.cue_name == "reaction_startle_scared" for e in audio.events)
    assert machine.tag_log[-1].tag == "[BOT: mood=SURPRISED, gesture=shiver]"

    # Beat 1 pendulum swing + Beat 2 dizzy dangle spin
    frames_b1 = [machine.step(0.05) for _ in range(12)]
    assert max(abs(f.face_bob_x) for f in frames_b1) > 4.5
    assert min(f.face_bob_y for f in frames_b1) < -1.5

    _advance_seconds(machine, 0.45)
    frame_dizzy = machine.step(0.05)
    assert frame_dizzy.mood == "DIZZY"
    assert frame_dizzy.sweat_alpha == 1.0
    assert machine.tag_log[-1].tag == "[BOT: mood=DIZZY, gesture=dizzy_spin]"
    # Verify @_@ spiral eyes render cleanly onto 410x502
    dizzy_target = RecordingDisplayTarget()
    FaceRenderer(target=dizzy_target, disp_w=410, disp_h=502).render(frame_dizzy)
    assert len(dizzy_target.ops) > 90

    # Beat 3 scared PLEADING puppy eyes + whimper
    _advance_seconds(machine, 1.10)
    frame_scared = machine.step(0.05)
    assert frame_scared.mood == "PLEADING"
    assert any(e.cue_name == "reaction_whimper" for e in audio.events)
    assert machine.tag_log[-1].tag == "[BOT: mood=PLEADING]"

    # Beat 4 shake-off & settle back to NEUTRAL
    _advance_seconds(machine, 1.80)
    frame_settle = machine.step(0.05)
    assert frame_settle.mood == "NEUTRAL"
    assert machine.tag_log[-1].tag == "[BOT: mood=NEUTRAL]"
    cue_names = [e.cue_name for e in audio.events]
    for expected_cue in ("reaction_startle_scared", "reaction_dizzy_swirl", "reaction_whimper", "reaction_shake_off"):
        assert expected_cue in cue_names

    # Also works via phrase ("kick Chintu off" / "kicked off dock" / "detach Chintu") without servo errors
    assert LocalWakeWordDetector.classify_text("kick Chintu off") == "kicked_off_dock"
    assert LocalWakeWordDetector.classify_text("kicked off dock") == "kicked_off_dock"
    assert LocalWakeWordDetector.classify_text("detach Chintu") == "kicked_off_dock"
    dock.set_manual_override(True)
    chg.set_manual_override(True)
    assert machine.trigger_wake_phrase("kick Chintu off") is True
    assert machine.charging.is_charging() is False
    assert machine.dock.is_docked() is False


def test_shake_worried_then_adjusted_sequence():
    assert LocalWakeWordDetector.classify_text("shake Chintu") == "shake_chintu"
    audio = NullAudioCuePlayer()
    machine = ChintuStateMachine(audio_player=audio, cold_startup=False)
    assert machine.trigger_tap() is True
    _run_until_idle(machine)
    audio.events.clear()

    # Trigger shake via phrase
    assert machine.trigger_wake_phrase("shake Chintu") is True
    frames_b1 = [machine.step(0.05) for _ in range(12)]
    assert frames_b1[0].mood == "SURPRISED"
    assert frames_b1[0].alert_alpha == 1.0
    assert max(abs(f.face_bob_x) for f in frames_b1) > 4.0
    assert max(abs(f.face_bob_y) for f in frames_b1) > 2.0

    # Beat 2: Worried PLEADING + sweat drop + whimper
    _advance_seconds(machine, 0.7)
    f2 = machine.step(0.05)
    assert f2.mood == "PLEADING"
    assert f2.sweat_alpha == 1.0

    # Beat 3: Self-adjusting THINKING
    _advance_seconds(machine, 1.6)
    f3 = machine.step(0.05)
    assert f3.mood == "THINKING"

    # Beat 4: Adjusted & Fine -> HAPPY -> NEUTRAL
    _advance_seconds(machine, 1.05)
    f4 = machine.step(0.05)
    assert f4.mood == "HAPPY"
    assert f4.happy_arcs is True

    _advance_seconds(machine, 1.2)
    f5 = machine.step(0.05)
    assert f5.mood == "NEUTRAL"

    cue_names = [e.cue_name for e in audio.events]
    for c in ("reaction_shaken_rattle", "reaction_whimper", "reaction_adjust_blip", "reaction_adjusted_ok"):
        assert c in cue_names


def test_alarm_countdown_and_awake_alarm_reminder():
    assert LocalWakeWordDetector.classify_text("set alarm 5s") == "set_alarm"
    assert LocalWakeWordDetector.extract_alarm_delay_s("set alarm 5s") == 5.0
    assert LocalWakeWordDetector.classify_text("ring alarm") == "ring_alarm"

    # 1. Scheduled alarm from SLEEP -> wakes immediately into STIR with bell glyph & strictly 2 wake cues
    audio = NullAudioCuePlayer()
    machine = ChintuStateMachine(audio_player=audio, cold_startup=False)
    assert machine.trigger_wake_phrase("set alarm 3s") is True
    assert machine.alarm_remaining_s == pytest.approx(3.0, abs=0.1)
    _advance_seconds(machine, 2.5)
    assert machine.state == ChintuState.SLEEP
    _advance_seconds(machine, 0.6)
    assert machine.state == ChintuState.STIR
    f_stir = machine.step(0.05)
    assert f_stir.bell_alpha == 1.0
    _run_until_idle(machine)
    assert [e.cue_name for e in audio.events] == ["stir_chirp", "baby_yawn"]

    # 2. Alarm trigger while IDLE_AWAKE -> 3-beat creative alarm reminder
    audio.events.clear()
    assert machine.trigger_wake_phrase("ring alarm") is True
    f1 = machine.step(0.05)
    assert f1.mood == "SURPRISED"
    assert f1.bell_alpha == 1.0
    _advance_seconds(machine, 1.3)
    f2 = machine.step(0.05)
    assert f2.mood == "HAPPY"
    _advance_seconds(machine, 1.4)
    f3 = machine.step(0.05)
    assert f3.mood == "WINK"
    _advance_seconds(machine, 1.1)
    f4 = machine.step(0.05)
    assert f4.mood == "NEUTRAL"
    assert any(e.cue_name == "reaction_alarm_ring" for e in audio.events)


def test_expressive_talking_babble_and_d_mouth():
    audio = NullAudioCuePlayer()
    machine = ChintuStateMachine(audio_player=audio, cold_startup=False)
    # Never talks while asleep
    assert machine.trigger_wake_phrase("hello Chintu") is False
    assert machine.state == ChintuState.SLEEP

    assert machine.trigger_tap() is True
    _run_until_idle(machine)
    audio.events.clear()

    assert machine.trigger_wake_phrase("tell me a story?") is True
    assert machine.is_speaking is True
    frames = [machine.step(0.05) for _ in range(30)]
    assert max(f.talk_open for f in frames) > 0.7
    assert any(e.cue_name == "reaction_babble_curious" for e in audio.events)

    # Render rounded D-shape talking mouth with tongue onto 410x502
    talk_frame = max(frames, key=lambda f: f.talk_open)
    tgt = RecordingDisplayTarget()
    FaceRenderer(target=tgt, disp_w=410, disp_h=502).render(talk_frame)
    assert any(op[5] == 0xFF5C8A for op in tgt.ops if op[0] == "rect")

    _advance_seconds(machine, 0.5)
    assert machine.is_speaking is False
    assert machine.current_mood == "NEUTRAL"
