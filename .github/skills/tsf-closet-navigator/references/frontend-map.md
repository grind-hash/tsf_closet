# フロントエンド アーキテクチャマップ

> 最終検証: 2026-05-02 | 更新条件: コンポーネント、Context、Hook、APIモジュールの追加・リネーム・削除時

## ルーティング (App.tsx + routes/index.tsx)

ルーティングは `main.tsx` の `BrowserRouter` 下で `App.tsx` が `useLocation()` により画面を切り替える方式。ルート定数とヘルパー `getGameSessionPath()` は `frontend/src/routes/index.tsx` に集約されている。

| パス               | コンポーネント            | 備考                                        |
| ------------------ | ------------------------ | ------------------------------------------- |
| `/`                | AppMain → GamePlayScreen | デフォルト: メインゲーム画面                  |
| `/play/:sessionId` | AppMain → GamePlayScreen | セッション指定                                 |
| `/play/new`        | AppMain → GamePlayScreen | 新規セッション（復元なし）                   |
| `/gallery`         | GalleryScreen            | `/gallery/:sessionId` もマッチ               |
| `/endings`         | EndingsScreen            | `experimentalEndingEnabled` フラグで制御     |
| `/achievements`    | AchievementsScreen       |                                             |
| `/settings`        | SettingsScreen           |                                             |

## Context プロバイダ

### GameContext (`useGame()`)

- **ファイル**: `frontend/src/contexts/GameContext.tsx`
- **状態**: sessionId, isActive, character, characters[], currentImage, currentHistoryIndex, stats, history[], attributes[], conversationHistory[], ending, selfMode, isTransforming, isLoading, error, feelingText, transformationCount, lastGeneratedSeed, lastSurroundingsImage
- **アクション**: START_SESSION, RESTORE_SESSION, SET_CHARACTERS, UPDATE_STATS, ADD_HISTORY_ITEM, SET_HISTORY, SET_CURRENT_IMAGE, SET_ENDING, NAVIGATE_HISTORY, SET_TRANSFORMING, SET_LOADING, SET_ERROR, SET_ATTRIBUTES, ADD_ATTRIBUTE, REMOVE_ATTRIBUTE, SET_SELF_MODE, SET_CONVERSATION_HISTORY, APPEND_FEELING_TEXT, SET_FEELING_TEXT, SET_TRANSFORMATION_COUNT, SET_LAST_GENERATED_SEED, SET_LAST_SURROUNDINGS_IMAGE, REMOVE_HISTORY_ENTRY, CLEAR_SESSION

### ChatContext (`useChat()`)

- **ファイル**: `frontend/src/contexts/ChatContext.tsx`
- **状態**: messages[], inputText, instructionType, attachedImage, isStreaming, highlightedMessageId, scrollToMessageId, pendingIdentities[], messageListRef
- **アクション**: SET_MESSAGES, ADD_MESSAGE, UPDATE_MESSAGE, APPEND_TO_MESSAGE, SET_MESSAGE_STREAMING, SET_INPUT_TEXT, SET_INSTRUCTION_TYPE, SET_ATTACHED_IMAGE, SET_STREAMING, SET_HIGHLIGHTED_MESSAGE, SET_SCROLL_TO_MESSAGE, UPSERT_PENDING_IDENTITY, ATTACH_FEELING_MESSAGE, RESOLVE_PENDING_IDENTITY, FINALIZE_PENDING_IDENTITY, FAIL_PENDING_IDENTITY, REPLACE_MESSAGE_ID, CLEAR_INPUT, CLEAR_MESSAGES
- **補助**: `getLatestPendingIdentity()`, `resolvePendingIdentity(tempToken, historyId)` などをヘルパーとして公開

### SettingsContext (`useSettings()`)

- **ファイル**: `frontend/src/contexts/SettingsContext.tsx`
- **状態**: difficulty, language, nsfwMode, imageProvider, totalCost, showCost, anlasBalance, defaultInstructionType, inpaintSettings, inpaintEnabled, inpaintMask, changeSettings, showAchievementNotifications, showRealityAttributeNotification, experimentalEndingEnabled, soundEnabled, soundVolume, rightPanelOpen, preciseReferences, selfProfile, seed, enableSurroundingsImage, surroundingsIncludePeople, fontFamily, clothingColorConsistency, linkChatToImage, enableMultiplePeople, novelaiTextModel, novelaiTier
- **アクション**: SET_DIFFICULTY, SET_LANGUAGE, SET_NSFW_MODE / TOGGLE_NSFW, SET_IMAGE_PROVIDER, SET_TOTAL_COST / ADD_TOTAL_COST / RESET_TOTAL_COST, SET_SHOW_COST, SET_ANLAS_BALANCE, SET_DEFAULT_INSTRUCTION_TYPE, SET_INPAINT_SETTINGS, SET_INPAINT_ENABLED, SET_INPAINT_MASK, SET_CHANGE_SETTINGS ほか設定ごとの SET_/TOGGLE_ アクション多数
- **補助**: 初期化時に `localStorage` とサーバー設定をマージし、`PUT /settings` への永続化を担当

