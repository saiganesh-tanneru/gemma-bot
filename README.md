# 🤖 Gemma-Bot: Webots Desktop Companion Simulation

A complete Webots simulation of **Gemma-Bot**, an expressive desktop companion robot.

![Webots](https://img.shields.io/badge/Webots-R2025a-blue.svg)
![Python](https://img.shields.io/badge/Python-3.x-green.svg)
![License](https://img.shields.io/badge/License-MIT-orange.svg)

---

## ✨ Features

- **Expressive OLED Eyes**: Animated in real-time on a 128×64 pixel display with natural blinks, saccades, and multiple emotional states (Happy, Surprised, Sleepy, Angry, Neutral).
- **Dual-Axis Servo Neck**:
  - **Pan / Yaw**: Smooth horizontal rotation (`head_yaw`).
  - **Tilt / Pitch**: Smooth vertical nodding (`head_pitch`).
- **Autonomous Idle Life**: Automatically glances around the room and blinks naturally when idle.
- **Interactive Sensors**: Virtual forehead camera and capacitive touch sensor for head-pat interactions.
- **Physical Desktop Base**: Grounded, upright stationary desk enclosure that stays stable during all head movements.

---

## 🚀 How to Run in Webots

1. Open **Webots** (`/Applications/Webots.app`).
2. Go to **File → Open World...**.
3. Select `worlds/gemma_bot.wbt`.
4. Press the **Play (▶)** button on the top toolbar to start the simulation.

---

## 🎮 Interactive Controls

Click into the 3D Webots viewport and use your keyboard:

| Key | Mode / Action | Behavior |
| :--- | :--- | :--- |
| `1` | **Neutral** | Natural random blinks and organic idle gaze |
| `2` or `SPACE` | **Happy / Pet** | Squinting smiling eyes (`^_^`) and joyful head wiggle |
| `3` | **Surprised** | Wide round eyes and head perks straight up |
| `4` | **Sleepy** | Drooping eyelids, head droops forward, breathing Zzz |
| `5` | **Angry** | Slanted expressive brows |
| `←` / `→` | **Pan Head** | Manually steer servo head left or right |
| `↑` / `↓` | **Tilt Head** | Manually tilt servo head up or down |

---

## 📂 Project Structure

```
gemma-bot/
├── controllers/
│   └── gemma_bot_controller/
│       └── gemma_bot_controller.py   # Real-time OLED & servo controller
├── worlds/
│   └── gemma_bot.wbt                 # Webots 3D simulation world
└── README.md                         # Project documentation
```
