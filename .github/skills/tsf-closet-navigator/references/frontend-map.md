# フロントエンド アーキテクチャマップ

> 最終検証: 2026-08-10 | 対象: `frontend/src`、`frontend/tests/e2e`

## 起動とルーティング

- `main.tsx`: `BrowserRouter` と全体 Context を提供する。
- `App.tsx`: `useLocation()` で画面を切り替える。通常ゲームのSSE送信ボディもここで組み立てる。
- `routes/index.tsx`: パス定数と `getGameSessionPath()` を定義する。RouterProviderはまだ使用しない。

| パス | 画面 | 備考 |
| --- | --- | --- |
| `/`、`/play`、`/play/new`、`/play/:sessionId` | `GamePlayScreen` | 通常ゲーム、新規開始、復元 |
| `/gallery`、`/gallery/:sessionId` | `GalleryScreen` | セッション/履歴/お気に入り |
| `/endings` | `EndingsScreen` | 実験設定で有効化 |
| `/achievements` | `AchievementsScreen` | 実績一覧 |
| `/settings` | `SettingsScreen` | 設定、メモリ、TTS |
| `/adventure`、`/adventure/:runId` | `AdventureScreen` | 実験設定で有効化、専用Provider |

## Context

### 全体Provider

`main.tsx` は外側から `SettingsProvider` → `NotificationProvider` → `GameProvider` → `ChatProvider` の順に提供する。

| Context | Hook | 主な状態/責務 |
| --- | --- | --- |
| `SettingsContext` | `useSettings()` | 言語、難易度、生成プロバイダー、inpaint、履歴遡及、プレイメモ設定、複数人物、TTS、Adventure等の設定と保存 |
| `NotificationContext` | `useNotification()` | 通知キューと実績通知 |
| `GameContext` | `useGame()` | Session、History、画像、stats、属性、会話復元、SessionCharacter、セッションプレイメモ |
| `ChatContext` | `useChat()` | メッセージ、入力、指示タイプ、添付、一時ID、ストリーミング、音声再生状態 |

### Adventure専用Provider

`App.tsx` は `/adventure` 配下だけを `AdventureProvider` で包む。

`AdventureContext` は Run/Template、activeRun、セットアップ生成、ターン/画像ストリーム、フェーズ、逐次ナラティブ、エラーを管理する。通常ゲームの `GameContext` や `useGameSSE` に統合しない。

## 主な設定境界

`SettingsContext` の追加機能は既定値と保存先を確認して変更する。

- `experimentalAdventureEnabled`: Adventure画面のゲート
- `playMemoryEnabled`、`playMemorySystemEnabled`、`playMemoryUserEnabled`: セッションプレイメモ
- `historyLookbackCount`、`historyLookbackTargets`: 指示タイプ別の履歴遡及
- `respectClothingLayers`: 衣装レイヤー可視性。既定OFF
- `enableMultiplePeople`: 複数人画像生成
- `multiCharacterPanelEnabled`: SessionCharacterのプロンプト反映
- `adventureEnableCompositeScene`: Adventureの背景/人物合成初期値
- `tts*`: AivisSpeech設定
- `memoryText`: ユーザー単位の長期メモリ本文

## Hook

| Hook | 目的 |
| --- | --- |
| `useSession` | セッション開始/復元、キャラクター読込、GameContext更新 |
| `useSSE` | GET/POST SSEの解析、停止、エラー処理 |
| `useGameSSE` | 通常ゲームSSEを4つの全体Contextへ接続 |
| `useAchievements` | 実績一覧/詳細取得 |
| `useGallery` | ギャラリーの検索、ページング、削除 |
| `useInfiniteScroll` | IntersectionObserverによる追加読込 |
| `useTagSuggest` | タグ候補取得 |
| `useTransparentImage` | 透過画像の読込とフォールバック |

## APIモジュール

