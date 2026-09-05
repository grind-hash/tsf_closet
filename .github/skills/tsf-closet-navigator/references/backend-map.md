# バックエンド アーキテクチャマップ

> 最終検証: 2026-08-28 | 対象: `backend/gateway`、`backend/migrations`

## FastAPI 構成

- エントリーポイント: `backend/gateway/app.py`
- APIモデル（Pydantic）: `backend/gateway/schemas/`（ドメイン別。下表）
- 内部状態モデル（dataclass）: `backend/gateway/models.py`（難易度プリセット、臨界点、`SessionStats`、`Character`、`PersistedHistory` / `PersistedSession` など）
- ルーター公開: `backend/gateway/routes/__init__.py`
- DBモデル: `backend/gateway/databases/models.py`
- DB初期化・セッション: `backend/gateway/databases/base.py`、`database.py`、`orm.py`
- Alembic: `backend/migrations/versions/`
- `routes/*_router.py` は `app.py` でマウントする。原則 `/api` を付け、互換 API（`system_router` / `novelai_router` / `openai_images_router`）だけ prefix 無し。`app.py` 自体はライフサイクル・CORS・ルーター登録・静的配信のみ。

## API モデル（`gateway/schemas/`）

ルーターとサービスが共有する Pydantic モデル。使うモジュールから直接 import する（`gateway/models.py` からは import しない。テストもルーター経由ではなく `gateway.schemas.*` から import する）。ルーター内に `BaseModel` を定義しない。参照ゼロのモデル（SSE イベント型、`ChatRequest` / `ChatResponse`、`HealthResponse`、`SelfProfile` 等）は分割時に削除済みで、新しいモデルは該当ドメインへ追加する。

| ファイル          | 内容                                                                                                         |
| ----------------- | ------------------------------------------------------------------------------------------------------------ |
| `session.py`      | `SessionResponse` / `HistoryItem` / `SessionSummary` / `SessionListResponse`、プレイメモ、分岐開始、ゲーム開始、履歴選択・リセット |
| `play.py`         | `PlayRequest`（`preview_prompt` 用）と `PlayStreamRequest` / `CharacterReferenceParam`（SSE 送信用）           |
| `conversation.py` | `ConversationMessageResponse`、指示候補生成の `SuggestInstruction*`                                          |
| `parameters.py`   | `SessionStatsResponse`（camelCase alias + `populate_by_name`）、難易度一覧                                    |
| `characters.py`   | `CharacterInfo` / `CharacterListResponse`、セッション人物・人物プリセットの CRUD、人物タグ生成、`CharacterPositionLiteral` |
| `gallery.py`      | エンディングギャラリー                                                                                       |
| `novelai.py`      | インペイント用マスク管理（`MaskSaveRequest` / `MaskInfo` / `MaskListResponse`）と Anlas 残高（`AnlasBalanceResponse` / `AnlasUsageModel`。通常ゲームと Prompt Expander で共用） |
| `common.py`       | `ErrorResponse`                                                                                              |
| `adventure.py`    | Adventure の Run 作成・設定更新・ターン・画像・トーク・プロンプト確認の各リクエスト、`AdventureImageModel` Literal、`SCENARIO_MAX_TURNS_REQUEST_MAX` |
| `prompt_expander.py` | Prompt Expander の全リクエスト / レスポンスと入力値の Literal（`ImageModelLiteral` 等。定数との整合を import 時に assert）、`MangaOptionsModel.to_options()` |
| `settings.py`     | アプリ設定（`SettingsModel` / `SettingsUpdateRequest`）、互換ユーザー設定（`UserSettings*`）、自分自身モードのプロフィール生成・保存 |
| `gallery.py`      | ギャラリー一覧・詳細・削除（`GalleryItem` / `GallerySession` / `DeleteResponse`）とエンディングギャラリー                      |
| `favorites.py` / `memory.py` / `aivisspeech.py` / `avatar.py` / `achievements.py` | 各ルーターのリクエスト / レスポンス |

## ルーター

