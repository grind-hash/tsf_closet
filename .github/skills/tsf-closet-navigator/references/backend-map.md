# Backend Architecture Map

> Last verified: 2026-03-07 | Update when: routes, services, or DB models are added/renamed/removed

## FastAPI Application

- **Entry**: `backend/gateway/app.py` — CORS middleware, static files, DB lifecycle, router mounts
- **Models (Pydantic)**: `backend/gateway/models.py` — Request/response schemas

## API Routes

### `/game` — [backend/gateway/routes/game_router.py](../../backend/gateway/routes/game_router.py)

| #     | Method | Path                                | Purpose                                |
| ----- | ------ | ----------------------------------- | -------------------------------------- |
| 1     | GET    | `/game/characters`                  | Character list                         |
| 2     | GET    | `/game/session/{id}`                | Get session state                      |
| 3     | POST   | `/game/play`                        | Execute transformation (non-streaming) |
| 4     | POST   | `/game/play/stream`                 | Execute transformation (SSE stream)    |
| 5     | GET    | `/game/session`                     | Get current active session             |
| 6     | GET    | `/game/session/image/{id}`          | Get session PNG image                  |
| 7     | GET    | `/game/difficulties`                | Difficulty presets list                |
| 8     | POST   | `/game/start`                       | Start new session                      |
| 9     | POST   | `/game/start-custom`                | Start with custom image                |
| 10    | GET    | `/game/custom-characters`           | List custom characters                 |
| 11    | DELETE | `/game/session`                     | Reset session                          |
| 12    | POST   | `/game/history/{id}/select`         | Select history item                    |
| 13    | GET    | `/game/sessions`                    | Session list (paginated)               |
| 14    | GET    | `/game/sessions/{id}`               | Session detail                         |
| 15    | POST   | `/game/sessions/{id}/restore`       | Restore session                        |
| 16    | GET    | `/game/gallery`                     | Gallery list                           |
| 17    | GET    | `/game/endings`                     | Endings list                           |
| 18    | GET    | `/game/ending/{id}`                 | Ending detail                          |
| 19    | POST   | `/game/chat`                        | Character chat                         |
| 20    | GET    | `/game/chat/stream`                 | Character chat (streaming)             |
| 21    | GET    | `/game/conversation/{id}`           | Conversation history                   |
| 22    | GET    | `/game/improve-quality/stream`      | Re-generate image (SSE)                |
| 23    | POST   | `/game/attributes`                  | Add reality attribute                  |
| 24    | DELETE | `/game/attributes/{id}`             | Remove attribute                       |
| 25    | GET    | `/game/attributes/{id}`             | Get session attributes                 |
| 26    | POST   | `/game/preview/prompt`              | Preview prompts                        |
| 27    | GET    | `/game/masks`                       | List masks (system/history/preset)     |
| 28    | POST   | `/game/masks`                       | Save mask                              |
| 29-31 | GET    | `/game/masks/{type}/{id}`           | Get mask image                         |
| 32    | DELETE | `/game/masks/preset/{id}`           | Delete preset mask                     |
| 33    | GET    | `/game/anlas`                       | NovelAI Anlas balance                  |
| 34    | POST   | `/game/generate-base-tags`          | Generate base tags                     |
| 35    | DELETE | `/game/session/{id}/latest-history` | Delete latest history                  |

### `/settings` — [backend/gateway/routes/settings_router.py](../../backend/gateway/routes/settings_router.py)

| Method | Path                              | Purpose                       |
| ------ | --------------------------------- | ----------------------------- |
| GET    | `/settings/user`                  | Get user settings             |
| PUT    | `/settings/user`                  | Update user settings          |
| GET    | `/settings/self-profile`          | Get self-mode profile         |
| POST   | `/settings/self-profile/generate` | Generate self profile via LLM |
| PUT    | `/settings/self-profile`          | Update self profile           |

### `/achievements` — [backend/gateway/routes/achievements_router.py](../../backend/gateway/routes/achievements_router.py)

| Method | Path                     | Purpose                      |
| ------ | ------------------------ | ---------------------------- |
| GET    | `/achievements`          | All achievements list        |
| GET    | `/achievements/{id}`     | Achievement detail           |
| GET    | `/achievements/unlocked` | User's unlocked achievements |

### `/gallery` — [backend/gateway/routes/gallery_router.py](../../backend/gateway/routes/gallery_router.py)

| Method | Path            | Purpose             |
| ------ | --------------- | ------------------- |
| GET    | `/gallery`      | Paginated gallery   |
| GET    | `/gallery/{id}` | Gallery item detail |
| DELETE | `/gallery/{id}` | Delete gallery item |

## Services

| File                        | Class/Module            | Primary Responsibility                                       |
| --------------------------- | ----------------------- | ------------------------------------------------------------ |
| `game_service.py`           | `GameService`           | Main play loop: instruction → LLM → image gen → SSE response |
| `llm_service.py`            | `LLMService`            | LLM API calls (OpenAI/OpenRouter/LiteLLM)                    |
| `image_generation.py`       | `OpenRouterImageClient` | Image gen via OpenRouter/Gemini multi-modal                  |
| `conversation_service.py`   |                         | Chat history management per session                          |
| `achievement_service.py`    |                         | Achievement unlock condition checking                        |
| `achievement_classifier.py` |                         | Classify instruction text → achievement categories           |
| `settings_service.py`       |                         | User setting CRUD                                            |
| `summary_service.py`        |                         | Ending condition evaluation                                  |
| `session.py`                |                         | In-memory session state store                                |
| `characters.py`             |                         | Character metadata (list, select, init)                      |
| `comfy.py`                  |                         | ComfyUI API client (workflow execution)                      |
| `litellm_client.py`         |                         | LiteLLM integration for local LLM                            |
| `anlas_service.py`          |                         | NovelAI Anlas (token) balance                                |
| `tag_classifier.py`         |                         | NLP tagging (costume/exposure/age)                           |
| `action_prompts.py`         |                         | Dress-up instruction prompt templates                        |
| `reality_prompts.py`        |                         | Reality-change prompt templates                              |
| `self_mode_prompts.py`      |                         | Self-mode prompt templates                                   |
| `summary_prompts.py`        |                         | Summary/ending prompt templates                              |
| `prompts.py`                |                         | Shared prompt utilities                                      |
| `endings.py`                |                         | Ending definitions and data                                  |
| `conversation.py`           |                         | Conversation data structures                                 |

## Database (SQLAlchemy)

- **Models**: `backend/gateway/databases/models.py`
- **ORM/Engine**: `backend/gateway/databases/orm.py` (base.py re-export)
- **Migrations**: `backend/migrations/versions/` (Alembic)

### Tables

| Model                            | Key Fields                                                                                     |
| -------------------------------- | ---------------------------------------------------------------------------------------------- |
| `User`                           | id, nsfw_mode, difficulty, language, self_profile_json                                         |
| `Session`                        | id, user FK, character_id, active, transformation_count                                        |
| `SessionStats`                   | session FK, bloom, shame, adaptation, passed_critical_points (JSON), difficulty, nsfw_mode     |
| `History`                        | session FK, instruction, image_path, feeling_text, before/after descriptions, instruction_type |
| `Conversation`                   | session FK, role, content, timestamp                                                           |
| `Achievement` / `AchievedEnding` | User's unlocked items with timestamps                                                          |
| `SessionAttribute`               | session FK, text (reality attributes)                                                          |
| `TransformationTag`              | history FK, costume_category, exposure_level, age_impression                                   |

## Constants

- `backend/gateway/consts/language.py`: `LanguageCode` enum (ja/en), normalization, default=ja
