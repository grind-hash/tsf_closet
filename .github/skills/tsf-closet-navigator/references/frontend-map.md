# Frontend Architecture Map

> Last verified: 2026-03-07 | Update when: components, contexts, hooks, or API modules are added/renamed/removed

## Routing (App.tsx)

| Path               | Component                | Notes                    |
| ------------------ | ------------------------ | ------------------------ |
| `/`                | AppMain → GamePlayScreen | Default: main game       |
| `/play/:sessionId` | AppMain → GamePlayScreen | Session-specific         |
| `/play/new`        | AppMain → GamePlayScreen | New session (no restore) |
| `/gallery`         | GalleryScreen            |                          |
| `/endings`         | EndingsScreen            | Experimental flag        |
| `/achievements`    | AchievementsScreen       |                          |
| `/settings`        | SettingsScreen           |                          |

## Context Providers

### GameContext (`useGame()`)

- **File**: `frontend/src/contexts/GameContext.tsx`
- **State**: sessionId, isActive, character, currentImage, stats, history[], attributes[], ending, selfMode, isTransforming, transformationCount
- **Actions**: START_SESSION, RESTORE_SESSION, UPDATE_STATS, ADD_HISTORY_ITEM, SET_CURRENT_IMAGE, SET_ENDING, SET_TRANSFORMING

### ChatContext (`useChat()`)

- **File**: `frontend/src/contexts/ChatContext.tsx`
- **State**: messages[], inputText, instructionType, attachedImage, isStreaming, highlightedMessageId
- **Actions**: ADD_MESSAGE, UPDATE_MESSAGE, SET_INPUT_TEXT, SET_INSTRUCTION_TYPE, SET_STREAMING

### SettingsContext (`useSettings()`)

- **File**: `frontend/src/contexts/SettingsContext.tsx`
- **State**: difficulty, language, nsfwMode, imageProvider, inpaintSettings, changeSettings, rightPanelOpen, preciseReferences, selfProfile, seed, experimentalEndingEnabled, showRealityAttributeNotification
- **Actions**: UPDATE_DIFFICULTY, UPDATE_LANGUAGE, TOGGLE_NSFW, SET_INPAINT_SETTINGS, UPDATE_CHANGE_SETTINGS

### NotificationContext (`useNotification()`)

- **File**: `frontend/src/contexts/NotificationContext.tsx`
- **State**: notifications[], maxNotifications
- **Actions**: ADD_NOTIFICATION, REMOVE_NOTIFICATION, CLEAR_ALL_NOTIFICATIONS

## Custom Hooks

| Hook              | File                       | Purpose                                                          |
| ----------------- | -------------------------- | ---------------------------------------------------------------- |
| `useSession`      | `hooks/useSession.ts`      | Session CRUD, character loading, SSE update handlers             |
| `useSSE`          | `hooks/useSSE.ts`          | SSE event stream (text, image, stats, ending, achievement, etc.) |
| `useAchievements` | `hooks/useAchievements.ts` | Achievement list/detail fetching                                 |
| `useGallery`      | `hooks/useGallery.ts`      | Gallery pagination, detail, delete                               |
| `useTagSuggest`   | `hooks/useTagSuggest.ts`   | Tag suggestion/classification                                    |

### useSSE Event Types

| Event                     | Callback                                             | Data                    |
| ------------------------- | ---------------------------------------------------- | ----------------------- |
| `text`                    | `onText(chunk)`                                      | Text chunks (streaming) |
| `image`                   | `onImage(base64, historyId, seed?)`                  | Generated image         |
| `surroundings_image`      | `onSurroundingsImage(base64, historyId, seed?)`      | Scenery image           |
| `stats`                   | `onStats({bloom, shame, adaptation})`                | Updated stats           |
| `critical`                | `onCritical({threshold, name, effect_type, speech})` | Critical point event    |
| `ending`                  | `onEnding({ending_id, title, ...})`                  | Game ending             |
| `achievement`             | `onAchievement({achievement_id, name, ...})`         | Unlocked achievement    |
| `complete`                | `onComplete(historyId, transformationCount)`         | Stream finished         |
| `cost`                    | `onCost(cost)`                                       | API cost                |
| `anlas`                   | `onAnlas(balance)`                                   | NovelAI balance update  |
| `reality_attribute_added` | `onRealityAttributeAdded({id, text})`                | New attribute           |
| `error`                   | `onError(message)`                                   | Error                   |

## API Modules