| 実パス              | ファイル                        | 主な責務                                                                        |
| ------------------- | ------------------------------- | ------------------------------------------------------------------------------- |
| `/api/game`         | `routes/game_router.py`         | セッション、プレイSSE、会話、履歴、画像、属性、プレイメモ、プロンプト、指示候補 |
| `/api/game`         | `routes/character_router.py`    | セッション人物、主人公確保、人物プリセット、人物タグ生成                        |
| `/api/adventure`    | `routes/adventure_router.py`    | シナリオテンプレート、Run、ターンSSE、画像再生成                                |
| `/api/gallery`      | `routes/gallery_router.py`      | セッション/履歴一覧、検索、詳細、削除、要約、Markdown/HTMLエクスポート          |
| `/api/favorites`    | `routes/favorites_router.py`    | お気に入り一覧、追加、ラベル変更、削除                                          |
| `/api/achievements` | `routes/achievements_router.py` | 実績一覧と詳細                                                                  |
| `/api/settings`     | `routes/settings_router.py`     | 設定、互換ユーザー設定、セルフプロフィール                                      |
| `/api/memory`       | `routes/memory_router.py`       | ユーザーメモ本文、生成ジョブ、状態、取消、分析エクスポート                      |
| `/api/aivisspeech`  | `routes/aivisspeech_router.py`  | エンジン/モデル管理、話者一覧、音声合成                                         |
| `/api/prompt-expander` | `routes/prompt_expander_router.py` | Prompt Expander（実験的）: 専用設定、セッション/エントリ、アップロード、LLM 拡張、NovelAI 生成、画像/マスク配信、キャラ提案 |
| `/api/avatars` | `routes/avatar_router.py` | 3D モデル(VRM)の登録（唯一の `UploadFile` multipart。`POST` 201、400 `invalid_vrm`、413 `file_too_large`。フォーム欄 `name` / `character_name` / `variant_label` は任意で、`character_name` 未指定ならファイル名 `名前_衣装_….vrm` から自動分類、空文字で未分類）、一覧 `{items}`、更新 `PATCH {name?, character_name?, variant_label?}`（1 つ以上必須、空文字で解除。`AvatarUpdateRequest`）、一括分類 `POST /auto-classify` → `{updated, updated_ids, items}`（未設定のキャラクター名・差分ラベルだけをモデル名の規則で埋める。設定済みは変えない）、削除 204、配信 `GET /{id}/file`（`model/gltf-binary`、inline）。Adventure 対面会話モードで攻略対象の代わりに描く |

### `game_router.py` の主要操作

| 操作                                            | パス                                                                                                                  |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| キャラクター一覧、セッション取得/開始/復元/削除 | `/characters`、`/session/{id}`、`/start`、`/start-custom`、`/sessions/{id}/restore`、`DELETE /session`                |
| 通常プレイ                                      | `POST /play/stream`                                                                                     |
| 履歴選択・分岐・削除                            | `/history/{id}/select`、`/history/{id}/branch-session`、`DELETE /history/{id}`、`DELETE /session/{id}/latest-history` |
| 会話                                            | `/chat`、`/chat/stream`、`/conversation/{id}`、会話単体/履歴単位削除                                                  |
| プレイメモ                                      | `PATCH /sessions/{id}/play-memory`、`POST /sessions/{id}/play-memory/regenerate`                                      |
| 指示支援                                        | `POST /suggest-instruction`、`POST /preview/prompt`、`POST /generate-base-tags`                                       |
| 画像支援                                        | `/improve-quality/stream`、`POST /standing-portrait`、`/masks`、`/anlas`                                              |
| 現実改変属性                                    | `POST /attributes`、`GET/DELETE /attributes/{id}`                                                                     |

### 複数人物とプリセット

`character_router.py` は `/api/game` 配下に次を追加する。

