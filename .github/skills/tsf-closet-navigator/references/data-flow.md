# データフローパターン

> 最終検証: 2026-08-10 | 通常ゲームとAdventureは別のストリーム契約を持つ

## 通常ゲームの送信経路

```text
ChatInput
  └─ 指示 + InstructionType + 添付/送信タイプ
      ↓
GamePlayScreen
  └─ App.handleTransform
      ├─ SettingsContextから生成/履歴/メモリ/複数人物設定を構築
      └─ useGameSSE.startPostStream
          ↓ POST /api/game/play/stream
GameService.play_with_stream
  ├─ 指示タイプ分岐
  ├─ 履歴・プレイメモ・人物コンテキスト解決
  ├─ LLM/画像生成
  ├─ History/Conversation/Stats等の永続化
  └─ SSE
      ↓
useSSE → useGameSSE
  ├─ GameContext
  ├─ ChatContext
  ├─ SettingsContext
  └─ NotificationContext
```

送信ボディの中心は `session_id`、`instruction`、`instruction_type`、`language`。設定により `use_history_lookback`、`use_memory`、`use_play_memory`、`respect_clothing_layers`、`enable_multiple_people`、`use_character_panel`、seed、inpaint、精密参照、情景画像を加える。

## 指示タイプ別の境界

| 指示タイプ | 主な副作用 |
| --- | --- |
| `dress_up` | 画像、心境、stats、履歴、タグ、実績、人物外見 |
| `reality_alter` | 画像、心境、stats、履歴、属性、実績、人物外見 |
| `action` | 画像、心境、stats、履歴。設定時は情景画像も生成 |
| `conversation` | 会話を保存し、画像生成を行わない |
| `image_only` | 画像と画像履歴だけを保存。心境、stats、実績、人物状態を更新しない |

`image_only` は失敗時にHistoryを残さない。保存する場合は指示、画像、空の心境、seed、画像状態記述を保持する。

## プロンプトとメモリ

```text
original_instruction
  ├─ 心境/会話用 instruction      履歴・プレイメモ等を用途別に展開
  └─ 画像用 image_instruction     画像メモリON時だけ有効メモを追加
```

- `prompt_override` はユーザーが直接確定した画像プロンプトとして扱い、自動の履歴遡及を混ぜない。
- `PlayMemoryService.build_context` は、ONのユーザーメモ、自動メモ、ユーザー単位メモリを用途に応じて整列する。
- `use_memory` は画像生成へのメモリ反映、`use_play_memory` はセッションプレイメモ機能の利用を表す。混同しない。
- 履歴遡及は `history_context.py` と `frontend/src/utils/historyLookback.ts` の両側で指示タイプ別に制御する。

## 通常ゲームSSE

| イベント | 主な受信処理 |
| --- | --- |
| `text` | 心境/応答チャンクをChat/Gameへ追加 |
| `image` | 画像とhistory_idを確定し、セッションを同期 |
| `surroundings_image` | `GameContext.lastSurroundingsImage` を更新 |
| `stats` | bloom/shame/adaptationを更新 |
| `critical` | 臨界点表示/テキストを追加 |
| `ending` | EndingModal用状態を更新 |
| `achievement` | 実績通知 |
| `reality_attribute_added` | 属性を追加 |
| `cost`、`anlas` | コスト/残高をSettingsへ反映 |
| `complete` | 履歴ID・変身回数を確定。プレイメモ更新失敗も通知 |
| `error` | ストリーム停止とエラー表示 |

## メッセージと履歴ID

送信直後は `PendingMessageIdentity` に一時トークンを置き、`image` または `complete` の `history_id` でユーザーメッセージと心境メッセージを確定する。復元時は `History` と `Conversation` を時系列に統合する。

- History: ユーザー指示 + `feeling_text`
- Conversation: 会話のユーザー/キャラクターメッセージ
- 復元側のキャラクター応答は `role: system` になり得るため、キャラクター側を取得するときは `role !== "user"` を基準にする。

## セッションプレイメモ

```text
PlayMemorySettings
  ↓ GameContext.updatePlayMemory / regeneratePlayMemory
PATCH /api/game/sessions/{id}/play-memory
POST  /api/game/sessions/{id}/play-memory/regenerate
  ↓
Session.play_memory_* に保存
  ↓
次のplayで PlayMemoryService が必要なコンテキストを構築
```

ユーザー単位の長期メモリは別経路である。

```text
MemorySettings → /api/memory/text
              → /api/memory/generate → status/export/cancel
              → User.memory_text / MemoryJobServiceの一時ジョブ
```

## 複数人物

```text
CharacterPanel / CharacterPresetPicker
  ↓ apis/characters.ts
/api/game/session/{id}/characters と /character-presets
  ↓
SessionCharacter / CharacterPreset
  ↓
GameContext.sessionCharacters
  ↓ use_character_panel=true の画像プロンプト
character_service → game_service / llm_service
```

`enableMultiplePeople` は複数人生成自体、`multiCharacterPanelEnabled` はSessionCharacterをプロンプトへ注入するかを制御する。主人公は `ensure-protagonist` で冪等に確保する。

## Adventure

```text
AdventureScreen
  ↓ AdventureContext
apis/adventure.ts
  ├─ setup/generate、runs CRUD
  ├─ runs/{id}/turns/stream
  └─ runs/{id}/image/stream
      ↓
adventure_router → AdventureService
  ├─ AdventureRun / AdventureTurn
  ├─ scenarios/*.json
  ├─ director / resolution / image prompt
  └─ adventure/images/{run_id}
      ↓
AdventureContext.activeRun とターン履歴
```

Adventureのイベントは `status`、`narrative_chunk`、`narrative_done`、`turn`、`image`、`portrait_image`、`complete`、`error`。通常ゲームの `useSSE` には流さず、`apis/adventure.ts` の専用パーサを使う。

ターン表示では新規画像がないターンも、開始画像または直前の実効画像を時系列に引き継ぐ。Runの現在画像と開始画像の用途を混同しない。

## ギャラリー、お気に入り、エクスポート

```text
GalleryScreen
  ├─ apis/gallery.ts → /api/gallery
  │    ├─ Session/History検索とページング
  │    ├─ 要約
  │    └─ Markdown / Novel HTML ZIP
  └─ apis/favorites.ts → /api/favorites
       └─ FavoriteOutfit (History参照)
```

エクスポートは画面上の一時状態ではなく、DBに永続化されたHistory/Conversation/Session設定を情報源にする。

## 主なDB書き込み

| 操作 | モデル |
| --- | --- |
| セッション開始/通常プレイ | `Session`、`SessionStats`、`History`、`Conversation`、`TransformationTag` |
| プレイメモ | `Session.play_memory_*` |
| 複数人物 | `SessionCharacter`、`CharacterPreset` |
| Adventure | `AdventureRun`、`AdventureTurn` |
| お気に入り | `FavoriteOutfit` |
| 設定/長期メモリ | `User` |
| 実績 | `UserAchievement`、`AchievementCount`、`AchievedEnding` |
| 要約 | `PlaySummary` |
