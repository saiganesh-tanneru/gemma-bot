# GemaBot review-plan demo

Stationary desk companion updated to the **fitted 4-part CAD** (`cad/build_chintu_cad.py`): `146.0 mm` tall, `Ø86 mm` tapered base (`50 mm` tall), `Ø32 mm` gimbal ball socket (center at `z = 72.5 mm`), `68×58×46 mm` seamless head (`7 mm` fillet), `47.2×39.2 mm` (`2.06"` `502×410` landscape) AMOLED face, `50×30 mm` top solar crown bumper (`head_touch`), burnt-orange side ear rings, copper base light ring, and shoulder button, sitting directly on the desk. The head still pans (`±80°`) and tilts (`±26°` around the ball center). There are no wheels or legs.

This world reuses `controllers/gemma_bot_controller` (including the Emotion Engine and Sarvam voice pipeline). `worlds/gemma_bot.wbt` is not modified.

Open **`worlds/gemabot_review_plan.wbt`** in Webots R2025a.

## What you should see

- Charcoal seamless head (`68×58×46 mm`) and tapered base (`Ø86 mm`), burnt-orange side ear rings, copper base light ring, orange shoulder button, `50×30 mm` solar crown (`head_touch`), and a **CHINTU** mark on the base.
- The face is the live 128×64 OLED: soft light-blue rounded eyes (`#8EC9DB`), a white highlight, and a small smile. A larger `protos/textures/face_screen.png` is the panel's starting texture.
- The dock clock reads **10:42** (`protos/textures/clock_1042.png`).
- A desk, laptop, cup, and plant. The camera looks at the robot from the front of the desk.

Keyboard and touch match the existing controller: `1`–`6` moods, arrow keys pan/tilt, space pets the head. The crown touch sensor is `head_touch`.

## Run it locally

From a clone of this repo:

```bash
git fetch origin demo/review-plan-world
git checkout demo/review-plan-world

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Prerequisites:

- **Webots R2025a** (the world header is `#VRML_SIM R2025a utf8`).
- Python 3. On Linux, Webots starts controllers with `python3` if that is the `python` on `PATH`, or set Webots → Preferences → General → Python command to `python3`.
- For the voice path only: `pip install -r requirements-voice.txt` and `cd voice_client && npm install`.

Sarvam uses the same environment variable this branch already reads. Do not put the key in git.

```bash
export SARVAM_API_KEY="your-key"
```

Optional: `cp .env.example .env` and set `SARVAM_API_KEY` there. `config.py` loads `.env` without overriding variables that are already set.

### Open the world

1. Launch Webots R2025a.
2. **File → Open World…** and choose `worlds/gemabot_review_plan.wbt`.
3. Press **Play**.

The controller binds the existing command server on `http://127.0.0.1:8765` (`GEMMA_BOT_HOST` / `GEMMA_BOT_PORT`). In the console you should see `🤖 Gemma-Bot Desktop Companion Initialized with AI Integration!`.

On Linux the Webots binary is often `/usr/local/webots/webots`. The Mac default in `config.py` is `/Applications/Webots.app/Contents/MacOS/webots`. Point `WEBOTS_APP` at whichever one you have before using the launcher below.

### Voice path (unchanged Sarvam calls)

`start_all.sh` still launches `worlds/gemma_bot.wbt` unless you override `GEMMA_WORLD_PATH`:

```bash
export SARVAM_API_KEY="your-key"
export WEBOTS_APP="/usr/local/webots/webots"   # or the Mac .app binary
export GEMMA_WORLD_PATH="$PWD/worlds/gemabot_review_plan.wbt"
./start_all.sh
```

To start the pieces yourself, with Webots already playing this world:

```bash
python3 -m uvicorn voice_server.main:app --host 0.0.0.0 --port 8000
python3 gemma_talk_bridge.py
cd voice_client && npm run dev
```

The web UI is `http://localhost:5173`. Nothing in `voice_server/`, `intent_parser.py`, or `controllers/gemma_bot_controller/tts.py` was changed for this world: same Sarvam models and endpoints (`saaras:v4`, `sarvam-105b`, `bulbul:v3`, `https://api.sarvam.ai/...`).

Send a gesture without voice:

```bash
python3 ai_assistant.py "nod yes and smile"
```

## Devices the controller already expects

Matched in `protos/GemaBotReview.proto`, not by editing the controller:

| Device | Name | Notes |
| :--- | :--- | :--- |
| Display | `oled_display` | `502×410` landscape (`2.06"` AMOLED, auto-detected by controller) |
| Camera | `camera` | 160×120, looks out of the face above the AMOLED |
| Pan motor | `head_yaw` | about Z, ±1.4 rad (±80°) |
| Tilt motor | `head_pitch` | about X through the `Ø32 mm` gimbal ball center (`z = 72.5 mm`), ±0.454 rad (±26°) |
| Sensors | `yaw_sensor`, `pitch_sensor` | present, as in the original world |
| Touch | `head_touch` | `50×30 mm` floating solar-panel bumper on the crown |

The robot’s Webots name is `Chintu` (`GemaBotReview.proto`), and the curved base graphic says **CHINTU**.

## Files

| Path | Role |
| :--- | :--- |
| `worlds/gemabot_review_plan.wbt` | Desk scene. Basic time step 16 ms, same as the original world. |
| `protos/GemaBotReview.proto` | Robot body and joints. |
| `protos/GemaClockDock.proto` | Clock dock. |
| `protos/textures/` | `face_happy.png`, `face_joy.png`, `clock_1042.png`, `logo_gema.png`. |
| `scripts/generate_review_plan_world.py` | Regenerates the PROTOs and world from the concept dimensions. |

## Deviations from the concept renders

- The head bevel is a coarse chamfer (5 segments). A denser mesh flat-shaded into a chevron pattern in Webots, so the shell is faceted rather than the smooth Cycles bevel in the deck renders.
- The tilt axis passes through the head centre (the orange discs), which is the concept. The original `gemma_bot.wbt` pitched at the top of the neck. Motor names, axes, signs, and limits are the same, so nod and pan commands move the same way.
- The clock PNG was padded onto a 1024×512 sheet so Webots would not stretch the non-power-of-two source. The digits keep their aspect ratio. Webots still prints a warning that `face_happy.png` (1200×900) is not a power of two; that file is replaced as soon as the controller draws the OLED.
- No controller, config default, or Sarvam client code was edited. `start_all.sh` still defaults to `worlds/gemma_bot.wbt`; set `GEMMA_WORLD_PATH` as above to launch this world.
