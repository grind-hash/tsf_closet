# データフローパターン

> 最終検証: 2026-08-25 | 通常ゲームとAdventureは別のストリーム契約を持つ
>
> Adventure の流れは `docs/adventure-flow.md` にシーケンス図（Mermaid）でもまとめてある。
> Adventure の経路を変えたら両方を更新する。

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

| 指示タイプ      | 主な副作用                                                        |
| --------------- | ----------------------------------------------------------------- |
| `dress_up`      | 画像、心境、stats、履歴、タグ、実績、人物外見                     |
| `reality_alter` | 画像、心境、stats、履歴、属性、実績、人物外見                     |
| `action`        | 画像、心境、stats、履歴。設定時は情景画像も生成                   |
| `conversation`  | 会話を保存し、画像生成を行わない                                  |
| `image_only`    | 画像と画像履歴だけを保存。心境、stats、実績、人物状態を更新しない |

`image_only` は失敗時にHistoryを残さない。保存する場合は指示、画像、空の心境、seed、画像状態記述を保持する。

`image_only` には「前画像を使わない（i2iなし）」オプションがある。FE は `ChatContext.imageOnlyTextToImage`（永続化しない）をチャット入力ツールバーのトグルスイッチ `chat-input__switch` で切り替え、`image_only` 以外・selfhost のときは disabled + title で理由を出す（隠さない）。送信時は `transformOptions.imageOnlyTextToImage` → `App.handleTransform` が `image_only_text_to_image=true` を付ける（確認ダイアログ経由の再送・プロンプト上書き送信も同じ経路）。BE は `play_with_stream(image_only_text_to_image=...)` を `image_only` 分岐内だけで読み、前画像の i2i・Vision 説明・`after_description` の継承・`WORN_UNDER_LAYERS` 継承・直前履歴由来の主人公タグ・マスクを使わず `_generate_image(None, ...)` → `image_service.generate_image(image_bytes=None)` で新規生成する（メモリ・プレイメモ・セッション属性・登場人物パネル・seed・ネガティブ・プロンプト上書き・精密参照は従来どおり）。プロンプトは `image_only_prompts.py` の `get_image_only_generate_system_prompt` / `build_image_only_generate_prompt`（非 Opus）と `IMAGE_ONLY_TEXT_TO_IMAGE_RULE`（Opus、`extra_system_suffix` 末尾）を使い、History の `before_description` は空で保存する。selfhost(ComfyUI) は text-to-image 不可のため LLM 呼び出し前に `GameServiceError` で拒否する。

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

| イベント                  | 主な受信処理                                                                                                                       |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `text`                    | 心境/応答チャンクをChat/Gameへ追加                                                                                                 |
| `image`                   | 画像とhistory_idを確定し、セッションを同期                                                                                         |
| `surroundings_image`      | `GameContext.lastSurroundingsImage` を更新                                                                                         |
| `stats`                   | bloom/shame/adaptationを更新                                                                                                       |
| `critical`                | 臨界点表示/テキストを追加                                                                                                          |
| `ending`                  | EndingModal用状態を更新                                                                                                            |
| `achievement`             | 実績通知                                                                                                                           |
| `reality_attribute_added` | 属性を追加                                                                                                                         |
| `cost`、`anlas`           | コスト/残高をSettingsへ反映。`anlas` にはV5利用上限 `usage` も同梱（`anlas_service` が `/user/subscription` から残高と併せて取得） |
| `complete`                | 履歴ID・変身回数を確定。プレイメモ更新失敗も通知                                                                                   |
| `error`                   | ストリーム停止とエラー表示                                                                                                         |

## NovelAI 画像モデル選択（V4.5/V5）

ユーザー設定 `novelai_image_model`（NSFW用）/ `novelai_curated_image_model`（非NSFW用）を、呼び出し側（game_service / adventure_service）が `consts/novelai_models.py` の `resolve_user_image_model(user_settings, nsfw_mode)` で解決し、`novelai_model_override` として `image_service` に配管する。インペイントモデル・SDK Literal 用ベースモデル・V5 判定は同 consts が唯一の情報源（V5 Curated のインペイントは NovelAI 本家に合わせ `nai-diffusion-4-5-curated-inpainting`）。SDK の `GenerateImageParams.model` は v4.5 までの Literal のため、V5 名は送信直前の `req.model` 上書きで差し替える。V5 では精密参照（character reference）が使えず、FE（`isNovelaiV5Active` で UI 無効化・不送信）と BE（各構築箇所＋クライアント内の防御的破棄）の両方で落とす。Adventure の立ち絵は V4.5=白背景生成＋FE透過処理、V5=プロンプト `transparent background` でネイティブ透過（`imageAlpha.ts` は既に透過を持つ画像を素通しするため混在履歴も安全）。V5 利用上限（`usage.percent`）は生成毎に減り、使い切り後の生成は Anlas を消費するため、両モード（GamePlayScreen / AdventureContext.submitTurn）で生成前に抑止チェック付き確認ダイアログを挟む（sessionStorage `v5_usage_warn_suppressed`）。上限バーは通常ゲーム HUD（Anlas 左隣）・設定パネル・設定画面に加え、Adventure のプレイ HUD にも置く（romance は `HudTile` の `gaugeRatio`、非 romance は `adventure-hud__usage`。Anlas 表示自体も V5 実効時は精密参照 OFF でも表示し、バッジを V5 に切り替える）。精密参照の Anlas 確認ダイアログを検証する E2E は、実 DB のモデル選択に結果が左右されないよう `/api/settings/user` の GET をモックして V4.5 に固定すること（`mockV45ImageModels`）。

