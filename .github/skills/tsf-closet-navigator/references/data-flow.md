# データフローパターン

> 最終検証: 2026-05-02 | 更新条件: 新しい統合パターンやデータ経路が追加された場合

## メインゲームループ（変身処理）

```
ユーザー入力 (ChatInput)
  │  instructionType: dress_up | reality_change | conversation | action など
  │  text: 指示テキスト
  │  attachedImage?: base64 (任意のマスク/参照画像)
  ▼
[上位ラッパー] useGameSSE → useSSE.startPostStream()
  │  POST /game/play/stream (SSE / fetch ストリーム)
  │  Body: { session_id, instruction, instruction_type, language,
  │          nsfw_mode, difficulty, change_settings, inpaint_settings,
  │          mask_base64?, self_mode?, precise_references?, seed? }
  ▼
[バックエンド] GameService.play_with_stream()
  │
  ├─ 1. LLM: 画像編集プロンプト生成（指示 → 英語プロンプト）
  │     └─ llm_service.generate_image_prompt()
  │
  ├─ 2. LLM: 心境テキスト生成（キャラクターの反応）
  │     └─ llm_service.generate_feeling()
  │     └─ SSE: event=text, data=心境テキストのチャンク
  │
  ├─ 3. 画像生成（ステップ 2 と並列）
  │     ├─ ComfyUI inpaint (ローカル)
  │     ├─ OpenRouter マルチモーダル (Gemini等)
  │     └─ NovelAI (anlas経由)
  │     └─ SSE: event=image, data={image, history_id, seed}
  │     └─ SSE: event=surroundings_image (設定有効時)
  │
  ├─ 4. タグ分類（衣装/露出度/年齢印象）
  │     └─ tag_classifier.classify()
  │
  ├─ 5. ステータス更新（bloom/shame/adaptation 計算）
  │     └─ SSE: event=stats, data={bloom, shame, adaptation}
  │
  ├─ 6. 臨界点チェック（25/50/75/100% の閾値）
  │     └─ SSE: event=critical (閾値を超えた場合)
  │
  ├─ 7. 実績チェック / 現実改変属性追加
  │     └─ SSE: event=achievement (新規解除時)
  │     └─ SSE: event=reality_attribute_added
  │
  ├─ 8. エンディングチェック
  │     └─ summary_service.check_ending()
  │     └─ SSE: event=ending (条件達成時)
  │
  └─ 9. 完了
        └─ SSE: event=cost / event=anlas
        └─ SSE: event=complete, data={historyId, transformationCount}
  ▼
[フロントエンド] useGameSSE (コールバックスイッチャー)
  ├─ onText             → GameContext.appendFeelingText
  ├─ onImage            → ChatContext.resolvePendingIdentity + GameContext.updateFromSSE → restoreActiveSession
  ├─ onSurroundingsImage→ GameContext.setLastSurroundingsImage
  ├─ onStats            → GameContext.updateStats
  ├─ onCritical         → GameContext.appendFeelingText (名前/台詞を心境に追加)
  ├─ onAchievement      → NotificationContext.showAchievementNotification
  ├─ onRealityAttributeAdded → GameContext.addAttribute (+ 設定で通知)
  ├─ onEnding           → GameContext.setEnding → EndingModal
  ├─ onCost / onAnlas   → SettingsContext.addTotalCost / setAnlasBalance
  └─ onComplete         → isTransforming=false、クリーンアップ
```

## セッションライフサイクル

```
キャラクター選択 (WelcomeScreen)
  │  POST /game/start { character_id, difficulty, nsfw_mode }
  ▼
セッション作成 (DB: Session + SessionStats 行)
  │  レスポンス: { session_id, character, stats, current_image_url }
  ▼
GameContext.START_SESSION ディスパッチ
  │  sessionId 保存、画像読込、ステータス初期化
  ▼
ゲームループ（変身の繰り返し）
  ▼
エンディング発動 または ユーザーリセット
  │  POST /game/session (DELETE) または EndingModal 表示
  ▼
セッション非活性化 (DB: session.active = false)
```

## 設定フロー

```
SettingsScreen / SettingsContext
  │  useSettings().setDifficulty / setLanguage / toggleNsfw / etc.
  ▼
PUT /settings { difficulty, language, nsfw_mode, image_provider, ... }
  │  (旧クライアントとの互換のため PUT /settings/user も有効)
  ▼
[バックエンド] settings_service → DB: User 行更新
  ▼
SettingsContext ステート更新（ローカル localStorage 同期も並行）
```

## プレイ要約生成フロー

```
ギャラリーセッション選択 → PlaySummaryModal
  ├─ GET /gallery/sessions/{id}/summary
  │    └─ 存在したら表示 (PlaySummary テーブルから)
  └─ 未生成なら POST /gallery/sessions/{id}/summary
        └─ LLM が History/Conversation を集約 → PlaySummary に保存 → 表示
```