- `/session/{session_id}/characters`: セッション人物の一覧・追加
- `/session/{session_id}/characters/ensure-protagonist`: 主人公レコードの冪等確保
- `/session/{session_id}/characters/{character_id}`: 更新・削除
- `/session/{session_id}/characters/from-preset/{preset_id}`: プリセット適用
- `/characters/generate-tags`: 複数人物タグの一括生成
- `/character-presets`: プリセット CRUD

### Adventure

- `GET /templates`
- `POST /setup/generate`
- `POST/GET /runs`、`GET/DELETE /runs/{run_id}`
- `POST /runs/{run_id}/turns/stream`
- `POST /runs/{run_id}/image/stream`
- `POST /runs/{run_id}/choices/regenerate`
- `PATCH /runs/{run_id}/settings`
- `PATCH /runs/{run_id}/reality-rules`（現実改変ルールの全件置換。手番を消費しない）
- `POST /runs/{run_id}/talk/stream`（romance のトークモード。手番を消費しない会話の SSE。`talk_chunk` / `talk_done`）
- `POST /setup/generate` / `POST /runs` / `PATCH /runs/{run_id}/settings` の `companion_mode`（romance の対面会話モード。1手番＝1往復・昼夜なし・ターン数で進行）
- `POST /runs/{run_id}/image/stream` の `target` は `scene` / `portrait` / `partner`（攻略対象の立ち絵のみ。対面会話モードの↻）
- `POST /runs` / `PATCH /runs/{run_id}/settings` の `inventory_enabled`（持ち物システム。全プリセット、作品シナリオでは無視）。`POST /runs/{run_id}/turns/stream` / `preview-prompt` の `input_kind: item_action` ＋ `item_action{item_id, action, target}`（`AdventureItemActionRequest`）
- `GET /images/{run_id}/{filename}`

### 互換/補助API（/api 配下ではないルーター）

`app.py` にはエンドポイントを置かず、次のルーターを prefix 無しでマウントする。

| パス                                             | ファイル                          | 目的                         |
| ------------------------------------------------ | --------------------------------- | ---------------------------- |
| `/health`                                        | `routes/system_router.py`         | プロバイダーを含むヘルス情報 |
| `/api/history/images/{history_id}`               | `routes/history_router.py`        | 履歴画像取得（`/api` 配下）  |
| `/api/history/surroundings/{history_id}`         | `routes/history_router.py`        | 情景画像取得（`/api` 配下）  |
| `/novelai/subscription`、`/novelai/suggest-tags` | `routes/novelai_router.py`        | NovelAI補助                  |
| `/v1/images/edits`、`/v1/images/variations`      | `routes/openai_images_router.py`  | OpenAI互換画像API。multipart の解析と ComfyUI 実行は `services/openai_image_form.py` |

## サービス

### ゲームと生成

