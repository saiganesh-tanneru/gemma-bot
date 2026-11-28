"""Stateful Emotion Engine: smooth eye morphing, weighted roulette, blinks, and idle life."""

from dataclasses import dataclass
import math
import random
from typing import Dict, Optional, Tuple

from emotion_engine.chirp import ChirpPlayer, NullChirpPlayer
from emotion_engine.presets import (
    CONVERSATION_STATE_PRESETS,
    EMOTIONS,
    ChirpSpec,
    EmotionSpec,
    EyeConfig,
    resolve_mood,
)


@dataclass
class EmotionState:
    """Internal companion drives (in [0.0, 1.0]) and physical hardware context."""

    energy: float = 1.0
    boredom: float = 0.0
    bond: float = 0.5
    detached: bool = False
    battery_pct: float = 100.0
    thermal_hot: bool = False

    def clamp(self) -> None:
        self.energy = max(0.0, min(1.0, self.energy))
        self.boredom = max(0.0, min(1.0, self.boredom))
        self.bond = max(0.0, min(1.0, self.bond))
        self.battery_pct = max(0.0, min(100.0, self.battery_pct))

    def step_idle_decay(self, dt_seconds: float) -> None:
        """Gradually builds boredom and gently decays energy while idle."""
        self.boredom += 0.008 * dt_seconds
        self.energy -= 0.002 * dt_seconds
        self.clamp()


@dataclass(frozen=True)
class EmotionReaction:
    """Unified output emitted by stimulus handlers for controller or MCU execution."""

    mood: Optional[str] = None
    gesture: Optional[str] = None
    chirp: Optional[ChirpSpec] = None
    target_yaw: Optional[float] = None
    target_pitch: Optional[float] = None
    gaze_x: Optional[float] = None
    gaze_y: Optional[float] = None
    interrupt_speech: bool = False


class BlinkController:
    """Manages natural blink envelope and randomized inter-blink interval."""

    def __init__(self, rng: Optional[random.Random] = None) -> None:
        self._rng = rng or random.Random()
        self.blink_progress: float = 0.0
        self.is_blinking: bool = False
        self.blink_speed: float = 0.18
        self.next_blink: int = 140

    def trigger(self) -> None:
        if not self.is_blinking:
            self.is_blinking = True
            self.blink_progress = 0.0

    def step(self) -> float:
        if self.is_blinking:
            self.blink_progress += self.blink_speed
            if self.blink_progress >= 1.0:
                self.blink_progress = 1.0
                self.blink_speed = -0.22
            elif self.blink_progress <= 0.0:
                self.blink_progress = 0.0
                self.is_blinking = False
                self.blink_speed = 0.20

        self.next_blink -= 1
        if self.next_blink <= 0:
            self.trigger()
            self.next_blink = self._rng.randint(120, 260)
        return self.blink_progress