Adventure は run 単位でモデルを上書きできる: `POST /adventure/runs` の `image_model` と `PATCH /runs/{id}/settings` の `image_model`（`"default"` で上書き解除、None は据え置き）が `state_json["image_model_override"]` に入り、`_resolve_image_model(nsfw_mode, state)` が最優先で読む（`_serialize_run` は `image_model_override` を配信、`_lean_state_for_llm` では除外）。選択肢は setup 画面とプレイ中ギアポップオーバーの両方にある `adventure-image-model-picker`（`ADVENTURE_IMAGE_MODEL_CHOICES`、既定「設定に従う」）。FE の V5 実効判定はグローバルの `isNovelaiV5Active` ではなく `activeRun.image_model_override ?? effectiveNovelaiImageModel` を `isV5ImageModel` に通した run 単位の値を使う（精密参照トグルの無効化、Anlas/V5 上限表示、`AdventureContext.submitTurn` の確認ダイアログすべて）。setup 側の選択は `adventure_setup_prefs` の `imageModel` に保存され、リプレイでは引き継がれない（毎回 setup で選ぶ）。Adventure の立ち絵（主人公・攻略対象）は `_PORTRAIT_EXTRA_NEGATIVE`（multiple views / reference sheet / 2girls 等）を negative へ常に併合する: full body + 透過/白背景の組み合わせ、特に V5 は同一人物が2人並ぶキャラクターシート風の絵を出しやすいため。

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

Adventureのイベントは `status`、`narrative_chunk`、`narrative_done`、`turn`、`image`、`portrait_image`、`partner_image`、`background_image`、`cost`、`complete`、`error`。通常ゲームの `useSSE` には流さず、`apis/adventure.ts` の専用パーサを使う。

生成プロバイダーは通常ゲームと同じグローバル設定に従う（テキスト=`FEELING_PROVIDER`、画像=`IMAGE_PROVIDER`。かつては Adventure だけ NovelAI 固定だった）。テキストは `adventure_service` の `_generate_text` ラッパー（`_text_provider()` 解決＋コスト集計）を必ず通し、直接 `llm_service.generate_text` を呼ばない。画像の4ヘルパ（合成 `_generate_image_unlocked`・立ち絵・攻略対象立ち絵・背景）は `_image_provider()` で分岐し、非NovelAIではキャラクター枠/negative/seed が無いため `_flatten_scene_prompt` で1本に畳み、参照画像は精密参照設定に関わらず常に使う（追加費用なし。Anlas確認ダイアログ・残高表示・見積もりは FE 側で `imageProvider === "novelai"` のときだけ出す）。selfhost(ComfyUI) は txt2img 不可のため背景生成をスキップし（`_generate_background_image_unlocked` が AdventureError、呼び出し側は握って続行）、立ち絵・合成は既存画像の編集で賄う。OpenRouter は従量課金APIなので並列化する: `model_execution_gate` は openrouter を直列化せず、`stream_turn` と `_generate_opening_visuals` は背景・主人公立ち絵・攻略対象立ち絵を `asyncio.gather` で並列生成（合成のみ後段）。並列時の state_json 更新は `_persist_locks[run_id]` で保存部だけ直列化する（受信パスの next_state 反映は従来どおり必須）。

API料金は `_CostTracker`（ContextVar `_cost_tracker`。create_task がコンテキストを複製しても同一オブジェクトを共有）で1オペレーション単位に集計する。`stream_turn` は `complete` 直前に `cost` イベント、`create_run`・`generate_setup`・`regenerate_choices`・`generate_image`・`generate_portrait` は応答の `cost_usd`（image/stream ルーターはこれを `cost` イベントへ変換）。narrative ストリームの料金は `generate_feeling_stream(usage_callback=...)` → OpenRouter の usage チャンクで取る。FE は `AdventureContext` が `SettingsContext.addTotalCost` へ累算し（通常ゲームと同じ累計）、HUD メトリクス行に `showCost` のとき累計を表示する（`adventure-hud__cost` / romance は HudTile）。run の `image_provider` 列には作成時のプロバイダーが入るが、生成時は常に現在の設定を読む。既存ユニットテストは NovelAI 経路前提のため `tests/unit/test_adventure_service.py` の autouse fixture がプロバイダーを novelai に固定している。

ターン表示では新規画像がないターンも、開始画像または直前の実効画像を時系列に引き継ぐ。Runの現在画像と開始画像の用途を混同しない。

自動生成タイプのターン数は `scenario_max_turns` として `POST /adventure/setup/generate` と `POST /adventure/runs` の両方へ送り、`AdventureRun.max_turns` に保存する。境界値は `gateway/consts/adventure_turns.py` が唯一の情報源で、既定15手・5〜30手。作品シナリオはテンプレJSON、リプレイは元runの値を引き継ぐため、この項目は自動生成分岐だけに効く。`_setup_system_prompt` の英文と開始シーンのディレクタープロンプトにも同じ手数を渡し、生成されるゴール文面の尺と一致させる。

ミッション案の自動生成は、ユーザーが入力済みの舞台・ゴール・制約を `POST /adventure/setup/generate` の `scenario_setting` / `scenario_objective` / `scenario_constraints`（空の項目はキーを送らない）として受け取り、`_build_setup_user_draft` が非空項目だけの `user_draft` を user prompt に載せ、`_setup_system_prompt(..., draft=...)` が `_SETUP_DRAFT_GUIDANCE`（意味・固有名詞・条件を保ち、文言の仕上げと空欄の補完だけを許す。romance は下書きに相手の名前があれば 新しい名前を発明しない）を付ける。下書きが全て空なら従来どおり `user_draft` も指示も出さない。FE は応答で3項目を上書きする（従来どおり）。 制約の上限件数は `gateway/consts/adventure_setup.py` の `SCENARIO_CONSTRAINTS_MAX_ITEMS`（20件）が唯一の情報源で、`AdventureCreateRequest` / `AdventureSetupGenerateRequest` / LLM 出力 `AdventureSetupOutput` の3か所に同じ値を使う（かつて4件固定で、詳細なキャラクター設定を十数行書くと `POST /runs` が 422 になった）。FE は `SCENARIO_CONSTRAINTS_MAX_ITEMS` を同値で持ち、件数超過時は開始・生成ボタンを無効化して理由（`disabledReason.tooManyConstraints`）を入力欄のヒントと status の両方に出す。

