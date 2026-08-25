# フロントエンド アーキテクチャマップ

> 最終検証: 2026-08-10 | 対象: `frontend/src`、`frontend/tests/e2e`

## 起動とルーティング

- `main.tsx`: `BrowserRouter` と全体 Context を提供する。
- `App.tsx`: `useLocation()` で画面を切り替える。通常ゲームのSSE送信ボディもここで組み立てる。
- `routes/index.tsx`: パス定数と `getGameSessionPath()` を定義する。RouterProviderはまだ使用しない。

| パス                                          | 画面                 | 備考                                           |
| --------------------------------------------- | -------------------- | ---------------------------------------------- |
| `/`、`/play`、`/play/new`、`/play/:sessionId` | `GamePlayScreen`     | 通常ゲーム、新規開始、復元                     |
| `/gallery`、`/gallery/:sessionId`             | `GalleryScreen`      | セッション/履歴/お気に入り                     |
| `/endings`                                    | `EndingsScreen`      | 実験設定で有効化                               |
| `/achievements`                               | `AchievementsScreen` | 実績一覧                                       |
| `/settings`                                   | `SettingsScreen`     | 設定、メモリ、TTS                              |
| `/adventure`、`/adventure/:runId`             | `AdventureScreen`    | 実験設定で有効化、専用Provider                 |
| `/bgm-test`                                   | `BgmTestScreen`      | BGMカタログの試聴。実験設定(Adventure)で有効化 |
| `/prompt-expander`、`/prompt-expander/:sessionId` | `PromptExpanderScreen` | Prompt Expander（実験設定で有効化、専用Provider） |

## Context

### 全体Provider

`main.tsx` は外側から `SettingsProvider` → `NotificationProvider` → `GameProvider` → `ChatProvider` の順に提供する。

| Context               | Hook                | 主な状態/責務                                                                                             |
| --------------------- | ------------------- | --------------------------------------------------------------------------------------------------------- |
| `SettingsContext`     | `useSettings()`     | 言語、難易度、生成プロバイダー、inpaint、履歴遡及、プレイメモ設定、複数人物、TTS、Adventure等の設定と保存 |
| `NotificationContext` | `useNotification()` | 通知キューと実績通知                                                                                      |
| `GameContext`         | `useGame()`         | Session、History、画像、stats、属性、会話復元、SessionCharacter、セッションプレイメモ                     |
| `ChatContext`         | `useChat()`         | メッセージ、入力、指示タイプ、添付、一時ID、ストリーミング、音声再生状態                                  |

### Prompt Expander専用Provider

`App.tsx` は `/prompt-expander` 配下だけを `PromptExpanderProvider` で包む（`experimentalPromptExpanderEnabled` が OFF なら `/play/new` へリダイレクト）。

`PromptExpanderContext`（`usePromptExpander()`）は PE セッション一覧/詳細、エントリ、専用設定（`GET/PUT /api/prompt-expander/settings`、生成パラメータはこの設定そのもの）、作業欄状態（参照元、正/ネガの本文と拡張モード、キャラクタースロット）、`pendingExpansion`（欄直下のインライン結果カード。`target: positive|negative`）、`positiveOrigin`/`negativeOrigin`（「欄へ反映」した拡張のモードと指示。履歴メタデータ用。欄が空になると消える）、`pendingUsageWarn`（V5 利用上限の確認）、PE ローカルの `anlas` を持つ。拡張は欄右上の「拡張」ボタン（`expandPositive`/`expandNegative`）→ インライン結果カード（「欄へ反映」`applyExpansion` ／「この内容で生成」`generateFromExpansion`（カードは生成後も残す。原文はクリック時点の欄の内容）／「破棄」）で、下部の「生成」（`runGenerate`）は常に欄の内容をそのまま送る。`restoreEntry` は拡張ありのエントリなら原文を欄へ戻し変換結果を `pendingExpansion` として再現、それ以外は最終プロンプトを欄へ戻す（seed は設定 `restore_seed`=ON のときだけ戻す）。`regenerateEntry` はエントリのプロンプト/設定のまま seed を付けずに生成する。`suggestCharacters` は欄の下書きを `input_text` として送る。設定の `confirm_before_generate` / `inherit_source_prompts` は API には残るが UI の確認トグルは無い（継承トグルは i2i セクション）。通常ゲームの Context や `useGameSSE` には統合しない。

### Adventure専用Provider

