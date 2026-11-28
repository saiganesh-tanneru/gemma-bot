"""Chintu Wake Ritual, Sleep/Charging State Machine, Meters, and EMO Intelligence."""

from dataclasses import dataclass, field
from enum import Enum
import math
import random
from typing import Callable, Dict, List, Optional, Tuple

from controllers.chintu_controller.audio_cues import AudioCuePlayer, NullAudioCuePlayer
from controllers.chintu_controller.face_renderer import FaceFrameState
from controllers.chintu_controller.hardware import (
    ChargingSensor,
    DockDetector,
    LocalWakeWordDetector,
    ServoRig,
    TouchDebouncer,
)
from controllers.chintu_controller.registry import (
    CHINTU_GESTURES,
    CHINTU_MOODS,
    format_bot_tag,
    validate_gesture,
    validate_mood,
)


class ChintuState(str, Enum):
    SLEEP = "SLEEP"
    CHARGING_SLEEP = "CHARGING_SLEEP"
    STIR = "STIR"
    FLUTTER = "FLUTTER"
    YAWN = "YAWN"
    LOOK_AROUND = "LOOK_AROUND"
    FOUND_YOU = "FOUND_YOU"
    IDLE_AWAKE = "IDLE_AWAKE"
    DROWSY = "DROWSY"


WAKE_STATES = frozenset({
    ChintuState.STIR,
    ChintuState.FLUTTER,
    ChintuState.YAWN,
    ChintuState.LOOK_AROUND,
    ChintuState.FOUND_YOU,
})

SLEEP_STATES = frozenset({
    ChintuState.SLEEP,
    ChintuState.CHARGING_SLEEP,
})

# Score durations (seconds)
COLD_BOOT_SLEEP_S = 1.0
ACT1_STIR_S = 1.4
ACT2_FLUTTER_S = 2.2
ACT3_SCRUNCH_S = 0.4
ACT3_POP_S = 0.3
ACT3_SETTLE_S = 0.2
ACT4_LOOK_S = 3.4
ACT5_FOUND_S = 3.3
SLEEP_SERVO_DETACH_S = 20.0
INACTIVITY_DROWSY_S = 1800.0  # 30 min with no interaction


@dataclass
class TagLogEntry:
    timestamp_s: float
    state: str
    tag: str


@dataclass
class ChintuMeters:
    """0-100 meters per EMO intelligence spec."""

    energy: float = 100.0
    boredom: float = 0.0
    bond: float = 0.0

    def clamp(self) -> None:
        self.energy = max(0.0, min(100.0, self.energy))
        self.boredom = max(0.0, min(100.0, self.boredom))
        self.bond = max(0.0, min(100.0, self.bond))


class ChintuBlinkEngine:
    """Randomized awake blink engine: every 2.4-5.5 s, 120 ms close (longer when energy < 25)."""

    def __init__(self, rng: Optional[random.Random] = None) -> None:
        self._rng = rng or random.Random()
        self.enabled: bool = False
        self.blink_progress: float = 0.0
        self._blinking: bool = False
        self._blink_elapsed_s: float = 0.0
        self._next_blink_s: float = self._rng.uniform(2.4, 5.5)

    def trigger(self) -> None:
        if not self._blinking:
            self._blinking = True
            self._blink_elapsed_s = 0.0

    def step(self, dt_s: float, energy: float = 100.0) -> float:
        if not self.enabled:
            self._blinking = False
            self.blink_progress = 0.0
            return 0.0

        close_dur = 0.22 if energy < 25.0 else 0.12
        total_dur = close_dur * 2.0

        if self._blinking:
            self._blink_elapsed_s += dt_s
            if self._blink_elapsed_s >= total_dur:
                self._blinking = False
                self.blink_progress = 0.0
            elif self._blink_elapsed_s <= close_dur:
                self.blink_progress = self._blink_elapsed_s / close_dur
            else:
                self.blink_progress = 1.0 - ((self._blink_elapsed_s - close_dur) / close_dur)
        else:
            self._next_blink_s -= dt_s
            if self._next_blink_s <= 0.0:
                self.trigger()
                self._next_blink_s = self._rng.uniform(2.4, 5.5)

        return self.blink_progress


