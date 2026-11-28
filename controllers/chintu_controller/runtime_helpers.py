"""Shared command queue processing and status synchronization for Webots and standalone Playground."""

from typing import Callable, Optional

from controllers.chintu_controller.audio_cues import AudioCuePlayer, SystemAudioCuePlayer
from controllers.chintu_controller.hardware import ChargingSensor, DockDetector, ServoRig
from controllers.chintu_controller.server import CHINTU_COMMAND_QUEUE, CHINTU_STATUS
from controllers.chintu_controller.wake_engine import ChintuStateMachine


def process_chintu_command_queue(
    machine: ChintuStateMachine,
    charging_sensor: ChargingSensor,
    dock_detector: DockDetector,
    on_cold_startup: Callable[[], ChintuStateMachine],
    on_face_pan_override: Callable[[float], None],
) -> ChintuStateMachine:
    """Drains CHINTU_COMMAND_QUEUE identically for Webots and standalone Playground."""
    active_machine = machine
    while not CHINTU_COMMAND_QUEUE.empty():
        cmd = CHINTU_COMMAND_QUEUE.get_nowait()
        if cmd.get("cold_startup"):
            active_machine = on_cold_startup()
            continue
        if cmd.get("kicked_off_dock"):
            active_machine.trigger_kicked_off_dock()
            continue
        if cmd.get("shake"):
            active_machine.trigger_shake()
        if "say" in cmd or "talk" in cmd:
            text = str(cmd.get("say") or cmd.get("talk") or "hello")
            active_machine.trigger_talk(text)
        if "is_charging" in cmd:
            val = cmd["is_charging"]
            charging_sensor.set_manual_override(None if val is None else bool(val))
        if "is_docked" in cmd:
            val = cmd["is_docked"]
            dock_detector.set_manual_override(None if val is None else bool(val))
        if cmd.get("tap"):
            active_machine.trigger_tap()
        if cmd.get("alarm"):
            active_machine.trigger_alarm()
        if "alarm_in_s" in cmd and cmd["alarm_in_s"] is not None:
            active_machine.schedule_alarm_in(float(cmd["alarm_in_s"]))
        if cmd.get("clap"):
            active_machine.handle_loud_sound(pan_deg=float(cmd.get("pan_deg", 20.0)))
        if "face_pan_deg" in cmd:
            pan = float(cmd["face_pan_deg"])
            on_face_pan_override(pan)
            active_machine.handle_face_spotted(pan_deg=pan)
        if "weather_ambient" in cmd:
            active_machine.set_weather_ambient(bool(cmd["weather_ambient"]))
        if "weather_unit" in cmd:
            active_machine.set_weather_unit(str(cmd["weather_unit"]))
        if cmd.get("weather_clear"):
            active_machine.clear_weather()
        if "weather_city" in cmd and cmd["weather_city"]:
            active_machine.trigger_live_weather(str(cmd["weather_city"]))
        if isinstance(cmd.get("weather_sim"), dict):
            sim = cmd["weather_sim"]
            cond = str(sim.get("condition") or "sunny")
            active_machine.trigger_weather(
                cond,
                city=str(sim.get("city") or "Playground"),
                temp_c=sim.get("temp_c"),
                wind_kmh=sim.get("wind_kmh"),
            )
        if "weather" in cmd and isinstance(cmd["weather"], str):
            wx = cmd["weather"].strip().lower()
            if wx in ("off", "clear", "none", ""):
                active_machine.clear_weather()
            else:
                active_machine.trigger_weather(wx)
        for key in ("phrase", "wake_phrase", "wake_word", "speech", "text"):
            if isinstance(cmd.get(key), str):
                active_machine.trigger_wake_phrase(cmd[key])
    return active_machine