直前にプレイしたシナリオへの復帰導線: 最後に開いた/作成した run の ID を `utils/adventureLastRun.ts`（localStorage `adventure_last_run_id`、同一タブ通知用のカスタムイベント付き）に保存し、`AdventureContext.lastRunId` が `loadRun` 成功・`createRun` で更新、`loadRun` 失敗・`removeRun` で一致時にクリアする。Hub はヘッダー直下に `.adventure-continue` バナー（保存済み一覧と同じ `AdventureRunRow`、削除ボタン無し）を、再取得済み `runs` に該当 run があり `canActOnRun` が真のときだけ出す（終了済みは出さない）。SideMenu は AdventureProvider の外側でも描画されるため Context ではなく `useSyncExternalStore` で同ユーティリティを購読し、TSFシナリオ項目の下に「直前のシナリオへ」サブ項目を出す（ID のみ保存。削除済み run を指した場合は AdventurePlay の `loadRun` 失敗で Hub へ戻る）。Backend に `last_played_at` は持たない（`updated_at` は画像再生成でも動くため「プレイ」の指標にならない）。

語りの人称は run の `state_json` に `narration_voice`（`second_person` 既定 / `third_person` / `first_person`）と `narration_pronoun` で持ち、境界値は `gateway/consts/adventure_narration.py` が唯一の情報源。`_director_system_prompt`、`_narrative_system_prompt`、`_resolution_system_prompt`、修復プロンプト、`_clothing_narrative_suffix` の5箇所へ渡す。人称指示は同意・主体性のガード文を必ず伴い、`_lean_state_for_llm` では user prompt から除外する。旧 run はキー欠落時に二人称へ倒す。

セリフの口調は人称とは独立した軸で、run の `state_json` に `player_speech_style`（`polite` 既定 / `casual` / `formal` / `custom`）と `player_speech_custom`（custom 時の自由入力）を持つ。境界値は `gateway/consts/adventure_speech.py` が唯一の情報源で、プロンプト英文は `_SPEECH_STYLE_RULES` と `_SPEECH_STYLE_GUARD`（`adventure_service.py`）にある。`_speech_style_instruction` が主人公と（romance なら）攻略対象を1つの `SPEECH REGISTER:` ブロックへまとめ、`_speech_rule_from_state` が state と `state["sim"]` から組み立てる。渡すのは**物語文を書く経路だけ**（`_director_system_prompt` とその修復プロンプト、`_narrative_system_prompt`、`stream_turn` の本文生成、`preview_turn_prompts` の `narrative.system`）で、`_resolution_system_prompt` には渡さない（`choices[].label` は人称も口調も持たない中立の行動句と定めており矛盾するため。代わりに同ラベル規則へ `no speech style` を明記した）。`_visual_system_prompt` と `_clothing_narrative_suffix` も対象外。`_lean_state_for_llm` は両キーを user prompt から除外し、`_REWIND_KEEP_KEYS` には含める（口調は物語の出来事ではなく設定なので巻き戻しで戻さない）。旧 run はキー欠落時に丁寧語へ倒すため、進行中の旧 run も次の手番から丁寧語になる。変更は `POST /runs`（`player_speech_style` / `player_speech_custom` / `romance_partner_speech_style`）と `PATCH /runs/{id}/settings`（同3項目、None は据え置き）の2経路で、後者は現実改変ルールと同じく**手番を消費しない**。`_serialize_run` が主人公側2キーを配信し、攻略対象側は `public_sim_view` の `partner_speech_style` に載る。FE はセットアップの「物語の演出」に主人公・攻略対象の口調を並べて置く。プレイ中の導線は HUD チップ列の `adventure-hud__chip--speech`（`hudPanel="speechStyle"`）で、ポップオーバーに主人公と攻略対象の口調を対で出し、「口調を変更」から `AdventureSpeechStyleModal` で即時 PATCH する（ステージ上に新しい浮遊ポップオーバーは足さない）。**主人公ドックの中には置かない**: 既定で閉じている折りたたみパネルかつスクロールが必要で、入口として発見されなかった実績がある。チップの値は分類名だけを出し（`custom` の自由入力全文はポップオーバーで読める）、`max-width` で幅を抑える。HUD で伸縮するのは `.adventure-hud__title`（ゴール文）だけなので、チップを増やすとその分ゴールが縮む。`min-width: 5rem` の下限を入れて幅0まで潰れないようにしてある（省略表示は `h1 > span` の ellipsis が担当）。主人公の選択は localStorage の `adventure_setup_prefs` へ引き継ぐが、攻略対象の口調は run 固有なので保存しない。

選択肢ラベルは行動パネル（幅 260〜360px の縦カラム）に3件並ぶため、長いと折り返して読めなくなる。`_CHOICES_LENGTH_INSTRUCTION` が director/resolution 両プロンプトで「日本語20字・英語8語以内、粒度は変えず書き方だけ短く」を要求し、romance の両ガイダンスにも「半日を埋める計画は計画自体が決めるもので、ラベルの長さではない」と併記する。上限 `_CHOICE_LABEL_MAX_LENGTH`(60) は `AdventureChoice.label` の寛容 validator と `_sanitize_choices` の両方で `_truncate_overlong_text` により切り詰められ、長さを理由に修復リトライや既定3択への差し替えを起こさない。romance の行動ボタン `.adventure-romance-actions` は flex-wrap ではなく2列グリッドで、3〜4個がラギッドに折り返らないようにする。

