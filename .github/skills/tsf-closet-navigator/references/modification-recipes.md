# Modification Recipes

> Last verified: 2026-03-07 | Update when: new modification patterns are discovered or file structure changes

Quick lookup: "I want to do X" → "Read/modify these files"

## Backend Recipes

### Add a new API endpoint

| Step | Action                           | Files                                              |
| ---- | -------------------------------- | -------------------------------------------------- |
| 1    | Define Pydantic request/response | `backend/gateway/models.py`                        |
| 2    | Add route handler                | `backend/gateway/routes/{router}.py`               |
| 3    | (If new router) Register in app  | `backend/gateway/app.py`                           |
| 4    | Add business logic               | `backend/gateway/services/{service}.py`            |
| 5    | (If DB needed) Add model         | `backend/gateway/databases/models.py`              |
| 6    | (If DB needed) Create migration  | `uv run alembic revision --autogenerate -m "desc"` |

### Modify game play logic (transformation pipeline)

| Priority | Files to Read                                                          |
| -------- | ---------------------------------------------------------------------- |
| Core     | `backend/gateway/services/game_service.py` (play_with_stream)          |
| LLM      | `backend/gateway/services/llm_service.py`                              |
| Image    | `backend/gateway/services/image_generation.py`                         |
| Prompts  | `backend/gateway/services/action_prompts.py` or `reality_prompts.py`   |
| Stats    | `backend/gateway/services/game_service.py` (stats calculation section) |

### Add/modify an achievement

| Files                                                | Purpose                           |
| ---------------------------------------------------- | --------------------------------- |
| `backend/gateway/services/achievement_service.py`    | Unlock conditions                 |
| `backend/gateway/services/achievement_classifier.py` | Category classification           |
| `backend/gateway/databases/models.py`                | Achievement/AchievedEnding models |

### Modify ending conditions

| Files                                         | Purpose                 |
| --------------------------------------------- | ----------------------- |
| `backend/gateway/services/summary_service.py` | Ending evaluation logic |
| `backend/gateway/services/summary_prompts.py` | Ending prompt templates |
| `backend/gateway/services/endings.py`         | Ending definitions      |

### Modify LLM prompts

| Prompt Type          | File                                            |
| -------------------- | ----------------------------------------------- |
| Dress-up instruction | `backend/gateway/services/action_prompts.py`    |
| Reality change       | `backend/gateway/services/reality_prompts.py`   |
| Self-mode            | `backend/gateway/services/self_mode_prompts.py` |
| Summary/ending       | `backend/gateway/services/summary_prompts.py`   |
| Shared utilities     | `backend/gateway/services/prompts.py`           |

### Add a new DB table

| Step | Action                  | Files                                                       |
| ---- | ----------------------- | ----------------------------------------------------------- |
| 1    | Define SQLAlchemy model | `backend/gateway/databases/models.py`                       |
| 2    | Generate migration      | `uv run alembic revision --autogenerate -m "add_tablename"` |
| 3    | Apply migration         | `uv run alembic upgrade head`                               |

## Frontend Recipes

### Add a new page/screen

| Step | Action           | Files                                                 |
| ---- | ---------------- | ----------------------------------------------------- |
| 1    | Create component | `frontend/src/components/{feature}/FeatureScreen.tsx` |
| 2    | Add route        | `frontend/src/App.tsx` (pathname switch)              |
| 3    | Add nav link     | `frontend/src/components/layout/SideMenu.tsx`         |
| 4    | Add i18n keys    | `frontend/src/assets/` (locale JSON files)            |

### Add shared state

| Step | Action                               | Files                                  |
| ---- | ------------------------------------ | -------------------------------------- |
| 1    | Check if it fits an existing Context | See Context table in SKILL.md          |
| 2a   | Add to existing Context              | `frontend/src/contexts/{Context}.tsx`  |
| 2b   | (New context) Create new             | `frontend/src/contexts/NewContext.tsx` |
| 3    | (New context) Wrap in provider       | `frontend/src/main.tsx` or `App.tsx`   |

### Modify game UI (main play screen)

| Files                                            | Purpose                       |
| ------------------------------------------------ | ----------------------------- |
| `frontend/src/components/GamePlayScreen.tsx`     | Main game view layout         |
| `frontend/src/components/chat/ChatContainer.tsx` | Chat panel                    |
| `frontend/src/components/chat/ChatInput.tsx`     | User input + instruction type |
| `frontend/src/components/ParameterBars.tsx`      | Stats display                 |
| `frontend/src/components/HistoryPanel.tsx`       | History sidebar               |
| `frontend/src/components/layout/MainLayout.tsx`  | Two-column layout frame       |
| `frontend/src/components/layout/RightPanel.tsx`  | Right sidebar                 |

### Add a new API call from frontend

| Step | Action                             | Files                                             |
| ---- | ---------------------------------- | ------------------------------------------------- |
| 1    | Add function                       | `frontend/src/apis/{module}.ts`                   |
| 2    | (If new types needed) Define types | `frontend/src/types/index.ts`                     |
| 3    | Call from hook or Context action   | `frontend/src/hooks/` or `frontend/src/contexts/` |

### Modify SSE event handling

| Files                                        | Purpose                                               |
| -------------------------------------------- | ----------------------------------------------------- |
| `frontend/src/hooks/useSSE.ts`               | SSE event parsing + callbacks                         |
| `frontend/src/components/GamePlayScreen.tsx` | Callback wiring                                       |
| Receiving Context                            | `GameContext` / `ChatContext` / `NotificationContext` |

### Add i18n translations

| Step | Files                                                      |
| ---- | ---------------------------------------------------------- |
| 1    | Add keys to locale JSONs in `frontend/src/assets/`         |
| 2    | Use `useTranslation()` hook or `t()` function in component |
| 3    | Config in `frontend/src/i18n.ts`                           |

## Full-Stack Recipes

### New feature end-to-end

| Layer    | Step                          | Files                                     |
| -------- | ----------------------------- | ----------------------------------------- |
| Backend  | 1. Pydantic models            | `backend/gateway/models.py`               |
| Backend  | 2. Service logic              | `backend/gateway/services/new_service.py` |
| Backend  | 3. Route                      | `backend/gateway/routes/{router}.py`      |
| Backend  | 4. (If DB) Models + migration | `databases/models.py` + Alembic           |
| Frontend | 5. Types                      | `frontend/src/types/index.ts`             |
| Frontend | 6. API client                 | `frontend/src/apis/{module}.ts`           |
| Frontend | 7. Hook or Context action     | `hooks/` or `contexts/`                   |
| Frontend | 8. UI component               | `components/{feature}/`                   |
| Frontend | 9. Route (if page)            | `App.tsx`                                 |
| Frontend | 10. i18n                      | Locale files                              |
| Test     | 11. E2E (Playwright)          | `frontend/tests/e2e/`                     |

### Add SSE event type

| Layer    | Step                          | Files                                        |
| -------- | ----------------------------- | -------------------------------------------- |
| Backend  | 1. Emit event in game_service | `backend/gateway/services/game_service.py`   |
| Frontend | 2. Add callback type          | `frontend/src/hooks/useSSE.ts`               |
| Frontend | 3. Wire callback              | `frontend/src/components/GamePlayScreen.tsx` |
| Frontend | 4. Handle in Context          | Appropriate Context file                     |
