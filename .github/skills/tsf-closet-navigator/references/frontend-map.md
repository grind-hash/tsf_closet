# フロントエンド アーキテクチャマップ

> 最終検証: 2026-08-28 | 対象: `frontend/src`、`frontend/tests/e2e`

## 起動とルーティング

- `main.tsx`: `BrowserRouter` と全体 Context を提供する。
- `App.tsx`: `App` が `NotificationContainer` を描いてから `AppRoutes` に委譲し、`AppRoutes` が `useLocation()` で画面を切り替える。通常ゲームのSSE送信ボディは `AppMain` で組み立てる。**通知コンテナはルート分岐より外側に置くこと**: `AppMain` の中に置くと、ギャラリー・設定・Adventure・Prompt Expander で出した通知がキューに溜まったまま描画されず、通常プレイ画面へ移動して初めて出るという不具合になる。
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

`SettingsContext` / `GameContext` / `ChatContext` の Provider value は `useMemo` で包み、Provider の再描画で消費者全員が再描画されないようにしている（新しい関数や値を value に足すときは依存配列にも加える。Biome の `useExhaustiveDependencies` が検査する）。

`main.tsx` は外側から `SettingsProvider` → `NotificationProvider` → `GameProvider` → `ChatProvider` の順に提供する。

| Context               | Hook                | 主な状態/責務                                                                                             |
| --------------------- | ------------------- | --------------------------------------------------------------------------------------------------------- |
| `SettingsContext`     | `useSettings()`     | 言語、難易度、生成プロバイダー、inpaint、履歴遡及、プレイメモ設定、複数人物、TTS、Adventure等の設定と保存 |
| `NotificationContext` | `useNotification()` | 通知キューと実績通知                                                                                      |
| `GameContext`         | `useGame()`         | Session、History、画像、stats、属性、会話復元、SessionCharacter、セッションプレイメモ                     |
| `ChatContext`         | `useChat()`         | メッセージ、入力、指示タイプ、添付、一時ID、ストリーミング、音声再生状態                                  |

### Prompt Expander専用Provider

`App.tsx` は `/prompt-expander` 配下だけを `PromptExpanderProvider` で包む（`experimentalPromptExpanderEnabled` が OFF なら `/play/new` へリダイレクト）。

`PromptExpanderContext`（`usePromptExpander()`）は PE セッション一覧/詳細、エントリ、専用設定（`GET/PUT /api/prompt-expander/settings`、生成パラメータはこの設定そのもの）、作業欄状態（参照元、正/ネガの本文と拡張モード、キャラクタースロット。キャラクタープロンプトの ON/OFF だけは localStorage `prompt_expander_character_mode` に保持して再読み込み後も復元）、`pendingExpansion`（欄直下のインライン結果カード。`target: positive|negative`）、`positiveOrigin`/`negativeOrigin`（「欄へ反映」した拡張のモードと指示。履歴メタデータ用。欄が空になると消える）、`pendingUsageWarn`（V5 利用上限の確認）、PE ローカルの `anlas` を持つ。拡張は欄右上の「拡張」ボタン（`expandPositive`/`expandNegative`）→ インライン結果カード（「欄へ反映」`applyExpansion` ／「この内容で生成」`generateFromExpansion`（カードは生成後も残す。原文はクリック時点の欄の内容）／「破棄」）で、下部の「生成」（`runGenerate`）は常に欄の内容をそのまま送る。`restoreEntry` は拡張ありのエントリなら原文を欄へ戻し変換結果を `pendingExpansion` として再現、それ以外は最終プロンプトを欄へ戻す（seed は設定 `restore_seed`=ON のときだけ戻す）。`regenerateEntry` はエントリのプロンプト/設定のまま seed を付けずに生成する。`suggestCharacters` は欄の下書きを `input_text` として送る。設定の `confirm_before_generate` / `inherit_source_prompts` は API には残るが UI の確認トグルは無い（継承トグルは i2i セクション）。精密参照は `reference`（i2i 元と同じ `PromptExpanderSource`、セッション内のみ）と設定 `use_precise_reference` / `reference_type` / `reference_strength` / `reference_fidelity` から `referenceActive`（ON かつ `supportsPreciseReference`(V4.5 系) かつ画像あり）を導き、有効時だけ `reference_*` を生成本文に載せる。参照付き生成は `generate()` が `pendingReferenceWarn` で止め、`AnlasConfirmDialog` の確定（抑止は sessionStorage `prompt_expander_anlas_warn_suppressed`）後に `postGenerate` する（V5 上限ゲートとはモデル系統で排他）。背景透過は設定 `transparent_background` から `transparentActive`（漫画モード中は false）を導き `/expand` と `/generate` の両方に載せる（V4.5 の白背景指定が効かないことがあるため、設定 `transparent_emphasis`(0〜3、既定2) を透過有効時だけ `/generate` に載せる）。インペイント（部分修正）は設定 `use_inpaint` と Context の `inpaintMask`（`{dataUrl?|fromEntryId?, thumbnailUrl, label}`。セッション内のみ）から `inpaintActive`（ON かつ i2i 元あり かつマスクあり）を導き、`inpaint_mask` か `inpaint_mask_entry_id` を載せる。ベース画像は i2i 元と共用する。`regenerateEntry` は history/entry 参照を再送し upload 参照は落とす。i2i 元が再現できるインペイントエントリは `inpaint_mask_entry_id` で同じマスクを再送する。`restoreEntry` は透過の印を戻し、参照付きエントリなら参照トグルと強度も戻す（参照画像そのものは i2i 元と同じく復元しない）。インペイントエントリは `use_inpaint` を ON にし `inpaintMask={fromEntryId}` を戻す（マスクはサーバー保存なので復元できる）。`uploadImage` とピッカーは `target: source|reference` で入れ先を切り替える。通常ゲームの Context や `useGameSSE` には統合しない。