作品シナリオの装備判定 `_last_equipment_action` は、エイリアス前後を走査して最も近い着脱動詞を帰属させる。他アイテムの語で走査を打ち切るが、並列助詞（と／や／and）で繋がる場合と、直後が修飾助詞（の／に等）の場合は境界にしない。長い語に内包されただけの一致（「ヘッドドレス」中の「ドレス」）は数えない。画像側では未装備アイテムを `_equipment_negative_tags` で negative に出し、`_strip_unworn_equipment_tags` で player_tags からも除く。外衣着用時は下着 negative を出さない（`CLOTHING_LAYER_COVERED_NEGATIVE` と矛盾するため）。

preset="romance"（恋愛シミュレーション）は自動生成のみで、日数(5〜15日、1日=昼夜2ターン)を `scenario_max_turns=日数×2` として送る。好感度・金銭・ギフト採点・告白成否は `services/adventure_romance.py` の純関数が決定し、LLM は数値を書かない。告白ラインは `romance_confession_threshold(total_days)` で日数にスケールする（1手 `ROMANCE_CONFESSION_PACE` 想定、上限75。15日=75、7日=41、5日=32。日数不明の旧データは75）。会話ターンの affection_delta は resolution ガイダンスの採点基準（前向き+2、関心・ヒントに刺されば+3、平坦+1、+0は気まずい/反復のみ）に従い、±3クランプは従来どおり。現実改変で「交際を始める」を明示宣言した場合は resolution の `start_dating`（reality_alter ターン限定で有効）が告白成功と同じ扱い（全 milestone + success）になる。専用ボタン（バイト/ギフト/属性付与/告白）と重複する選択肢は narrative/resolution 両ガイダンスで禁止。day/slot は `turn_number` から導出し状態に保存しない。`state_json["sim"]` に相手・カタログ・隠し好み(`hidden_preferences`)を持ち、`_serialize_run` と `turn` イベントには隠し好みを除いた `public_sim_view` だけを `sim` として載せる。ターンは `input_kind: gift|work|confess`（gift は `gift_id` 併送、資金不足はターン未消費のエラー）を追加。属性付与は既存の現実改変機構を再利用し、HUD の現実改変チップを「付与した属性」表示に差し替える。開始素材で選んだ人物は主人公ではなく攻略対象（NPC として main_characters / npc_tags に描画、外見は `sim.partner_appearance`）。主人公（自分）はテンプレートキャラクター（`romance_player_character_id`、既定 char1）または特定セッション時点の変身状態（`romance_player_session_id`＋`romance_player_history_id`、指定時はテンプレより優先で `_build_snapshot` を流用）で、開始画像・外見ロック・立ち絵は主人公側へ差し替え、FE は選択を localStorage の adventure_setup_prefs に保存する。テンプレキャラの外見ロックは `_romance_template_player_appearance` が characters.json の gender から性別トークン(male, 1boy / female, 1girl)を明示する（base_tags に無いと画像が女性寄りに描画されるため）。director/narrative/visual の同一性署名の複写指示は sex を含み、`ROMANCE_VISUAL_GUIDANCE` は player_tags への性別トークン復唱を要求する。romance 時は HUD・メッセージウィンドウ・行動ボタンを `adventure-hud--romance` / `adventure-messagebox--romance` のローズトーンに切り替える。非合成モードでは攻略対象の立ち絵を主人公と並置表示する: 参照は run ディレクトリの `partner_initial.*`。最新パスは `state_json["partner_portrait_path"]`（開幕分は `opening_partner_portrait_path`）、ターン別パスは各ターンの state_delta に保持し（いずれも `_lean_state_for_llm` で除外）、開幕に加えて主人公と同様に毎ターン `_generate_partner_portrait_unlocked` で直列生成する（step "partner" の status を送出、FE 進捗バーにも partner 工程あり。失敗はターンを止めず前の1枚を維持）。ただしターン中のタグ決定は `_romance_partner_turn_portrait_tags` が行い、相手がその手番の `main_characters` に居なければ空文字を返して**描き直さず前の1枚を残す**。居ない相手を `sim.partner_appearance` から描くと、服装情報が無いぶん裸で描かれ、かつ改変前の古い外見へ戻って見える（実際に発生した不具合）。`npc_tags` を取れないが相手は場面に居る場合だけ `sim.partner_appearance` ＋ エントリの clothing で補う。生成ヘルパは state を自前でDB保存するが、stream 終端の全 state コミットに上書きされるため、consumer が受けたパスを必ず next_state へ反映してからコミットする。配信は SSE `partner_image`、`_serialize_run.partner_portrait_url` / `opening_partner_portrait_url`、`_serialize_turn.partner_portrait_url` で、FE は過去フレーム閲覧中もその手番時点の相手立ち絵をステージ・モーダル（攻略対象チップ/シーン並置）に表示する（欠けたターンは直前の1枚を引き継ぐ）。`_serialize_turn` は state_delta_json に sim があるターン（=romance）へ、確定時点の `sim`（public_sim_view）と攻略対象の様子 `partner_note`（main_characters の該当エントリ description）を載せ、`_serialize_run` は開幕フレーム(手番0)用に `opening_sim`（開始値は定数のため `opening_sim_view` が現在の sim から再構成）も返す。`public_sim_view` は現実改変で書き換わる `partner_appearance` も配信し、FE は主人公ドック内の第2セクションに攻略対象の外見（`sim.partner_appearance`）と服装（`visual_state.main_characters` を `partner_name` の部分一致で引く）を主人公と同じ体裁で並べる。`partner_appearance` はターンで変化するため `opening_sim` の同項目は開幕時の値に戻せない（現在値が入る）。開幕フレームの表示に使わないこと。ターン詳細モーダルはこれを使い攻略対象カード（名前・好感度・段階・様子）と Day 表記（day/slot は FE の `romanceDaySlot` で turn_number から再導出）を表示し、`ImagePreviewModal` の `className` 経由の `adventure-preview--romance` でローズテーマ化する。リプレイ（もう一度遊ぶ）は「同一シナリオ・新規 sim」として対応: `create_run` の replay 分岐が素材（`source_session_id`/`source_history_id`＝攻略対象）と主人公選択（`sim.player_character_id`、`session:` 形式なら `sim.player_history_id` 併用。リクエストに `romance_player_*` があればそちら優先）を元 run から引き継ぎ、日数は `clamp_romance_max_turns` で丸める。相手プロフィール・ギフトカタログ・隠し好みは毎回 LLM で再生成される（意図した仕様）。攻略対象の口調 `sim["partner_speech_style"]` も同じ扱いで、`RomanceSetupOutput.partner_speech_style` として `romance_setup_system_prompt` が人物像から生成し（`partner_profile` からは「話し方」の記述を外して役割の重複を消した）、ユーザーがセットアップで書いた上書き値があればそちらが優先される。`ROMANCE_NARRATIVE_GUIDANCE` が「毎手番この口調を守り、主人公の口調へ収束させない。空なら partner_profile から導く」と定め、空欄でも従来どおり動く。ミッション案の自動生成プロンプト（`_setup_system_prompt` の romance 分岐）は、恋敵を扱う機構が実装されていないため complications の例示から `rivals` を外してある。