| Module       | File                   | Endpoints                                  |
| ------------ | ---------------------- | ------------------------------------------ |
| game         | `apis/game.ts`         | `previewPrompt()`, `deleteLatestHistory()` |
| settings     | `apis/settings.ts`     | GET/PUT user settings, self-profile CRUD   |
| achievements | `apis/achievements.ts` | GET list, detail, unlocked                 |
| gallery      | `apis/gallery.ts`      | GET list, detail; DELETE item              |
| anlas        | `apis/anlas.ts`        | GET balance, POST login                    |

## Components Tree

```
components/
├── GamePlayScreen.tsx         ← Main game view (image + chat + panels)
├── HistoryPanel.tsx           ← Transformation history sidebar
├── ParameterBars.tsx          ← Stats display (bloom/shame/adaptation)
├── AttributeSection.tsx       ← Reality attributes list
├── EndingModal.tsx            ← Game ending overlay
├── SessionListModal.tsx       ← Session browser/restore
├── InpaintModal.tsx           ← Mask-based image editing
├── ImagePreviewModal.tsx      ← Full-size image viewer
├── NovelAIWarningModal.tsx    ← NovelAI subscription warning
├── ApiKeyConsentModal.tsx     ← API key consent dialog
├── CustomImageSizeWarningModal.tsx
│
├── chat/
│   ├── ChatContainer.tsx      ← Chat panel wrapper
│   ├── ChatInput.tsx          ← User input (text + instruction type selector)
│   ├── ChatMessage.tsx        ← Single message bubble
│   ├── ChatMessageList.tsx    ← Message list scroll container
│   └── WelcomeScreen.tsx      ← Character select / session start
│
├── layout/
│   ├── MainLayout.tsx         ← Two-column layout frame
│   ├── RightPanel.tsx         ← Right sidebar (history + attributes)
│   └── SideMenu.tsx           ← Navigation sidebar
│
├── settings/
│   ├── SettingsScreen.tsx     ← Settings page
│   └── SelfProfileEditor.tsx  ← Self-mode personality editor
│
├── gallery/
│   ├── GalleryScreen.tsx      ← Gallery page
│   ├── GalleryCard.tsx        ← Single gallery thumbnail
│   ├── GalleryList.tsx        ← Gallery grid
│   ├── PlaySummaryModal.tsx   ← Session summary overlay
│   └── SharePreviewCard.tsx   ← Share image preview
│
├── achievements/
│   ├── AchievementsScreen.tsx ← Achievements page
│   ├── AchievementCard.tsx    ← Single achievement display
│   └── AchievementToast.tsx   ← Unlock notification toast
│
├── endings/
│   └── EndingsScreen.tsx      ← Endings collection page
│
├── panel/
│   └── CharacterStatePanel.tsx ← Character status panel
│
├── notifications/
│   └── NotificationContainer.tsx ← Toast notification layer
│
└── ui/
    └── ImageOverlay.tsx       ← Image loading overlay
```

## Type Definitions (`types/index.ts`)

| Type                  | Key Fields                                                                                                                                        |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SessionStats`        | bloom, shame, adaptation, passedCriticalPoints[], difficulty, nsfwMode                                                                            |
| `HistoryItem`         | id, instruction, imageUrl, feelingText, beforeDescription, afterDescription, instructionType, costumeCategory, exposureLevel, ageImpression, seed |
| `Character`           | id, name, thumbnail, description                                                                                                                  |
| `Ending`              | id, name, description, triggerCondition, badge, speech, summary                                                                                   |
| `ChatMessage`         | role, content, timestamp                                                                                                                          |
| `InstructionType`     | "dress_up" \| "reality_change" \| "conversation"                                                                                                  |
| `ChangeSettings`      | preserveElements[], changeScope, customPreserveText                                                                                               |
| `InpaintSettings`     | enabled, brushSize, eraserMode, i2iStrength, maskStrength, invertMask, negativePrompt, promptOverride                                             |
| `SessionAttribute`    | id, text                                                                                                                                          |
| `ConversationMessage` | id, role, content, createdAt, instruction_type                                                                                                    |
| `SessionSummary`      | sessionId, characterId, characterName, thumbnailUrl, transformationCount, isActive, createdAt                                                     |
| `MaskInfo`            | id, name, type, url, created_at                                                                                                                   |

## Internationalization

- **Config**: `frontend/src/i18n.ts` — react-i18next setup
- **Files**: `frontend/src/assets/` (locales)
- **Languages**: ja / en