### Adventure専用Provider

`App.tsx` は `/adventure` 配下だけを `AdventureProvider` で包む。

`AdventureContext` は Run/Template、activeRun、セットアップ生成、ターン/画像ストリーム、フェーズ、エラーを管理する。トークンごとに更新される逐次ナラティブだけは別 Context に分け、`useAdventureStreamingNarrative()` で読む（`useAdventure()` の value はトークンで変わらない）。`narrativeSettled` は手番ストリームの本文（`narrative_done`）が確定したかで、3D モデル表示中の先読み読み上げと行動パネル進捗（`quietStage`）の切替に使う（`turn` 到着後も保持し、ストリーム終了で false）。romance のトークモード（手番を消費しない会話）は `submitTalk` / `talking` / `talkDraft` / `pendingTalkInput` で、`talk_done` を `activeRun.talk_log` に追記する（手番送信とは `streaming || talking` で相互排他）。 直前に開いた run ID は `lastRunId`（`utils/adventureLastRun.ts`、localStorage `adventure_last_run_id`）として公開し、Hub の再開バナーと SideMenu の「直前のシナリオへ」が参照する。通常ゲームの `GameContext` や `useGameSSE` に統合しない。3D モデル(VRM)は `avatarModels` / `refreshAvatarModels`（Provider マウント時に `GET /api/avatars`）と `companionAvatarFailed` / `setCompanionAvatarFailed`（読込失敗で立ち絵へ戻す。run や割当が変わるとリセット）を持ち、`performSubmitTurn` はアバター表示中に `generate_partner_portrait:false` を送る。

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

## Storage

`utils/storage.ts` の `readStorage` / `writeStorage` / `removeStorage` / `readStorageFlag` / `writeStorageFlag`（`kind` は "local" | "session"）が localStorage / sessionStorage への唯一の窓口。使えない環境（プライベートモード等）でも例外を出さず null / false を返す。React の状態と同期する値は `hooks/usePersistedState`、命令的な旗（Anlas 警告の抑止、セッション ID、/health のキャッシュ等）はヘルパーを直接使う。`utils/*Preferences.ts` 系の小さな設定モジュールは従来どおり自前で読み書きしている。

## Hook

