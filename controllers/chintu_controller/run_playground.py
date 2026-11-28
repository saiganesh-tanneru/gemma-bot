"""Standalone Chintu by Sarworks Face Playground runner (no Webots required)."""

import argparse
from pathlib import Path
import sys
import time
from typing import Optional

_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from controllers.chintu_controller.audio_cues import (
    AudioCuePlayer,
    NullAudioCuePlayer,
    create_audio_cue_player,
)
from controllers.chintu_controller.hardware import ChargingSensor, DockDetector, ServoRig
from controllers.chintu_controller.runtime_helpers import (
    process_chintu_command_queue,
    sync_chintu_status,
)
from controllers.chintu_controller.server import start_chintu_server
from controllers.chintu_controller.wake_engine import ChintuStateMachine


class StandalonePlaygroundRuntime:
    """Runs Chintu's wake state machine, servos model, audio cues, and HTTP playground without Webots."""

    def __init__(
        self,
        port: int = 8765,
        host: str = "127.0.0.1",
        cold_startup: bool = True,
        start_server: bool = True,
        audio_player: Optional[AudioCuePlayer] = None,
        dt_s: float = 0.02,
    ) -> None:
        self.dt_s = float(dt_s)
        self.charging_sensor = ChargingSensor()
        self.dock_detector = DockDetector()
        self.servo_rig = ServoRig(dock_detector=self.dock_detector)
        self.audio_player = audio_player or create_audio_cue_player()
        self._face_pan_override: Optional[float] = None

        self.machine = self._make_machine(cold_startup=cold_startup)
        self.server = start_chintu_server(port=port, host=host) if start_server else None
        self._sync_status(self.machine._build_face_frame(0.0))

    def _make_machine(self, cold_startup: bool = True) -> ChintuStateMachine:
        return ChintuStateMachine(
            audio_player=self.audio_player,
            charging_sensor=self.charging_sensor,
            dock_detector=self.dock_detector,
            servo_rig=self.servo_rig,
            face_target_provider=self._detect_face_pan,
            cold_startup=cold_startup,
        )

    def _detect_face_pan(self) -> Optional[float]:
        return self._face_pan_override

    def _set_face_pan_override(self, pan: float) -> None:
        self._face_pan_override = pan

    def process_commands(self) -> None:
        self.machine = process_chintu_command_queue(
            machine=self.machine,
            charging_sensor=self.charging_sensor,
            dock_detector=self.dock_detector,
            on_cold_startup=lambda: self._make_machine(cold_startup=True),
            on_face_pan_override=self._set_face_pan_override,
        )

    def _sync_status(self, frame) -> None:
        sync_chintu_status(
            machine=self.machine,
            servo_rig=self.servo_rig,
            charging_sensor=self.charging_sensor,
            dock_detector=self.dock_detector,
            audio_player=self.audio_player,
            frame=frame,
        )

    def step_once(self) -> None:
        self.process_commands()
        frame = self.machine.step(self.dt_s)
        self._sync_status(frame)

    def run_forever(self) -> None:
        if self.server is not None:
            addr = self.server.server_address
            print(f"Chintu Face Playground running (no Webots): http://{addr[0]}:{addr[1]}/playground")
        next_tick = time.monotonic()
        try:
            while True:
                self.step_once()
                next_tick += self.dt_s
                sleep_s = next_tick - time.monotonic()
                if sleep_s > 0:
                    time.sleep(sleep_s)
                else:
                    next_tick = time.monotonic()
        except KeyboardInterrupt:
            pass
        finally:
            self.audio_player.close()
            if self.server is not None:
                self.server.shutdown()
                self.server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Chintu Face Playground standalone (without Webots).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-cold-startup", action="store_true", help="Start asleep instead of auto-waking.")
    parser.add_argument("--browser-audio-only", action="store_true", help="Mute host afplay and play audio in browser.")
    args = parser.parse_args()

    audio = NullAudioCuePlayer() if args.browser_audio_only else None
    rt = StandalonePlaygroundRuntime(
        port=args.port,
        host=args.host,
        cold_startup=not args.no_cold_startup,
        audio_player=audio,
    )
    rt.run_forever()


if __name__ == "__main__":
    main()