| ファイル | 主な公開操作 |
| --- | --- |
| `apis/game.ts` | プロンプトプレビュー、指示候補、立ち絵、削除、履歴分岐 |
| `apis/adventure.ts` | Template/Run CRUD、セットアップ、ターン/画像SSE、設定、URL正規化 |
| `apis/characters.ts` | SessionCharacter、主人公確保、Preset、人物タグ |
| `apis/favorites.ts` | お気に入り一覧、追加、ラベル変更、削除、toggle |
| `apis/gallery.ts` | セッション/履歴、フレーム、詳細、削除、要約、エクスポート |
| `apis/memory.ts` | ユーザーメモ本文、生成ジョブ、状態、取消、分析DL |
| `apis/settings.ts` | セルフプロフィール生成/保存/取得 |
| `apis/speechSynthesis.ts` | AivisSpeech導入、起動、話者、合成 |
| `apis/achievements.ts` | 実績一覧/詳細 |
| `apis/anlas.ts` | NovelAI Anlas残高 |

## UI構成

```text
components/
  GamePlayScreen.tsx          通常ゲームの画像、履歴、チャット統合
  ImagePreviewModal.tsx       履歴画像と対応テキストのプレビュー
  HistoryPanel.tsx            履歴ナビゲーション
  AttributeSection.tsx        現実改変属性
  InpaintModal.tsx            マスク編集
  SessionListModal.tsx        セッション一覧/復元
  session/BranchSessionDialog.tsx

  chat/
    WelcomeScreen.tsx         キャラクター/モード選択
    ChatInput.tsx             指示と送信タイプ選択、添付
    ChatMessageList.tsx       メッセージ一覧
    ChatMessage.tsx           表示、削除、音声操作
    AudioControlBar.tsx       TTS再生

  adventure/
    AdventureScreen.tsx       セットアップ、Run、ターン履歴、画像
    AdventureImagePromptModal.tsx
    AdventureGiftShopModal.tsx    romance のギフト購入（gift_id 送信）
    AdventureAttributeModal.tsx   romance の属性付与（現実改変プレフィックス組み立て）

  gallery/
    GalleryScreen.tsx         セッション/履歴/お気に入り表示と検索
    GalleryCard.tsx
    ComparisonSliderModal.tsx 画像比較
    PlaySummaryModal.tsx
    SharePreviewCard.tsx

  panel/
    CharacterStatePanel.tsx   通常ゲームの人物状態
    CharacterPanel.tsx        複数人物編集
    CharacterPresetPicker.tsx

  settings/
    SettingsScreen.tsx
    PlayMemorySettings.tsx    セッションプレイメモ設定
    MemorySettings.tsx        ユーザーメモ生成/編集
    SpeechSynthesisSettings.tsx
    SelfProfileEditor.tsx
```

## 主要型

- `InstructionType`: `dress_up | reality_alter | conversation | action | image_only`
- `HistoryItem`: 指示、画像、心境、前後記述、タグ、seed、情景画像
- `SessionCharacter` / `CharacterPreset`: 複数人物と再利用定義
- `PlayMemoryState`: セッションの自動/ユーザーメモ本文とON/OFF
- `ChatMessage` / `PendingMessageIdentity`: 履歴ID確定前後のメッセージ対応
- `AdventureRun` / `AdventureTurn` / `AdventureImagePrompt`: Adventure API契約
- `HistoryLookbackTargets`: 指示タイプごとの履歴遡及対象

## i18n、CSS、テスト

- i18nは `frontend/src/i18n.ts` に日本語/英語リソースを持つ。新規UI文字列は両言語を更新する。
- 各大規模画面は隣接CSSを持つ。既存レイアウトを保ち、変更画面だけ確認する。
- Context単体テストは `frontend/src/contexts/tests/`、E2Eは `frontend/tests/e2e/`。
- 主な対象E2E: `action-mode.spec.ts`、`image-only-preview.spec.ts`、`adventure-mode.spec.ts`、`adventure-portrait-alpha.spec.ts`。
