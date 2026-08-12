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

自動生成タイプのターン数は `scenario_max_turns` として `POST /adventure/setup/generate` と `POST /adventure/runs` の両方へ送り、`AdventureRun.max_turns` に保存する。境界値は `gateway/consts/adventure_turns.py` が唯一の情報源で、既定15手・5〜30手。作品シナリオはテンプレJSON、リプレイは元runの値を引き継ぐため、この項目は自動生成分岐だけに効く。`_setup_system_prompt` の英文と開始シーンのディレクタープロンプトにも同じ手数を渡し、生成されるゴール文面の尺と一致させる。

語りの人称は run の `state_json` に `narration_voice`（`second_person` 既定 / `third_person` / `first_person`）と `narration_pronoun` で持ち、境界値は `gateway/consts/adventure_narration.py` が唯一の情報源。`_director_system_prompt`、`_narrative_system_prompt`、`_resolution_system_prompt`、修復プロンプト、`_clothing_narrative_suffix` の5箇所へ渡す。人称指示は同意・主体性のガード文を必ず伴い、`_lean_state_for_llm` では user prompt から除外する。旧 run はキー欠落時に二人称へ倒す。

作品シナリオの装備判定 `_last_equipment_action` は、エイリアス前後を走査して最も近い着脱動詞を帰属させる。他アイテムの語で走査を打ち切るが、並列助詞（と／や／and）で繋がる場合と、直後が修飾助詞（の／に等）の場合は境界にしない。長い語に内包されただけの一致（「ヘッドドレス」中の「ドレス」）は数えない。画像側では未装備アイテムを `_equipment_negative_tags` で negative に出し、`_strip_unworn_equipment_tags` で player_tags からも除く。外衣着用時は下着 negative を出さない（`CLOTHING_LAYER_COVERED_NEGATIVE` と矛盾するため）。

preset="romance"（恋愛シミュレーション）は自動生成のみで、日数(5〜15日、1日=昼夜2ターン)を `scenario_max_turns=日数×2` として送る。好感度・金銭・ギフト採点・告白成否は `services/adventure_romance.py` の純関数が決定し、LLM は数値を書かない。day/slot は `turn_number` から導出し状態に保存しない。`state_json["sim"]` に相手・カタログ・隠し好み(`hidden_preferences`)を持ち、`_serialize_run` と `turn` イベントには隠し好みを除いた `public_sim_view` だけを `sim` として載せる。ターンは `input_kind: gift|work|confess`（gift は `gift_id` 併送、資金不足はターン未消費のエラー）を追加。属性付与は既存の現実改変機構を再利用し、UI のモーダルが「現実改変：〜」を組み立てるだけで、HUD の現実改変チップを「付与した属性」表示に差し替える。開始素材で選んだ人物は主人公ではなく攻略対象（NPC として main_characters / npc_tags に描画、外見は `sim.partner_appearance`）。主人公（自分）はテンプレートキャラクター（`romance_player_character_id`、既定 char1）または特定セッション時点の変身状態（`romance_player_session_id`＋`romance_player_history_id`、指定時はテンプレより優先で `_build_snapshot` を流用）で、開始画像・外見ロック・立ち絵は主人公側へ差し替え、FE は選択を localStorage の adventure_setup_prefs に保存する。romance 時は HUD・メッセージウィンドウ・行動ボタンを `adventure-hud--romance` / `adventure-messagebox--romance` のローズトーンに切り替える。非合成モードでは攻略対象の立ち絵を主人公と並置表示する: 参照は run ディレクトリの `partner_initial.*`。最新パスは `state_json["partner_portrait_path"]`（開幕分は `opening_partner_portrait_path`）、ターン別パスは各ターンの state_delta に保持し（いずれも `_lean_state_for_llm` で除外）、開幕に加えて主人公と同様に毎ターン `_generate_partner_portrait_unlocked` で直列生成する（step "partner" の status を送出、FE 進捗バーにも partner 工程あり。失敗はターンを止めず前の1枚を維持）。生成ヘルパは state を自前でDB保存するが、stream 終端の全 state コミットに上書きされるため、consumer が受けたパスを必ず next_state へ反映してからコミットする。配信は SSE `partner_image`、`_serialize_run.partner_portrait_url` / `opening_partner_portrait_url`、`_serialize_turn.partner_portrait_url` で、FE は過去フレーム閲覧中もその手番時点の相手立ち絵をステージ・モーダル（攻略対象チップ/シーン並置）に表示する（欠けたターンは直前の1枚を引き継ぐ）。`_serialize_turn` は state_delta_json に sim があるターン（=romance）へ、確定時点の `sim`（public_sim_view）と攻略対象の様子 `partner_note`（main_characters の該当エントリ description）を載せ、`_serialize_run` は開幕フレーム(手番0)用に `opening_sim`（開始値は定数のため `opening_sim_view` が現在の sim から再構成）も返す。ターン詳細モーダルはこれを使い攻略対象カード（名前・好感度・段階・様子）と Day 表記（day/slot は FE の `romanceDaySlot` で turn_number から再導出）を表示し、`ImagePreviewModal` の `className` 経由の `adventure-preview--romance` でローズテーマ化する。リプレイは非対応（sim を再構築できないため BE でガード、FE で導線除外）。

Adventureの画像設定は run の `state_json` に持つ。`use_precise_reference`、`enable_composite_scene`、`respect_clothing_layers` を `POST /runs` と `PATCH /runs/{id}/settings` で設定し、`_prepare_image_prompt` と `_generate_image_unlocked` が state から読む。`respect_clothing_layers` は設定画面のグローバル値をAdventureScreenが同期し、ON時は外衣に覆われた装備下着タグを positive から外して被覆用 negative を足す。

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
