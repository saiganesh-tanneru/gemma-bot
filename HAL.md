# Hardware abstraction layer

The controller talks to devices through `hal`. Features and tests can run on the in-memory mocks, with no Webots process and no network. The Webots adapters keep the current sim behavior.

Nothing in this package opens a socket or calls a cloud API. Speech synthesis stays in `controllers/gemma_bot_controller/tts.py`. The HAL speaker only plays WAV clips.

## Layout

| Path | Role |
| --- | --- |
| `hal/interfaces.py` | The device interfaces a driver implements |
| `hal/types.py` | Capability flags, limits, and state values |
| `hal/mock.py` | In-memory devices and `build_mock_hardware()` |
| `hal/webots.py` | Webots adapters and `build_webots_hardware()` |
| `hal/storage.py` | JSON config: RAM, and an atomic file |
| `hal/face_target.py` | Adapts a `Display` to the existing face renderer |
| `hal/bundle.py` | `Hardware`, the bundle the controller holds |

`GemmaBotCompanion` builds a Webots bundle itself. Pass `hardware=` to use a mock or a board driver.

```python
from hal import build_mock_hardware
from gemma_bot_controller import GemmaBotCompanion

bot = GemmaBotCompanion(start_server=False, hardware=build_mock_hardware())
```

## Devices

| Interface | What callers use | Webots adapter | Mock |
| --- | --- | --- | --- |
| `HeadServos` | `set_position`, `set_velocity`, feedback | `head_yaw` / `head_pitch` and the position sensors. `supports_roll` is false | RAM. `supports_roll=True` adds roll |
| `Display` | pen, rectangle, text | `oled_display`, color 128×64, colors passed through | Mono 128×64 by default (pen becomes black or white). `display_kind="color_panel"` keeps RGB |
| `AudioOut` | `play_wav`, volume, `stop` | No speaker in the world. Plays on the host with the same player order as `tts.py`. Volume 0 does not start a player | Records clips. Volume 0 does not count as playing |
| `AudioIn` | `state().hardware_mute`, `read` | No mic. `device_present` is false, so reads are empty. Mute can be injected | PCM s16le. Mute drops queued samples |
| `Touch` | `is_pressed` (raw value strictly above 0.5) | `head_touch` | `set_pressed` / `set_value` |
| `Leds` | `status`, `mic`, `offline`, `celebration` | No LED node. `present` is false. Writes are remembered so callers do not crash | `present` is true |
| `Power` | battery, USB, dock, `voltage_dip` | USB is assumed because the process is running. `telemetry_present` is false: nothing was measured | Battery at 100%. `set_voltage` sets the dip flag |
| `Thermal` | celsius and throttle | No sensor. Throttle stays `normal` and the controller does not slow the head | 28°C. `set_celsius` updates throttle |
| `Network` | `online` | `online` true, `monitored` false. The link is not checked | `monitored` true. `set_online` |
| `Clock` | `now().valid`, `monotonic` | Host wall clock, source `host`. `set_time` is refused so the sim cannot change the OS clock | `advance` moves the monotonic clock only. `set_invalid` clears the wall time |
| `ConfigStore` | `set` / `commit` / `rollback` | `data/robot-config.json`, created on the first commit. Rename is atomic | RAM only |
| `Camera` | `enable` | Enables the sim camera. `frame()` does not call `getImage` | `push_frame` for tests. The controller does not read frames |

The controller still owns mood, gestures, and the keyboard. Raw `display`, `touch`, and motor attributes stay on the controller so the existing Webots stubs keep working. Commands go through `bot.hardware`.

## Capability flags

- **Roll.** `HeadCapabilities.supports_roll`. False on this sim (yaw ±1.4 rad, pitch ±0.45 rad, from `worlds/gemma_bot.wbt`). The keyboard and `look_at` clamps (±1.2 / ±0.4) stay in the controller. A driver clamps to its own mechanical stops and raises `UnsupportedAxisError` for a missing axis.
- **Panel.** `DisplayCapabilities.color` and `kind`. `mono_128x64` quantizes with integer Rec. 601 weights; luma at or above 128 is white. `color_panel` is what the Webots display is.
- **Mic mute.** `MicState.hardware_mute` is the physical switch. `inject_hardware_mute` exists only on the sim and the mock. A board driver samples the GPIO inside `state()` and leaves the injector unimplemented.
- **Power.** `voltage_dip` is true when a measured rail is strictly under 4.6 V. `telemetry_present` is false when the driver did not measure anything. Dock is `docked` and `charging` on `PowerState` (no wireless-charging flag).
- **Thermal.** `throttle_for_celsius`: under 34°C `normal`, from 34°C `reduced`, from 38°C `limited`. With no sensor the state is `normal` and `sensor_present` is false. The controller multiplies head speed by 1.0 / 0.7 / 0.4 only when a sensor is present, so the sim's motion does not change.
- **Network.** `monitored` is false when this process did not check a link. Do not ping the internet to fill this in.
- **Clock.** If `valid` is false, `wall_time` is None. Do not show a time in that case. Timers use `monotonic()`, not the wall clock.

`Hardware.snapshot()` is the plain dict the controller copies into `hardware_status` each tick.

## Add a board driver

1. Add a module under `hal/` (for example `hal/board.py`). Implement the interfaces in `hal/interfaces.py`. Do not import Webots, and do not open a socket from a read method.
2. Set the capability flags from the board: roll only if that joint exists, `color` false for a 128×64 mono OLED, `device_present` false when a part is not stuffed.
3. Map `HeadServos` onto the PWM or serial bus. Clamp with `clamp_to_limits`. Return `None` from `feedback_position` when the sensor has no reading.
4. Map `Display` draw calls onto the panel. Call `mono_color` first when the panel is 1-bit.
5. `AudioOut.play_wav` writes the speaker. `AudioIn.read` returns s16le mono and returns empty while the mute switch is closed. Do not upload audio.
6. `Power.state` comes from the fuel gauge, VBUS, and the dock pin. `Thermal.state` comes from the temperature sensor; `throttle_for_celsius` is the default curve.
7. `Network.state` comes from the OS link state. `Clock` reads the RTC. If the oscillator was stopped or the coin cell is dead, return `valid=False` and `wall_time=None`. Implement `set_time` for the RTC only. Do not set the computer's clock.
8. Persist config with `FileConfigStore` or an EEPROM writer that commits by replace-or-equivalent, so a power cut keeps the previous values. `get` must not hand back a live internal dict.
9. Build a `Hardware` and pass it to `GemmaBotCompanion(hardware=...)`.
10. Run `pytest tests/test_hal.py`. Point the same cases at the new driver where the lab has hardware, and keep the mocks for everything else.

Sim-only setters (`set_online`, `set_celsius`, `inject_hardware_mute`, `set_voltage`) are for tests. A board class does not need them.