| Hook                  | 目的                                                                                                                                                                                                                                                            |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `usePersistedState`   | `useState` 互換で値を localStorage / sessionStorage に保持（初期化時に読み、更新時に書く。`serialize` / `deserialize` で形式を指定。不正値は初期値へ）。開閉状態や ON/OFF の好みはこれを使い、コンポーネント内で `localStorage` を直接触らない |
| `useAttributePresets` | 属性プリセット（localStorage `attribute_presets`）の一覧・保存・削除。`useSyncExternalStore` で右パネルと人物パネルの表示を同時に更新し、他タブの `storage` イベントも反映。`loadPresetAttributes(preset, addAttribute)` で順に追加 |
| `useAttributeInput`   | 属性の追加・編集（元の属性を削除して置換）・削除の入力状態。右パネルと人物パネルで共通 |
| `useSSE`              | GET/POST SSEの解析、停止、エラー処理                                                                                                                                                                                                                            |
| `useGameSSE`          | 通常ゲームSSEを4つの全体Contextへ接続                                                                                                                                                                                                                           |
| `useGallery`          | ギャラリーの検索、ページング、削除                                                                                                                                                                                                                              |
| `useInfiniteScroll`   | IntersectionObserverによる追加読込                                                                                                                                                                                                                              |
| `useTransparentImage` | 透過画像の読込とフォールバック（表示中は blob URL を retain/release で保持）                                                                                                                                                                                                                                 |
| `usePreciseReferenceFiles` | 精密参照画像ファイルの検証（PNG/JPEG/WebP・10MB・最大6枚）と DataURL 変換、`SettingsContext.addPreciseReference` への追加。RightPanel のドロップゾーンと GamePlayScreen の画面全体ドロップが共用。`PRECISE_REFERENCE_SECTION_ID` はスクロール先の DOM id |
| `useWindowFileDrop` | 画面全体（window）へのファイルドロップ検知。ファイルを含むドラッグ中だけ true を返し、drop を `onFiles` に渡す（個別ドロップゾーンが preventDefault 済みなら二重処理しない）。表示は `components/ui/FileDropOverlay`（薄グレー＋アップロードアイコン、pointer-events なし）と組で使う |
| `useAdventureBgm`     | Adventure BGMのループ再生、fade、autoplay/404対応。キー→URL対応はマウント時に `GET /api/adventure/bgm` で取得（未知キーは既定曲へ）。mute/volumeの永続化は `utils/bgmPreferences.ts`(localStorage `adventure_bgm_prefs`)へ集約し、BGMテスト画面と音量を共有する。`setDucked` でセリフ読み上げ中に音量を下げる |
| `useAdventureVoice`   | Adventure(romance)のセリフ読み上げ。AivisSpeech で合成した音声を専用 Audio で再生し、古い合成結果はリクエスト id で捨てる。ON/OFF・音量は `utils/voicePreferences.ts`(localStorage `adventure_voice_prefs`、既定OFF・音量50%)。グローバル `ttsEnabled` と話者が無ければ no-op。`getLevel()` は `utils/voiceLevelMeter.ts`（モジュール共有の AudioContext + AnalyserNode。running でないうちは接続せず pointerdown/keydown の resume 後に接続）の音量 0..1 で、3D モデルの口パクに使う |
| `useAdventureNarration` | `useAdventureVoice` を包み、いつ何を読むかを決める。読み上げ(0) 3D モデル表示中は本文ストリームの確定行を逐次 `appendSegments`（先読みした手番番号を控える）、(1) 新しい手番の到着で攻略対象のセリフ（先読み済みは読まない）、(2) トークの返答確定でその返答。戻り値は `UseAdventureVoiceResult` そのまま |
| `useAdventureSpeechInput` | トークモードの音声入力。`useSpeechInput` を包み、暫定テキストを入力欄へ流し込み、確定で置き換え、自動送信（`utils/speechInputPreferences.ts`、既定 OFF）なら `onSubmit`。読み上げ中とトークモード離脱で聞き取りを止め、開始前に読み上げを止める |
| `useAdventureFrameNavigation` | `buildStageFrames` の結果と、ステージの閲覧位置（`selectedFrameIndex`、null は最新）・ライトボックスの位置とタブ（`lightboxIndex` / `lightboxView`）。手番到着で最新へ戻す effect、`goToFrame`（ターンストリップ用）、`openLightboxFrame`（タブ選択を引き継ぎ、無いタブはシーンへ）を持つ |
| `useAdventureStagePortraits` | ステージと主人公ドックに出す白抜き済み立ち絵 4 種（`useTransparentImage` × 4、`PORTRAIT_ALPHA_OPTIONS`）。ステージ用は表示中フレームに追従し、ドック用は常に最新 |
| `useConversationStream` | 会話のみ(chat/stream)の送信。SSE をストリーミング表示し、会話 ID を確定して conversationHistory へ積む。play_memory_update の通知も扱う |
| `useTransformRequest` | 変身(dress_up / reality_alter / action / image_only)の送信前処理。NovelAI のマスク・i2i・精密参照オプションを組み立て、V5 利用上限使い切りと精密参照の Anlas 追加消費は AnlasConfirmDialog で確認してから `onTransform`。`resolveTransformKinds` で transformation_type / instruction_type を決める |
| `useRestoredChatMessages` | セッション復元時に history + conversationHistory を時系列で統合して setMessages(初回のみ)。?historyId= の遷移でスクロールと画像移動。`resetRestoration` で再構築を許可 |
| `useFeelingMessages` | 心境テキストのストリーミング表示と確定、周囲状況画像の紐づけ |
| `useMessageEditDelete` | メッセージ削除(履歴付き / 会話のみ)と「修正して再生成」(最新履歴削除 → 指示と種別を入力欄へ戻し再同期)。確認ダイアログの状態も持つ |
| `useSessionExport` | チャットのエクスポートメニュー(clipboard / md / csv / json / novel / 画像同梱 zip の進捗) |
| `useAdventureDrawPreferences` | 立ち絵を毎ターン描くかの好み（主人公 / 攻略対象、localStorage `adventure_draw_*_every_turn`）。Hub と Play で共有し、`AdventureContext.submitTurn` が同じキーを読む |

## APIモジュール