BGM は各ターンの resolution 構造化出力の `bgm`（semantic key、既定 `daily`）で決まる。キー・説明文・音源ファイル名は `backend/gateway/data/bgm/catalog.json` が唯一の情報源で、ローダ `consts/adventure_bgm.py` が mtime 変化時のみ再読込する（ホットリロード。破損時は last-good 維持、初回破損は daily 単曲の組み込み既定。トラバーサル値はエントリごと拒否）。音源追加は「.ogg を同ディレクトリへ配置 + catalog.json にエントリー追記」だけで、ビルド・再起動とも不要。選択方針は共有定数 `BGM_SELECTION_RULES` が director/resolution 両プロンプトに載り、`state.sim.affection`/`stage`（romance）と物語進行を重要度の物差しにして、序盤の小さな贈り物・挨拶程度に `important_event` を使わせない。不正値は寛容 validator が None(据え置き)へ劣化させ修復リトライに落とさない。LLM は選曲理由 `bgm_reason` も同時に出力し（narrative と同言語・200字以内、寛容 validator が clamp/None 化）、`_merge_output` が `state["bgm"]`/`state["bgm_reason"]` をペアで保持（`bgm` None は両方前値維持、`_lean_state_for_llm` で理由は LLM から隠す）、開幕は `create_run` が `bgm`/`opening_bgm`/`bgm_reason`/`opening_bgm_reason` を seed、LLM へは turn_context の `current_bgm` として「明確な場面転換時のみ変更」ルールと共に渡す。配信は `_serialize_turn` の `bgm`/`bgm_reason`（state_delta 由来なので据え置きターンにも直近ペアが入る）と `_serialize_run` の `bgm`/`bgm_reason`/`opening_bgm`/`opening_bgm_reason`、カタログは `GET /api/adventure/bgm`（`key`/`url` に加えて BGMテスト画面の表示用に `file`/`description`/`credit` も返す。`credit` は出所の**表示文そのもの**を持つ任意フィールドで、生成AI・配布素材・自作で言い回しが変わるため FE では加工せずそのまま出す。表記不要な曲は省略。必須にするとカタログ全体が破損扱いになり組み込み既定へ劣化するため任意にすること）、音源は `GET /api/adventure/bgm/audio/{filename}`（カタログ登録名のみ許可）。FE はマウント時にカタログを fetch した `hooks/useAdventureBgm.ts` が再生を担い（取得失敗は無音で進行、未知キーは既定曲へ）、AdventureScreen は表示中フレーム（過去閲覧含む）から現在キー+理由を導出し、HUD の現在地ピル直下の `♪キー` チップ（`adventure-hud__bgm-chip`）から hudPanel="bgm" のポップオーバーで選曲理由を表示する。同一キーは厳密 no-op、変更時のみ fade out→swap→fade in。初回は必ず mute（`adventure_bgm_prefs`、読み書きは `utils/bgmPreferences.ts`）。`/bgm-test` の `components/bgm/BgmTestScreen.tsx` は同じカタログを単発再生（fade/loop なし）で試聴し、mute には触れず音量だけを `adventure_bgm_prefs` 経由で本編と共有する。旧 run/turn の `bgm`/`bgm_reason` は null で FE が daily・「理由未記録」文言に倒す。

プロンプト確認は `POST /adventure/runs/{id}/preview-prompt`（`ENABLE_PROMPT_PREVIEW` 有効時のみ。無効なら `prompt_preview_disabled`）。LLMを一切呼ばず、手番も消費せず、state も書き換えない（`_build_turn_contexts` が state を破壊的に更新するため deepcopy 上で組み立てる）。1手番＝物語・判定・ビジュアルの3呼び出しで、`turn_context` の組み立ては `_build_turn_contexts`、ビジュアルの user prompt は `_visual_user_payload` に集約し、送信経路とプレビューで必ず同じ文字列になるようにしてある（別実装にするとプレビューが嘘になる）。ビジュアルの `narrative` はその手番の生成結果なので占位文字列＋`narrative_is_placeholder` で返す。画像工程は `state["last_image_prompt"]` を `prompt_override` として `_prepare_image_prompt` へ渡す（`None` を渡すと画像タグ生成のLLM呼び出しが走ってしまう）。定型サフィックスは `_SCENE_PROMPT_SUFFIX` / `_PLAYER_PROMPT_SUFFIX` / `_NPC_PROMPT_SUFFIX` / `_PORTRAIT_PROMPT_SUFFIX` を送信側と共有する。フラグは通常ゲームの session stats 経由でしか FE に届かないため、Adventure 用に `_serialize_run` の `enable_prompt_preview` で配信し、FE は画像設定ポップオーバー内の「プロンプトを確認」から `AdventurePromptPreviewModal` を開く。

