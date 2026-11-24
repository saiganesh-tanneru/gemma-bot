# 🤖 Gemma-Bot: Webots Desktop Companion Simulation

A complete Webots simulation of **Gemma-Bot**, an expressive desktop companion robot with built-in **AI Command Integration**.

![Webots](https://img.shields.io/badge/Webots-R2025a-blue.svg)
![Python](https://img.shields.io/badge/Python-3.x-green.svg)
![AI-Enabled](https://img.shields.io/badge/AI-Command--Integrated-brightgreen.svg)
![License](https://img.shields.io/badge/License-MIT-orange.svg)

---

## ✨ Features

- **AI Command Integration (`ai_assistant.py`)**: Send natural language commands (or structured JSON) directly from your terminal or an LLM/Gemini to control gestures, moods, gaze, and speech in real-time.
- **Expressive OLED Eyes**: Animated in real-time on a 128×64 pixel display with natural blinks, saccades, and multiple emotional states (`HAPPY`, `SURPRISED`, `SLEEPY`, `ANGRY`, `THINKING`, `LOVE`, `NEUTRAL`).
- **Physical Gesture Engine**:
  - `nod`: Double nodding agreement up and down.
  - `shake`: Shaking head left and right (disagreement).
  - `wiggle`: Happy companion shimmy.
  - `curious` / `tilt`: Inquisitive head tilt.
  - `perk_up`: Sudden attentive head rise.
  - `droop`: Sleepy or sad bow.
- **Embedded HTTP Command Server**: The Webots controller runs an HTTP REST endpoint on `http://127.0.0.1:8765/command` to accept commands from any external AI agent, script, or web app.
- **Autonomous Idle Life**: Automatically glances around the room and blinks naturally when idle.

---

## 🚀 How to Run

### 1. Launch in Webots
1. Open **Webots** (`/Applications/Webots.app`).
2. Go to **File → Open World...** and select `worlds/gemma_bot.wbt`.
3. Press the **Play (▶)** button on the top toolbar.

### 2. Send AI Commands (via Terminal)

In a terminal, run:

```bash
cd /Users/saiganeshtanneru/Documents/GitHub/robots/gemma-bot

# Quick single natural language commands:
python3 ai_assistant.py "nod yes and smile"
python3 ai_assistant.py "look left and act surprised"
python3 ai_assistant.py "shake your head no"
python3 ai_assistant.py "tell me a joke"
python3 ai_assistant.py "go to sleep"
python3 ai_assistant.py "I love you"

# Interactive AI conversation shell:
python3 ai_assistant.py -i

# Check live robot telemetry:
python3 ai_assistant.py --status
```

---

## 🌐 AI API Specification (`POST http://127.0.0.1:8765/command`)

You can also send JSON commands directly using `curl` or any language:

```bash
curl -X POST http://127.0.0.1:8765/command \
     -H "Content-Type: application/json" \
     -d '{
       "mood": "HAPPY",
       "gesture": "nod",
       "gaze": "left",
       "speech": "I am Gemma-Bot!"
     }'
```

### Supported JSON Parameters:
| Parameter | Type | Options / Values |
| :--- | :--- | :--- |
| `mood` | string | `"NEUTRAL"`, `"HAPPY"`, `"SURPRISED"`, `"SLEEPY"`, `"ANGRY"`, `"THINKING"`, `"LOVE"` |
| `gesture` | string | `"nod"`, `"shake"`, `"wiggle"`, `"curious"`, `"perk_up"`, `"droop"` |
| `gaze` | string | `"left"`, `"right"`, `"up"`, `"down"`, `"center"` |
| `look_at` | array `[yaw, pitch]` | e.g. `[0.4, -0.2]` (custom servo angles) |
| `speech` | string | Spoken dialogue printed to console & animated on OLED display |

---

## 🎮 Manual Keyboard Controls

Click into the 3D Webots viewport and use your keyboard:

| Key | Mode / Action | Behavior |
| :--- | :--- | :--- |
| `1` | **Neutral** | Natural random blinks and organic idle gaze |
| `2` or `SPACE` | **Happy / Pet** | Squinting smiling eyes (`^_^`) and joyful head wiggle |
| `3` | **Surprised** | Wide round eyes and head perks straight up |
| `4` | **Sleepy** | Drooping eyelids, head droops forward, breathing Zzz |
| `5` | **Angry** | Slanted expressive brows |
| `6` | **Thinking** | Looking up-right with animated thinking dots |
| `←` / `→` | **Pan Head** | Manually steer servo head left or right |
| `↑` / `↓` | **Tilt Head** | Manually tilt servo head up or down |