すべての `apis/*` は `utils/http.ts` を経由する。`requestJson(url, init?, { fallbackMessage? })` が fetch と JSON 取得、非 2xx → `ApiError`（`status` / `code` = FastAPI の `detail.code`）、204 → undefined を担い、`jsonInit(method, body)` が JSON ボディ付き RequestInit を作る。blob やストリームを返す関数は `apiErrorFromResponse(response)` で同じ `ApiError` を投げる。UI は `instanceof ApiError` と `code` で分岐する（Prompt Expander の `memory_empty`、アバターの `invalid_vrm` 等）。SSE の読み取りは `utils/sse.ts` の `readSseEvents(response.body)`（`event:` / `data:` を chunk 境界に関係なく組み立てる非同期イテレータ）を使い、`apis/adventure.ts` のターン/画像/トークと `GamePlayScreen` の会話ストリームが共用する。`hooks/useSSE` は通常ゲームの SSE 専用（中断・エラー処理込み）で据え置き。


| ファイル                  | 主な公開操作                                                     |
| ------------------------- | ---------------------------------------------------------------- |
| `apis/game.ts`            | プロンプトプレビュー、指示候補、立ち絵、削除、履歴分岐、セッション取得/復元/終了、キャラクター一覧、属性、プレイメモ（GameContext は raw `fetch` を持たない） |
| `apis/adventure.ts`       | Template/Run CRUD、セットアップ、ターン/画像SSE、設定、URL正規化 |
| `apis/characters.ts`      | SessionCharacter、主人公確保、Preset、人物タグ                   |
| `apis/favorites.ts`       | お気に入り一覧、追加、ラベル変更、削除、toggle                   |
| `apis/gallery.ts`         | セッション/履歴、フレーム、詳細、削除、要約、エクスポート        |
| `apis/memory.ts`          | ユーザーメモ本文、生成ジョブ、状態、取消、分析DL                 |
| `apis/settings.ts`        | セルフプロフィール生成/保存/取得、ユーザー設定 `fetchUserSettings` / `updateUserSettings(差分)`、アプリ設定 `fetchAppSettings` / `updateAppSettings`（SettingsContext は raw `fetch` を持たない） |
| `apis/system.ts`          | `/health`（API_BASE 外の互換エンドポイント）からプロバイダー構成を取得 |
| `apis/speechSynthesis.ts` | AivisSpeech導入、起動、話者、合成                                |
| `apis/anlas.ts`           | NovelAI Anlas残高                                                |
| `apis/promptExpander.ts`  | PE 設定/セッション/エントリ/アップロード/拡張/生成/キャラ提案、`promptExpanderImageUrl` |
| `apis/avatars.ts`         | 3D モデル(VRM)の一覧/アップロード(唯一の `FormData` 送信。`uploadAvatarModel(file, {name?, characterName?, variantLabel?})`)/更新 `updateAvatarModel(id, {name?, character_name?, variant_label?})`（`renameAvatarModel` はその包み）/削除、`avatarModelFileUrl`、`AvatarApiError.code`（`invalid_vrm` / `file_too_large`）、一括分類 `autoClassifyAvatarModels`（`POST /auto-classify`）。衣装差分の表示補助 `groupAvatarModels`（キャラクター別、未分類は末尾、グループ内は差分ラベル順）/ `avatarVariantLabel` / `classifyAvatarFilename`（backend の規則のミラー。編集フォームの事前入力用） |

## 共通 UI（`components/ui/`）

- `ConfirmDialog`: 確認ダイアログの共通部品（`title` / 本文 `children` / `confirmLabel` / `cancelLabel` / `onConfirm({doNotShowAgain})` / `onCancel`。`doNotShowAgainLabel` でチェック欄、`busy` で処理中の無効化、`dismissible` でオーバーレイ・Escape キャンセル、`confirmDisabled` で確定だけ無効化）。ボタンは左キャンセル・右確定。CSS は `confirm-dialog*`。画面ごとにモーダルをインライン実装しない
- `AnlasConfirmDialog`: Anlas 追加消費の確認（`gameplay.anlas*` の見出し・文言と抑止チェック）。通常ゲームの精密参照 / V5 上限、Adventure の開始・ターン・V5 上限、Prompt Expander の精密参照 / V5 上限で共用。抑止の保存先（sessionStorage キー）は呼び出し側
- `components/attributes/AttributePresetSaveDialog`: 属性プリセット名の入力ダイアログ（右パネル / 人物パネル共用）

## UI構成

