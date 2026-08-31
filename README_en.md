🌐 **[日本語](README.md)** | **English**

[![License](https://img.shields.io/badge/license-MIT-green.svg)](License.txt)

<p align="center">
  <img src="repo_resources/brand_image.jpg" alt="TSF Closet" width="720" />
</p>

# TSF Closet

> **TSF Closet** is an interactive dress-up game forked from [nata-water/wakuwaku-transform-magic](https://github.com/nata-water/wakuwaku-transform-magic), specialized for the TSF (gender transformation) theme.

Give natural-language instructions to change character outfits and watch AI transform the image while depicting the character's psychological changes in real-time. The game features parameter fluctuations, critical-point events, and a visual-novel-style game system.

---

## Screenshots

### Gameplay

|                    Initial Screen                     |                      After Dress-Up                       |
| :---------------------------------------------------: | :-------------------------------------------------------: |
| ![Game screen (initial)](repo_resources/screen01.png) | ![After dress-up (princess)](repo_resources/screen02.png) |

### Play Summary & Title

|                  Before Generation                  |                  After Generation                  |                     Share Preview                      |
| :-------------------------------------------------: | :------------------------------------------------: | :----------------------------------------------------: |
| ![Before generation](repo_resources/screen05_0.png) | ![After generation](repo_resources/screen05_1.png) | ![Share preview save](repo_resources/screen05_1_2.png) |

### Inpaint (Partial Changes)

|                   Mask Editing                    |                      Generating                      |                      Result                      |
| :-----------------------------------------------: | :--------------------------------------------------: | :----------------------------------------------: |
| ![Inpaint editing](repo_resources/screen05_2.png) | ![Inpaint generating](repo_resources/screen05_3.png) | ![Inpaint result](repo_resources/screen05_4.png) |

### Gallery

|                      Session List                      |                      Image List                      |
| :----------------------------------------------------: | :--------------------------------------------------: |
| ![Gallery (session list)](repo_resources/screen04.png) | ![Gallery (image list)](repo_resources/screen05.png) |

### First-Time Setup (NovelAI)

|                    API Key Consent                    |                 Subscription Warning                 |
| :---------------------------------------------------: | :--------------------------------------------------: |
| ![API key consent modal](repo_resources/screen06.png) | ![Subscription warning](repo_resources/screen07.png) |

---

## Key Features

| Feature                   | Description                                                            |
| ------------------------- | ---------------------------------------------------------------------- |
| **Character Selection**   | Preset characters or custom image upload                               |
| **Dress-Up Execution**    | Natural language outfit instructions (e.g. "Change into a bunny suit") |
| **AI Image Generation**   | Switch between ComfyUI / OpenRouter / NovelAI providers                |
| **Mood Text Generation**  | Vision LLM + Text LLM stream character reactions in real-time          |
| **Parameter System**      | Bloom, Shame, and Adaptation fluctuate based on outfits                |
| **Critical-Point Events** | Special dialogue triggers when Bloom reaches thresholds                |
| **Achievement System**    | 12 achievements auto-detected                                          |
| **Gallery**               | Browse past transformation images and completed endings                |
| **Play Summary & Title**  | LLM auto-generates a summary and title (epithet) from play history     |
| **Share Preview**         | Save summary card as OGP-style image (1200×630) or copy to clipboard   |
| **Inpaint / Masks**       | Partial outfit changes (system / history / preset masks)               |
| **Character Chat**        | Chat with characters beyond dress-up instructions                      |
| **TSF Scenario**          | Novel-game mode starting from a transformed state, with 5 mission types incl. romance sim (experimental) |
| **Face-to-Face Mode**     | One turn = one exchange with the partner; 3D model (VRM) display and voice input (experimental) |
| **Prompt Expander**       | Expand natural-language instructions into NovelAI prompts and generate images independently (experimental) |
| **Speech Synthesis**      | Reads lines aloud via AivisSpeech (experimental)                       |
| **NAI Diffusion V5**      | Per-NSFW/SFW model selection and remaining-usage display               |
| **Memory**                | Preference memory (across plays) and play memory (within a play) feed generation |
| **Favorite Outfits**      | Star history images, label them, and resume from the favorites tab     |
| **Branch / Compare**      | Start a new session from any history image; Before/After slider        |
| **Export**                | Save chat history as Markdown / novel-style HTML ZIP                   |
| **Multiple Characters**   | Persistent appearances across sessions and character presets (experimental) |
| **Multilingual**          | Japanese / English switching (with conversation language validation)   |

---

## Architecture

```
┌────────────────────┐
│  Browser (React)   │
│  :3000 (dev)       │
└────────┬───────────┘
         │ /api/*
         ▼
┌────────────────────┐     ┌──────────────────────────────────┐
│  FastAPI Backend   │────▶│  Image Generation                │
│  :8000             │     │  ├ ComfyUI (selfhost, GPU)       │
│                    │     │  ├ OpenRouter API (cloud)         │
│  ├ Game / Chars    │     │  └ NovelAI Image API             │
│  ├ Adventure       │     └──────────────────────────────────┘
│  ├ Prompt Expander │     ┌──────────────────────────────────┐
│  ├ Gallery / Favs  │────▶│  LLM / Vision                   │
│  ├ Achievements    │     │  ├ LiteLLM → Ollama (selfhost)  │
│  ├ Memory          │     │  ├ OpenRouter Vision / LLM      │
│  ├ Avatars (VRM)   │     │  └ NovelAI Text API              │
│  ├ AivisSpeech     │     └──────────────────────────────────┘
│  ├ Settings        │     ┌──────────────────────────────────┐
│  └ Health          │────▶│  Speech Synthesis                │
└────────────────────┘     │  └ AivisSpeech Engine (TTS)      │
                           └──────────────────────────────────┘
```

### Tech Stack

| Layer     | Technology                                         |
| --------- | -------------------------------------------------- |
| Frontend  | React 19 + TypeScript + Vite                       |
| Backend   | FastAPI + Python 3.12                              |
| Database  | SQLite (aiosqlite + SQLAlchemy + Alembic)          |
| Image Gen | ComfyUI (Qwen Image Edit) / OpenRouter / NovelAI   |
| Text Gen  | LiteLLM Proxy → Ollama / OpenRouter / NovelAI Text |
| i18n      | i18next (ja / en)                                  |
| Container | Docker Compose (6 services)                        |

---

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Image generation provider (one of the following):
  - ComfyUI + NVIDIA GPU (self-hosted)
  - OpenRouter API key
  - NovelAI API key (Opus plan recommended)

### 1. Setup

```powershell
# Backend dependencies
cd backend
uv sync

# Frontend dependencies
cd ../frontend
npm install
```

### 2. Environment Variables

Copy `.env.example` to `.env` and configure for your provider:

```powershell
Copy-Item .env.example .env
```

### 3. Start the Application

```powershell
# Backend (port 8000)
cd backend
uv run uvicorn gateway.app:app --host 0.0.0.0 --port 8000 --reload

# Frontend (port 3000) - in a separate terminal
cd frontend
npm run dev
```

Open `http://localhost:3000/` in your browser.

---

## Docker Deployment

```powershell
docker compose up -d
# Apply backend database migrations
docker compose exec backend bash -c "uv run alembic upgrade head"
```

> **Note**: ComfyUI model downloads may take over an hour. Monitor progress with `docker compose logs -f comfyui`.

| Service      | Description     | Port       |
| ------------ | --------------- | ---------- |
| `frontend`   | React + nginx   | 80         |
| `backend`    | FastAPI         | (internal) |
| `litellm`    | LiteLLM Proxy   | 4000       |
| `litellm_db` | PostgreSQL 16   | 5432       |
| `ollama`     | Local LLM (GPU) | —          |
| `comfyui`    | Image Gen (GPU) | 8188       |

**System Requirements** (Docker):

- NVIDIA GPU (ollama, comfyui)
- Storage: 100 GB+ free space
- Memory: 64 GB+ recommended

---

## Portable Build

Build a Windows portable distribution package for users without a GPU environment:

```powershell
.\scripts\build_portable.ps1 -Version "0.1.0" -Provider novelai
```

| Parameter       | Description                           | Default   |
| --------------- | ------------------------------------- | --------- |
| `-Version`      | Version string                        | `dev`     |
| `-Provider`     | `novelai` / `selfhost` / `openrouter` | `novelai` |
| `-Force`        | Overwrite existing output             | —         |
| `-NoZip`        | Skip ZIP creation                     | —         |
| `-SkipFrontend` | Skip frontend build                   | —         |
| `-SkipPython`   | Skip Python environment setup         | —         |

Output: `dist/tsf_closet_portable_v{Version}_{Provider}/`

---

## Image Generation Providers

Switch via the `IMAGE_PROVIDER` environment variable:

| Provider     | Example Env Var                          | Requirements                |
| ------------ | ---------------------------------------- | --------------------------- |
| `selfhost`   | `COMFYUI_BASE_URL=http://127.0.0.1:8188` | NVIDIA GPU + ComfyUI        |
| `openrouter` | `OPENROUTER_API_KEY=sk-...`              | OpenRouter API key          |
| `novelai`    | `NOVELAI_API_KEY=pst-...`                | NovelAI API key (Opus rec.) |

Text generation (mood text) can also be switched via `FEELING_PROVIDER`.

> **OpenRouter Notes**
>
> - R18 / NSFW image generation and editing are **not supported** (no compatible models found at this time).
> - Since nano banana is used internally, some prompts like "bunny girl" may trigger content filters and cause image generation errors.

> **NAI Diffusion V5**
>
> - The image models used for NSFW and SFW (V4.5 Full / V5 Full / V4.5 Curated / V5 Curated) can each be selected in the settings screen.
> - Remaining V5 usage is displayed (generation after the cap consumes Anlas).
> - Precise reference is available only with V4.5 models.

---

## Game System

### Parameters

| Parameter  | Range     | Description                                                |
| ---------- | --------- | ---------------------------------------------------------- |
| Bloom      | 0 – 100   | Adaptation to feminization. Increases with outfit exposure |
| Shame      | 0 – 100   | Rises with revealing outfits. Affects bloom speed          |
| Adaptation | -50 – +50 | Positive = accepting, Negative = resisting                 |

### Difficulty

| Difficulty            | Initial Shame | Bloom Rate | Adaptation Rate |
| --------------------- | ------------- | ---------- | --------------- |
| Easy (more resistant) | 70            | 0.5x       | 1.0x            |
| Normal                | 50            | 1.0x       | 1.0x            |
| Hard (falls quickly)  | 30            | 1.5x       | 1.2x            |

### Critical-Point Events

When Bloom reaches certain thresholds, the character delivers special dialogue:

| Threshold | Description                                   |
| --------- | --------------------------------------------- |
| 25%       | Becomes aware of discomfort with feminization |
| 50%       | Torn between resistance and pleasure          |
| 75%       | Begins to accept feminine sensations          |
| 100%      | Fully adapted as female                       |

### Endings (4 Types)

| Ending               | Condition Summary                         |
| -------------------- | ----------------------------------------- |
| Pleasure Bloom End   | Bloom 100 + most transforms are revealing |
| Self-Acceptance End  | Bloom 100 + most transforms are cute      |
| Resistance Limit End | 15+ transforms + Bloom below 50           |
| Curiosity Gone Wild  | Bloom 100 + distributed tags              |

### Achievement System (12 Types)

Achievements are automatically unlocked based on conditions such as transform count, cross-dressing count, collection count, and bloom level.

---

## TSF Scenario (Adventure Mode)

An experimental mode that starts an independent novel-game scenario from a transformed state (any point of a session). Enable "TSF Scenario" under "Experimental" in the settings screen to show it in the main menu.

- **Missions**: 5 types — Romance Simulation, Infiltration, Escape & Return, Negotiation, and Impersonation & Dress-Up. Stage, goal, and constraints can be AI-generated, entered directly, or chosen from a bundled story scenario
- **Romance Simulation**: day-based progression (day/night), affection, money, part-time jobs, a gift shop, confession, and an epilogue after the ending. The protagonist can use an appearance from another session, and you can set the name the partner calls the protagonist
- **Reality Alteration**: declare world rules with "reality: ..." that apply to every later judgement (attributes can also be granted without spending a turn)
- **Talk**: free chat that does not spend a turn. Affection, money, and days stay the same, and the conversation carries into the next scene
- **Auto BGM**: picks background music to match the scene (tracks made with Suno AI); a BGM test screen is available
- **Narration & Speech Styles**: choose the narrative person (first / second / third) and the speech styles of the protagonist and the partner
- **More**: turn rewind, scene-image prompt editing and regeneration, a log view, and Anlas cost estimates
- Playable with OpenRouter / selfhost (ComfyUI) in addition to NovelAI (some features are limited depending on the provider)

See [docs/adventure-flow.md](docs/adventure-flow.md) for the detailed processing flow (Japanese).

<!-- TODO: screenshot repo_resources/screen08_adventure_title.png (mission select) / repo_resources/screen09_adventure_sim.png (romance sim HUD) -->

### Face-to-Face Mode

A mode available in the romance simulation (off by default). The partner stands right in front of you and one turn becomes one exchange. There is no day/night split; the outcome settles after the configured number of exchanges.

- Only the partner's portrait and the background (when the location changes) are generated. Selfhost (ComfyUI) cannot generate backgrounds
- Line read-aloud is supported: only the partner's scripted lines are played via AivisSpeech, and the BGM is ducked while a line plays
- Microphone voice input is supported (Chrome / Edge). It uses the browser's speech recognition, so in Chrome your voice is sent to Google's servers

<!-- TODO: screenshot repo_resources/screen10_adventure_companion.png (face-to-face mode + 3D model) -->

---

## 3D Model (VRM) Avatars

In face-to-face mode, a 3D model (VRM 0.x / 1.0) can replace the partner's portrait. Register models by drag & drop under "3D Model (VRM)" in the settings screen.

- The mouth moves in sync with the phoneme timing of the read-aloud voice, and the expression and gesture change with every reply
- Files named like `CharacterName_Outfit_HairVer.vrm` are auto-classified into characters and outfit variants. With two or more variants of the same character, the model switches to match outfit changes in the story
- A preview of registered models lets you check expressions and gestures
- Convert FBX or PMX to VRM before registering, and follow each model's distribution terms

<!-- TODO: screenshot repo_resources/screen13_avatar_preview.png (3D model preview) -->

---

## Prompt Expander

An experimental screen that expands natural-language instructions into NovelAI prompts with an LLM and generates images independently of the game. Enable "Prompt Expander" under "Experimental" in the settings screen to show it in the main menu.

- Output format is selectable (Japanese text / tags). History is managed per session with restore, regenerate, use-as-i2i-source, and hand-off to normal play / TSF Scenario
- Character prompts are supported (up to 22 slots on V5 models, 6 on V4.5). Preferred character ideas can be suggested from memory and inserted into slots
- Manga (panel) mode (NAI Diffusion V5 models only): choose panel count, layout, reading order (Japanese right-to-left by default), and dialogue language. A synopsis can be drafted into notation-annotated script
- Inpainting (partial fixes), precise reference (V4.5 models only; each reference costs additional Anlas), transparent backgrounds, and drag & drop onto the screen are supported

<!-- TODO: screenshot repo_resources/screen11_prompt_expander.png (manga mode) -->

---

## Speech Synthesis (AivisSpeech)

An experimental feature that reads lines aloud with the AivisSpeech engine. Enable it under "Speech Synthesis (AivisSpeech)" in the settings screen.

- Supports chat read-aloud in normal play and automatic line playback in the TSF Scenario (face-to-face mode)
- VOICEVOX-compatible engines can also be connected
- The default voice volume is 50%; volume and playback speed are adjustable

<!-- TODO: screenshot repo_resources/screen12_settings_tts.png (speech synthesis settings) -->

---

## Memory (Preference Memory / Play Memory)

- **Preference Memory**: analyzes past play logs and auto-generates your preferred situations. Freely editable, and applied across plays to instructions, suggestions, and image generation
- **Play Memory (experimental)**: automatically summarizes the course of each play and feeds it back into generation within that play. Settings you want to keep can be written as a user memo. When enabled, an auto memo is generated per chat, so responses may take longer

---

## API Endpoints

### Game (`/api/game`)

| Method   | Path            | Description                      |
| -------- | --------------- | -------------------------------- |
| `POST`   | `/start`        | Start game session               |
| `POST`   | `/start-custom` | Start session with custom image  |
| `POST`   | `/play/stream`  | Execute dress-up (SSE streaming) |
| `GET`    | `/characters`   | Get character list               |
| `GET`    | `/session`      | Get active session               |
| `GET`    | `/sessions`     | List sessions (paginated)        |
| `DELETE` | `/session`      | Reset session                    |
| `POST`   | `/chat`         | Chat with character              |
| `GET`    | `/endings`      | List endings                     |
| `GET`    | `/masks`        | Get mask list                    |

### Gallery (`/api/gallery`)

| Method   | Path                             | Description                                  |
| -------- | -------------------------------- | -------------------------------------------- |
| `GET`    | `/`                              | List gallery items                           |
| `GET`    | `/sessions`                      | Gallery by session                           |
| `GET`    | `/{item_id}`                     | Item details (with prev/next nav)            |
| `DELETE` | `/{item_id}`                     | Delete item                                  |
| `GET`    | `/sessions/{session_id}/summary` | Get play summary & title                     |
| `POST`   | `/sessions/{session_id}/summary` | Generate play summary & title (`?language=`) |

### Achievements (`/api/achievements`)

| Method | Path                | Description            |
| ------ | ------------------- | ---------------------- |
| `GET`  | `/`                 | List achievements      |
| `GET`  | `/{achievement_id}` | Get achievement detail |

### Settings (`/api/settings`)

| Method | Path    | Description             |
| ------ | ------- | ----------------------- |
| `GET`  | `/`     | Get session settings    |
| `PUT`  | `/`     | Update session settings |
| `GET`  | `/user` | Get user settings       |
| `PUT`  | `/user` | Update user settings    |

### Other Routers (Overview)

| Prefix                 | Description                                                                            |
| ---------------------- | --------------------------------------------------------------------------------------- |
| `/api/adventure`       | TSF Scenario (runs / templates / turn SSE / talk SSE / reality rules / rewind / BGM)     |
| `/api/prompt-expander` | Prompt Expander (sessions / entries / expansion / generation / manga script / settings)  |
| `/api/avatars`         | 3D model (VRM) registration, auto-classification, and file serving                       |
| `/api/aivisspeech`     | Speech synthesis (`/synthesize`, `/synthesize-timed` with viseme timeline, engine mgmt.) |
| `/api/memory`          | Preference memory generation jobs and text editing                                       |
| `/api/favorites`       | Favorite outfits (list / add / relabel)                                                  |
| `/api/game` (multi)    | Session characters and character presets                                                 |

### SSE Events (`/api/game/play/stream`)

| Event         | Data                                       |
| ------------- | ------------------------------------------ |
| `feeling`     | Character mood text (chunked)              |
| `image`       | Generated image Base64 data                |
| `tags`        | Outfit tag info (category, exposure level) |
| `stats`       | Parameter change values                    |
| `critical`    | Critical-point dialogue                    |
| `ending`      | Ending judgment result                     |
| `achievement` | Achievement unlock notification            |
| `done`        | Processing complete                        |

---

## Environment Variables

<details>
<summary>Click to expand</summary>

### Common

| Variable                     | Description                                                | Default    |
| ---------------------------- | ---------------------------------------------------------- | ---------- |
| `PORT`                       | Server port                                                | `8000`     |
| `LOG_LEVEL`                  | Log level                                                  | `info`     |
| `IMAGE_PROVIDER`             | Image gen provider (`selfhost` / `openrouter` / `novelai`) | `selfhost` |
| `IMAGE_DESCRIPTION_PROVIDER` | Image description provider                                 | `selfhost` |
| `FEELING_PROVIDER`           | Mood text provider                                         | `selfhost` |
| `ENABLE_PROMPT_PREVIEW`      | Prompt preview feature for the TSF Scenario                | `false`    |

### ComfyUI (selfhost)

| Variable                  | Default                                   |
| ------------------------- | ----------------------------------------- |
| `COMFYUI_BASE_URL`        | `http://127.0.0.1:8188`                   |
| `COMFYUI_WORKFLOW_PATH`   | `workflows/qwen_image_edit_template.json` |
| `COMFYUI_REQUEST_TIMEOUT` | `180`                                     |

### LiteLLM (selfhost)

| Variable                | Default (.env.example)                        |
| ----------------------- | --------------------------------------------- |
| `LITELLM_BASE_URL`      | `http://127.0.0.1:4000`                       |
| `LITELLM_LLAVA_MODEL`   | `ollama/ministral-3:14b-instruct-2512-q4_K_M` |
| `LITELLM_LLM_MODEL`     | `ollama/ministral-3:14b-instruct-2512-q4_K_M` |
| `LITELLM_FEELING_MODEL` | `ollama/ministral-3:14b-instruct-2512-q4_K_M` |

In the selfhost configuration (`.env.example.selfhost`) the default for all three models is `gemma4:e4b`.

### OpenRouter

| Variable                  | Default (.env.example)          |
| ------------------------- | ------------------------------- |
| `OPENROUTER_API_KEY`      | (required)                      |
| `OPENROUTER_IMAGE_MODEL`  | `google/gemini-2.5-flash-image` |
| `OPENROUTER_VISION_MODEL` | `google/gemini-3-flash-preview` |
| `OPENROUTER_LLM_MODEL`    | `google/gemini-3-flash-preview` |

### NovelAI

| Variable                        | Default                                |
| ------------------------------- | -------------------------------------- |
| `NOVELAI_API_KEY`               | (required)                             |
| `NOVELAI_MODEL`                 | `nai-diffusion-4-5-full`               |
| `NOVELAI_INPAINT_MODEL`         | `nai-diffusion-4-5-full-inpainting`    |
| `NOVELAI_CURATED_MODEL`         | `nai-diffusion-4-5-curated`            |
| `NOVELAI_CURATED_INPAINT_MODEL` | `nai-diffusion-4-5-curated-inpainting` |
| `NOVELAI_STEPS`                 | `28`                                   |
| `NOVELAI_SCALE`                 | `5.0`                                  |
| `NOVELAI_I2I_STRENGTH`          | `0.9`                                  |
| `NOVELAI_TEXT_MODEL`            | `glm-4-6`                              |

### Data Persistence

| Variable             | Default                |
| -------------------- | ---------------------- |
| `DATABASE_PATH`      | `data/database.sqlite` |
| `HISTORY_IMAGES_DIR` | `data/history_images`  |
| `HISTORY_MAX_COUNT`  | `50`                   |
| `CHARACTERS_DIR`     | `images/characters`    |

</details>

---

## Adding Characters

Edit [backend/images/characters/characters.json](backend/images/characters/characters.json) and place images in the same directory:

```json
{
  "characters": [
    {
      "id": "char1",
      "name": "Protagonist",
      "description": "An ordinary high school boy",
      "image_path": "char1.png",
      "pronoun": "I",
      "personality": "Shy and serious"
    }
  ]
}
```

You can also upload custom images through the UI when starting a game.

---

## Frontend Screens

| Path               | Screen                                    |
| ------------------ | ----------------------------------------- |
| `/` `/play`        | Main game screen                          |
| `/gallery`         | Gallery                                   |
| `/achievements`    | Achievement list                          |
| `/endings`         | Ending list (enabled via Experimental)    |
| `/adventure`       | TSF Scenario (enabled via Experimental)   |
| `/bgm-test`        | BGM test (with TSF Scenario enabled)      |
| `/prompt-expander` | Prompt Expander (enabled via Experimental) |
| `/settings`        | Settings                                  |

---

## Development

```powershell
# Backend (hot reload)
cd backend
uv run alembic upgrade head
uv run uvicorn gateway.app:app --host 0.0.0.0 --port 8000 --reload

# Frontend (Vite dev server)
cd frontend
npm run dev

# Lint
cd frontend; npm run lint
cd backend; uv run ruff check .

# Tests
cd frontend; npm run e2e:test
cd backend; uv run pytest
```

### Migrations

```powershell
cd backend
uv run alembic revision --autogenerate -m "migration_comment"
uv run alembic upgrade head
```

---

## Differences from the Original Fork

This project was forked from [wakuwaku-transform-magic](https://github.com/nata-water/wakuwaku-transform-magic) by nata-water (a kid-friendly transformation dress-up app), with the following changes:

- Complete rewrite for the TSF (gender transformation) theme
- Parameter system redesign (Excitement → Bloom / Shame / Adaptation)
- Ending condition redesign
- NovelAI provider added (including NAI Diffusion V5 support)
- Inpaint / mask feature added
- Achievement system added
- Gallery feature expanded (favorite outfits, transform comparison, keyword search, session branching)
- Conversation (chat) feature added
- Multilingual support (i18next)
- Portable build script
- Image quality improvements
- TSF Scenario (adventure mode) added
- Face-to-face mode and 3D model (VRM) avatars added
- Prompt Expander added
- Speech synthesis (AivisSpeech) added
- Preference memory / play memory added
- Persistent multiple characters and character presets added

---

## License

[MIT License](License.txt) - Copyright (c) 2026 nata-water