現実改変ルール `state_json["reality_rules"]` は2経路で書き換わる。ターン経路は `_detect_reality_declaration` → `_append_reality_rule`（append + 重複排除、上限12件は最古を捨てる。物語中の宣言は必ず効かせる必要があるため拒否しない）。管理経路は `PATCH /adventure/runs/{id}/reality-rules` → `update_reality_rules` で、一覧を丸ごと差し替える（ルールにIDが無いため全件置換。追加・編集・削除・並べ替えを1本で賄う）。**手番は消費しない**（`turn_count` / `status` / `AdventureTurn` に触れないので、通常ゲームの `SessionAttribute` と同じく「プロンプト注入だけ」の操作になる）。上限超過は黙って切らず `too_many_reality_rules` で拒否し、検証はロック取得前に済ませてDBに触れない。表記の正規化（空白畳み込み＋300字切り）は `_normalize_reality_rule` / `_normalize_reality_rules` に集約し両経路で共有する。`update_run_settings` と同じ `self._run_locks[run_id]` を取るので `stream_turn` との競合は直列化される。`_serialize_run` は既に `reality_rules` を返すためシリアライザ変更は不要で、`_serialize_turn` には載せない（FE はターン後に run を再取得する）。巻き戻しは対象手番のスナップショットを復元するため、その手番より後に管理経路で加えた変更は失われる（`_REWIND_KEEP_KEYS` に入れると「宣言した手番ごと巻き戻したのにルールだけ残る」というより悪い挙動になるので入れない）。FE は `AdventureAttributeModal` が一覧・編集・削除・追加を担う管理画面で、操作は即時 PATCH（未保存状態を作らない）。編集対象は添字ではなく本文文字列で保持する（ターン追記やFIFO削除で一覧がずれても別ルールを上書きしないため）。フッターは追加時「閉じる／付与のみ／付与して行動」、編集時「編集をやめる／保存」。「付与して行動」だけが `submitTurn("現実改変：〜")` で1手番を使い、PATCH は行わない（ターン側が自分で追記する）。ボタン名を「付与」にしないこと（Playwright の name 照合は部分一致で「付与して行動」と衝突する）。入口は HUD ポップオーバーの「属性を管理」／非romanceは「ルールを管理」ボタン（名前に「現実改変」を入れないこと。HUDチップと衝突する）。文言は `adventure.realityRuleManager.*` を基準にし、呼称が変わる項目だけ `adventure.romance.attribute.*` で上書きする。削除しても確定済みの外見（`appearance_lock` / `sim["partner_appearance"]`）は戻らない仕様で、モーダルにその注記を出す。

手番を使わず付与したルールは「宣言された手番」を持たないため、そのままでは `reality_rule_declared_this_turn` に載らず、プロンプトの服装・外見ロック（「明示的に選ばない限り前ターンの服装を維持」）に負けて永久に反映されない。これを避けるため `update_reality_rules` は新規追加分を `state["pending_reality_rules"]` に控え（削除された分と既反映分は積まない）、次の `stream_turn` で `_take_established_reality_rules` が入力による宣言と併せて1つの `reality_rule_declared_this_turn` にまとめ、state から消す（一度きりの通知。ターンが途中で落ちれば控えが残り次の手番で再試行される）。この手番は `appearance_update_allowed` が真になり、`_apply_appearance_lock` / `_apply_partner_appearance_lock` が visual 出力を新しいロックとして採用する（外見を変える付与を永続化するため）。`pending_reality_rules` は `_lean_state_for_llm` で除外する（内容は別途渡すため）。あわせて `_REALITY_RULES_INSTRUCTION` は「reality_rules の各項目は以後のすべての手番で効き続ける」ことを、`_visual_system_prompt` と `_narrative_system_prompt` は「ルール自体が服装や外見を規定する場合、そのルールが `previous_visual_state` に優先し、リストに残る限り毎ターン満たす」ことを明記する。これが無いと「僕はバニーレオタードを着る」のような服装ルールは、服装ロックに阻まれて宣言経路でも反映されない。

現実改変での外見の永続化は主人公と攻略対象で対称に行う。主人公は `_apply_appearance_lock(allow_update=True)` が `state["appearance_lock"]` を、攻略対象は `_apply_partner_appearance_lock` がその手番の visual 出力の npc_tags を `_identity_tags_only`（`_CLOTHING_TAG_PATTERN` / `_SCENE_OR_ACTION_TAG_PATTERN` で服装・情景を除去。素の npc_tags は服装を含むため必須）に通して `sim["partner_appearance"]` を更新し、どちらも `input_kind == "reality_alter"` のターンだけ動く。相手側は `apply_romance_outcome`（resolution の `updated_partner_appearance`）**より後**に適用して visual 由来を優先させる。resolution は visual を見ない別呼び出しで、入れ替わり宣言でも相手の元の外見をそのまま restate してくることが実際にあり、上書きされると次の手番で相手が元の姿へ戻る。実際に描かれた絵の根拠である visual 出力を正とする。相手が場面に居ない・タグが取れない・服装しか無いターンはすべて no-op で既存値を消さない。服装は現実改変で体・同一性が変わったときだけロックが外れ「服は体に従う」（入れ替わりなら双方の服も入れ替わる）。この例外は `_visual_system_prompt` と `_narrative_system_prompt` の両方に要る（narrative は visual 呼び出しの主入力なので、本文が旧衣装を書くと絵も従う）。`ROMANCE_VISUAL_GUIDANCE` / `ROMANCE_NARRATIVE_GUIDANCE` の「相手の特徴を主人公へ混ぜるな」にも入れ替え宣言の例外があり、`ROMANCE_VISUAL_GUIDANCE` は攻略対象の npc_tags にも性別トークン開始を要求する（主人公側の `_romance_template_player_appearance` に相当する砦が相手側には無いため）。