`App.tsx` は `/adventure` 配下だけを `AdventureProvider` で包む。

`AdventureContext` は Run/Template、activeRun、セットアップ生成、ターン/画像ストリーム、フェーズ、逐次ナラティブ、エラーを管理する。 直前に開いた run ID は `lastRunId`（`utils/adventureLastRun.ts`、localStorage `adventure_last_run_id`）として公開し、Hub の再開バナーと SideMenu の「直前のシナリオへ」が参照する。通常ゲームの `GameContext` や `useGameSSE` に統合しない。

## 主な設定境界

`SettingsContext` の追加機能は既定値と保存先を確認して変更する。

- `experimentalAdventureEnabled`: Adventure画面のゲート
- `experimentalPromptExpanderEnabled`: Prompt Expander画面とメニュー、WelcomeScreen/Adventureピッカーの「Prompt Expander」入口のゲート
- `playMemoryEnabled`、`playMemorySystemEnabled`、`playMemoryUserEnabled`: セッションプレイメモ
- `historyLookbackCount`、`historyLookbackTargets`: 指示タイプ別の履歴遡及
- `respectClothingLayers`: 衣装レイヤー可視性。既定OFF
- `enableMultiplePeople`: 複数人画像生成
- `multiCharacterPanelEnabled`: SessionCharacterのプロンプト反映
- `adventureEnableCompositeScene`: Adventureの背景/人物合成初期値
- `novelaiImageModel` / `novelaiCuratedImageModel`: NovelAI画像モデル選択（NSFW用/非NSFW用、バックエンド永続）。選択肢と `isV5ImageModel` は `constants/novelaiImageModels.ts`。実効モデルとV5判定は context value の `effectiveNovelaiImageModel` / `isNovelaiV5Active` で取得する（V5時: 精密参照UIを無効化、`character_references` 不送信、`NovelaiUsageBar` で利用上限表示、使い切り時は生成前に確認ダイアログ）
- `anlasBalance.usage`: NovelAI V5 の利用上限（SSE `anlas` イベントと `/api/game/anlas` に同梱）
- `tts*`: AivisSpeech設定
- `memoryText`: ユーザー単位の長期メモリ本文

## Hook

| Hook                  | 目的                                                                                                                                                                                                                                                            |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `useSession`          | セッション開始/復元、キャラクター読込、GameContext更新                                                                                                                                                                                                          |
| `useSSE`              | GET/POST SSEの解析、停止、エラー処理                                                                                                                                                                                                                            |
| `useGameSSE`          | 通常ゲームSSEを4つの全体Contextへ接続                                                                                                                                                                                                                           |
| `useAchievements`     | 実績一覧/詳細取得                                                                                                                                                                                                                                               |
| `useGallery`          | ギャラリーの検索、ページング、削除                                                                                                                                                                                                                              |
| `useInfiniteScroll`   | IntersectionObserverによる追加読込                                                                                                                                                                                                                              |
| `useTagSuggest`       | タグ候補取得                                                                                                                                                                                                                                                    |
| `useTransparentImage` | 透過画像の読込とフォールバック                                                                                                                                                                                                                                  |
| `useAdventureBgm`     | Adventure BGMのループ再生、fade、autoplay/404対応。キー→URL対応はマウント時に `GET /api/adventure/bgm` で取得（未知キーは既定曲へ）。mute/volumeの永続化は `utils/bgmPreferences.ts`(localStorage `adventure_bgm_prefs`)へ集約し、BGMテスト画面と音量を共有する |

## APIモジュール

| ファイル                  | 主な公開操作                                                     |
| ------------------------- | ---------------------------------------------------------------- |
| `apis/game.ts`            | プロンプトプレビュー、指示候補、立ち絵、削除、履歴分岐           |
| `apis/adventure.ts`       | Template/Run CRUD、セットアップ、ターン/画像SSE、設定、URL正規化 |
| `apis/characters.ts`      | SessionCharacter、主人公確保、Preset、人物タグ                   |
| `apis/favorites.ts`       | お気に入り一覧、追加、ラベル変更、削除、toggle                   |
| `apis/gallery.ts`         | セッション/履歴、フレーム、詳細、削除、要約、エクスポート        |
| `apis/memory.ts`          | ユーザーメモ本文、生成ジョブ、状態、取消、分析DL                 |
| `apis/settings.ts`        | セルフプロフィール生成/保存/取得                                 |
| `apis/speechSynthesis.ts` | AivisSpeech導入、起動、話者、合成                                |
| `apis/achievements.ts`    | 実績一覧/詳細                                                    |
| `apis/anlas.ts`           | NovelAI Anlas残高                                                |
| `apis/promptExpander.ts`  | PE 設定/セッション/エントリ/アップロード/拡張/生成/キャラ提案、`promptExpanderImageUrl` |

