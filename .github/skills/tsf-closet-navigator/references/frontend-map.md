# フロントエンド アーキテクチャマップ

> 最終検証: 2026-03-07 | 更新条件: コンポーネント、Context、Hook、APIモジュールの追加・リネーム・削除時

## ルーティング (App.tsx)

| パス               | コンポーネント            | 備考                          |
| ------------------ | ------------------------ | ----------------------------- |
| `/`                | AppMain → GamePlayScreen | デフォルト: メインゲーム画面   |
| `/play/:sessionId` | AppMain → GamePlayScreen | セッション指定                 |
| `/play/new`        | AppMain → GamePlayScreen | 新規セッション（復元なし）     |
| `/gallery`         | GalleryScreen            |                               |
| `/endings`         | EndingsScreen            | 実験的機能フラグ               |
| `/achievements`    | AchievementsScreen       |                               |
| `/settings`        | SettingsScreen           |                               |

## Context プロバイダ

### GameContext (`useGame()`)

- **ファイル**: `frontend/src/contexts/GameContext.tsx`
- **状態**: sessionId, isActive, character, currentImage, stats, history[], attributes[], ending, selfMode, isTransforming, transformationCount
- **アクション**: START_SESSION, RESTORE_SESSION, UPDATE_STATS, ADD_HISTORY_ITEM, SET_CURRENT_IMAGE, SET_ENDING, SET_TRANSFORMING

### ChatContext (`useChat()`)

- **ファイル**: `frontend/src/contexts/ChatContext.tsx`
- **状態**: messages[], inputText, instructionType, attachedImage, isStreaming, highlightedMessageId
- **アクション**: ADD_MESSAGE, UPDATE_MESSAGE, SET_INPUT_TEXT, SET_INSTRUCTION_TYPE, SET_STREAMING

### SettingsContext (`useSettings()`)

- **ファイル**: `frontend/src/contexts/SettingsContext.tsx`
- **状態**: difficulty, language, nsfwMode, imageProvider, inpaintSettings, changeSettings, rightPanelOpen, preciseReferences, selfProfile, seed, experimentalEndingEnabled, showRealityAttributeNotification
- **アクション**: UPDATE_DIFFICULTY, UPDATE_LANGUAGE, TOGGLE_NSFW, SET_INPAINT_SETTINGS, UPDATE_CHANGE_SETTINGS

### NotificationContext (`useNotification()`)

- **ファイル**: `frontend/src/contexts/NotificationContext.tsx`
- **状態**: notifications[], maxNotifications
- **アクション**: ADD_NOTIFICATION, REMOVE_NOTIFICATION, CLEAR_ALL_NOTIFICATIONS

## カスタム Hook

| Hook              | ファイル                   | 目的                                                   |
| ----------------- | -------------------------- | ------------------------------------------------------ |
| `useSession`      | `hooks/useSession.ts`      | セッション CRUD、キャラクター読込、SSE更新ハンドラ       |
| `useSSE`          | `hooks/useSSE.ts`          | SSE イベントストリーム（text, image, stats, ending 等）  |
| `useAchievements` | `hooks/useAchievements.ts` | 実績一覧/詳細の取得                                     |
| `useGallery`      | `hooks/useGallery.ts`      | ギャラリーページネーション、詳細、削除                   |
| `useTagSuggest`   | `hooks/useTagSuggest.ts`   | タグ候補/分類                                           |

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

| モジュール   | ファイル               | エンドポイント                             |
| ------------ | ---------------------- | ------------------------------------------ |
| game         | `apis/game.ts`         | `previewPrompt()`, `deleteLatestHistory()` |
| settings     | `apis/settings.ts`     | GET/PUT ユーザー設定、セルフプロファイルCRUD |
| achievements | `apis/achievements.ts` | GET 一覧、詳細、解除済み                    |
| gallery      | `apis/gallery.ts`      | GET 一覧、詳細; DELETE 項目                 |
| anlas        | `apis/anlas.ts`        | GET 残高、POST ログイン                     |

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
│   ├── ChatContainer.tsx      ← チャットパネルラッパー
│   ├── ChatInput.tsx          ← ユーザー入力（テキスト + 指示タイプ選択）
│   ├── ChatMessage.tsx        ← 単一メッセージバブル
│   ├── ChatMessageList.tsx    ← メッセージリストスクロールコンテナ
│   └── WelcomeScreen.tsx      ← キャラクター選択 / セッション開始
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
│   ├── GalleryScreen.tsx      ← ギャラリーページ
│   ├── GalleryCard.tsx        ← ギャラリーサムネイル
│   ├── GalleryList.tsx        ← ギャラリーグリッド
│   ├── PlaySummaryModal.tsx   ← セッションサマリーオーバーレイ
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

| 型                    | 主要フィールド                                                                                                                                    |
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

## 国際化

- **設定**: `frontend/src/i18n.ts` — react-i18next セットアップ
- **ファイル**: `frontend/src/assets/` (ロケール)
- **対応言語**: ja / en