進行型の現実改変（「ターン毎に徐々に女体化する」等）: `_PROGRESSIVE_RULE_PATTERN` / `_progressive_reality_rules` が「毎ターン・徐々に・gradually」等の語で検出し、該当ルールが reality_rules に1件でも残る間は**毎ターン** `appearance_update_allowed` を真にして外見ロックの更新を許す（宣言ターン以降ロックに阻まれて変化が止まる問題への対処）。検出結果は `turn_context["progressive_reality_rules"]` と `_visual_user_payload` に載り、`_REALITY_RULES_INSTRUCTION` 末尾と `_visual_system_prompt` の両方が「毎ターン1段階ずつ進め、前段階へ戻すな。同一性署名はこのルールが変える特徴を守らない」と指示する。ロックが毎ターン前進するため `_appearance_diverged` が真になり、立ち絵参照も自動で最新立ち絵側へ切り替わる。

現実改変はタイムリミットとギフトカタログも書き換えられる（どちらも reality_alter ターン限定）。タイムリミット: 非 romance は resolution 出力の `updated_max_turns`（`_TIME_LIMIT_ALTER_INSTRUCTION` が非 romance プロンプトにだけ載る）、romance は `updated_total_days`（`ROMANCE_RESOLUTION_GUIDANCE` に記載）を、`_apply_time_limit_alteration` が `_merge_output` の手数切れ判定より前に clamp（下限=現在の手番/日、上限=`ADVENTURE_ALTER_TURNS_MAX`(60) / `ROMANCE_ALTER_DAYS_MAX`(30日)）して `run.max_turns`（romance は `sim["total_days"]` も）へ反映し、ターンコミットが `persisted.max_turns` を常に同期する。エピローグ中は無視。巻き戻しは state しか復元しないため max_turns の変更は巻き戻しで戻らない。ギフトカタログ: romance の resolution 出力 `updated_gift_catalog`（`RomanceAlteredGift` のリスト。空=変更なし。tier 帯への価格クランプをしないので無料化可、`preference` で好みも同時指定可）を `apply_gift_catalog_update` が全品目置換として適用する。既存品は名前一致で ID を引き継ぎ（好み・贈答済み参照を壊さない）、新規品は未使用の連番、消えた品の好み・贈答記録は掃除する。適用は `_apply_preference_updates` より先（ID 照合を新カタログで行うため）。

Adventureの画像設定は run の `state_json` に持つ。`use_precise_reference`、`enable_composite_scene`、`respect_clothing_layers` を `POST /runs` と `PATCH /runs/{id}/settings` で設定し、`_prepare_image_prompt` と `_generate_image_unlocked` が state から読む。精密参照ON時の合成シーンの character reference は主人公（そのターンの立ち絵、無ければ初期画像）が1枚目で、romance では攻略対象が npc としてシーンに登場するターンに限り `_romance_partner_scene_reference` が `partner_image_path`（開始素材）を2枚目として弱参照（strength 0.35 / fidelity 0.55）で追加する。ただし現実改変で外見が開始時から乖離した後は、元の姿のままの参照画像を使わない: `_appearance_diverged` / `_partner_appearance_diverged` が `state["initial_appearance_lock"]` / `state["initial_partner_appearance"]`（`create_run` で seed、旧 run は `stream_turn` 冒頭で現在値からバックフィル、`_lean_state_for_llm` で LLM から隠す）と現在値を比較し、真なら `_generate_portrait_unlocked` は `run.portrait_image_path`、`_generate_partner_portrait_unlocked` と `_romance_partner_scene_reference` は `state["partner_portrait_path"]` を参照し、それも無ければ参照なしで描く（古い姿を弱参照するより無参照が正しい）。立ち絵生成系は DB から state を読み直すため、宣言ターン自体は乖離前として扱われ従来どおり元画像を参照する。参照強度は `has_fresh_portrait=False` のまま（強参照にすると衣装が再固定される）。参照とキャラ枠の紐付けはAPIに無くモデルの照合に任せる。romance で精密参照ONのターン送信は、画像プロバイダーが novelai のときに限り FE の `AdventureContext.submitTurn` が送信前にAnlas確認ダイアログを挟む（保留は `pendingAnlasTurn`、抑止は sessionStorage `adventure_anlas_warn_suppressed` でブラウザセッション単位。ギフト・属性付与モーダル経由の送信も同じガードを通る）。セットアップ画面の開始も、novelai かつ精密参照ON時はプリセットを問わず `handleCreate` が同じ確認を挟む（オープニング画像生成が既にAnlasを消費するため）。ダイアログは共通コンポーネント `AdventureAnlasConfirmDialog` で、通常ゲーム側と同じ体裁・抑止チェックを持つ。`respect_clothing_layers` は設定画面のグローバル値をAdventureScreenが同期し、ON時は外衣に覆われた装備下着タグを positive から外して被覆用 negative を足す。

## Prompt Expander（実験的機能）

```text
PromptExpanderScreen (/prompt-expander, /prompt-expander/:sessionId)
  ↓ PromptExpanderContext（Provider は /prompt-expander 配下だけ。App.tsx で包む）
apis/promptExpander.ts
  ├─ GET/PUT /api/prompt-expander/settings     専用設定（users.prompt_expander_settings_json）
  ├─ /sessions, /sessions/{id}, /sessions/{id}/uploads, /entries, /images/{entry_id}
  ├─ POST /expand                              LLM のみ（NovelAI テキスト glm-4-6 / xialong-v1 固定）
  ├─ POST /manga-script                        あらすじ → 記法付きネーム（漫画モード・V5 専用、LLM のみ）。FE は結果で入力欄を置き換え「元の文に戻す」を出す
  ├─ POST /sessions/{id}/generate              画像のみ（NovelAI 固定、raw_prompt=True）。応答に entry + anlas
  └─ POST /suggest-characters                  PE メモリ（無ければグローバルメモリ）＋ `input_text`（欄の下書き）から好みのキャラ提案。両方空なら memory_empty
      ↓
prompt_expander_router → prompt_expander_service / prompt_expander_prompts
  ├─ PromptExpanderSession / PromptExpanderEntry
  └─ data/prompt_expander_images/{session_id}/{entry_id}.png
```