### NotificationContext (`useNotification()`)

- **ファイル**: `frontend/src/contexts/NotificationContext.tsx`
- **状態**: notifications[], maxNotifications
- **アクション**: ADD_NOTIFICATION, REMOVE_NOTIFICATION, CLEAR_ALL_NOTIFICATIONS
- **ヘルパー**: `showNotification(...)`, `showAchievementNotification(...)`

## カスタム Hook

| Hook              | ファイル                   | 目的                                                                                                       |
| ----------------- | -------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `useSession`      | `hooks/useSession.ts`      | セッション CRUD、キャラクター読込、SSE更新ハンドラ                                                               |
| `useSSE`          | `hooks/useSSE.ts`          | 汎用 SSE イベントパーサ (GET=EventSource / POST=fetch)。コールバック`onText/onImage/onStats/...`               |
| `useGameSSE`      | `hooks/useGameSSE.ts`      | `useSSE` をゲーム Context と統合した上位ラッパー。`App.tsx`/`GamePlayScreen` はこちらを利用             |
| `useAchievements` | `hooks/useAchievements.ts` | 実績一覧/詳細の取得                                                                                         |
| `useGallery`      | `hooks/useGallery.ts`      | ギャラリーページネーション、詳細、削除                                                                       |
| `useTagSuggest`   | `hooks/useTagSuggest.ts`   | タグ候補/分類                                                                                               |

### useSSE イベント一覧

| イベント                  | コールバック                                          | データ                     |
| ------------------------- | ---------------------------------------------------- | -------------------------- |
| `text`                    | `onText(chunk)`                                      | テキストチャンク（逐次）    |
| `image`                   | `onImage(base64, historyId, seed?)`                  | 生成画像                    |
| `surroundings_image`      | `onSurroundingsImage(base64, historyId, seed?)`      | 情景画像                    |
| `stats`                   | `onStats({bloom, shame, adaptation})`                | 更新されたステータス        |
| `critical`                | `onCritical({threshold, name, effect_type, speech})` | 臨界点イベント              |
| `ending`                  | `onEnding({ending_id, title, ...})`                  | ゲームエンディング          |
| `achievement`             | `onAchievement({achievement_id, name, ...})`         | 実績解除                    |
| `complete`                | `onComplete(historyId, transformationCount)`         | ストリーム完了              |
| `cost`                    | `onCost(cost)`                                       | API コスト                  |
| `anlas`                   | `onAnlas(balance)`                                   | NovelAI 残高更新            |
| `reality_attribute_added` | `onRealityAttributeAdded({id, text})`                | 新規属性追加                |
| `error`                   | `onError(message)`                                   | エラー                      |

## API モジュール

| モジュール   | ファイル               | 主なエクスポート                                                                                                                       |
| ------------ | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| game         | `apis/game.ts`         | `previewPrompt()`, `deleteLatestHistory()`, `deleteConversation()`, `deleteConversationMessage()`, `deleteHistoryEntry()`            |
| settings     | `apis/settings.ts`     | `getSelfProfile()`, `generateSelfProfile()`, `saveSelfProfile()`（`/settings` 本体は `SettingsContext` が直接 fetch）         |
| achievements | `apis/achievements.ts` | `fetchAchievementsList()`, `fetchAchievementDetail()`                                                                                |
| gallery      | `apis/gallery.ts`      | `fetchGalleryList()`, `fetchGalleryItem()`, `deleteGalleryItem()`, `getSessionSummary()`, `generateSessionSummary()`                  |
| anlas        | `apis/anlas.ts`        | `fetchAnlasBalance()`                                                                                                                |

## コンポーネントツリー

