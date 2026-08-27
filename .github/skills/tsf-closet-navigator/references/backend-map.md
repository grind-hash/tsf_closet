# バックエンド アーキテクチャマップ

> 最終検証: 2026-08-10 | 対象: `backend/gateway`、`backend/migrations`

## FastAPI 構成

- エントリーポイント: `backend/gateway/app.py`
- APIモデル: `backend/gateway/models.py`
- ルーター公開: `backend/gateway/routes/__init__.py`
- DBモデル: `backend/gateway/databases/models.py`
- DB初期化・セッション: `backend/gateway/databases/base.py`、`database.py`、`orm.py`
- Alembic: `backend/migrations/versions/`
- すべての `routes/*_router.py` は `app.py` で `/api` を付けてマウントされる。

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
| `/api/prompt-expander` | `routes/prompt_expander_router.py` | Prompt Expander（実験的）: 専用設定、セッション/エントリ、アップロード、LLM 拡張、NovelAI 生成、画像配信、キャラ提案 |

### `game_router.py` の主要操作

| 操作                                            | パス                                                                                                                  |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| キャラクター一覧、セッション取得/開始/復元/削除 | `/characters`、`/session/{id}`、`/start`、`/start-custom`、`/sessions/{id}/restore`、`DELETE /session`                |
| 通常プレイ                                      | `POST /play`、`POST /play/stream`                                                                                     |
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
- `POST /runs/{run_id}/image/stream` の `target` は `scene` / `portrait` / `partner`（攻略対象の立ち絵のみ。1on1 立ち絵モードの↻）
- `GET /images/{run_id}/{filename}`

### FastAPI アプリ直下の互換/補助API

| パス                                             | 目的                         |
| ------------------------------------------------ | ---------------------------- |
| `/health`                                        | プロバイダーを含むヘルス情報 |
| `/api/history/images/{history_id}`               | 履歴画像取得                 |
| `/api/history/surroundings/{history_id}`         | 情景画像取得                 |
| `/novelai/subscription`、`/novelai/suggest-tags` | NovelAI補助                  |
| `/v1/images/edits`、`/v1/images/variations`      | OpenAI互換画像API            |

## サービス

### ゲームと生成