- 通常ゲームの `image_only` と違い、拡張は欄右上の「拡張」ボタンによる明示操作で、拡張と画像生成は別 API。結果は欄直下のインラインカードで確認・編集してから「欄へ反映」または「この内容で生成」（カードは生成後も残り、繰り返し・微調整できる。`instruction` はクリック時点の欄の内容）し、下部の「生成」は欄の内容をそのまま送る（拡張の由来は Context の origin として `positive_expand_mode`/`instruction` に載る）。履歴の「欄へ復元」は拡張ありエントリなら原文を欄へ戻して変換結果をカードとして再現し、「このプロンプトで再生成」はエントリの内容のまま seed 無し（毎回乱数）で `POST /generate` する。タグ/漫画モードの拡張では日本語の「ショーツ」を panties に寄せる語彙ルールと、指示に「ショーツ」があるときの単独タグ `shorts`→`panties` 置換を掛ける。設定 `confirm_before_generate` は API に残るが FE では使わない。SSE は使わない。
- `raw_prompt=True`（`image_generation.py`）は `_format_prompt` の `、。→", "` 置換・長い接尾辞・`extra_negative`・サーバー既定ネガティブへのフォールバックをすべて無効化する（日本語自然文プロンプトを壊さないため）。SDK の `quality=True` と `uc_preset` は従来どおり。同時に `noise_override=0.0` が既定値へ落ちる不具合も `is not None` 判定に修正した。
- 正/ネガそれぞれ「日本語で拡張」（V5 向け自然文）と「タグで拡張」（英語タグ、移植元の品質タグ補完あり）。キャラクターモードは JSON `{base_prompt, character_prompts[]}` で、上限は `consts/prompt_expander.max_character_prompts(image_model)`（V5=22 / V4.5=6）。超過は切り詰め、0 件は `invalid_llm_output`。
- 漫画モード（V5 専用、`supports_manga_mode`）: 設定（`manga_mode` / `manga_panel_count`(0=おまかせ) / `manga_layout` / `manga_dialogue` / `manga_text_language`(auto/ja/en) / `manga_sound_effects` / `manga_reading_direction`(rtl=日本式右上始まりが既定/ltr)）は `PromptExpanderSettings` JSON に保存。FE は V5 選択時だけ `POST /expand` に `manga_mode=true, manga:{...}` を載せ（Context の `mangaActive`）、BE は `MangaOptions` で `build_manga_system_prompt` に差し替えて JSON `{base_tags, panel_description, character_prompts[]}` を `parse_manga_json` で「タグ見出し + コマ説明文」に結合する（キャラモード OFF は character_prompts を無視）。漫画モードは拡張モード（日本語/タグ）に依存せず引用符内のセリフ・効果音以外は常に英語（日本語の説明文は V5 がナレーション枠として描画するため）。FE も漫画モード中は `positive_mode` を `tags` に固定して送る（`effectivePositiveMode`）。V4.5 で送ると `manga_requires_v5`(422)。生成時は `manga_mode` / `manga_panel_count` をエントリ列に残しバッジ・復元に使う（生成内容には影響しない）。指示文の記法 `「セリフ」『モノローグ』【ナレーション】《効果音》` と行頭の `①②③`/`1:`（コマ番号）は BE の `extract_manga_notation` が抜き出し、system prompt の記法ルールと user prompt の「Marked text」一覧で LLM に原文どおり描かせ、出力に欠けた文字は `ensure_manga_notation_texts` が定型英文で補う（空括弧は内容を LLM に任せる）。ナレーション枠は【】で書いたときだけ出るのが既定で、設定 `manga_narration`（`manga.narration`）ON のときだけ LLM が場面転換等で自動追加する。
- 参照元（i2i 元）は `source_kind: none | history | entry | upload`。`entry` なら保存済み最終プロンプト/キャラプロンプト/ネガを「現在のプロンプト」として LLM へ渡し（`inherit_source_prompts`）、`history` なら `after_description` を参考情報として渡す。NSFW は画像モデルの family（full/curated）から導出し、ADULT/SAFE ルールと `nsfw_mode` の両方に使う。
- 開始素材連携: 通常ゲームは WelcomeScreen が PE 画像を data URL 化して既存 `POST /api/game/start-custom` に流す（BE 無変更）。Adventure は `POST /adventure/setup/generate` / `POST /adventure/runs` に `source_prompt_expander_entry_id`（`source_session_id` と排他、両方あれば PE 優先。リプレイは元 run から引き継ぐ）を受け、`_build_snapshot` が `_build_prompt_expander_snapshot` へ分岐する（appearance = 最終プロンプト＋キャラプロンプト、timeline/attributes/stats なし、nsfw は family 由来）。run は画像をコピーするため `AdventureRun.source_prompt_expander_entry_id` に FK は張らない。

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

| 操作                      | モデル                                                                    |
| ------------------------- | ------------------------------------------------------------------------- |
| セッション開始/通常プレイ | `Session`、`SessionStats`、`History`、`Conversation`、`TransformationTag` |
| プレイメモ                | `Session.play_memory_*`                                                   |
| 複数人物                  | `SessionCharacter`、`CharacterPreset`                                     |
| Adventure                 | `AdventureRun`、`AdventureTurn`                                           |
| お気に入り                | `FavoriteOutfit`                                                          |
| 設定/長期メモリ           | `User`                                                                    |
| 実績                      | `UserAchievement`、`AchievementCount`、`AchievedEnding`                   |
| 要約                      | `PlaySummary`                                                             |