## UI構成

```text
components/
  GamePlayScreen.tsx          通常ゲームの画像、履歴、チャット統合
  ImagePreviewModal.tsx       履歴画像と対応テキストのプレビュー
  HistoryPanel.tsx            履歴ナビゲーション
  AttributeSection.tsx        現実改変属性
  InpaintModal.tsx            マスク編集
  SessionListModal.tsx        セッション一覧/復元
  NovelaiUsageBar.tsx         NovelAI V5利用上限バー(HUD/設定パネル/設定画面共用、表示可否は親が判断)
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
    AdventureBgmControl.tsx       BGMボタン+ポップオーバー（mute/volume表示。再生は useAdventureBgm）

  bgm/
    BgmTestScreen.tsx         BGMカタログ全曲の一覧と試聴(単発再生、fade/loopなし)

  promptExpander/
    PromptExpanderScreen.tsx        セッション一覧/作業画面、Anlas・V5利用上限、同意モーダル。設定は MainLayout の rightPanel（開閉は localStorage `prompt_expander_settings_panel_open`）
    PromptExpanderSessionList.tsx   PEセッションの作成/改名/削除/一覧
    PromptExpanderSection.tsx       アコーディオン見出し（aria-expanded、右側ツールバー枠）。開閉は hooks/usePersistedSectionState（localStorage `prompt_expander_sections_open`）
    PromptExpanderDeleteButton.tsx  削除用アイコンボタン（ギャラリー同様ゴミ箱アイコン、ホバーで赤）。削除を赤塗り/赤枠のテキストボタンにしない
    PromptExpanderProgress.tsx      処理中表示（スピナー＋情報色ブルーの帯＋下端の不確定バー）。プロンプト化中と画像生成中で共用。警告色/アクセント色は使わない
    PromptExpanderComposer.tsx      セクション順: 生成パラメータ → プロンプト／指示（各欄右上にモード切替・「拡張」・「✨提案」）→ キャラクタープロンプト → i2i設定 → 「生成」
    PromptExpanderExpansionPanel.tsx 欄直下のインライン拡張結果カード（欄へ反映／この内容で生成／破棄）
    PromptExpanderEntryList.tsx / EntryCard.tsx  履歴セクション（絞り込みチップ すべて/通常/漫画/アップロード = localStorage `prompt_expander_entry_filter`、欄へ復元・このプロンプトで再生成・i2i元・通常プレイ/TSFシナリオへ・削除）。画像は右クリック保存が効くよう <button> で包まず div[role=button]。プレビューは ImagePreviewModal に className="prompt-expander-preview" で 96vw/96vh 拡大（閉じる/前後ボタンは枠内に置き直し、`positionLabel` で n / N、表示中カードは `--previewed` で強調）
    PromptExpanderSettingsPanel.tsx テキストモデル、「欄へ復元」でシードも復元する（`restore_seed`、既定OFF）、PEメモリ＋「メモリ情報を持ってくる」
    PromptExpanderUploadDialog.tsx  添付（履歴に残す／i2i元にする）
    PromptExpanderSuggestModal.tsx  メモリ＋欄の下書きからの好みキャラ提案（取得結果は閉じても保持し、次回開いてもリセットしない）
    PromptExpanderSourcePickerModal.tsx  i2i元ピッカー（PEエントリ／プレイセッション=AdventureSessionPickerModal再利用）
    PromptExpanderEntryGrid.tsx / EntryPickerModal.tsx  他画面から再利用するPE画像ピッカー

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
- 主な対象E2E: `action-mode.spec.ts`、`image-only-preview.spec.ts`、`adventure-mode.spec.ts`、`adventure-portrait-alpha.spec.ts`、`prompt-expander.spec.ts`。
- 定数ミラー: `constants/promptExpander.ts`（画像モデル4種、キャラ上限 V5=22/V4.5=6、サイズ、漫画モードのコマ数/レイアウト/セリフ言語と `supportsMangaMode`）。`V5_USAGE_WARN_SUPPRESSED_KEY` は `constants/novelaiImageModels.ts` に集約。
