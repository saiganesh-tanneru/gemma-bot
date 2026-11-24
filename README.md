# 🤖 Jamiryo Webots Simulation

A Webots simulation of the **Jamiryo** desktop companion robot, featuring:
- **Expressive OLED Eyes:** Rendered on a 128x64 display with blinking, pupil gaze, and multiple emotional states.
- **Dual-Axis Movable Head:** Servo-driven Pan (Yaw) and Tilt (Pitch) head movement.
- **Interactive Companion Behaviors:** Responds to touch/key events and exhibits natural idle glance/blink behaviors.
- **Integrated Camera & Touch Sensor:** Full virtual sensor pipeline matching the physical hardware.

---

## 🚀 How to Run in Webots

1. Open **Webots**.
2. Go to **File → Open World...**.
3. Select `worlds/jamiryo.wbt`.
4. Press the **Play (▶)** button on the top toolbar.

---

## 🎮 Interactive Controls

Click into the 3D Webots viewport and use your keyboard:

| Key | Action | Behavior |
| :--- | :--- | :--- |
| `1` | **Neutral** | Natural blinking and organic idle gaze wandering |
| `2` or `SPACE` | **Happy / Pet** | Squinting smiling eyes + joyful head wiggle |
| `3` | **Surprised** | Large wide eyes + head perks up |
| `4` | **Sleepy** | Drooping eyelids, head droop forward, breathing Zzz |
| `5` | **Angry** | Slanted brow eyes |
| `←` / `→` | **Turn Head** | Manually pan the servo head left/right |
| `↑` / `↓` | **Tilt Head** | Manually tilt the servo head up/down |