| ファイル                  | 主な責務                                                                                                                                                                                                                                                                                                                         |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `game_service.py`         | 指示タイプ分岐、心境/画像生成、永続化、パラメータ、SSE                                                                                                                                                                                                                                                                           |
| `providers.py`            | 生成プロバイダー判定の唯一の入口。`Provider`（StrEnum: selfhost / openrouter / novelai）と `resolve_image_provider` / `resolve_text_provider` / `resolve_image_description_provider`（大文字小文字と未知の値を正規化し、上書き値を優先）。`settings.*_provider` を直接比較しない |
| `http_client.py`          | 外部 API 向け `httpx.AsyncClient` の生成（`async_client(timeout=...)`。timeout は必ず明示し、`httpx.AsyncClient(` を直接書かない）と、レート制限（429）時に 1 回だけやり直す `retry_once_on_rate_limit` / `is_rate_limited`。テストは `httpx.AsyncClient` を monkeypatch すれば差し替えられる |
| `cost_tracker.py`         | 1 操作の API 料金（USD）集計。入口で `begin_cost_tracking()`、LLM / 画像の結果を受けたら `record_cost(cost_usd)`。`contextvars` で受け渡すので `asyncio.create_task` の producer 内の加算も呼び出し元に届く。通常ゲームの SSE `cost` は前回通知からの差分を `_pending_cost_event` で送り、Adventure は終端で合計を送る |
| `llm_json.py`             | LLM 出力から JSON を取り出す共通処理。`strip_code_fence`（コードフェンス除去。各サービスで独自実装しない）、`extract_json_object`（前後の説明文を落として `{...}` を抜く）、`validate_model_json`（Pydantic 検証。文字列内の生改行は `strict=False` で救済）、`generate_validated`（生成→検証→失敗時に 1 回だけ修復依頼→再検証。2 回目失敗は `StructuredOutputError`）。Adventure の director / setup / resolution / 画像プロンプトはすべてこれを使う |
| `llm_service.py`          | OpenRouter/NovelAI/互換LLM呼び出し。プロバイダー分岐は `LLMService._client_for`（feeling / text / stream）と `_vision_or_edit_client_for`（画像説明・画像編集プロンプト。NovelAI に経路が無く openrouter 以外は LiteLLM）の 2 か所だけで、各クライアントは `_OpenRouterTextClient` / `_NovelAITextClient` / `_SelfhostTextClient` で同じ形（`LLMResult`）に揃える                                                                                                                                                                                                                                                                                               |
| `image_generation.py`     | OpenRouter/NovelAI画像生成とプロバイダー共通化。マスク付き生成は `mask_bytes` で `action=infill`＋インペイント用モデルへ自動で切り替わり、マスクの量子化グリッドはベース画像の 1/8（`PROMPT_EXPANDER_MASK_GRID_DIVISOR`）から導く（固定値だと landscape/square で縦横比が崩れる）。NovelAIモデル定義（V5/インペイント対応、SDK Literal用ベースモデル）は `consts/novelai_models.py` が唯一の情報源で、ユーザー選択は User の `novelai_image_model` / `novelai_curated_image_model` から `resolve_user_image_model` で解決し `novelai_model_override` として配管する。精密参照（character reference）を送れるかは `supports_character_references(model)`（V5 は False）で判定し、各サービスで `is_v5_image_model` の否定を書かない |
| `image_paths.py`          | DB に保存された画像パス文字列（`history_images/...`、`images/characters/...`、旧データの絶対パスやファイル名のみ）を実ファイルへ解決する `resolve_stored_image_path(raw, history_images_dir=...)`。通常ゲームの現在画像、Adventure の開始素材、`session_store.resolve_history_image_file` が共用する（候補順: data 相対 → BASE_DIR 相対 → 文字列どおり → 履歴ディレクトリ直下の同名） |
| `anlas_service.py`        | NovelAI `/user/subscription` からAnlas残高とV5利用上限 `usage` を1コールで取得                                                                                                                                                                                                                                                   |
| `comfy.py`                | selfhost ComfyUI クライアント                                                                                                                                                                                                                                                                                                    |
| `litellm_client.py`       | LiteLLM 統合                                                                                                                                                                                                                                                                                                                     |
| `model_execution_gate.py` | モデル実行の直列化/排他制御                                                                                                                                                                                                                                                                                                      |
| `history_context.py`      | 指示タイプ別の履歴遡及と時系列コンテキスト                                                                                                                                                                                                                                                                                       |
| `clothing_layers.py`      | 衣装レイヤー可視性ルール                                                                                                                                                                                                                                                                                                         |
| `gender_congruence.py`    | 性別適合のルール/LLM判定                                                                                                                                                                                                                                                                                                         |

### プロンプト

| ファイル                            | 対象                                        |
| ----------------------------------- | ------------------------------------------- |
| `prompts.py`                        | 着せ替え、心境、NovelAI、共通画像プロンプト。NovelAI 向け品質タグと nsfw の付与は `enhance_prompt_for_novelai(prompt, nsfw_mode=...)` に一本化（game / adventure で私的ラッパーを持たない） |
| `reality_prompts.py`                | 現実改変                                    |
| `self_mode_prompts.py`              | セルフモード                                |
| `image_only_prompts.py`             | `image_only` 専用画像指示                   |
| `instruction_suggestion_prompts.py` | 指示候補                                    |
| `memory_prompts.py`                 | ユーザーメモ生成/統合                       |
| `summary_prompts.py`                | 要約と分岐状況                              |

