# Data Flow Patterns

> Last verified: 2026-03-07 | Update when: new integration patterns or data pathways are introduced

## Main Game Loop (Transformation)

```
User Input (ChatInput)
  │  instructionType: dress_up | reality_change | conversation
  │  text: instruction string
  │  attachedImage?: base64 (optional mask/reference)
  ▼
useSSE.startStream()
  │  POST /game/play/stream (SSE)
  │  Body: { session_id, instruction, instruction_type, language,
  │          nsfw_mode, difficulty, change_settings, inpaint_settings,
  │          mask_base64?, self_mode?, precise_references? }
  ▼
[Backend] GameService.play_with_stream()
  │
  ├─ 1. LLM: Generate image edit prompt (instruction → English prompt)
  │     └─ llm_service.generate_image_prompt()
  │
  ├─ 2. LLM: Generate feeling text (character reaction)
  │     └─ llm_service.generate_feeling()
  │     └─ SSE: event=text, data=feeling chunks
  │
  ├─ 3. Image Generation (parallel with step 2)
  │     ├─ ComfyUI inpaint (local)
  │     ├─ OpenRouter multi-modal (Gemini/etc)
  │     └─ NovelAI (via anlas)
  │     └─ SSE: event=image, data={base64, historyId, seed}
  │
  ├─ 4. Tag Classification (costume/exposure/age)
  │     └─ tag_classifier.classify()
  │
  ├─ 5. Stats Update (bloom/shame/adaptation calculation)
  │     └─ SSE: event=stats, data={bloom, shame, adaptation}
  │
  ├─ 6. Critical Point Check (25/50/75/100% thresholds)
  │     └─ SSE: event=critical (if threshold crossed)
  │
  ├─ 7. Achievement Check
  │     └─ SSE: event=achievement (if newly unlocked)
  │
  ├─ 8. Ending Check
  │     └─ summary_service.check_ending()
  │     └─ SSE: event=ending (if triggered)
  │
  └─ 9. Complete
        └─ SSE: event=complete, data={historyId, transformationCount}
  ▼
[Frontend] useSSE callbacks
  ├─ onText    → ChatContext.ADD_MESSAGE
  ├─ onImage   → GameContext.SET_CURRENT_IMAGE + History updated
  ├─ onStats   → GameContext.UPDATE_STATS
  ├─ onCritical→ Visual effect (ParameterBars animation)
  ├─ onAchievement → NotificationContext toast
  ├─ onEnding  → GameContext.SET_ENDING → EndingModal
  └─ onComplete→ isTransforming=false, cleanup
```

## Session Lifecycle

```
Character Select (WelcomeScreen)
  │  POST /game/start { character_id, difficulty, nsfw_mode }
  ▼
Session Created (DB: Session + SessionStats rows)
  │  Response: { session_id, character, stats, current_image_url }
  ▼
GameContext.START_SESSION dispatched
  │  sessionId stored, image loaded, stats initialized
  ▼
Game Loop (transformations repeat)
  ▼
Ending Triggered OR User Resets
  │  POST /game/session (DELETE) OR EndingModal shown
  ▼
Session Deactivated (DB: session.active = false)
```

## Settings Flow

```
SettingsScreen / SettingsContext
  │  useSettings().updateDifficulty/updateLanguage/toggleNsfw/etc.
  ▼
PUT /settings/user { difficulty, language, nsfw_mode, ... }
  ▼
[Backend] settings_service → DB: User row updated
  ▼
SettingsContext state updated (local)
```

## Image Generation Pipeline

```
Instruction + Current Image
  ▼
GameService._generate_image_edit_prompt()
  │  LLM generates English editing prompt from instruction
  ▼
                ┌─────────────┬──────────────┬────────────┐
                │  ComfyUI    │ OpenRouter   │ NovelAI    │
                │  (local)    │ (cloud)      │ (cloud)    │
                │  inpaint    │ multi-modal  │ img2img    │
                │  workflow    │ Gemini/etc   │ via SDK    │
                └──────┬──────┴──────┬───────┴─────┬──────┘
                       ▼             ▼             ▼
                    PNG bytes     PNG bytes     PNG bytes
                       │             │             │
                       └─────────────┴─────────────┘
                                     ▼
                           Save to history_images/
                           Return base64 via SSE
```

## State Management Architecture

```
                      React Context Layer
   ┌──────────────┬──────────────┬──────────────┬────────────────┐
   │ GameContext   │ ChatContext  │ SettingsCtx  │ NotificationCtx│
   │ (session,    │ (messages,   │ (preferences,│ (toasts)       │
   │  image,      │  input,      │  providers)  │                │
   │  stats,      │  streaming)  │              │                │
   │  history)    │              │              │                │
   └──────┬───────┴──────┬───────┴──────┬───────┴────────┬───────┘
          │              │              │                │
   ┌──────┴───────┐ ┌────┴──────┐ ┌────┴──────┐  ┌─────┴──────┐
   │ useSession   │ │ ChatInput │ │ Settings  │  │ Toast      │
   │ useSSE       │ │ ChatMsg   │ │ Screen    │  │ Container  │
   │ GamePlay     │ │ Container │ │           │  │            │
   └──────────────┘ └───────────┘ └───────────┘  └────────────┘
```

## Communication Patterns

| Pattern           | Usage                                                                    | Direction       |
| ----------------- | ------------------------------------------------------------------------ | --------------- |
| REST (fetch)      | Session CRUD, settings, gallery, achievements                            | Client ↔ Server |
| SSE (EventSource) | `/game/play/stream`, `/game/chat/stream`, `/game/improve-quality/stream` | Server → Client |
| No WebSocket      | SSE is the only real-time channel                                        | —               |

## Database Write Points

| Trigger             | Tables Written                                                   |
| ------------------- | ---------------------------------------------------------------- |
| Start session       | Session, SessionStats                                            |
| Each transformation | History, Conversation, TransformationTag, SessionStats (updated) |
| Add attribute       | SessionAttribute                                                 |
| Unlock achievement  | Achievement/AchievedEnding                                       |
| Update settings     | User                                                             |
| Save mask           | File system (data/preset_masks/)                                 |