def sync_chintu_status(
    machine: ChintuStateMachine,
    servo_rig: ServoRig,
    charging_sensor: ChargingSensor,
    dock_detector: DockDetector,
    audio_player: Optional[AudioCuePlayer],
    frame,
) -> None:
    """Publishes identical live status & frame payloads for /status and /playground."""
    events = getattr(audio_player, "events", None)
    CHINTU_STATUS.update({
        "product": "Chintu",
        "manufacturer": "Sarworks",
        "state": machine.state.value,
        "mood": machine.current_mood,
        "pan_deg": round(servo_rig.pan_deg, 2),
        "tilt_deg": round(servo_rig.tilt_deg, 2),
        "is_charging": charging_sensor.is_charging(),
        "is_docked": dock_detector.is_docked(),
        "servos_attached": servo_rig.attached,
        "energy": round(machine.meters.energy, 2),
        "boredom": round(machine.meters.boredom, 2),
        "bond": round(machine.meters.bond, 2),
        "wake_count": machine.wake_count,
        "last_wake_duration_s": (
            round(machine.last_wake_duration_s, 3)
            if machine.last_wake_duration_s is not None
            else None
        ),
        "yawn_wav_duration_s": round(machine.yawn_duration_s, 4),
        "tts_calls_during_wake": machine.tts_call_count_during_wake,
        "alarm_remaining_s": machine.alarm_remaining_s,
        "host_audio": isinstance(audio_player, SystemAudioCuePlayer),
        "last_audio_cue": (
            {"seq": len(events), "cue": events[-1].cue_name}
            if events
            else None
        ),
        "weather": (
            machine.weather_snapshot.to_dict(machine.weather_unit)
            if machine.weather_snapshot is not None
            else None
        ),
        "weather_ambient": machine.weather_ambient,
        "weather_unit": machine.weather_unit,
        "weather_fetching": machine.weather_service.is_fetching,
        "weather_error": machine.weather_error,
        "tag_log": [
            {"timestamp_s": e.timestamp_s, "state": e.state, "tag": e.tag}
            for e in machine.tag_log[-32:]
        ],
        "frame": {
            "face_mode": frame.face_mode,
            "mood": frame.mood,
            "left_eye_open": round(frame.left_eye_open, 3),
            "right_eye_open": round(frame.right_eye_open, 3),
            "eye_scale": round(frame.eye_scale, 3),
            "face_scale": round(frame.face_scale, 3),
            "gaze_x": round(frame.gaze_x, 3),
            "gaze_y": round(frame.gaze_y, 3),
            "mouth_open": round(frame.mouth_open, 3),
            "mouth_wobble": round(frame.mouth_wobble, 4),
            "talk_open": round(frame.talk_open, 3),
            "talk_width": round(frame.talk_width, 3),
            "face_bob_x": round(frame.face_bob_x, 3),
            "face_bob_y": round(frame.face_bob_y, 3),
            "smile_amount": round(frame.smile_amount, 3),
            "happy_arcs": frame.happy_arcs,
            "sparkles": round(frame.sparkles, 3),
            "heart_alpha": round(frame.heart_alpha, 3),
            "sweat_alpha": round(frame.sweat_alpha, 3),
            "alert_alpha": round(frame.alert_alpha, 3),
            "bell_alpha": round(frame.bell_alpha, 3),
            "zzz_phase": round(frame.zzz_phase, 3),
            "dizzy_phase": round(frame.dizzy_phase, 3),
            "is_charging": frame.is_charging,
            "brightness": round(frame.brightness, 3),
            "blink_progress": round(frame.blink_progress, 3),
            "weather_condition": frame.weather_condition,
            "weather_intensity": round(frame.weather_intensity, 3),
            "weather_phase": round(frame.weather_phase, 3),
            "weather_flash": round(frame.weather_flash, 3),
            "weather_bolt": int(frame.weather_bolt),
            "weather_temp_label": frame.weather_temp_label,
            "umbrella_alpha": round(frame.umbrella_alpha, 3),
            "blanket_alpha": round(frame.blanket_alpha, 3),
            "jacket_alpha": round(frame.jacket_alpha, 3),
        },
    })