### セッション、メモリ、人物

| ファイル                    | 主な責務                                           |
| --------------------------- | -------------------------------------------------- |
| `session.py`                | Session/History/Conversation のストアと復元        |
| `session_branch_service.py` | 履歴地点からのセッション分岐                       |
| `play_memory_service.py`    | セッション単位の自動/ユーザープレイメモ            |
| `memory_job_service.py`     | ユーザー単位メモリ生成ジョブと監査スナップショット |
| `character_service.py`      | SessionCharacter、CharacterPreset、人物外見同期    |
| `characters.py`             | テンプレートキャラクターメタデータ                 |
| `conversation_service.py`   | 会話管理                                           |
| `settings_service.py`       | User設定                                           |

### 独立機能

| ファイル                                              | 主な責務                                                                                                                                                                       |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `avatar_service.py`                                   | 3D モデル(VRM)の検証・保存・配信。GLB ヘッダと JSON チャンクだけを読み `extensions.VRM`(0.x) / `VRMC_vrm`(1.0) の meta を `{title, author, license, license_url, allowed_user, commercial}` に正規化（追加依存なし）。アップロードは `settings.avatar_models_dir`（既定 `data/avatar_models`）へ `.part` にストリーム書きし、`settings.avatar_upload_max_bytes`（既定 128 MiB。画像プロキシ用 `multipart_max_part_size` 8 MiB は使わない）を超えたら中断、検証後に `{id}.vrm` へ `os.replace`。`resolve_avatar_file` は bare filename しか通さない。`AvatarError.code` は `invalid_vrm` / `file_too_large` / `avatar_not_found` / `file_missing`。衣装差分の分類: `classify_avatar_filename`（`名前_衣装_髪型Ver` → (キャラクター名, 差分ラベル)。区切り無し・空は未分類）、`update_avatar`（None 据え置き、空文字で解除。`rename_avatar` はその薄い包み）、`list_avatar_variants`（同じ `character_name` を `variant_label` 順で自身込み。未分類は自身のみ、未登録は空）、`auto_classify_avatars`（全モデルのうち未設定の項目だけを `classify_avatar_filename(model.name)` で埋めて更新分を返す。名前が meta.title 由来のモデルは規則に合わず対象外）、`avatar_variant_label` / `avatar_display_name`（`キャラクター / 差分`） |
| `adventure_service.py`                                | Run作成、ディレクター/解決、ターン、画像、実効画像の直列化。BGMキーは `gateway/data/bgm/catalog.json`（ローダは `consts/adventure_bgm.py`、mtimeホットリロード）が唯一の情報源 |
| `adventure_romance.py`                                | romance プリセットの決定論ロジック（日数/好感度/金銭/ギフト採点/告白）。境界値は `consts/adventure_romance.py`。対面会話モードの台本ルール `romance_script_format_guidance`・現在地キー `romance_location_key`・昼夜タグ除去 `strip_romance_time_of_day`、トークモードの `romance_talk_system_prompt` と `talk_log` 操作（`append_talk_entry` / `recent_talk_entries` / `public_talk_log` / `normalize_talk_reply`）もここ |
| `adventure_inventory.py`                              | 持ち物システム（全プリセット、既定 OFF）。判定 LLM の World Event（`WorldEvent` / `coerce_world_events`）と現実改変ターンの `RealityPatch`（`coerce_reality_patch`）の寛容 validator、`apply_world_events`（所持・数量・能力を検証して適用）/ `apply_reality_patch`（検証なしで書き換え）/ `resolve_item_action`（パネル操作の検証。純関数）/ `apply_item_resolution`（着脱・破棄の確定適用）、NPC 名の照合 `resolve_npc_name`、LLM・配信ビュー（`lean_inventory_for_llm` / `npc_states_for_llm` / `worn_inventory_items` / `public_inventory_view` / `public_npc_states`）、プロンプト文（`INVENTORY_NARRATIVE_INSTRUCTION` / `WORLD_EVENTS_INSTRUCTION` / `REALITY_PATCH_INSTRUCTION` / `INVENTORY_VISUAL_INSTRUCTION`）。語彙・上限は `consts/adventure_inventory.py` |
| `adventure_template_loader.py`                        | `scenarios/*.json` の検証とローカライズ                                                                                                                                        |
| `favorite_service.py`                                 | FavoriteOutfit CRUD                                                                                                                                                            |
| `export_service.py`                                   | MarkdownとNovel HTML ZIP生成                                                                                                                                                   |
| `summary_service.py`                                  | プレイ要約                                                                                                                                                                     |
| `aivisspeech_service.py`                              | AivisSpeechの導入、起動、合成、WAV結合                                                                                                                                         |
| `achievement_service.py`、`achievement_classifier.py` | 実績判定と分類                                                                                                                                                                 |
| `tag_classifier.py`                                   | 変身タグ分類                                                                                                                                                                   |
| `prompt_expander_service.py`、`prompt_expander_prompts.py` | Prompt Expander。`PromptExpanderSettings`（`users.prompt_expander_settings_json`）、セッション/エントリ CRUD、画像ファイル（`data/prompt_expander_images/{session}/{entry}.png`）、`expand_prompts`（NovelAI テキストモデル固定）、`generate_entry`（`image_service.generate_image(provider_override="novelai", raw_prompt=True)`）、キャラ提案（メモリに加え `input_text`=欄の下書きを受け、両方空のときだけ `memory_empty`）。プロンプト原文・サニタイズは `prompt_expander_prompts.py`（タグ/漫画モードには日本語の空似言葉ルール `JAPANESE_TAG_GLOSSARY_RULE`（ショーツ→panties）を付け、指示に「ショーツ」がある場合は `replace_false_friend_tokens` で単独タグ shorts を panties に置換）。画像配信は `FileResponse(filename="{entry_id}.png", content_disposition_type="inline")`。漫画モードの記法（「」『』【】《》・コマ番号）は `extract_manga_notation` / `build_manga_notation_block` / `ensure_manga_notation_texts`、自動ナレーションは `MangaOptions.narration`（設定 `manga_narration`）。ネーム下書きは `draft_manga_script`（`build_manga_script_prompts` / `sanitize_manga_script`、`POST /manga-script`）。境界値は `consts/prompt_expander.py`（V5=22 人 / V4.5=6 人、画像モデル 4 種、サイズ 3 種、漫画モードのコマ数 0〜6 / レイアウト / セリフ言語）、テキストモデルは `consts/novelai_text_models.py` が唯一の情報源。精密参照は `generate_entry` が `reference_kind`（none/history/entry/upload。`resolve_source` を i2i 元と同じ経路で再利用）から bytes を解決し `character_references=[{image, type, strength, fidelity}]` を渡す（V4.5 系のみ。V5 で `reference_kind != none` は `precise_reference_requires_v45`(422)）。背景透過は `transparent_background`（漫画モード時は無効）で送信用プロンプトにだけ `apply_transparent_background`（V5 `transparent background, no shadow` / V4.5 `simple background, white background, no shadow`、negative に `multiple views, reference sheet, character sheet, turnaround` を `merge_tags` で冪等併合）を掛け、エントリの `final_prompt` は接尾辞なしで保存する。`expand_prompts` は `transparent_background` で `build_positive_system_prompt` に背景を書かせない規則（`TRANSPARENT_BACKGROUND_RULE_TAGS` / `_JA`、漫画モードでは無視）を足す。参照種別 3 種・既定 character/0.85/1.0・Anlas 5/枚・透過タグは `consts/prompt_expander.py`。背景透過タグの強調は `transparent_emphasis`(0〜3、既定2)→`emphasize_tag` で V4.5 の `simple background`/`white background` にだけ `{}` を掛ける（V5 は常に無強調）。`merge_tags` の重複判定は `clothing_layers.normalize_tag_for_match` で強調記法を外してから行う。インペイントは `inpaint_mask`（新規描画の base64）または `inpaint_mask_entry_id`（保存済みマスクの再利用）を `mask_bytes` として `generate_image` に渡し、i2i 元が無ければ `inpaint_requires_source`(422)。マスクは `{entry_id}_mask.png` として画像と同じ場所に保存し（`entry_mask_file` / `resolve_entry_mask_file`）、`GET /entries/{id}/mask` で配信、`delete_entry` は画像とマスクの両方のパスを返す |

