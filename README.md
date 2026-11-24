# 🤖 Gemma-Bot: Webots Desktop Companion Simulation

A complete Webots simulation of **Gemma-Bot**, an expressive desktop companion robot with built-in **AI Command Integration**.

![Webots](https://img.shields.io/badge/Webots-R2025a-blue.svg)
![Python](https://img.shields.io/badge/Python-3.x-green.svg)
![AI-Enabled](https://img.shields.io/badge/AI-Command--Integrated-brightgreen.svg)
![License](https://img.shields.io/badge/License-MIT-orange.svg)

<div align="center">
  <img src="docs/assets/gemma_bot_webots.jpg" alt="Gemma-Bot in Webots Simulation" width="650"/>
  <p><em>Gemma-Bot desktop companion robot rendered inside Cyberbotics Webots with high-contrast OLED display.</em></p>
</div>

---

## ✨ Features

- **AI Command Integration (`ai_assistant.py`)**: Send natural language commands (or structured JSON) directly from your terminal or an LLM/Gemini to control gestures, moods, gaze, and speech in real-time.
- **Audible Talk-Back & Lip-Sync**: Gemma-Bot speaks out loud with native voice synthesis and synchronizes an animated talking mouth on its OLED display with conversational micro-nodding.
- **Whisper-Quiet Servos**: Motor whining sounds are completely muted via `sound ""` configuration for clean, silent motion.
- **Gemma-Talk Voice Assistant Bridge (`gemma_talk_bridge.py`)**: Seamlessly connects to your local `gemma-talk` voice assistant (Silero VAD, faster-whisper, Ollama gemma, Kokoro-82M TTS) so Gemma-Bot acts as the physical companion embodiment for your voice conversations!
- **High-Contrast OLED Screen & Selectable Color Themes**: 128×64 pixel display with true OLED blacks (no white blowout) and 6 switchable color themes (Electric Cyan, Matrix Emerald, Retro Amber, Neon Blue, Cyberpunk Violet, High Contrast White).
- **Physical Gesture Engine**: 18 lifelike multi-phase trajectory gestures (`nod`, `shake`, `wiggle`, `curious`, `tilt_left`, `tilt_right`, `perk_up`, `droop`, `bounce`, `groove`, `shiver`, `scan`, `confused`, `bow`, `cheer`, `yawn`, `shy`, `peek_a_boo`, `dizzy_spin`).
- **Embedded HTTP Command Server**: The Webots controller runs an HTTP REST endpoint on `http://127.0.0.1:8765/command` to accept commands from any external AI agent, script, or web app.
- **Autonomous Idle Life**: Automatically glances around the room, blinks naturally, and exhibits organic micro-movements when idle.

---

## 🎭 Expressive OLED Expressions Suite

Gemma-Bot features 15 distinct animated companion moods and emoji expressions rendered on its 128×64 OLED visor:

<div align="center">
  <img src="docs/assets/expressions_grid.png" alt="Gemma-Bot OLED Expressions Suite" width="950"/>
</div>

---

## 🎨 Selectable Screen Color Themes

You can customize the robot's screen colors at runtime. Press **`X`** in the Webots window, use natural language in the CLI, or send a JSON command:

<div align="center">
  <img src="docs/assets/color_themes.png" alt="Gemma-Bot Screen Color Themes" width="750"/>
</div>

| Theme | Accent Color | Description | Quick CLI Command |
| :--- | :---: | :--- | :--- |
| **Electric Cyan** | `#00F0FF` | Default vibrant neon OLED cyan | `python3 ai_assistant.py "cyan screen"` |
| **Matrix Emerald** | `#00FF66` | Retro phosphor green terminal | `python3 ai_assistant.py "green screen"` |
| **Retro Amber** | `#FFAA00` | Warm golden amber CRT glow | `python3 ai_assistant.py "amber screen"` |
| **Neon Blue** | `#2979FF` | Deep electric sapphire blue | `python3 ai_assistant.py "blue screen"` |
| **Cyberpunk Violet** | `#D500F9` | Vivid futuristic magenta/purple | `python3 ai_assistant.py "purple screen"` |
| **High Contrast White** | `#FFFFFF` | Crisp classic monochrome OLED | `python3 ai_assistant.py "white screen"` |

---

## 🚀 Quick Start (1-Command All-In-One)

To launch **everything** (Ollama, Webots simulation in real-time mode, Gemma-Talk voice backend, physical gesture bridge, and web audio UI) with one command:

```bash
cd /Users/saiganeshtanneru/Documents/GitHub/robots/gemma-bot
./start_all.sh
```
*(Or from `gemma-talk`, run `./start-with-bot.sh`).*

When running, just speak naturally into your microphone! Press **Ctrl+C** anytime to cleanly stop all services.

---

## 🛠️ Individual Manual Controls

### 1. Launch in Webots Manually
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
python3 ai_assistant.py "green screen"
python3 ai_assistant.py "curious"
python3 ai_assistant.py "perk up"
python3 ai_assistant.py "tell me a joke"
python3 ai_assistant.py "go to sleep"
python3 ai_assistant.py "I love you"

# Interactive AI conversation shell:
python3 ai_assistant.py -i

# Check live robot telemetry:
python3 ai_assistant.py --status
```

---

## 🎙️ Reusing with Gemma-Talk (Voice Assistant Companion)

Gemma-Bot integrates directly with **Gemma-Talk** (`/Users/saiganeshtanneru/Documents/gemma-talk`), transforming your local voice assistant into an expressive physical desktop buddy:

```mermaid
flowchart LR
    User[Voice Input / Mic] --> VAD[Silero VAD]
    VAD --> STT[faster-whisper]
    STT --> LLM[Ollama / Gemma]
    LLM --> TTS[Kokoro-82M TTS]
    LLM -. State & Tokens .-> Bridge[gemma_talk_bridge]
    Bridge --> REST[Robot REST API :8765]
    REST --> Webots[Gemma-Bot Webots Simulation]
    Webots --> OLED[128x64 OLED Display]
    Webots --> Servos[Pan/Tilt Servos]
```

1. **Start Gemma-Talk Backend Server**:
   ```bash
   cd /Users/saiganeshtanneru/Documents/gemma-talk
   ./start-server.sh
   ```
2. **Start the Bridge in Gemma-Bot**:
   ```bash
   cd /Users/saiganeshtanneru/Documents/GitHub/robots/gemma-bot
   python3 gemma_talk_bridge.py
   ```
3. **Open Gemma-Talk in your browser** (`http://localhost:5173`).
   - When you speak, Gemma-Bot enters **LISTENING** mode (head perks up, eyes focus).
   - When Ollama generates the response, Gemma-Bot enters **THINKING** mode (curious head tilt, eyes look up with thinking dots).
   - When Kokoro synthesizes speech, Gemma-Bot enters **SPEAKING** mode (animated lip-sync, happy smile, conversational nodding).
   - When you interrupt (barge-in), Gemma-Bot instantly silences speech, halts its mouth, and blinks attentively!

---

## 🌐 AI API Specification (`POST http://127.0.0.1:8765/command`)

You can also send JSON commands directly using `curl` or any language:

```bash
curl -X POST http://127.0.0.1:8765/command \
     -H "Content-Type: application/json" \
     -d '{
       "mood": "HAPPY",
       "gesture": "nod",
       "screen_color": "AMBER",
       "gaze": "left",
       "speech": "I am Gemma-Bot!"
     }'
```

### Supported JSON Parameters:
| Parameter | Type | Options / Values |
| :--- | :--- | :--- |
| `mood` | string / emoji | `"NEUTRAL"`, `"HAPPY"`, `"COOL"`, `"STAR_EYES"`, `"PLEADING"`, `"CRYING"`, `"WINK"`, `"TONGUE"`, `"LOVE"`, `"DIZZY"`, `"SMIRK"`, `"SURPRISED"`, `"SLEEPY"`, `"ANGRY"`, `"THINKING"` (or raw emojis: `😎`, `🤩`, `🥺`, `😭`, `😉`, `😋`, `😍`, `😵`, `😏`, `😀`, `😮`, `😴`, `😡`, `🤔`) |
| `gesture` | string | `"nod"`, `"shake"`, `"wiggle"`, `"curious"`, `"tilt_left"`, `"tilt_right"`, `"perk_up"`, `"droop"`, `"bounce"`, `"groove"`, `"shiver"`, `"scan"`, `"confused"`, `"bow"`, `"cheer"`, `"yawn"`, `"shy"`, `"peek_a_boo"`, `"dizzy_spin"` |
| `screen_color` | string | `"CYAN"`, `"GREEN"`, `"AMBER"`, `"BLUE"`, `"PURPLE"`, `"WHITE"` |
| `gaze` | string | `"left"`, `"right"`, `"up"`, `"down"`, `"center"` |
| `look_at` | array `[yaw, pitch]` | e.g. `[0.4, -0.2]` (custom servo angles) |
| `speech` | string | Spoken dialogue printed to console, spoken out loud, & animated on OLED display |

---

## 🎮 Manual Keyboard Controls

Click into the 3D Webots viewport and use your keyboard:

### Face Emojis & Display:
| Key | Emoji / Mood | Expression |
| :---: | :--- | :--- |
| `1` | **Neutral 😐** | Natural random blinks and organic idle gaze |
| `2` | **Happy 😀** | Squinting smiling eyes (`^_^`) and bright smile |
| `3` | **Surprised 😮** | Wide round eyes and 'O' mouth |
| `4` | **Sleepy 😴** | Drooping eyelids, resting slump, floating Zzz |
| `5` | **Angry 😡** | Inward slanted aggressive brows |
| `6` | **Thinking 🤔** | Looking up-right with cycling thinking dots |
| `7` | **Love 😍** | Glowing pixel heart eyes and pink companion smile |
| `8` | **Cool 😎** | Pixelated sunglasses with white gloss reflection streaks and smirk |
| `9` | **Star Eyes 🤩** | Twinkling 4-point yellow star eyes with shiny centers |
| `0` | **Pleading 🥺** | Giant sparkly anime puppy eyes with specular highlights |
| `W` | **Wink 😉** | One open rounded eye, one winking smile arc |
| `C` | **Crying 😭** | Sad drooping eyes with animated flowing blue teardrops |
| `T` | **Tongue 😋** | Squinting happy eyes with cute pink tongue |
| `D` | **Dizzy 😵** | Cross `X_X` eyes and wavy mouth |
| `S` | **Smirk 😏** | Asymmetric eyebrow, sly side glance and smirk |
| `X` | **Cycle Screen Color** | Cycle themes: Cyan → Green → Amber → Blue → Purple → White |

### Physical Head Gestures:
| Key | Gesture | Motion Description |
| :---: | :--- | :--- |
| `N` | **Nod** | Smooth double nodding agreement up & down |
| `H` | **Shake** | Head shaking left & right (disagreement) |
| `B` | **Bounce** | Fast vertical energetic bobbing |
| `G` | **Groove / Dance** | Smooth figure-8 head groove |
| `V` | **Shiver / Tremble** | High-frequency micro-jitter (cold or nervous) |
| `R` | **Scan / Search** | Sweeping panoramic room scan with wide gaze |
| `P` | **Perk Up** | Sudden attentive upward head rise |
| `Y` | **Yawn** | Stretching upward tilt then relaxing slump |
| `O` | **Bow** | Polite formal bow forward |
| `U` | **Confused** | Puzzled alternating tilt left and right |
| `Z` | **Dizzy Spin** | Smooth orbital circular head roll |
| `J` | **Cheer** | Head tossed back in joy with happy shakes |
| `K` | **Shy** | Head turns away and tucks down |
| `Q` | **Peek-a-Boo** | Dips head with closed eyes, then pops up! |
| `[` | **Tilt Left** | Sustained curious head tilt left |
| `]` | **Tilt Right** | Sustained curious head tilt right |
| `SPACE` | **Pet / Wiggle** | Joyful companion shimmy |
| `←` / `→` | **Pan Head** | Manual servo pan left/right |
| `↑` / `↓` | **Tilt Head** | Manual servo tilt up/down |