| ファイル                  | 主な責務                                                                                                                                                                                                                                                                                                                         |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `game_service.py`         | 指示タイプ分岐、心境/画像生成、永続化、パラメータ、SSE                                                                                                                                                                                                                                                                           |
| `llm_service.py`          | OpenRouter/NovelAI/互換LLM呼び出し                                                                                                                                                                                                                                                                                               |
| `image_generation.py`     | OpenRouter/NovelAI画像生成とプロバイダー共通化。NovelAIモデル定義（V5/インペイント対応、SDK Literal用ベースモデル）は `consts/novelai_models.py` が唯一の情報源で、ユーザー選択は User の `novelai_image_model` / `novelai_curated_image_model` から `resolve_user_image_model` で解決し `novelai_model_override` として配管する |
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
| `prompts.py`                        | 着せ替え、心境、NovelAI、共通画像プロンプト |
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
| `adventure_service.py`                                | Run作成、ディレクター/解決、ターン、画像、実効画像の直列化。BGMキーは `gateway/data/bgm/catalog.json`（ローダは `consts/adventure_bgm.py`、mtimeホットリロード）が唯一の情報源 |
| `adventure_romance.py`                                | romance プリセットの決定論ロジック（日数/好感度/金銭/ギフト採点/告白）。境界値は `consts/adventure_romance.py`。1on1 立ち絵モードの台本ルール `romance_script_format_guidance`・現在地キー `romance_location_key`・昼夜タグ除去 `strip_romance_time_of_day`、トークモードの `romance_talk_system_prompt` と `talk_log` 操作（`append_talk_entry` / `recent_talk_entries` / `public_talk_log` / `normalize_talk_reply`）もここ |
| `adventure_template_loader.py`                        | `scenarios/*.json` の検証とローカライズ                                                                                                                                        |
| `favorite_service.py`                                 | FavoriteOutfit CRUD                                                                                                                                                            |
| `export_service.py`                                   | MarkdownとNovel HTML ZIP生成                                                                                                                                                   |
| `summary_service.py`                                  | プレイ要約                                                                                                                                                                     |
| `aivisspeech_service.py`                              | AivisSpeechの導入、起動、合成、WAV結合                                                                                                                                         |
| `achievement_service.py`、`achievement_classifier.py` | 実績判定と分類                                                                                                                                                                 |
| `tag_classifier.py`                                   | 変身タグ分類                                                                                                                                                                   |
| `prompt_expander_service.py`、`prompt_expander_prompts.py` | Prompt Expander。`PromptExpanderSettings`（`users.prompt_expander_settings_json`）、セッション/エントリ CRUD、画像ファイル（`data/prompt_expander_images/{session}/{entry}.png`）、`expand_prompts`（NovelAI テキストモデル固定）、`generate_entry`（`image_service.generate_image(provider_override="novelai", raw_prompt=True)`）、キャラ提案（メモリに加え `input_text`=欄の下書きを受け、両方空のときだけ `memory_empty`）。プロンプト原文・サニタイズは `prompt_expander_prompts.py`（タグ/漫画モードには日本語の空似言葉ルール `JAPANESE_TAG_GLOSSARY_RULE`（ショーツ→panties）を付け、指示に「ショーツ」がある場合は `replace_false_friend_tokens` で単独タグ shorts を panties に置換）。画像配信は `FileResponse(filename="{entry_id}.png", content_disposition_type="inline")`。漫画モードの記法（「」『』【】《》・コマ番号）は `extract_manga_notation` / `build_manga_notation_block` / `ensure_manga_notation_texts`、自動ナレーションは `MangaOptions.narration`（設定 `manga_narration`）。ネーム下書きは `draft_manga_script`（`build_manga_script_prompts` / `sanitize_manga_script`、`POST /manga-script`）。境界値は `consts/prompt_expander.py`（V5=22 人 / V4.5=6 人、画像モデル 4 種、サイズ 3 種、漫画モードのコマ数 0〜6 / レイアウト / セリフ言語）、テキストモデルは `consts/novelai_text_models.py` が唯一の情報源。精密参照は `generate_entry` が `reference_kind`（none/history/entry/upload。`resolve_source` を i2i 元と同じ経路で再利用）から bytes を解決し `character_references=[{image, type, strength, fidelity}]` を渡す（V4.5 系のみ。V5 で `reference_kind != none` は `precise_reference_requires_v45`(422)）。背景透過は `transparent_background`（漫画モード時は無効）で送信用プロンプトにだけ `apply_transparent_background`（V5 `transparent background, no shadow` / V4.5 `simple background, white background, no shadow`、negative に `multiple views, reference sheet, character sheet, turnaround` を `merge_tags` で冪等併合）を掛け、エントリの `final_prompt` は接尾辞なしで保存する。`expand_prompts` は `transparent_background` で `build_positive_system_prompt` に背景を書かせない規則（`TRANSPARENT_BACKGROUND_RULE_TAGS` / `_JA`、漫画モードでは無視）を足す。参照種別 3 種・既定 character/0.85/1.0・Anlas 5/枚・透過タグは `consts/prompt_expander.py` |

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
| `PromptExpanderSession`、`PromptExpanderEntry`          | Prompt Expander の履歴（1セッション複数エントリ）。エントリは指示・拡張モード・最終プロンプト/ネガ/キャラプロンプト・モデル・seed・i2i 強度/ノイズ・サイズ・漫画モード（`manga_mode` / `manga_panel_count`）・参照元（history/entry/upload）・背景透過の印（`transparent_background`）・精密参照（`reference_kind` / `reference_history_id` / `reference_entry_id`（FK SET NULL） / `reference_type` / `reference_strength` / `reference_fidelity`。migration `015_add_prompt_expander_reference`）・画像パス |
| `PlaySummary`                                           | セッション要約とタイムライン                                           |
| `UserAchievement`、`AchievementCount`、`AchievedEnding` | 実績/エンディング進捗                                                  |
| `ParameterChangeLog`                                    | パラメータ変更監査                                                     |

DB変更では `backend` で Alembic を実行する。既存SQLiteを使うテストでは外部キー設定を確認し、永続化の真偽はレスポンスだけでなくDB行でも検証する。