## 永続化モデル

| モデル                                                  | 主なデータ                                                             |
| ------------------------------------------------------- | ---------------------------------------------------------------------- |
| `User`                                                  | UI/生成/TTS/メモリ設定。NovelAI画像モデル選択（NSFW用/非NSFW用）、Prompt Expander 専用設定 JSON（`prompt_expander_settings_json`）を含む |
| `Session`                                               | 現在画像、active、変身回数、セッションプレイメモ                       |
| `History`                                               | 指示、指示タイプ、画像、情景画像、心境、前後記述、seed                 |
| `SessionStats`                                          | bloom、shame、adaptation、臨界点、難易度                               |
| `Conversation`                                          | セッション会話                                                         |
| `TransformationTag`                                     | 衣装、露出、年齢印象                                                   |
| `SessionAttribute`                                      | 現実改変属性                                                           |
| `AdventureRun`                                          | シナリオ状態、現在/初期/背景/立ち絵画像、設定、開始素材（session/history または `source_prompt_expander_entry_id`） |
| `AdventureTurn`                                         | 入力、語り、状態差分、画像、立ち絵、画像状態                           |
| `SessionCharacter`                                      | セッション人物の外見、位置、ロック、主人公フラグ                       |
| `CharacterPreset`                                       | 再利用可能な人物定義                                                   |
| `FavoriteOutfit`                                        | UserとHistoryを結ぶお気に入り                                          |
| `AvatarModel`                                           | 登録済み 3D モデル(VRM)。`name`(80)・`character_name`(80, nullable。同じキャラクターの衣装差分をまとめるグループ名。index `idx_avatar_models_character`)・`variant_label`(80, nullable。差分の説明)・`file_path`(bare filename `{id}.vrm`)・`file_size`・`vrm_spec_version`("0"/"1")・`meta_json`・`created_at`。migration `019_add_avatar_models` / `020_add_avatar_character_variant`。`user_id` は持たない |
| `PromptExpanderSession`、`PromptExpanderEntry`          | Prompt Expander の履歴（1セッション複数エントリ）。エントリは指示・拡張モード・最終プロンプト/ネガ/キャラプロンプト・モデル・seed・i2i 強度/ノイズ・サイズ・漫画モード（`manga_mode` / `manga_panel_count`）・参照元（history/entry/upload）・背景透過の印（`transparent_background`）・精密参照（`reference_kind` / `reference_history_id` / `reference_entry_id`（FK SET NULL） / `reference_type` / `reference_strength` / `reference_fidelity`。migration `015_add_prompt_expander_reference`）・インペイント（`inpaint` / `inpaint_mask_path`。migration `018_add_prompt_expander_inpaint`）・画像パス |
| `PlaySummary`                                           | セッション要約とタイムライン                                           |
| `UserAchievement`、`AchievementCount`、`AchievedEnding` | 実績/エンディング進捗                                                  |
| `ParameterChangeLog`                                    | パラメータ変更監査                                                     |

DB変更では `backend` で Alembic を実行する。DB を使うテストは `tests/conftest.py` の `isolated_db` フィクスチャ（一時 SQLite、外部キー有効、import 済みの全モジュールの `async_session_factory` / `sync_session_factory` を差し替え）を使い、実 DB `backend/data/database.sqlite` には接続しない。ルーター用の固定値スタブ（`StubSessionStore` / `StubSettingsService`）は `tests/support/stubs.py` にある。永続化の真偽はレスポンスだけでなくDB行でも検証する。