```text
components/
  GamePlayScreen.tsx          通常ゲームのプレイ画面の編成(送信の振り分け: 会話 → useConversationStream / 変身 → useTransformRequest、お気に入り、画像ナビゲーション、インペイント/プレビュー/周囲画像のモーダル)。チャット欄の復元は useRestoredChatMessages、心境メッセージは useFeelingMessages、削除/修正は useMessageEditDelete(+ chat/MessageEditDeleteDialogs)、エクスポートは useSessionExport(+ chat/ChatExportHeader)、Anlas 残高バーは AnlasBar に分けている。NovelAI 選択時は画面全体への画像ドロップを window で受けて精密参照画像へ追加し（ドラッグ中は薄グレーのオーバーレイ）、`setPanelOpen(true)` で右パネルを開いてから精密参照セクションへ scrollIntoView。V5 実効時はオーバーレイに利用不可の説明を出し追加しない
  ImagePreviewModal.tsx       履歴画像と対応テキストのプレビュー
  HistoryPanel.tsx            履歴ナビゲーション
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

  layout/
    MainLayout.tsx            サイドバー・右パネルの枠(開閉トグル `.main-layout__toggle-right`)
    RightPanel.tsx            通常プレイの右パネル。表示条件と並び順だけを持ち、中身は rightPanel/ 配下(AivisEngineSection / AttributesSection / ClothingLayersSection / NovelaiSettingsSection(+ PromptBuilderPanel / PreciseReferencesPanel) / PromptPreviewSection / LanguageSection / SettingsSummarySection)。状態は hooks の useAivisEngine / usePromptBuilder(localStorage `prompt_builder`、`composePromptBuilderText`) / usePromptPreview / usePreciseReferenceDropZone

  adventure/
    AdventureScreen.tsx       /adventure（Hub）と /adventure/:runId（Play）の切り替えと CSS の読み込みだけ
    AdventureHub.tsx          セットアップ画面（開始素材・シナリオ・オプション・保存済み Run 一覧）
    AdventurePlay.tsx         プレイ画面の編成（run の読込・送信 submit/submitTalkMessage・キーボード操作・モーダル開閉・進捗セグメント・3D モデルの表情/身振りキー）。描画は以下へ委譲し、子は共有状態を `useAdventure()` / `useSettings()` から直接読む。派生値は `utils/adventureSceneView.ts` の `buildAdventureSceneView` で 1 回だけ求め `scene` として渡す
    AdventureHud.tsx              HUD（HudTile・Day/好感度/所持金/利用上限/Anlas/API料金・チップ列・ポップオーバー: 持ち物 / 口調 / BGM / 進行目標 / 世界ルール / 手掛かり）。`AdventureHudPanel` 型を export
    AdventureProtagonistDock.tsx  左レールの主人公ドック（最新の外見・服装、romance は攻略対象も）
    AdventureStage.tsx            画像ステージ（背景/合成・立ち絵・3D モデル `avatar` props・進捗オーバーレイ・過去閲覧バナー・立ち絵失敗の再試行・↻・⚙・AdventureBgmControl）。画像設定ポップオーバーは children
    AdventureImageSettingsPopover.tsx  ⚙ の中身。run 設定（`updateSettings`: モデル上書き・持ち物・対面会話・3D モデル・精密参照・合成）とブラウザ単位の好み（立ち絵を毎ターン描く）
    AdventureImageOptionRows.tsx  Hub と Play で共有する行部品 `AdventureToggleRow`（`adventure-precise-toggle` の見出し+説明+スイッチ）/ `AdventureImageModelPicker` / `AdventureTurnEstimate`（所要時間と「テキストのみ」告知）
    AdventureMessageBox.tsx       メッセージ窓（メタ行の 🔊/据え置き案内/持ち物の変化/ログ/非表示、行動、本文 `AdventureScriptText`、行動パネル: 行動/トーク切替・選択肢再生成・進捗・選択肢・romance 行動ボタン・`AdventureTalkThread`・`AdventureFreeInput`、またはエンディング）
    AdventureTalkThread.tsx       トークモードの会話スレッド（今の手番の会話 + 送信中の下書き。末尾へ自動スクロール）
    AdventureFreeInput.tsx        常設の自由入力欄（トークモードは 500 字・🎤・自動送信トグル・認識エラー）
    AdventureScriptText.tsx       台本形式(名前「セリフ」)の本文を話者ラベル付きで描く
    AdventureResultOverlay.tsx    終了時のリザルトカード（`useTransparentImage` で白抜きした立ち絵、進行目標、ログ/リプレイ/戻る/エピローグ）
    AdventureLogDrawer.tsx        ログドロワー（全文の読み返しとターンストリップ。開いた時と手番追加で末尾へスクロール）
    AdventureFramePreviewModal.tsx フレームのライトボックス（`ImagePreviewModal` に概要/シーン/背景/立ち絵/攻略対象のタブと手番の詳細を載せる。合成プレビュー用の白抜きはここで行う）
    AdventureScenarioPickerModal.tsx  作品／プレイ済みシナリオの選択モーダル（Hub から開く）
    AdventureAvatarOptions.tsx        3D モデルの選択肢と衣装差分ヒント（Hub / Play 共有）
    AdventureImagePromptModal.tsx
    AdventureGiftShopModal.tsx    romance のギフト購入（gift_id 送信）
    AdventureAttributeModal.tsx   romance の属性付与（現実改変プレフィックス組み立て）
    AdventureInventoryPanel.tsx   持ち物システムの HUD ポップオーバー中身（所持品と capabilities ごとの 渡す/使う/着る・脱ぐ/捨てる → submitTurn("item_action")。ログ文言の整形 formatInventoryLogEntry / formatInventoryEvents / formatInventoryActor と React key 用 keyedInventoryEntries を export し、メッセージ窓のメタ行とライトボックスでも使う）
    AdventureBgmControl.tsx       サウンドボタン(♪)+ポップオーバー。BGM(mute/volume)とセリフ読み上げ(ON/OFF・音量・状態・停止。TTS無効時は disabled+案内)を並べる。再生は useAdventureBgm / useAdventureVoice
    avatar/CompanionAvatarStage.tsx  対面会話モードの 3D モデル(VRM)ステージ。攻略対象 <img> の代わりに `.adventure-stage__frame` 内へ置く(default export、`React.lazy` で three.js を別チャンクに)。canvas はエンジンごとに動的生成(開発モードの二重 effect で Context Lost を拾わないため)
    avatar/vrmAvatarEngine.ts        React 非依存の描画エンジン(three + @pixiv/three-vrm)。読込・待機姿勢(ボーンの実方向から回転軸を求めて腕下ろし・肘曲げ・指の握り。VRM 0.x/1.0 の向き差を吸収)・外接ボックス基準の上半身フレーミング・呼吸/揺れ・まばたき・視線・音量口パク・表情クロスフェード・手続き的ジェスチャー・dispose
    avatar/avatarMotion.ts           three 非依存の純関数(ジェスチャーのキーフレーム表、idlePose、待機姿勢の関節角 ARM_REST/FINGER_CURL と tiltTowards、mouthWeightsFromLevel、blink)。vitest 対象

  bgm/
    BgmTestScreen.tsx         BGMカタログ全曲の一覧と試聴(単発再生、fade/loopなし)

  promptExpander/
    PromptExpanderScreen.tsx        セッション一覧/作業画面、Anlas・V5利用上限、同意モーダル。作業画面ではヘッダーに「← 一覧へ戻る」（`ROUTES.PROMPT_EXPANDER` へ navigate）と現在のセッション名を出す。設定は MainLayout の rightPanel（開閉は localStorage `prompt_expander_settings_panel_open`）。レイアウトは `.prompt-expander__scroll`（本文がスクロール）＋ `.prompt-expander__control-bar`（スクロールしない下端）の2段。sticky は使わない（workspace が align-items:start の grid のため吸着範囲がコンポーザ列に縛られる）
    PromptExpanderControlBar.tsx    画面下端の常時表示コントロールエリア。現在値チップ（モデル/サイズ/透過/漫画/インペイント/精密参照）、「すべて開く／すべて閉じる」、生成中の進捗、生成ボタン＋`+N Anlas`＋無効理由。生成ボタンはここだけに置く（コンポーザ内には無い）
    PromptExpanderSessionList.tsx   PEセッションの作成/改名/削除/一覧
    PromptExpanderSection.tsx       アコーディオン見出し（aria-expanded、右側ツールバー枠）。開閉は hooks/usePersistedSectionState（localStorage `prompt_expander_sections_open`）
    PromptExpanderDeleteButton.tsx  削除用アイコンボタン（ギャラリー同様ゴミ箱アイコン、ホバーで赤）。削除を赤塗り/赤枠のテキストボタンにしない
    PromptExpanderProgress.tsx      処理中表示（スピナー＋情報色ブルーの帯＋下端の不確定バー）。プロンプト化中と画像生成中で共用。警告色/アクセント色は使わない
    PromptExpanderComposer.tsx      セクション順: 生成パラメータ（末尾に「画像の背景を透過」スイッチ。無効化せず V5 / V4.5 / 漫画モードで説明文を切替）→ 漫画 → プロンプト／指示（各欄右上にモード切替・「拡張」・「✨提案」）→ キャラクタープロンプト → i2i設定 → インペイント（部分修正。既定OFF。i2i 元と同じ画像を使い、「マスクを編集」で `PromptExpanderInpaintModal` を開く。強度/ノイズは i2i 設定を流用）→ 精密参照（V4.5 系のみ。トグルは V5 で disabled + 理由、履歴/アップロード/解除の選択行、種別のセグメント型トグル、強度/忠実度スライダー、+5 Anlas の料金文言。ピッカー/アップロードは `target="reference"` で共用）。生成ボタンはコンポーザ内には無く `PromptExpanderControlBar` にある。生成パラメータの背景透過スイッチの下に強調段数（なし/{}/{{}}/{{{}}}）のセグメント型トグルを置き、V5・透過OFF でも隠さず理由を文言で出す。透過タグはエントリの最終プロンプトに保存されず設定の効きを画面で確かめられないため、正/ネガ両欄の直下に `TransparentTailPreview`（`.prompt-expander__transparent-tail`）で「送信時に追加: …」を出す。タグと重複判定は `constants/promptExpander.ts` の `transparentBackgroundTags` / `appendedTags` / `normalizeTagForMatch`（backend の `merge_tags` のミラー）で組み立てる。漫画モード中は欄の直上に記法チップ（「」『』【】《》①: カーソル位置へ挿入・選択範囲を包む・①は行頭に連番）と凡例、漫画セクションに「ナレーション枠を自動で入れる」トグル（`manga_narration`、既定OFF）。チップ行末の「あらすじからネームを下書き」（`draftScript` → `POST /manga-script`）は欄を記法付きネームで置き換え、`scriptDraftBackup` で「元の文に戻す」を出す。画面全体への画像ドロップ（`useWindowFileDrop`）は `PromptExpanderDropChooserModal`（NovelAI 風「この画像で何をしたいですか？」: i2i元 / インペイントの元 / 精密参照、履歴に残す・メモ付き）で入れ先を選ばせ、`uploadImage` 後に `openPromptExpanderSection` で該当セクションを開いて scrollIntoView。インペイント選択時は `use_inpaint` を ON にしてマスク編集モーダルを続けて開き、精密参照選択時は `use_precise_reference` を ON にする
    PromptExpanderInpaintModal.tsx  マスク編集（react-sketch-canvas。ブラシ/消しゴム/undo/redo/クリア）。マスクのプリセットは通常ゲームと同じ `/api/game/masks` を共用する。書き出しは 104x152 固定にせず元画像の 1/8 で求める
    PromptExpanderExpansionPanel.tsx 欄直下のインライン拡張結果カード（欄へ反映／この内容で生成／破棄）
    PromptExpanderEntryList.tsx / EntryCard.tsx  履歴セクション（絞り込みチップ すべて/通常/漫画/アップロード = localStorage `prompt_expander_entry_filter`、欄へ復元・このプロンプトで再生成・i2i元・通常プレイ/TSFシナリオへ・削除）。画像は右クリック保存が効くよう <button> で包まず div[role=button]。プレビューは ImagePreviewModal に className="prompt-expander-preview" で 96vw/96vh 拡大（閉じる/前後ボタンは枠内に置き直し、`positionLabel` で n / N、表示中カードは `--previewed` で強調）。背景透過エントリは `useTransparentImage`（`PROMPT_EXPANDER_ALPHA_OPTIONS`、Adventure と同じ threshold 12）で表示時に切り抜いてチェッカーボード上に出し、切り抜き中はスピナー、「透過PNGを保存」（切り抜き後の blob URL を `download`）と「参照にする」（`selectEntryAsReference`）を追加。バッジ末尾に「インペイント」「精密参照」「透過」。表示中の blob URL は `useTransparentImage` が `retainTransparentImage` で保持し、`utils/imageAlpha.ts` のキャッシュ（`CACHE_LIMIT` 48）は保持されていない結果だけを退避・revoke する（revoke 済み blob URL は `<img>` には残るが「名前を付けて画像を保存」の再取得で失敗するため）。`onError` の原本フォールバックは保険。プレビューも同じ URL を渡し `prompt-expander-preview--transparent` を付ける
    PromptExpanderSettingsPanel.tsx テキストモデル、「欄へ復元」でシードも復元する（`restore_seed`、既定OFF）、PEメモリ＋「メモリ情報を持ってくる」
    PromptExpanderUploadDialog.tsx  添付（履歴に残す／i2i元にする。`target="reference"` では「精密参照に使う」）
    PromptExpanderSuggestModal.tsx  メモリ＋欄の下書きからの好みキャラ提案（取得結果は閉じても保持し、次回開いてもリセットしない）
    PromptExpanderSourcePickerModal.tsx  i2i元／精密参照ピッカー（`target` で入れ先を切替。PEエントリ／プレイセッション=AdventureSessionPickerModal再利用）
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
    AvatarModelSettings.tsx   3Dモデル(VRM)の登録(ドロップゾーン+隠し file input `multiple`。複数ファイルを順に登録し、進捗 i/n をスピナーに出す。失敗分は飛ばして続ける)、キャラクター別のグループ表示(`groupAvatarModels`。見出しはキャラクター名の toggle ボタン(`aria-expanded`)・差分数・「キャラクター名を変更」(全件 PATCH)。キャラクターは既定で閉じ、開閉は localStorage `avatar_settings_group_open` に保持。未分類は末尾「キャラクター未設定」で常に展開。付け替え・自動分類で入ったグループは開く。`data-testid="avatar-group"`)、ドロップゾーン下のツールバー「ファイル名から自動分類」(`POST /api/avatars/auto-classify`。未設定の項目だけ埋め、結果を `role="status"` に出す)、親へ `onSummaryChange({total, characters})` で件数を知らせる(設定画面の見出し要約用)、各行に差分ラベル(未分類はモデル名)・モデル名(副次)・作者・ライセンス(リンク)・サイズ・登録日、行末に VRM 0.x/1.0 バッジとゴミ箱アイコン、「キャラクターを編集」でインライン編集(キャラクター名は既存名の datalist、差分の説明。未設定の欄は `classifyAvatarFilename(model.name)` で事前入力。空欄で解除。`data-testid="avatar-character-editor"`)、改名、削除確認。設定画面(`SettingsScreen`)では最下部(リセットの手前)の折りたたみセクションに置き、既定は閉じる(localStorage `settings_avatar_section_open`、`data-testid="settings-avatar-toggle"`、見出しに「登録 N件・キャラクター M」の要約)
    AvatarPreviewModal.tsx    登録済み VRM のプレビュー(表情 6 種・身振り 8 種を LLM 無しで確認。口は動かない)
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

- i18n は `frontend/src/i18n/` に名前空間ごとのファイルで持つ（`ja/<namespace>.ts` と `en/<namespace>.ts`、各言語の `index.ts` が結合、`i18n/index.ts` が初期化と `TranslationKey` 型を公開）。`t()` のキーは ja のリソースから型付けされ、存在しないキーや ja/en の乖離は `tsc` と `src/i18n/index.test.ts` で検出される。`t(\`ns.${x}\`)` のような動的キーは `x` を文字列リテラルの union 型にする（`string` のままでは型エラー）。新規UI文字列は両言語を更新する。
- `SideMenu` の `isActive` は完全一致に加えて `pathname.startsWith("{path}/")` も見る。詳細ページ（`/prompt-expander/:id`、`/adventure/:runId`、`/gallery/:sessionId`）で親項目が非活性になると、その項目から一覧へ戻れることに気付けないため。`/play/new` だけは従来どおり特例で先に判定する。
- 各大規模画面は隣接CSSを持つ。既存レイアウトを保ち、変更画面だけ確認する。
- `hooks/usePersistedSectionState.ts` はモジュールレベルのストア＋`useSyncExternalStore`で、マウント中のセクションIDと既定値をレジストリに持つ。`setAllPromptExpanderSections(open)` と `usePromptExpanderSectionsAllOpen()` はそのレジストリを見るので、セクションを増やしても固定リストの更新は要らない。
- Context単体テストは `frontend/src/contexts/tests/`、E2Eは `frontend/tests/e2e/`。
- 主な対象E2E: `action-mode.spec.ts`、`image-only-preview.spec.ts`、`gameplay-mocked.spec.ts`(通常プレイのエクスポート・会話ストリーム・削除/修正と右パネル各セクションをバックエンド無しで固定)、`adventure-mode.spec.ts`、`adventure-portrait-alpha.spec.ts`、`prompt-expander.spec.ts`。
- 持ち物の型は `apis/adventure.ts` の `AdventureInventory` / `AdventureInventoryItem` / `AdventureInventoryLogEntry` / `AdventureItemAction` / `AdventureTurnOptions`（`submitTurn` の options）。カテゴリ・操作の語彙は backend `consts/adventure_inventory.py` と一致させ、表示名は `adventure.inventoryCategory.*` / `adventure.inventoryAction.*`。
- Adventure 画面の純関数は `utils/adventureFrames.ts`（`buildStageFrames`: run → ステージ用フレーム列、`partnerPortraitInherited` / `partnerPortraitReasonKey` / `frameDaySlot`）、`utils/adventureSetupPrefs.ts`（セットアップ設定の localStorage 読み出しと正規化）、`utils/adventureVoiceSegments.ts`（読み上げセグメント化）、`utils/adventureFormat.ts`（`formatAnlasEstimate` / `mediaUrl` / `speechStyleLabel`）、`utils/adventureSceneView.ts`（`buildAdventureSceneView`: 表示中の本文・行動・現在地・選択肢・持ち物・romance の攻略対象名/服装・トークモードの会話をまとめた `AdventureSceneView`）に分け、定数（プリセット・ターン数境界・語り手の声・口調・localStorage キー）は `constants/adventure.ts` に置く。いずれも vitest 対象。
- Adventure の台本形式ユーティリティは `utils/adventureDialogue.ts`（`parseDialogueSegments` / `partnerLines` / `joinForSpeech` / `stripStageDirections`）。対面会話モードの見積もりは `utils/adventureTurnTimeEstimate.ts` の `companionMode`。
- 定数ミラー: `constants/promptExpander.ts`（画像モデル4種、キャラ上限 V5=22/V4.5=6、サイズ、漫画モードのコマ数/レイアウト/セリフ言語と `supportsMangaMode`、精密参照の種別/既定強度/`PROMPT_EXPANDER_ANLAS_PER_REFERENCE`/`PROMPT_EXPANDER_ANLAS_WARN_SUPPRESSED_KEY`/`supportsPreciseReference`、背景透過の `usesNativeTransparency`/`PROMPT_EXPANDER_ALPHA_OPTIONS`）。`V5_USAGE_WARN_SUPPRESSED_KEY` は `constants/novelaiImageModels.ts` に集約。`constants/companionAvatar.ts` は 3D モデルの表情 6 種・身振り 8 種で、backend `consts/companion_avatar.py` と完全一致させる（LLM に選ばせる語彙＝FE が実装している語彙）。衣装差分のキー("1","2",…)は手番ごとにバックエンドが組み直すため FE に定数は無い。