```
components/
├── GamePlayScreen.tsx         ← メインゲーム画面（画像 + チャット + パネル）
├── HistoryPanel.tsx           ← 変身履歴サイドバー
├── ParameterBars.tsx          ← ステータス表示（bloom/shame/adaptation）
├── AttributeSection.tsx       ← 現実改変属性リスト
├── EndingModal.tsx            ← ゲームエンディングオーバーレイ
├── SessionListModal.tsx       ← セッション一覧/復元
├── InpaintModal.tsx           ← マスクベース画像編集
├── ImagePreviewModal.tsx      ← フルサイズ画像ビューア
├── NovelAIWarningModal.tsx    ← NovelAI サブスクリプション警告
├── ApiKeyConsentModal.tsx     ← APIキー同意ダイアログ
├── CustomImageSizeWarningModal.tsx
│
├── chat/
│   ├── ChatInput.tsx          ← ユーザー入力（テキスト + 指示タイプ選択 + 添付画像）
│   ├── ChatMessage.tsx        ← 単一メッセージバブル（削除ボタン含む）
│   ├── ChatMessageList.tsx    ← メッセージリストスクロールコンテナ
│   └── WelcomeScreen.tsx      ← キャラクター選択 / セッション開始
│   (注: ChatContainer.tsx は削除済み。チャット領域は GamePlayScreen が直接構成)
│
├── layout/
│   ├── MainLayout.tsx         ← 2カラムレイアウトフレーム
│   ├── RightPanel.tsx         ← 右サイドバー（履歴 + 属性）
│   └── SideMenu.tsx           ← ナビゲーションサイドバー
│
├── settings/
│   ├── SettingsScreen.tsx     ← 設定ページ
│   └── SelfProfileEditor.tsx  ← セルフモード性格エディタ
│
├── gallery/
│   ├── GalleryScreen.tsx      ← ギャラリーページ（セッション / 履歴両ビューを持つ）
│   ├── GalleryCard.tsx        ← ギャラリーサムネイル
│   ├── GalleryList.tsx        ← ギャラリーグリッド
│   ├── PlaySummaryModal.tsx   ← セッションサマリーオーバーレイ（LLM生成要約）
│   └── SharePreviewCard.tsx   ← 共有画像プレビュー
│
├── achievements/
│   ├── AchievementsScreen.tsx ← 実績ページ
│   ├── AchievementCard.tsx    ← 実績カード表示
│   └── AchievementToast.tsx   ← 実績解除トースト通知
│
├── endings/
│   └── EndingsScreen.tsx      ← エンディングコレクションページ
│
├── panel/
│   └── CharacterStatePanel.tsx ← キャラクター状態パネル
│
├── notifications/
│   └── NotificationContainer.tsx ← トースト通知レイヤー
│
└── ui/
    └── ImageOverlay.tsx       ← 画像ローディングオーバーレイ
```

## 型定義 (`types/index.ts`)

主要型の一覧。完全なフィールドセットはソースを参照。

| 型                            | 用途                                                                                                       |
| ----------------------------- | --------------------------------------------------------------------------------------------------------- |
| `SessionStats`                | bloom, shame, adaptation, passedCriticalPoints[], difficulty, nsfwMode                                    |
| `HistoryItem`                 | id, instruction, imageUrl, feelingText, before/after descriptions, instructionType, タグ三要素, seed       |
| `Character` / `Ending`        | キャラクター・エンディングメタデータ                                                                       |
| `DifficultyPreset`            | 難易度プリセット                                                                                              |
| `ChatMessage`                 | id, role, content, createdAt, instructionType, relatedHistoryId, isStreaming, isFeelingText, surroundingsImageUrl |
| `PendingMessageIdentity`      | tempToken と historyId の仮をぶしトークンマッピング（ストリーミング中の ID 解決に使用）                  |
| `InstructionType`             | `dress_up` \| `reality_alter` \| `reality_change` \| `conversation` \| `action` など（ソース参照）          |
| `ChangeSettings`              | preserveElements[], changeScope, customPreserveText                                                       |
| `InpaintSettings`             | enabled, brushSize, eraserMode, i2iStrength, maskStrength, invertMask, negativePrompt, promptOverride     |
| `InpaintMaskState`            | base64マスクとメタデータ                                                                                     |
| `PreciseReference`            | 精密参照画像 (character/style/character&style)                                                            |
| `SessionAttribute`            | id, text                                                                                                  |
| `ConversationMessage`         | id, role, content, createdAt, instruction_type                                                            |
| `SessionSummary`              | sessionId, characterId, characterName, thumbnailUrl, transformationCount, isActive, createdAt             |
| `GalleryItem` / `GallerySession` | ギャラリー一覧表示データ                                                                                  |
| `MaskInfo` / `MaskListResponse` / `MaskPreset` | マスク関連                                                                                       |
| `SSEStatsData` / `SSEEndingData` / `SSECriticalData` / `SSEAchievementData` / `SurroundingsImageEvent` | SSEイベントペイロード |
| `Achievement` / `UserAchievementStatus`        | 実績データ                                                                                                |
| `AnlasBalance`                | NovelAI Anlas 残高                                                                                         |

## 国際化

- **設定**: `frontend/src/i18n.ts` — react-i18next セットアップ
- **ファイル**: `frontend/src/assets/` (ロケール)
- **対応言語**: ja / en
