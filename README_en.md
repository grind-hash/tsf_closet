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
| **Inpaint / Masks**       | Partial outfit changes (system / history / preset masks)               |
| **Character Chat**        | Chat with characters beyond dress-up instructions                      |
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
│  ├ Game Router     │     │  └ NovelAI Image API             │
│  ├ Gallery Router  │     └──────────────────────────────────┘
│  ├ Achievements    │     ┌──────────────────────────────────┐
│  ├ Settings Router │────▶│  LLM / Vision                   │
│  └ Health          │     │  ├ LiteLLM → Ollama (selfhost)  │
└────────────────────┘     │  ├ OpenRouter Vision / LLM      │
                           │  └ NovelAI Text API              │
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

| Method   | Path         | Description                       |
| -------- | ------------ | --------------------------------- |
| `GET`    | `/`          | List gallery items                |
| `GET`    | `/sessions`  | Gallery by session                |
| `GET`    | `/{item_id}` | Item details (with prev/next nav) |
| `DELETE` | `/{item_id}` | Delete item                       |

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

### ComfyUI (selfhost)

| Variable                  | Default                                   |
| ------------------------- | ----------------------------------------- |
| `COMFYUI_BASE_URL`        | `http://127.0.0.1:8188`                   |
| `COMFYUI_WORKFLOW_PATH`   | `workflows/qwen_image_edit_template.json` |
| `COMFYUI_REQUEST_TIMEOUT` | `180`                                     |

### LiteLLM (selfhost)

| Variable                | Default                                      |
| ----------------------- | -------------------------------------------- |
| `LITELLM_BASE_URL`      | `http://127.0.0.1:4000`                      |
| `LITELLM_LLAVA_MODEL`   | `ollama/ministral-3:3b-instruct-2512-q4_K_M` |
| `LITELLM_LLM_MODEL`     | `ollama/ministral-3:3b-instruct-2512-q4_K_M` |
| `LITELLM_FEELING_MODEL` | `ollama/ministral-3:3b-instruct-2512-q4_K_M` |

### OpenRouter

| Variable                  | Default                         |
| ------------------------- | ------------------------------- |
| `OPENROUTER_API_KEY`      | (required)                      |
| `OPENROUTER_IMAGE_MODEL`  | `google/gemini-2.5-flash-image` |
| `OPENROUTER_VISION_MODEL` | `mistralai/ministral-14b-2512`  |
| `OPENROUTER_LLM_MODEL`    | `x-ai/grok-4.1-fast`            |

### NovelAI

| Variable                | Default                             |
| ----------------------- | ----------------------------------- |
| `NOVELAI_API_KEY`       | (required)                          |
| `NOVELAI_MODEL`         | `nai-diffusion-4-5-full`            |
| `NOVELAI_INPAINT_MODEL` | `nai-diffusion-4-5-full-inpainting` |
| `NOVELAI_STEPS`         | `28`                                |
| `NOVELAI_SCALE`         | `5.0`                               |
| `NOVELAI_I2I_STRENGTH`  | `0.9`                               |
| `NOVELAI_TEXT_MODEL`    | `glm-4-6`                           |

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

| Path            | Screen           |
| --------------- | ---------------- |
| `/` `/play`     | Main game screen |
| `/gallery`      | Gallery          |
| `/achievements` | Achievement list |
| `/endings`      | Ending list      |
| `/settings`     | Settings         |

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
- NovelAI provider added
- Inpaint / mask feature added
- Achievement system added
- Gallery feature expanded
- Conversation (chat) feature added
- Multilingual support (i18next)
- Portable build script
- Image quality improvements

---

## License

[MIT License](License.txt) - Copyright (c) 2026 nata-water