## 画像生成パイプライン

```
指示テキスト + 現在の画像
  ▼
GameService._generate_image_edit_prompt()
  │  LLM が指示から英語の編集プロンプトを生成
  ▼
                ┌─────────────┬──────────────┬────────────┐
                │  ComfyUI    │ OpenRouter   │  NovelAI   │
                │  (ローカル)  │ (クラウド)    │ (クラウド)  │
                │  inpaint    │ マルチモーダル │  img2img   │
                │  workflow    │ Gemini等     │  SDK経由    │
                └──────┬──────┴──────┬───────┴─────┬──────┘
                       ▼             ▼             ▼
                    PNGバイト     PNGバイト      PNGバイト
                       │             │             │
                       └─────────────┴─────────────┘
                                     ▼
                           history_images/ に保存
                           base64 で SSE 返却
```

## 状態管理アーキテクチャ

```
                      React Context 層
   ┌──────────────┬──────────────┬──────────────┬────────────────┐
   │ GameContext   │ ChatContext  │ SettingsCtx  │ NotificationCtx│
   │ (セッション,  │ (メッセージ, │ (設定,       │ (トースト通知) │
   │  画像,        │  入力,       │  プロバイダ)  │                │
   │  ステータス,  │  ストリーミ  │              │                │
   │  履歴)        │  ング)       │              │                │
   └──────┬───────┴──────┬───────┴──────┬───────┴────────┬───────┘
          │              │              │                │
   ┌──────┴───────┐ ┌────┴──────┐ ┌────┴──────┐  ┌─────┴──────┐
   │ useSession   │ │ ChatInput │ │ Settings  │  │ Toast      │
   │ useSSE       │ │ ChatMsg   │ │ Screen    │  │ Container  │
   │ GamePlay     │ │ Container │ │           │  │            │
   └──────────────┘ └───────────┘ └───────────┘  └────────────┘
```

## 通信パターン

| パターン            | 用途                                                                     | 方向                    |
| ------------------- | ------------------------------------------------------------------------ | ----------------------- |
| REST (fetch)        | セッション CRUD、設定、ギャラリー、実績                                    | クライアント ↔ サーバー  |
| SSE (EventSource)   | `/game/play/stream`, `/game/chat/stream`, `/game/improve-quality/stream` | サーバー → クライアント  |
| WebSocket なし      | SSE が唯一のリアルタイムチャネル                                          | —                       |

## DB 書き込みポイント

| トリガー                  | 書き込まれるテーブル                                                  |
| ------------------------- | ------------------------------------------------------------------ |
| セッション開始              | Session, SessionStats                                              |
| 各変身処理              | History, Conversation, TransformationTag, SessionStats (更新)      |
| 属性追加                  | SessionAttribute                                                   |
| 実績解除 / 進捗更新       | UserAchievement, AchievementCount, AchievedEnding                  |
| 設定更新                  | User                                                               |
| プレイ要約生成            | PlaySummary                                                         |
| マスク保存                | ファイルシステム (data/preset_masks/)                                  |

## 注意点 / 非自明なパターン

### チャットメッセージ復元（2テーブル統合）

`GamePlayScreen` は**2つの異なるDBテーブル**からチャットメッセージを復元し、タイムスタンプ順にマージする:

| ソース        | DBテーブル      | 生成されるもの                                                | フロントエンド `role`                              |
| ------------- | --------------- | ------------------------------------------------------------- | -------------------------------------------------- |
| 変身履歴      | `History`       | ユーザー指示 (`role=user`) + 心境テキスト (`role=system`)      | `"user"` / `"system"` (isFeelingText)              |
| 会話ログ      | `Conversation`  | ユーザーメッセージ + キャラクター応答                           | `"user"` / `"system"` (復元時) or `"character"` (ライブ) |

**重要な注意点:**

1. **タイムスタンプソートが必須** — History と Conversation のレコードは時系列で交互に存在し、片方だけでは正しい順序にならない。
2. **キャラクター応答の `role` 値が混在する** — 復元された会話メッセージは `role: "system"` だが、ライブのメッセージは `role: "character"` になる。「キャラクター側の全メッセージ」を取得するには `role !== "user"` でフィルタすること。`role === "character"` では History 由来のメッセージを取りこぼす。
3. **feelingText メッセージ** は `isFeelingText: true` フラグと `💭` プレフィックスを持つ。エクスポートや表示用途では除去が必要な場合がある。
4. **エクスポート / 小説形式** — History 由来の feelingText と Conversation 由来のキャラクター応答の両方を取得するため、`role !== "user"` を使うこと。