class ChintuStateMachine:
    """Drives Chintu's cold startup, charging sleep, 5-act wake ritual, and EMO idle life."""

    def __init__(
        self,
        audio_player: Optional[AudioCuePlayer] = None,
        charging_sensor: Optional[ChargingSensor] = None,
        dock_detector: Optional[DockDetector] = None,
        servo_rig: Optional[ServoRig] = None,
        face_target_provider: Optional[Callable[[], Optional[float]]] = None,
        rng: Optional[random.Random] = None,
        cold_startup: bool = True,
    ) -> None:
        self.rng = rng or random.Random(42)
        self.audio = audio_player or NullAudioCuePlayer()
        self.charging = charging_sensor or ChargingSensor()
        self.dock = dock_detector or DockDetector()
        self.servos = servo_rig or ServoRig(dock_detector=self.dock)
        self.face_target_provider = face_target_provider
        self.touch_debouncer = TouchDebouncer()
        self.blink_engine = ChintuBlinkEngine(rng=self.rng)

        self.yawn_duration_s: float = float(self.audio.yawn_duration_s)
        self.act3_yawn_s: float = ACT3_SCRUNCH_S + self.yawn_duration_s + ACT3_POP_S * 0.0 + ACT3_SETTLE_S

        self.now_s: float = 0.0
        self.state: ChintuState = ChintuState.CHARGING_SLEEP if self.charging.is_charging() else ChintuState.SLEEP
        self.state_enter_s: float = 0.0
        self.wake_start_s: Optional[float] = None
        self.last_wake_duration_s: Optional[float] = None
        self.wake_count: int = 0
        self.tts_call_count_during_wake: int = 0

        self._cold_boot_pending: bool = bool(cold_startup)
        self._cold_boot_centered: bool = False
        self._prev_charging: bool = self.charging.is_charging()
        self._prev_docked: bool = self.dock.is_docked()

        self.meters = ChintuMeters(energy=100.0, boredom=0.0, bond=0.0)
        self.current_mood: str = "NEUTRAL"
        self.mood_set_at_s: float = 0.0
        self.last_interaction_s: float = 0.0
        self.last_pat_s: float = -100.0
        self.is_speaking: bool = False
        self.wants_conversation: bool = False

        self.tag_log: List[TagLogEntry] = []
        self.last_idle_gesture: Optional[str] = None
        self._next_idle_pick_s: float = self.rng.uniform(20.0, 45.0)
        self._next_alarm_s: Optional[float] = None

        # Active sub-step flags within acts
        self._yawn_sound_played: bool = False
        self._act4_phase: int = -1
        self._act4_locked_pan_deg: float = 0.0
        self._act5_nod_phase: int = -1
        self._act5_settled: bool = False

        # Temporary idle / reaction overrides
        self._reaction_until_s: float = -1.0
        self._reaction_started_s: float = -1.0
        self._reaction_mood: Optional[str] = None
        self._reaction_gesture: Optional[str] = None
        self._reaction_gaze: Tuple[float, float] = (0.0, 0.0)
        self._reaction_heart: bool = False
        self._reaction_sparkles: bool = False
        self._reaction_happy_arcs: bool = False
        self._reaction_shiver: bool = False
        self._reaction_kind: Optional[str] = None
        self._kicked_off_phase: int = 0
        self._alarm_bell_until_s: float = -1.0

        # Drowsy progression
        self._drowsy_yawn_started: bool = False
        self._drowsy_bow_started: bool = False
        self._drowsy_yawn_start_s: float = 1.2

        # Initialize Act 0 sleep posture safely
        self.servos.attach()
        if self._cold_boot_pending:
            self.servos.move_to(0.0, 0.0, 0.5, now_s=0.0, wake_limits=True)
        else:
            self.servos.move_to(0.0, -12.0, 0.8, now_s=0.0, wake_limits=True)

    @property
    def expected_wake_duration_s(self) -> float:
        return ACT1_STIR_S + ACT2_FLUTTER_S + self.act3_yawn_s + ACT4_LOOK_S + ACT5_FOUND_S

    def _emit_tag(self, mood: Optional[str] = None, gesture: Optional[str] = None) -> str:
        tag = format_bot_tag(mood=mood, gesture=gesture)
        self.tag_log.append(TagLogEntry(timestamp_s=round(self.now_s, 3), state=self.state.value, tag=tag))
        if mood is not None:
            self.current_mood = validate_mood(mood)
            self.mood_set_at_s = self.now_s
        return tag

    def _enter_state(self, new_state: ChintuState) -> None:
        self.state = new_state
        self.state_enter_s = self.now_s

    def _enter_sleep(self, bow_duration_s: float = 0.8) -> None:
        target = ChintuState.CHARGING_SLEEP if self.charging.is_charging() else ChintuState.SLEEP
        self._enter_state(target)
        self.blink_engine.enabled = False
        self.servos.move_to(0.0, -12.0, bow_duration_s, now_s=self.now_s, wake_limits=True)
        self.meters.energy = 100.0
        self.meters.clamp()

    def _start_wake_ritual(self, reason: str) -> bool:
        if self.state in WAKE_STATES:
            return False  # Mid-ritual trigger ignored!
        if self.state not in SLEEP_STATES and self.state != ChintuState.DROWSY:
            return False

        self._cold_boot_pending = False
        self.wake_start_s = self.now_s
        self._yawn_sound_played = False
        self._act4_phase = -1
        self._act4_locked_pan_deg = 0.0
        self._act5_nod_phase = -1
        self._act5_settled = False
        self._reaction_until_s = -1.0
        self.blink_engine.enabled = False

        self.servos.attach()
        self._enter_state(ChintuState.STIR)
        self.servos.move_to(0.0, -4.0, 0.6, now_s=self.now_s, wake_limits=True)
        self.audio.play_stir_chirp(now_s=self.now_s)
        self._emit_tag(mood="SLEEPY")
        return True

    def start_drowsy(self) -> bool:
        """Starts the DROWSY wind-down sequence -> solo yawn -> bow -> SLEEP/CHARGING_SLEEP."""
        if self.state in WAKE_STATES or self.state in SLEEP_STATES or self.state == ChintuState.DROWSY:
            return False
        self._enter_state(ChintuState.DROWSY)
        self.blink_engine.enabled = True
        self._drowsy_yawn_started = False
        self._drowsy_bow_started = False
        self._emit_tag(mood="SLEEPY")
        return True

    # ------------------------------------------------------------------
    # External triggers & stimuli
    # ------------------------------------------------------------------

    def trigger_wake_phrase(self, phrase: str) -> bool:
        """Handles local-first spoken/typed phrases like 'wake Chintu up' or 'Chintu, go to sleep'."""
        kind = LocalWakeWordDetector.classify_text(phrase)
        if kind == "wake_phrase":
            if self.state in WAKE_STATES:
                return False  # Ignored mid-ritual
            if self.state not in SLEEP_STATES:
                # Reset to sleep posture so the 'wake Chintu up' test phrase plays the full ritual
                self._enter_sleep(bow_duration_s=0.0)
            return self._start_wake_ritual(kind)
        if kind == "wake_word":
            if self.state in SLEEP_STATES:
                return self._start_wake_ritual(kind)
            if self.state in WAKE_STATES:
                return False  # Ignored mid-ritual
            # Awake + "Hey Chintu" -> perk up toward voice with stir chirp
            self._trigger_call_name_reaction(pan_deg=0.0)
            return True
        if kind == "go_to_sleep":
            return self.start_drowsy()
        if kind == "kicked_off_dock":
            return self.trigger_kicked_off_dock()
        if kind == "shake_chintu":
            return self.trigger_shake()
        if kind == "set_alarm":
            delay = LocalWakeWordDetector.extract_alarm_delay_s(phrase) or 5.0
            self.schedule_alarm_in(delay)
            return True
        if kind == "ring_alarm":
            return self.trigger_alarm()
        # Any other conversational phrase while awake makes Chintu talk with EMO babble + D-mouth!
        if self.state == ChintuState.IDLE_AWAKE and phrase and phrase.strip():
            return self.trigger_talk(phrase)
        return False

    def trigger_talk(self, phrase: str = "hello") -> bool:
        """Expressive EMO babble + rounded syllable lip-sync mouth (IDLE_AWAKE only, never in wake)."""
        if self.state != ChintuState.IDLE_AWAKE:
            return False
        text = str(phrase or "").lower()
        self.last_interaction_s = self.now_s
        self.meters.boredom = 0.0
        self.meters.bond += 1.0
        self.meters.clamp()

        if any(w in text for w in ("love", "cute", "sweet", "heart", "miss")):
            mood, gesture, sfx = "LOVE", "wiggle", "babble_affection"
        elif "?" in text or any(w in text for w in ("why", "how", "what", "who", "think", "story", "joke")):
            mood, gesture, sfx = "THINKING", "curious", "babble_curious"
        elif any(w in text for w in ("wow", "omg", "really", "whoa")):
            mood, gesture, sfx = "SURPRISED", "perk_up", "babble_curious"
        else:
            mood, gesture, sfx = "HAPPY", "nod", "babble_happy"

        self.is_speaking = True
        self._reaction_started_s = self.now_s
        self._reaction_until_s = self.now_s + 1.85
        self._reaction_mood = mood
        self._reaction_gesture = gesture
        self._reaction_gaze = (0.0, 0.0)
        self._reaction_heart = (mood == "LOVE")
        self._reaction_sparkles = (mood == "HAPPY")
        self._reaction_happy_arcs = False
        self._reaction_shiver = True
        self._reaction_kind = "talk"
        self._kicked_off_phase = 1
        self.audio.play_reaction_chirp(sfx, now_s=self.now_s)
        self._emit_tag(mood=mood, gesture=gesture)
        if self.dock.is_docked():
            pan = -10.0 if gesture == "curious" else 0.0
            self.servos.move_to(pan, -4.0, 0.3, now_s=self.now_s, wake_limits=True)
        return True

    @property
    def alarm_remaining_s(self) -> Optional[float]:
        if self._next_alarm_s is None:
            return None
        return round(max(0.0, self._next_alarm_s - self.now_s), 1)

    def schedule_alarm_in(self, delay_s: float) -> None:
        self._next_alarm_s = self.now_s + max(0.5, float(delay_s))

    def trigger_alarm(self) -> bool:
        if self.state in WAKE_STATES:
            return False
        if self.state in SLEEP_STATES:
            self._alarm_bell_until_s = self.now_s + 1.2
            return self._start_wake_ritual("alarm")
        # Awake / Drowsy -> creative 3-beat Alarm Clock Reminder
        self.last_interaction_s = self.now_s
        self.meters.boredom = 0.0
        self._reaction_started_s = self.now_s
        self._reaction_until_s = self.now_s + 4.0
        self._reaction_mood = "SURPRISED"
        self._reaction_gesture = "perk_up"
        self._reaction_gaze = (-0.5, -0.45)
        self._reaction_heart = False
        self._reaction_sparkles = False
        self._reaction_happy_arcs = False
        self._reaction_shiver = True
        self._reaction_kind = "alarm_reminder"
        self._kicked_off_phase = 1
        self._alarm_bell_until_s = self.now_s + 2.65
        self.audio.play_reaction_chirp("alarm_ring", now_s=self.now_s)
        self._emit_tag(mood="SURPRISED", gesture="perk_up")
        if self.dock.is_docked():
            self.servos.move_to(-14.0, 8.0, 0.3, now_s=self.now_s, wake_limits=True)
        return True

    def schedule_alarm(self, fire_at_s: float) -> None:
        self._next_alarm_s = float(fire_at_s)

    def handle_raw_touch(self, pressed: bool) -> bool:
        """Processes raw capacitive/bumper touch state with debounce."""
        fired, rapid = self.touch_debouncer.update(pressed, self.now_s)
        if not fired:
            return False
        return self.trigger_tap(is_rapid=rapid)

    def trigger_tap(self, is_rapid: bool = False) -> bool:
        """Handles a debounced single tap (head pat or sleep wake)."""
        if self.state in WAKE_STATES:
            return False  # Ignored mid-ritual
        if self.state in SLEEP_STATES:
            return self._start_wake_ritual("head_tap")
        if self.state == ChintuState.DROWSY:
            return False

        # IDLE_AWAKE reactions
        self.last_interaction_s = self.now_s
        self.meters.boredom = 0.0
        if is_rapid:
            self._reaction_until_s = self.now_s + 2.0
            self._reaction_mood = "DIZZY"
            self._reaction_gesture = "dizzy_spin"
            self._reaction_gaze = (0.0, 0.0)
            self._reaction_heart = False
            self._reaction_sparkles = False
            self._reaction_happy_arcs = False
            self.audio.play_reaction_chirp("dizzy_swirl", now_s=self.now_s)
            self._emit_tag(mood="DIZZY", gesture="dizzy_spin")
            self.servos.move_to(0.0, 4.0, 0.35, now_s=self.now_s, wake_limits=True)
            return True

        second_pat = (self.now_s - self.last_pat_s) <= 10.0
        self.last_pat_s = self.now_s
        self.meters.bond += 1.0
        self.meters.clamp()

        self._reaction_until_s = self.now_s + 1.8
        self._reaction_mood = "HAPPY"
        self._reaction_gesture = "wiggle" if second_pat else "nod"
        self._reaction_gaze = (0.0, 0.0)
        self._reaction_heart = True
        self._reaction_sparkles = second_pat
        self._reaction_happy_arcs = not second_pat
        self.audio.play_reaction_chirp("double_pat" if second_pat else "pat", now_s=self.now_s)
        self._emit_tag(mood="HAPPY", gesture=self._reaction_gesture)
        self.servos.move_to(8.0 if second_pat else 0.0, -4.0, 0.3, now_s=self.now_s, wake_limits=True)
        return True

    def _trigger_call_name_reaction(self, pan_deg: float = 0.0) -> None:
        self.last_interaction_s = self.now_s
        self.meters.boredom = 0.0
        self._reaction_until_s = self.now_s + 1.2
        self._reaction_mood = "SURPRISED"
        self._reaction_gesture = "perk_up"
        self._reaction_gaze = (max(-1.0, min(1.0, -pan_deg / 50.0)), -0.2)
        self._reaction_heart = False
        self._reaction_sparkles = False
        self._reaction_happy_arcs = False
        self.audio.play_stir_chirp(now_s=self.now_s)
        self._emit_tag(mood="SURPRISED", gesture="perk_up")
        self.servos.move_to(pan_deg, 4.0, 0.3, now_s=self.now_s, wake_limits=True)

    def handle_loud_sound(self, pan_deg: float = 20.0) -> bool:
        """Clap/loud noise: gaze snap + wide eyes 0.6s, NEVER wakes from sleep."""
        if self.state in SLEEP_STATES or self.state in WAKE_STATES or self.state == ChintuState.DROWSY:
            return False
        self._reaction_until_s = self.now_s + 1.4
        self._reaction_mood = "SURPRISED"
        self._reaction_gesture = "curious"
        self._reaction_gaze = (max(-1.0, min(1.0, -pan_deg / 50.0)), 0.0)
        self._reaction_heart = False
        self._reaction_sparkles = False
        self._reaction_happy_arcs = False
        self.audio.play_reaction_chirp("curious", now_s=self.now_s)
        self._emit_tag(mood="SURPRISED", gesture="curious")
        self.servos.move_to(pan_deg, 3.0, 0.3, now_s=self.now_s, wake_limits=True)
        return True

    def handle_face_spotted(self, pan_deg: float = 0.0) -> bool:
        """Camera sees Sai while IDLE_AWAKE: silent Found You reaction (no words)."""
        if self.state != ChintuState.IDLE_AWAKE:
            return False
        self.last_interaction_s = self.now_s
        self.meters.boredom = 0.0
        self.meters.bond += 1.0
        self.meters.clamp()
        self._reaction_until_s = self.now_s + 1.8
        self._reaction_mood = "HAPPY"
        self._reaction_gesture = "nod"
        self._reaction_gaze = (0.0, 0.0)
        self._reaction_heart = True
        self._reaction_sparkles = self.meters.bond >= 2.0
        self._reaction_happy_arcs = True
        self._emit_tag(mood="HAPPY", gesture="nod")
        self.servos.move_to(pan_deg, -4.0, 0.3, now_s=self.now_s, wake_limits=True)
        return True

    def _trigger_kicked_off_reaction(self) -> bool:
        """4-beat mid-air dangle reaction when kicked off safe dock:
        1. Shock & yank (SURPRISED + shiver + '!')
        2. Mid-air spin/dizzy dangle (DIZZY + dizzy_spin + sweat drop)
        3. Scared puppy eyes looking down for dock (PLEADING + whimper + sweat drop)
        4. Double-blink shake-off & settle (NEUTRAL)
        """
        if self.state in WAKE_STATES:
            return False  # Never interrupt wake ritual
        if self.state in SLEEP_STATES:
            return False
        self.last_interaction_s = self.now_s
        self.meters.boredom = 0.0
        self._reaction_started_s = self.now_s
        self._reaction_until_s = self.now_s + 4.6
        self._reaction_mood = "SURPRISED"
        self._reaction_gesture = "shiver"
        self._reaction_gaze = (0.0, 0.40)
        self._reaction_heart = False
        self._reaction_sparkles = False
        self._reaction_happy_arcs = False
        self._reaction_shiver = True
        self._reaction_kind = "kicked_off"
        self._kicked_off_phase = 1
        self.audio.play_reaction_chirp("startle_scared", now_s=self.now_s)
        self._emit_tag(mood="SURPRISED", gesture="shiver")
        return True

    def trigger_shake(self) -> bool:
        """4-beat 'Shaken & Worried -> Adjusted & Fine' sequence (5.0 s total):
        1. Being shaken (SURPRISED + shiver, 2D rattle, flickering eyes, '!')
        2. Worried & off-balance (PLEADING + shiver, sweat drop, darting glance, whimper)
        3. Self-adjusting check (THINKING + curious, steady gaze check, adjust_blip)
        4. Fine & adjusted! (HAPPY + nod, happy arcs + sparkles + heart + chime -> NEUTRAL)
        """
        if self.state in WAKE_STATES or self.state in SLEEP_STATES or self.state == ChintuState.DROWSY:
            return False
        self.last_interaction_s = self.now_s
        self.meters.boredom = 0.0
        self._reaction_started_s = self.now_s
        self._reaction_until_s = self.now_s + 5.0
        self._reaction_mood = "SURPRISED"
        self._reaction_gesture = "shiver"
        self._reaction_gaze = (0.0, 0.0)
        self._reaction_heart = False
        self._reaction_sparkles = False
        self._reaction_happy_arcs = False
        self._reaction_shiver = True
        self._reaction_kind = "shaken"
        self._kicked_off_phase = 1
        self.audio.play_reaction_chirp("shaken_rattle", now_s=self.now_s)
        self._emit_tag(mood="SURPRISED", gesture="shiver")
        if self.dock.is_docked():
            self.servos.move_to(10.0, 5.0, 0.3, now_s=self.now_s, wake_limits=True)
        return True

    def trigger_kicked_off_dock(self) -> bool:
        """Simulates sudden loss of both charging and dock safety."""
        self.charging.set_manual_override(False)
        self.dock.set_manual_override(False)
        self._prev_charging = False
        self._prev_docked = False
        if self.state in SLEEP_STATES:
            if self.state == ChintuState.CHARGING_SLEEP:
                return self._start_wake_ritual("unplug")
            return False
        return self._trigger_kicked_off_reaction()

    # ------------------------------------------------------------------
    # Simulation step
    # ------------------------------------------------------------------

    def step(self, dt_s: float) -> FaceFrameState:
        """Advances state machine, servos, blink engine, and returns current FaceFrameState."""
        dt = max(0.001, float(dt_s))
        self.now_s += dt

        # 1. Charging & dock transition logic
        charging_now = self.charging.is_charging()
        docked_now = self.dock.is_docked()
        charging_removed = self._prev_charging and not charging_now
        dock_detached = self._prev_docked and not docked_now

        if charging_now != self._prev_charging:
            if charging_now:
                # Plugging in NEVER wakes, NEVER speaks, NEVER restarts anything.
                if self.state == ChintuState.SLEEP:
                    self.state = ChintuState.CHARGING_SLEEP
                elif self.state == ChintuState.IDLE_AWAKE:
                    # Charging = sleeping; bow quietly into CHARGING_SLEEP
                    self._enter_sleep(bow_duration_s=0.8)
            else:
                # Unplugging triggers wake ONLY if he was charging-sleeping
                if self.state == ChintuState.CHARGING_SLEEP:
                    self._prev_charging = charging_now
                    self._prev_docked = docked_now
                    self._start_wake_ritual("unplug")

        # Sudden kicked-off-safe-space reaction when charging is off and dock detaches while awake/drowsy
        if (
            self.state in (ChintuState.IDLE_AWAKE, ChintuState.DROWSY)
            and not charging_now
            and not docked_now
            and (charging_removed or dock_detached)
        ):
            self._trigger_kicked_off_reaction()

        self._prev_charging = charging_now
        self._prev_docked = docked_now

        # 2. Scheduled alarm check
        if self._next_alarm_s is not None and self.now_s >= self._next_alarm_s:
            self._next_alarm_s = None
            self.trigger_alarm()

        # 3. Cold startup auto-wake after ~1.0s sleep face + safe servo center
        if self._cold_boot_pending and self.state in SLEEP_STATES:
            if not self._cold_boot_centered and self.now_s >= 0.45:
                self._cold_boot_centered = True
                self.servos.move_to(0.0, -12.0, 0.45, now_s=self.now_s, wake_limits=True)
            if self.now_s >= COLD_BOOT_SLEEP_S:
                self._start_wake_ritual("cold_startup")

        elapsed = self.now_s - self.state_enter_s

        # 4. State updates
        if self.state in SLEEP_STATES:
            self.meters.energy = 100.0
            if self.servos.attached and elapsed >= SLEEP_SERVO_DETACH_S:
                self.servos.detach()

        elif self.state == ChintuState.STIR:
            if elapsed >= ACT1_STIR_S:
                self._enter_state(ChintuState.FLUTTER)
                self._emit_tag(mood="SLEEPY")

        elif self.state == ChintuState.FLUTTER:
            # Head: tilt -4 -> +2, micro-shake pan +/-3 deg, two cycles, ease 0.3 s
            if elapsed < ACT2_FLUTTER_S:
                u = elapsed / ACT2_FLUTTER_S
                tilt = -4.0 + 6.0 * min(1.0, u * 1.4)
                pan = 3.0 * math.sin(u * 4.0 * math.pi)
                self.servos.snap_target_for_tick(pan, tilt, self.now_s, wake_limits=True)
            else:
                self._enter_state(ChintuState.YAWN)
                self.servos.move_to(0.0, 14.0, 0.8, now_s=self.now_s, wake_limits=True)
                self._emit_tag(mood="SLEEPY", gesture="yawn")

        elif self.state == ChintuState.YAWN:
            sound_start = ACT3_SCRUNCH_S
            sound_end = sound_start + self.yawn_duration_s
            total_act3 = sound_end + ACT3_SETTLE_S
            if elapsed >= sound_start and not self._yawn_sound_played:
                self._yawn_sound_played = True
                self.audio.play_baby_yawn(now_s=self.now_s)
            # Snap tilt back on the pop (last 0.3s of sound)
            if elapsed >= sound_end - ACT3_POP_S and self.servos.target_tilt_deg > 4.5:
                self.servos.move_to(0.0, 4.0, 0.3, now_s=self.now_s, wake_limits=True)
            if elapsed >= total_act3:
                self._enter_state(ChintuState.LOOK_AROUND)
                self._act4_phase = -1
                self._emit_tag(mood="SURPRISED", gesture="scan")

        elif self.state == ChintuState.LOOK_AROUND:
            # Eyes lead, head follows ~150 ms later
            if elapsed >= 0.15 and self._act4_phase < 0:
                self._act4_phase = 0
                self.servos.move_to(-50.0, 4.0, 0.7, now_s=self.now_s, wake_limits=True)
            elif elapsed >= 1.25 and self._act4_phase < 1:
                self._act4_phase = 1
                self.servos.move_to(50.0, 4.0, 0.7, now_s=self.now_s, wake_limits=True)
            elif elapsed >= 2.35 and self._act4_phase < 2:
                self._act4_phase = 2
                detected = self.face_target_provider() if self.face_target_provider else None
                target_pan = max(-50.0, min(50.0, float(detected))) if detected is not None else 0.0
                self._act4_locked_pan_deg = target_pan
                self.servos.move_to(target_pan, 4.0, 0.7, now_s=self.now_s, wake_limits=True)

            if elapsed >= ACT4_LOOK_S:
                self._enter_state(ChintuState.FOUND_YOU)
                self._act5_nod_phase = -1
                self._act5_settled = False
                self.meters.bond += 1.0
                self.meters.clamp()
                self._emit_tag(mood="HAPPY", gesture="nod")

        elif self.state == ChintuState.FOUND_YOU:
            # Two quick delighted nods (tilt dip -6 deg, ease 0.3 s) then return to +2
            if elapsed >= 0.50 and self._act5_nod_phase < 0:
                self._act5_nod_phase = 0
                self.servos.move_to(self._act4_locked_pan_deg, -6.0, 0.3, now_s=self.now_s, wake_limits=True)
            elif elapsed >= 0.85 and self._act5_nod_phase < 1:
                self._act5_nod_phase = 1
                self.servos.move_to(self._act4_locked_pan_deg, 2.0, 0.3, now_s=self.now_s, wake_limits=True)
            elif elapsed >= 1.20 and self._act5_nod_phase < 2:
                self._act5_nod_phase = 2
                self.servos.move_to(self._act4_locked_pan_deg, -6.0, 0.3, now_s=self.now_s, wake_limits=True)
            elif elapsed >= 1.55 and self._act5_nod_phase < 3:
                self._act5_nod_phase = 3
                self.servos.move_to(self._act4_locked_pan_deg, 2.0, 0.3, now_s=self.now_s, wake_limits=True)
            elif elapsed >= 2.20 and not self._act5_settled:
                self._act5_settled = True
                self._emit_tag(mood="NEUTRAL")

            if elapsed >= ACT5_FOUND_S:
                if self.wake_start_s is not None:
                    self.last_wake_duration_s = self.now_s - self.wake_start_s
                self.wake_count += 1
                self.meters.energy = 100.0
                self.meters.boredom = 0.0
                self.meters.clamp()
                self.last_interaction_s = self.now_s
                self.blink_engine.enabled = True
                self._enter_state(ChintuState.IDLE_AWAKE)

        elif self.state == ChintuState.IDLE_AWAKE:
            # Energy drain (~4 h = 14400 s, 2x while speaking/reacting)
            drain_rate = (100.0 / 14400.0) * (2.0 if (self.is_speaking or self.now_s < self._reaction_until_s) else 1.0)
            self.meters.energy -= drain_rate * dt
            # Boredom rises +1 every ~90 s with no interaction
            self.meters.boredom += (1.0 / 90.0) * dt
            # Bond decays slowly over days
            self.meters.bond -= (1.0 / 86400.0) * dt
            self.meters.clamp()

            if self.meters.boredom > 85.0:
                self.wants_conversation = True

            # Mood half-life decay back to NEUTRAL
            if self.current_mood != "NEUTRAL" and self.now_s >= self._reaction_until_s:
                half_life = 600.0 if self.current_mood == "SLEEPY" else 1200.0
                if (self.now_s - self.mood_set_at_s) >= half_life:
                    self.current_mood = "NEUTRAL"
                    self.mood_set_at_s = self.now_s

            if self.meters.energy < 25.0 and self.current_mood == "NEUTRAL":
                self.current_mood = "SLEEPY"
                self.mood_set_at_s = self.now_s

            # Idle gesture picker (20-45 s, never repeat previous, never while speaking)
            self._next_idle_pick_s -= dt
            if self._next_idle_pick_s <= 0.0:
                self._next_idle_pick_s = self.rng.uniform(20.0, 45.0)
                if not self.is_speaking and self.now_s >= self._reaction_until_s:
                    self._pick_idle_gesture()

            # Transition to DROWSY on Energy 0 or 30 min inactivity
            if self.meters.energy <= 0.0 or (self.now_s - self.last_interaction_s) >= INACTIVITY_DROWSY_S:
                self.start_drowsy()

        elif self.state == ChintuState.DROWSY:
            # 0..1.2s slow blink chain, 1.2..(1.2+yawn) solo yawn, then 2.0s bow -> sleep
            yawn_start = self._drowsy_yawn_start_s
            yawn_end = yawn_start + self.yawn_duration_s
            bow_end = yawn_end + 2.0
            if elapsed >= yawn_start and not self._drowsy_yawn_started:
                self._drowsy_yawn_started = True
                self.audio.play_baby_yawn(now_s=self.now_s)
                self.servos.move_to(0.0, 12.0, 0.7, now_s=self.now_s, wake_limits=True)
                self._emit_tag(mood="SLEEPY", gesture="yawn")
            if elapsed >= yawn_end and not self._drowsy_bow_started:
                self._drowsy_bow_started = True
                self.servos.move_to(0.0, -12.0, 2.0, now_s=self.now_s, wake_limits=True)
                self._emit_tag(mood="SLEEPY", gesture="droop")
            if elapsed >= bow_end:
                self._enter_sleep(bow_duration_s=0.3)

        self.servos.step(self.now_s)
        return self._build_face_frame(dt)

    def _pick_idle_gesture(self) -> str:
        pool: List[Tuple[str, float]] = [
            ("curious", 1.2),
            ("tilt_left", 1.0),
            ("tilt_right", 1.0),
            ("scan", 1.1),
            ("nod", 0.8),
            ("wiggle", 0.9 if self.current_mood == "HAPPY" else 0.4),
            ("yawn", 1.6 if (self.meters.energy < 35.0 or self.meters.boredom > 55.0) else 0.4),
            ("perk_up", 1.4 if self.meters.boredom > 60.0 else 0.7),
            ("droop", 1.3 if self.meters.energy < 25.0 else 0.3),
        ]
        filtered = [(g, w) for g, w in pool if g != self.last_idle_gesture and g in CHINTU_GESTURES]
        total = sum(w for _, w in filtered)
        pick = self.rng.uniform(0.0, total)
        acc = 0.0
        chosen = filtered[0][0]
        for g, w in filtered:
            acc += w
            if pick <= acc:
                chosen = g
                break
        self.last_idle_gesture = chosen
        self._reaction_until_s = self.now_s + 1.4
        self._reaction_mood = self.current_mood
        self._reaction_gesture = chosen
        self._reaction_heart = False
        self._reaction_sparkles = False
        self._reaction_happy_arcs = False

        if chosen == "tilt_left":
            self.servos.move_to(-22.0, 2.0, 0.5, now_s=self.now_s, wake_limits=True)
            self._reaction_gaze = (-0.6, 0.0)
        elif chosen == "tilt_right":
            self.servos.move_to(22.0, 2.0, 0.5, now_s=self.now_s, wake_limits=True)
            self._reaction_gaze = (0.6, 0.0)
        elif chosen == "curious":
            self.servos.move_to(-18.0, 5.0, 0.5, now_s=self.now_s, wake_limits=True)
            self._reaction_gaze = (-0.7, -0.2)
        elif chosen == "perk_up" and self.meters.boredom > 60.0:
            self.audio.play_reaction_chirp("attention", now_s=self.now_s)
            self.servos.move_to(0.0, 6.0, 0.4, now_s=self.now_s, wake_limits=True)
            self._reaction_gaze = (0.0, -0.3)
        else:
            self.servos.move_to(0.0, 2.0, 0.5, now_s=self.now_s, wake_limits=True)
            self._reaction_gaze = (0.0, 0.0)

        self._emit_tag(mood=self.current_mood, gesture=chosen)
        return chosen

    def _build_face_frame(self, dt_s: float) -> FaceFrameState:
        elapsed = self.now_s - self.state_enter_s
        blink = self.blink_engine.step(dt_s, energy=self.meters.energy)

        if self.state in SLEEP_STATES:
            breath = math.sin(2.0 * math.pi * self.now_s / 4.0) * 1.0
            zzz = (self.now_s % 3.0) / 3.0
            return FaceFrameState(
                face_mode="sleep",
                mood="SLEEPY",
                left_eye_open=0.0,
                right_eye_open=0.0,
                face_bob_y=breath,
                zzz_phase=zzz,
                is_charging=(self.state == ChintuState.CHARGING_SLEEP),
                brightness=0.40,
            )

        if self.state == ChintuState.STIR:
            left = 0.25 * min(1.0, elapsed / 0.4)
            right = 0.0 if elapsed < 0.8 else 0.25 * min(1.0, (elapsed - 0.8) / 0.4)
            return FaceFrameState(
                face_mode="stir",
                mood="SLEEPY",
                left_eye_open=left,
                right_eye_open=right,
                bell_alpha=1.0 if self.now_s < self._alarm_bell_until_s else 0.0,
                dizzy_phase=self.now_s,
                brightness=0.40 + 0.60 * min(1.0, elapsed / 0.6),
            )

        if self.state == ChintuState.FLUTTER:
            # 25% -> 70% -> 35% -> 85% -> 50% -> 100%
            pts = (0.25, 0.70, 0.35, 0.85, 0.50, 1.00)
            u = max(0.0, min(1.0, elapsed / ACT2_FLUTTER_S))
            pos = u * (len(pts) - 1)
            idx = min(len(pts) - 2, int(pos))
            frac = pos - idx
            op = pts[idx] + (pts[idx + 1] - pts[idx]) * frac
            return FaceFrameState(
                face_mode="flutter",
                mood="SLEEPY",
                left_eye_open=op,
                right_eye_open=op,
                brightness=1.0,
            )

        if self.state == ChintuState.YAWN:
            return self._build_yawn_frame(elapsed, sound_start=ACT3_SCRUNCH_S)

        if self.state == ChintuState.LOOK_AROUND:
            # Eyes lead, head follows ~150ms later
            if elapsed < 1.10:
                gx = -0.85 * min(1.0, elapsed / 0.25)
            elif elapsed < 2.20:
                gx = -0.85 + 1.70 * min(1.0, (elapsed - 1.10) / 0.25)
            else:
                target_gx = max(-0.85, min(0.85, self._act4_locked_pan_deg / 50.0))
                gx = 0.85 + (target_gx - 0.85) * min(1.0, (elapsed - 2.20) / 0.35)
            return FaceFrameState(
                face_mode="look",
                mood="SURPRISED",
                left_eye_open=1.0,
                right_eye_open=1.0,
                eye_scale=1.08,
                gaze_x=gx,
                gaze_y=-0.1,
                smile_amount=0.15,
            )

        if self.state == ChintuState.FOUND_YOU:
            if elapsed < 0.50:
                return FaceFrameState(
                    face_mode="found_you",
                    mood="HAPPY",
                    happy_arcs=True,
                    smile_amount=0.85,
                )
            if elapsed < 2.20:
                return FaceFrameState(
                    face_mode="found_you",
                    mood="HAPPY",
                    left_eye_open=1.0,
                    right_eye_open=1.0,
                    eye_scale=1.06,
                    sparkles=1.0,
                    heart_alpha=1.0,
                    smile_amount=0.95,
                )
            fade = max(0.0, 1.0 - (elapsed - 2.20) / max(0.1, ACT5_FOUND_S - 2.20))
            return FaceFrameState(
                face_mode="found_you",
                mood="NEUTRAL",
                left_eye_open=1.0,
                right_eye_open=1.0,
                eye_scale=1.0 + 0.06 * fade,
                sparkles=fade,
                heart_alpha=fade,
                smile_amount=0.35 + 0.60 * fade,
            )

        if self.state == ChintuState.DROWSY:
            yawn_start = self._drowsy_yawn_start_s
            yawn_end = yawn_start + self.yawn_duration_s
            if elapsed < yawn_start:
                slow_blink = abs(math.sin(elapsed * math.pi / 0.6))
                return FaceFrameState(
                    face_mode="content_idle",
                    mood="SLEEPY",
                    left_eye_open=0.5,
                    right_eye_open=0.5,
                    blink_progress=slow_blink * 0.7,
                    smile_amount=0.1,
                )
            if elapsed < yawn_end + ACT3_SETTLE_S:
                return self._build_yawn_frame(elapsed - yawn_start + ACT3_SCRUNCH_S, sound_start=ACT3_SCRUNCH_S)
            return FaceFrameState(
                face_mode="sleep",
                mood="SLEEPY",
                left_eye_open=0.1,
                right_eye_open=0.1,
                brightness=0.6,
            )

        # IDLE_AWAKE
        breath = math.sin(2.0 * math.pi * self.now_s / 4.0) * 0.6
        talk_open = 0.0
        talk_width = 0.5
        if self.now_s < self._reaction_until_s and self._reaction_mood is not None:
            bob_x = 0.0
            bob_y = breath
            eye_scale = 1.0
            gaze_x, gaze_y = self._reaction_gaze
            alert_alpha = 0.0
            sweat_alpha = 0.0
            l_open = 1.0
            r_open = 1.0
            reaction_blink = blink
            if self._reaction_shiver and self._reaction_kind == "talk":
                rel = self.now_s - self._reaction_started_s
                if rel < 1.55:
                    # Smooth continuous multi-syllable :D smile-talk cadence (never snaps to 0)
                    env = math.sin((rel / 1.55) * math.pi) ** 0.5
                    syl = 0.5 + 0.5 * math.sin(rel * 13.0) * math.cos(rel * 5.2)
                    talk_open = (0.18 + 0.82 * syl) * env
                    talk_width = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(rel * 8.5))
                    bob_y = -0.8 * abs(math.sin(rel * 7.5))
                    gaze_x = 0.18 * math.sin(rel * 2.2)
                    eye_scale = 1.03 + 0.03 * talk_open
                else:
                    if self._kicked_off_phase < 2:
                        self._kicked_off_phase = 2
                        self.is_speaking = False
                        self._reaction_mood = "NEUTRAL"
                        self._reaction_sparkles = False
                        self._reaction_heart = False
                        self._emit_tag(mood="NEUTRAL")
                        if self.dock.is_docked():
                            self.servos.move_to(0.0, 2.0, 0.3, now_s=self.now_s, wake_limits=True)
            elif self._reaction_shiver and self._reaction_kind == "shaken":
                rel = self.now_s - self._reaction_started_s
                if rel >= 1.10 and self._kicked_off_phase < 2:
                    self._kicked_off_phase = 2
                    self._reaction_mood = "PLEADING"
                    self._reaction_gesture = "shiver"
                    self.audio.play_reaction_chirp("whimper", now_s=self.now_s)
                    self._emit_tag(mood="PLEADING", gesture="shiver")
                    if self.dock.is_docked():
                        self.servos.move_to(-8.0, -3.0, 0.4, now_s=self.now_s, wake_limits=True)
                elif rel >= 2.75 and self._kicked_off_phase < 3:
                    self._kicked_off_phase = 3
                    self._reaction_mood = "THINKING"
                    self._reaction_gesture = "curious"
                    self.audio.play_reaction_chirp("adjust_blip", now_s=self.now_s)
                    self._emit_tag(mood="THINKING", gesture="curious")
                    if self.dock.is_docked():
                        self.servos.move_to(0.0, 2.0, 0.5, now_s=self.now_s, wake_limits=True)
                elif rel >= 3.80 and self._kicked_off_phase < 4:
                    self._kicked_off_phase = 4
                    self._reaction_mood = "HAPPY"
                    self._reaction_gesture = "nod"
                    self.audio.play_reaction_chirp("adjusted_ok", now_s=self.now_s)
                    self._emit_tag(mood="HAPPY", gesture="nod")
                    if self.dock.is_docked():
                        self.servos.move_to(0.0, -4.0, 0.3, now_s=self.now_s, wake_limits=True)
                elif rel >= 4.65 and self._kicked_off_phase < 5:
                    self._kicked_off_phase = 5
                    self._reaction_mood = "NEUTRAL"
                    self._emit_tag(mood="NEUTRAL")
                    if self.dock.is_docked():
                        self.servos.move_to(0.0, 2.0, 0.3, now_s=self.now_s, wake_limits=True)

                if rel < 1.10:
                    # Beat 1: Rapid 2D shake rattle + flickering eyes + '!'
                    bob_x = 5.5 * math.sin(rel * 36.0)
                    bob_y = 3.2 * math.cos(rel * 48.0)
                    eye_scale = 1.18
                    l_open = 0.55 + 0.45 * abs(math.sin(rel * 24.0))
                    r_open = 0.55 + 0.45 * abs(math.cos(rel * 26.0))
                    gaze_x = 0.6 * math.sin(rel * 20.0)
                    gaze_y = 0.3 * math.cos(rel * 24.0)
                    alert_alpha = 1.0
                    reaction_blink = 0.0
                elif rel < 2.75:
                    # Beat 2: Worried PLEADING puppy eyes + sweat drop + nervous left/right scan
                    u = rel - 1.10
                    decay = max(0.0, 1.0 - u / 1.65)
                    bob_x = 2.6 * math.sin(u * 28.0) * decay
                    bob_y = 0.8 * math.cos(u * 22.0) * decay
                    eye_scale = 1.08
                    gaze_x = 0.75 * math.sin(u * 4.2)
                    gaze_y = 0.35
                    sweat_alpha = 1.0
                    reaction_blink = 0.0
                elif rel < 3.80:
                    # Beat 3: Careful check & self-adjustment (THINKING)
                    u = rel - 2.75
                    bob_x = 0.0
                    bob_y = breath
                    gaze_x = -0.55 if u < 0.45 else (0.55 if u < 0.8 else 0.0)
                    gaze_y = -0.25
                    sweat_alpha = max(0.0, 0.5 * (1.0 - u / 0.5))
                    reaction_blink = abs(math.sin(u * math.pi / 0.2)) if u < 0.2 else 0.0
                else:
                    # Beat 4: Fine & adjusted! Happy arcs -> sparkle eyes + heart -> calm NEUTRAL
                    u = rel - 3.80
                    bob_x = 0.0
                    bob_y = breath
                    gaze_x = 0.0
                    gaze_y = 0.0
                    self._reaction_happy_arcs = u < 0.42
                    self._reaction_sparkles = 0.42 <= u < 0.85
                    self._reaction_heart = u < 0.85
            elif self._reaction_shiver and self._reaction_kind == "alarm_reminder":
                rel = self.now_s - self._reaction_started_s
                if rel >= 1.25 and self._kicked_off_phase < 2:
                    self._kicked_off_phase = 2
                    self._reaction_mood = "HAPPY"
                    self._reaction_gesture = "bounce"
                    self.audio.play_reaction_chirp("alarm_ring", now_s=self.now_s)
                    self._emit_tag(mood="HAPPY", gesture="bounce")
                    if self.dock.is_docked():
                        self.servos.move_to(0.0, 4.0, 0.3, now_s=self.now_s, wake_limits=True)
                elif rel >= 2.65 and self._kicked_off_phase < 3:
                    self._kicked_off_phase = 3
                    self._reaction_mood = "WINK"
                    self._reaction_gesture = "nod"
                    self.audio.play_reaction_chirp("adjusted_ok", now_s=self.now_s)
                    self._emit_tag(mood="WINK", gesture="nod")
                    if self.dock.is_docked():
                        self.servos.move_to(0.0, -4.0, 0.3, now_s=self.now_s, wake_limits=True)
                elif rel >= 3.55 and self._kicked_off_phase < 4:
                    self._kicked_off_phase = 4
                    self._reaction_mood = "NEUTRAL"
                    self._emit_tag(mood="NEUTRAL")
                    if self.dock.is_docked():
                        self.servos.move_to(0.0, 2.0, 0.3, now_s=self.now_s, wake_limits=True)

                if rel < 1.25:
                    eye_scale = 1.16
                    gaze_x = -0.50
                    gaze_y = -0.45
                    bob_y = -1.0 * abs(math.sin(rel * 12.0))
                elif rel < 2.65:
                    u = rel - 1.25
                    bob_y = -2.2 * abs(math.sin(u * 10.0))
                    gaze_x = 0.0
                    gaze_y = 0.0
                    self._reaction_happy_arcs = (int(u * 4.0) % 2) == 0
                    self._reaction_sparkles = not self._reaction_happy_arcs
                else:
                    u = rel - 2.65
                    bob_y = breath
                    gaze_x = 0.0
                    gaze_y = 0.0
                    self._reaction_happy_arcs = False
                    self._reaction_sparkles = False
                    self._reaction_heart = u < 0.90
            elif self._reaction_shiver:
                rel = self.now_s - self._reaction_started_s
                if rel >= 0.85 and self._kicked_off_phase < 2:
                    self._kicked_off_phase = 2
                    self._reaction_mood = "DIZZY"
                    self._reaction_gesture = "dizzy_spin"
                    self.audio.play_reaction_chirp("dizzy_swirl", now_s=self.now_s)
                    self._emit_tag(mood="DIZZY", gesture="dizzy_spin")
                elif rel >= 1.95 and self._kicked_off_phase < 3:
                    self._kicked_off_phase = 3
                    self._reaction_mood = "PLEADING"
                    self._reaction_gesture = "shiver"
                    self.audio.play_reaction_chirp("whimper", now_s=self.now_s)
                    self._emit_tag(mood="PLEADING")
                elif rel >= 3.65 and self._kicked_off_phase < 4:
                    self._kicked_off_phase = 4
                    self._reaction_mood = "NEUTRAL"
                    self._reaction_gesture = "shake"
                    self.audio.play_reaction_chirp("shake_off", now_s=self.now_s)
                    self._emit_tag(mood="NEUTRAL")

                if rel < 0.85:
                    # Beat 1: Sudden yank, wide shock eyes, '!' alert, fast pendulum + tremble
                    swing = math.sin(rel * 12.0) * 6.5
                    tremble = math.sin(rel * 48.0) * 0.9
                    bob_x = swing + tremble
                    bob_y = -2.8 * abs(math.sin(rel * 12.0))
                    eye_scale = 1.24
                    gaze_x = -0.9 * math.sin(rel * 12.0)
                    gaze_y = 0.40
                    alert_alpha = 1.0
                    l_open = 1.0 - 0.12 * abs(math.sin(rel * 22.0))
                    r_open = 1.0
                    reaction_blink = 0.0
                elif rel < 1.95:
                    # Beat 2: Mid-air keychain spin / dizzy figure-8 dangle + sweat drop
                    u = rel - 0.85
                    bob_x = 5.0 * math.sin(u * 7.5)
                    bob_y = 2.0 * math.sin(u * 15.0)
                    eye_scale = 1.05
                    gaze_x = 0.4 * math.cos(u * 7.5)
                    gaze_y = 0.25
                    sweat_alpha = 1.0
                    reaction_blink = 0.0
                elif rel < 3.65:
                    # Beat 3: Damped air-sway + scared puppy eyes looking down for safe dock
                    u = rel - 1.95
                    decay = math.exp(-u * 0.85)
                    sway = math.sin(u * 6.2)
                    bob_x = sway * 4.2 * decay
                    bob_y = 1.5 * abs(sway) * decay
                    eye_scale = 1.08
                    gaze_x = -0.45 * sway * decay
                    gaze_y = 0.75
                    sweat_alpha = max(0.0, 1.0 - u / 1.7)
                    reaction_blink = 0.0
                else:
                    # Beat 4: Brave double-blink shake-off & settle
                    u = rel - 3.65
                    bob_x = 2.4 * math.sin(u * 26.0) * max(0.0, 1.0 - u / 0.95)
                    bob_y = breath
                    gaze_x = 0.0
                    gaze_y = 0.0
                    reaction_blink = abs(math.sin(u * math.pi / 0.22)) if u < 0.44 else 0.0
            return FaceFrameState(
                face_mode="content_idle",
                mood=self._reaction_mood,
                left_eye_open=l_open,
                right_eye_open=r_open,
                eye_scale=eye_scale,
                gaze_x=gaze_x,
                gaze_y=gaze_y,
                face_bob_x=bob_x,
                face_bob_y=bob_y,
                happy_arcs=self._reaction_happy_arcs,
                sparkles=1.0 if self._reaction_sparkles else 0.0,
                heart_alpha=1.0 if self._reaction_heart else 0.0,
                sweat_alpha=sweat_alpha,
                alert_alpha=alert_alpha,
                bell_alpha=1.0 if self.now_s < self._alarm_bell_until_s else 0.0,
                talk_open=talk_open,
                talk_width=talk_width,
                smile_amount=0.85 if self._reaction_mood in ("HAPPY", "WINK") else 0.35,
                blink_progress=reaction_blink,
                dizzy_phase=self.now_s,
            )
        self.is_speaking = False
        self._reaction_shiver = False
        self._reaction_kind = None
        self._reaction_happy_arcs = False
        self._reaction_sparkles = False
        self._reaction_heart = False

        eye_open = 0.65 if self.current_mood == "SLEEPY" else 1.0
        return FaceFrameState(
            face_mode="content_idle",
            mood=self.current_mood,
            left_eye_open=eye_open,
            right_eye_open=eye_open,
            face_bob_y=breath,
            smile_amount=0.35,
            blink_progress=blink,
        )

    def _build_yawn_frame(self, elapsed: float, sound_start: float) -> FaceFrameState:
        sound_end = sound_start + self.yawn_duration_s
        pop_start = max(sound_start + 0.1, sound_end - ACT3_POP_S)

        if elapsed < sound_start:
            # 0.4 s uneven eye scrunch: left slams shut, right squishes to 35% slit
            u = max(0.0, min(1.0, elapsed / sound_start))
            return FaceFrameState(
                face_mode="yawn",
                mood="SLEEPY",
                left_eye_open=1.0 - u,
                right_eye_open=1.0 - 0.65 * u,
                mouth_open=0.0,
            )

        if elapsed <= sound_end:
            if elapsed < sound_start + 0.45:
                # Mouth blooms open as sound begins
                m_open = (elapsed - sound_start) / 0.45
                wobble = 0.0
                bob = 0.0
                l_eye, r_eye = 0.0, 0.35
            elif elapsed < pop_start:
                # Full stretch with +/-4% mouth wobble & +/-1.6 px face bob
                m_open = 1.0
                wobble = 0.04 * math.sin((elapsed - sound_start) * 18.0)
                bob = 1.6 * math.sin((elapsed - sound_start) * 11.0)
                l_eye, r_eye = 0.0, 0.35
            else:
                # 0.3 s *pop* close ending EXACTLY as the sound ends; eyes spring back to 100%
                u = (elapsed - pop_start) / max(0.05, sound_end - pop_start)
                m_open = max(0.0, 1.0 - u)
                wobble = 0.0
                bob = 0.0
                l_eye = u
                r_eye = 0.35 + 0.65 * u
            return FaceFrameState(
                face_mode="yawn",
                mood="SLEEPY",
                left_eye_open=l_eye,
                right_eye_open=r_eye,
                mouth_open=m_open,
                mouth_wobble=wobble,
                face_bob_y=bob,
            )

        # Post-pop 0.2s spring settle
        return FaceFrameState(
            face_mode="yawn",
            mood="SLEEPY",
            left_eye_open=1.0,
            right_eye_open=1.0,
            mouth_open=0.0,
        )
