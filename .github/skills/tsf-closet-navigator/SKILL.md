---
name: tsf-closet-navigator
description: "tsf_closet_base project navigator for context-efficient investigation and modification. Use when: exploring project architecture, locating files for a feature change, tracing data flow between frontend and backend, understanding API contracts, modifying game logic, adding new routes/contexts/components, debugging session or image generation issues. Reduces context window usage by providing pre-mapped architecture references instead of broad file exploration."
argument-hint: "Describe what you want to investigate or modify (e.g., 'add a new API endpoint', 'fix stats calculation', 'trace image generation flow')"
---

# TSF Closet Navigator

Context-efficient project investigation and modification skill for tsf_closet_base.

## When to Use

- Investigating how a feature works without reading dozens of files
- Planning where to make changes for a new feature or bug fix
- Tracing data flow between frontend ↔ backend
- Understanding which files to modify for a given change
- Onboarding to unfamiliar parts of the codebase

## Procedure

### Step 1: Classify the Task

Determine the modification category:

| Category        | Description                                          | Reference to Load                               |
| --------------- | ---------------------------------------------------- | ----------------------------------------------- |
| **Backend API** | New/modify endpoints, request/response models        | [backend-map.md](./references/backend-map.md)   |
| **Frontend UI** | Components, contexts, hooks, pages                   | [frontend-map.md](./references/frontend-map.md) |
| **Data Flow**   | End-to-end feature tracing (FE → API → Service → DB) | [data-flow.md](./references/data-flow.md)       |
| **Full-Stack**  | Changes spanning both frontend and backend           | Load both backend-map + frontend-map            |

### Step 2: Use the Modification Recipes

Based on the task, use the [modification recipes](./references/modification-recipes.md) to identify the **minimum set of files** to read and modify. Do NOT explore the file tree broadly — use the recipe tables instead.

### Step 3: Read Only What's Needed

Follow the recipe and read **only** the listed files. For each file, read only the relevant section (use grep_search or targeted line ranges).

### Step 4: Implement Changes

Apply changes following AGENTS.md conventions (Context-first state management, uv for Python, ESLint/Prettier/Ruff, etc.).

### Step 5: Self-Maintenance Check

After completing structural changes (new files, renamed files, new routes/contexts/hooks), update the affected reference file:

**Trigger conditions for update:**

- New route/endpoint added → update [backend-map.md](./references/backend-map.md)
- New component/context/hook added → update [frontend-map.md](./references/frontend-map.md)
- New data flow pattern introduced → update [data-flow.md](./references/data-flow.md)
- New modification pattern discovered → update [modification-recipes.md](./references/modification-recipes.md)

Use the [refresh prompt](./references/refresh-guide.md) for full regeneration when references feel outdated.

## Architecture Quick Reference (Always Loaded)

### Tech Stack

- **Frontend**: React 19 + TypeScript 5.9 + Vite 7.2 + React Router 7 (port 3000)
- **Backend**: FastAPI 0.115 + SQLAlchemy 2.0 + aiosqlite (port 8000)
- **Image Gen**: ComfyUI (inpaint/variation workflows)
- **LLM**: OpenAI-compatible API (via LiteLLM/OpenRouter/local)
- **Streaming**: Server-Sent Events (SSE) for real-time game responses
- **Package Mgmt**: uv (Python), npm (Node.js)

### Core Directories

```
backend/gateway/
  routes/          ← FastAPI routers (game, settings, achievements, gallery)
  services/        ← Business logic (game_service, llm_service, image_generation, etc.)
  databases/       ← SQLAlchemy models + ORM queries
  models.py        ← Pydantic request/response schemas
  consts/          ← Constants (language codes, etc.)

frontend/src/
  apis/            ← API client modules (game, settings, achievements, gallery, anlas)
  components/      ← React components (chat/, settings/, gallery/, achievements/, ui/)
  contexts/        ← 4 Contexts: Game, Chat, Settings, Notification
  hooks/           ← Custom hooks (useSession, useSSE, useAchievements, useGallery)
  types/           ← TypeScript type definitions (types/index.ts)
  routes/          ← Route definitions
```

### Context Providers (Frontend State)

| Context             | Hook                | Key State                                                             |
| ------------------- | ------------------- | --------------------------------------------------------------------- |
| GameContext         | `useGame()`         | sessionId, currentImage, stats, history, attributes, ending, selfMode |
| ChatContext         | `useChat()`         | messages, inputText, instructionType, isStreaming                     |
| SettingsContext     | `useSettings()`     | difficulty, language, nsfwMode, imageProvider, changeSettings         |
| NotificationContext | `useNotification()` | notifications[]                                                       |

### API Endpoints Summary

| Prefix          | Router                 | Key Operations                        |
| --------------- | ---------------------- | ------------------------------------- |
| `/game`         | game_router.py         | play (SSE), start, session/:id, reset |
| `/settings`     | settings_router.py     | user GET/PUT, self-profile            |
| `/achievements` | achievements_router.py | list, detail, unlocked                |
| `/gallery`      | gallery_router.py      | list (paginated), detail, delete      |