class EmotionEngine:
    """Reusable Emotion Engine combining parametric eye transitions, weighted selection, and posture."""

    def __init__(
        self,
        initial_mood: str = "NEUTRAL",
        transition_ms: float = 500.0,
        autonomous: bool = True,
        autonomous_interval_ticks: int = 600,
        chirp_player: Optional[ChirpPlayer] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        self._rng = rng or random.Random()
        self.chirp_player = chirp_player or NullChirpPlayer()
        self.state = EmotionState()
        self.blink = BlinkController(rng=self._rng)
        self.transition_ms = max(1.0, float(transition_ms))
        self.autonomous = autonomous
        self.autonomous_interval_ticks = max(1, int(autonomous_interval_ticks))
        self._autonomous_countdown = self.autonomous_interval_ticks

        canonical = resolve_mood(initial_mood)
        spec = EMOTIONS[canonical]
        self.current_mood: str = canonical
        self.origin_left: EyeConfig = spec.eye_left
        self.origin_right: EyeConfig = spec.right_eye
        self.target_left: EyeConfig = spec.eye_left
        self.target_right: EyeConfig = spec.right_eye
        self.current_left: EyeConfig = spec.eye_left
        self.current_right: EyeConfig = spec.right_eye
        self.transition_progress: float = 1.0

        self._custom_weights: Dict[str, float] = {}
        self.next_idle_action: int = 100

    @property
    def is_transitioning(self) -> bool:
        return self.transition_progress < 1.0

    @property
    def current_spec(self) -> EmotionSpec:
        return EMOTIONS[self.current_mood]

    def set_weight(self, emotion_name: str, weight: float) -> None:
        """Sets an explicit roulette weight override (>= 0) for a given emotion."""
        canonical = resolve_mood(emotion_name)
        if weight <= 0.0:
            self._custom_weights.pop(canonical, None)
        else:
            self._custom_weights[canonical] = float(weight)

    def compute_dynamic_weights(self) -> Dict[str, float]:
        """Computes roulette probabilities from Energy / Boredom / Bond and hardware context."""
        if self._custom_weights:
            return dict(self._custom_weights)

        st = self.state
        weights: Dict[str, float] = {
            "NEUTRAL": 1.0,
            "HAPPY": 0.4 + 0.8 * st.bond,
            "THINKING": 0.35 + 0.25 * (1.0 - st.boredom),
            "BORED": 0.05 + 1.4 * st.boredom,
            "UNIMPRESSED": 0.05 + 0.6 * st.boredom,
            "SLEEPY": 0.05 + 1.2 * (1.0 - st.energy),
            "PLEADING": 0.1 + 0.4 * st.boredom * st.bond,
            "SULKING": 0.02 + (0.6 if st.boredom > 0.75 and st.bond < 0.4 else 0.0),
            "GLEE": 0.15 + 0.5 * st.bond * st.energy,
        }
        if st.battery_pct <= 20.0 or st.thermal_hot:
            weights["WORRIED"] = 1.0
            weights["SLEEPY"] += 0.8
        if st.detached:
            weights["AWE"] = 0.6
            weights["SURPRISED"] = 0.4
        return {k: v for k, v in weights.items() if v > 0.0 and k in EMOTIONS}

    def select_weighted_emotion(self) -> str:
        """Selects an emotion via roulette-wheel sampling over current weights."""
        weights = self.compute_dynamic_weights()
        total = sum(weights.values())
        if total <= 0.0:
            return "NEUTRAL"
        pick = self._rng.uniform(0.0, total)
        acc = 0.0
        for name, w in weights.items():
            acc += w
            if pick <= acc:
                return name
        return "NEUTRAL"

    def set_emotion(
        self,
        mood_name: str,
        instant: bool = False,
        play_chirp: bool = False,
    ) -> EmotionSpec:
        """Transitions the eye geometry to mood_name (smooth 500 ms lerp unless instant=True)."""
        canonical = resolve_mood(mood_name)
        spec = EMOTIONS[canonical]
        self.current_mood = canonical
        self.target_left = spec.eye_left
        self.target_right = spec.right_eye

        if instant:
            self.origin_left = self.target_left
            self.origin_right = self.target_right
            self.current_left = self.target_left
            self.current_right = self.target_right
            self.transition_progress = 1.0
        else:
            self.origin_left = self.current_left
            self.origin_right = self.current_right
            self.transition_progress = 0.0
            self.blink.trigger()

        self._autonomous_countdown = self.autonomous_interval_ticks
        if play_chirp and spec.chirp is not None:
            self.chirp_player.play(spec.chirp)
        return spec

    def step_transition(self, dt_ms: float) -> float:
        """Advances active eye morph transition by dt_ms milliseconds."""
        if self.transition_progress < 1.0:
            self.transition_progress = min(1.0, self.transition_progress + dt_ms / self.transition_ms)
            self.current_left = self.origin_left.lerp(self.target_left, self.transition_progress)
            self.current_right = self.origin_right.lerp(self.target_right, self.transition_progress)
        return self.transition_progress

    def step_autonomous(self, dt_ms: float, is_idle: bool = True) -> Optional[str]:
        """Updates internal drives and triggers roulette emotion shifts when idle."""
        self.state.step_idle_decay(dt_ms / 1000.0)
        if not self.autonomous or not is_idle:
            return None
        self._autonomous_countdown -= 1
        if self._autonomous_countdown <= 0:
            self._autonomous_countdown = self.autonomous_interval_ticks
            chosen = self.select_weighted_emotion()
            if chosen != self.current_mood:
                self.set_emotion(chosen, instant=False, play_chirp=True)
                return chosen
        return None

    def compute_idle_pose(
        self,
        idle_timer: int,
        cur_yaw: float,
        cur_pitch: float,
        cur_gaze_x: float,
        cur_gaze_y: float,
    ) -> Tuple[float, float, float, float]:
        """Returns declarative (target_yaw, target_pitch, gaze_x, gaze_y) for current mood."""
        spec = self.current_spec
        behavior = spec.idle_behavior

        if behavior == "roam":
            self.next_idle_action -= 1
            if self.next_idle_action <= 0:
                choice = self._rng.random()
                if choice < 0.35:
                    gx, gy, ty, tp = 0.0, 0.0, 0.0, 0.0
                elif choice < 0.65:
                    gx = -0.75
                    gy = self._rng.uniform(-0.3, 0.3)
                    ty = self._rng.uniform(0.2, 0.5)
                    tp = gy * 0.2
                else:
                    gx = 0.75
                    gy = self._rng.uniform(-0.3, 0.3)
                    ty = self._rng.uniform(-0.5, -0.2)
                    tp = gy * 0.2
                self.next_idle_action = self._rng.randint(100, 240)
                return ty, tp, gx, gy
            return cur_yaw, cur_pitch, cur_gaze_x, cur_gaze_y

        if behavior in ("sway", "scan", "tremble"):
            ty = math.sin(idle_timer * spec.idle_yaw_freq) * spec.idle_yaw_amp
            tp = spec.idle_pitch if spec.idle_pitch is not None else cur_pitch
            gx = spec.idle_gaze_x if spec.idle_gaze_x is not None else cur_gaze_x
            gy = spec.idle_gaze_y if spec.idle_gaze_y is not None else cur_gaze_y
            return ty, tp, gx, gy

        if behavior == "bob":
            ty = math.sin(idle_timer * spec.idle_yaw_freq) * spec.idle_yaw_amp
            base_p = spec.idle_pitch if spec.idle_pitch is not None else 0.0
            tp = base_p + math.sin(idle_timer * 0.16) * 0.04
            gx = spec.idle_gaze_x if spec.idle_gaze_x is not None else cur_gaze_x
            gy = spec.idle_gaze_y if spec.idle_gaze_y is not None else cur_gaze_y
            return ty, tp, gx, gy

        if behavior == "droop":
            ty = 0.0
            tp = spec.idle_pitch if spec.idle_pitch is not None else 0.25
            gx = spec.idle_gaze_x if spec.idle_gaze_x is not None else cur_gaze_x
            gy = spec.idle_gaze_y if spec.idle_gaze_y is not None else cur_gaze_y
            return ty, tp, gx, gy

        return cur_yaw, cur_pitch, cur_gaze_x, cur_gaze_y

    # -----------------------------------------------------------------------
    # Unified stimulus handlers
    # -----------------------------------------------------------------------

    def handle_conversation_state(self, state_name: str, has_active_gesture: bool = False) -> Optional[EmotionReaction]:
        """Maps voice/assistant state transitions to mood, gaze, posture, and speech interrupt."""
        preset = CONVERSATION_STATE_PRESETS.get(str(state_name).upper())
        if preset is None:
            return None

        self.state.boredom = max(0.0, self.state.boredom - 0.15)
        self.state.clamp()

        mood = preset["mood"]
        if mood is not None:
            self.set_emotion(str(mood), instant=False, play_chirp=False)

        gesture = preset["gesture"] if not has_active_gesture else None
        return EmotionReaction(
            mood=str(mood) if mood is not None else None,
            gesture=str(gesture) if gesture is not None else None,
            target_yaw=preset["target_yaw"],  # type: ignore[arg-type]
            target_pitch=preset["target_pitch"],  # type: ignore[arg-type]
            gaze_x=preset["gaze_x"],  # type: ignore[arg-type]
            gaze_y=preset["gaze_y"],  # type: ignore[arg-type]
            interrupt_speech=bool(preset["interrupt"]),
        )

    def handle_touch(self, play_chirp: bool = True) -> EmotionReaction:
        """Handles crown head_touch rising edge: boosts bond, clears boredom, triggers HAPPY."""
        self.state.bond += 0.12
        self.state.boredom = max(0.0, self.state.boredom - 0.35)
        self.state.clamp()
        spec = self.set_emotion("HAPPY", instant=False, play_chirp=play_chirp)
        return EmotionReaction(
            mood=spec.name,
            gesture="wiggle",
            chirp=spec.chirp,
        )

    def handle_detach(self, detached: bool, play_chirp: bool = True) -> EmotionReaction:
        """Handles popped-off head state: triggers SURPRISED/AWE and sway chirp."""
        self.state.detached = bool(detached)
        if detached:
            spec = self.set_emotion("SURPRISED", instant=False, play_chirp=play_chirp)
            return EmotionReaction(mood=spec.name, chirp=spec.chirp)
        spec = self.set_emotion("HAPPY", instant=False, play_chirp=play_chirp)
        return EmotionReaction(mood=spec.name, gesture="nod", chirp=spec.chirp)

    def handle_shake(self, play_chirp: bool = True) -> EmotionReaction:
        """Handles shake/disturbance stimulus: DIZZY expression + trill chirp."""
        spec = self.set_emotion("DIZZY", instant=False, play_chirp=play_chirp)
        return EmotionReaction(mood=spec.name, gesture="dizzy_spin", chirp=spec.chirp)
