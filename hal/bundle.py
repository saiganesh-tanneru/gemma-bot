"""The bundle the controller holds. One of each device."""

from __future__ import annotations

from dataclasses import dataclass

from hal.interfaces import (
    AudioIn,
    AudioOut,
    Camera,
    Clock,
    ConfigStore,
    Display,
    HeadServos,
    Leds,
    Network,
    Power,
    Thermal,
    Touch,
)
from hal.types import THROTTLE_NORMAL


@dataclass
class Hardware:
    """Every device a Phase 1 feature is allowed to touch.

    Pose and mood stay on the controller. This object is only the hardware.
    """

    head: HeadServos
    display: Display
    audio_out: AudioOut
    audio_in: AudioIn
    touch: Touch
    leds: Leds
    power: Power
    thermal: Thermal
    network: Network
    clock: Clock
    storage: ConfigStore
    camera: Camera

    def snapshot(self) -> dict:
        """Plain dict of capability flags and live readings. Safe to log. No I/O beyond the drivers."""
        power = self.power.state()
        thermal = self.thermal.state()
        network = self.network.state()
        clock = self.clock.now()
        mic = self.audio_in.state()
        head = self.head.capabilities()
        panel = self.display.capabilities()
        leds = self.leds.capabilities()
        return {
            "supports_roll": head.supports_roll,
            "display_kind": panel.kind,
            "display_color": panel.color,
            "display_width": panel.width,
            "display_height": panel.height,
            "mic_hardware_mute": mic.hardware_mute,
            "mic_present": mic.device_present,
            "online": network.online,
            "network_monitored": network.monitored,
            "power_source": power.source,
            "usb_connected": power.usb_connected,
            "docked": power.docked,
            "charging": power.charging,
            "voltage_dip": power.voltage_dip,
            "battery_percent": power.battery_percent,
            "voltage_v": power.voltage_v,
            "power_telemetry": power.telemetry_present,
            "temperature_c": thermal.celsius,
            "throttle": thermal.throttle if thermal.sensor_present else THROTTLE_NORMAL,
            "thermal_sensor": thermal.sensor_present,
            "clock_valid": clock.valid,
            "clock_source": clock.source,
            "led_present": leds.present,
        }
