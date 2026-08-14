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

| 実パス | ファイル | 主な責務 |
| --- | --- | --- |
| `/api/game` | `routes/game_router.py` | セッション、プレイSSE、会話、履歴、画像、属性、プレイメモ、プロンプト、指示候補 |
| `/api/game` | `routes/character_router.py` | セッション人物、主人公確保、人物プリセット、人物タグ生成 |
| `/api/adventure` | `routes/adventure_router.py` | シナリオテンプレート、Run、ターンSSE、画像再生成 |
| `/api/gallery` | `routes/gallery_router.py` | セッション/履歴一覧、検索、詳細、削除、要約、Markdown/HTMLエクスポート |
| `/api/favorites` | `routes/favorites_router.py` | お気に入り一覧、追加、ラベル変更、削除 |
| `/api/achievements` | `routes/achievements_router.py` | 実績一覧と詳細 |
| `/api/settings` | `routes/settings_router.py` | 設定、互換ユーザー設定、セルフプロフィール |
| `/api/memory` | `routes/memory_router.py` | ユーザーメモ本文、生成ジョブ、状態、取消、分析エクスポート |
| `/api/aivisspeech` | `routes/aivisspeech_router.py` | エンジン/モデル管理、話者一覧、音声合成 |

### `game_router.py` の主要操作

| 操作 | パス |
| --- | --- |
| キャラクター一覧、セッション取得/開始/復元/削除 | `/characters`、`/session/{id}`、`/start`、`/start-custom`、`/sessions/{id}/restore`、`DELETE /session` |
| 通常プレイ | `POST /play`、`POST /play/stream` |
| 履歴選択・分岐・削除 | `/history/{id}/select`、`/history/{id}/branch-session`、`DELETE /history/{id}`、`DELETE /session/{id}/latest-history` |
| 会話 | `/chat`、`/chat/stream`、`/conversation/{id}`、会話単体/履歴単位削除 |
| プレイメモ | `PATCH /sessions/{id}/play-memory`、`POST /sessions/{id}/play-memory/regenerate` |
| 指示支援 | `POST /suggest-instruction`、`POST /preview/prompt`、`POST /generate-base-tags` |
| 画像支援 | `/improve-quality/stream`、`POST /standing-portrait`、`/masks`、`/anlas` |
| 現実改変属性 | `POST /attributes`、`GET/DELETE /attributes/{id}` |

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
- `GET /images/{run_id}/{filename}`

### FastAPI アプリ直下の互換/補助API

| パス | 目的 |
| --- | --- |
| `/health` | プロバイダーを含むヘルス情報 |
| `/api/history/images/{history_id}` | 履歴画像取得 |
| `/api/history/surroundings/{history_id}` | 情景画像取得 |
| `/novelai/subscription`、`/novelai/suggest-tags` | NovelAI補助 |
| `/v1/images/edits`、`/v1/images/variations` | OpenAI互換画像API |

## サービス

### ゲームと生成

| ファイル | 主な責務 |
| --- | --- |
| `game_service.py` | 指示タイプ分岐、心境/画像生成、永続化、パラメータ、SSE |
| `llm_service.py` | OpenRouter/NovelAI/互換LLM呼び出し |
| `image_generation.py` | OpenRouter/NovelAI画像生成とプロバイダー共通化 |
| `comfy.py` | selfhost ComfyUI クライアント |
| `litellm_client.py` | LiteLLM 統合 |
| `model_execution_gate.py` | モデル実行の直列化/排他制御 |
| `history_context.py` | 指示タイプ別の履歴遡及と時系列コンテキスト |
| `clothing_layers.py` | 衣装レイヤー可視性ルール |
| `gender_congruence.py` | 性別適合のルール/LLM判定 |

### プロンプト

| ファイル | 対象 |
| --- | --- |
| `prompts.py` | 着せ替え、心境、NovelAI、共通画像プロンプト |
| `reality_prompts.py` | 現実改変 |
| `self_mode_prompts.py` | セルフモード |
| `image_only_prompts.py` | `image_only` 専用画像指示 |
| `instruction_suggestion_prompts.py` | 指示候補 |
| `memory_prompts.py` | ユーザーメモ生成/統合 |
| `summary_prompts.py` | 要約と分岐状況 |

### セッション、メモリ、人物

| ファイル | 主な責務 |
| --- | --- |
| `session.py` | Session/History/Conversation のストアと復元 |
| `session_branch_service.py` | 履歴地点からのセッション分岐 |
| `play_memory_service.py` | セッション単位の自動/ユーザープレイメモ |
| `memory_job_service.py` | ユーザー単位メモリ生成ジョブと監査スナップショット |
| `character_service.py` | SessionCharacter、CharacterPreset、人物外見同期 |
| `characters.py` | テンプレートキャラクターメタデータ |
| `conversation_service.py` | 会話管理 |
| `settings_service.py` | User設定 |

### 独立機能

| ファイル | 主な責務 |
| --- | --- |
| `adventure_service.py` | Run作成、ディレクター/解決、ターン、画像、実効画像の直列化。BGMキーは `consts/adventure_bgm.py` が唯一の情報源 |
| `adventure_romance.py` | romance プリセットの決定論ロジック（日数/好感度/金銭/ギフト採点/告白）。境界値は `consts/adventure_romance.py` |
| `adventure_template_loader.py` | `scenarios/*.json` の検証とローカライズ |
| `favorite_service.py` | FavoriteOutfit CRUD |
| `export_service.py` | MarkdownとNovel HTML ZIP生成 |
| `summary_service.py` | プレイ要約 |
| `aivisspeech_service.py` | AivisSpeechの導入、起動、合成、WAV結合 |
| `achievement_service.py`、`achievement_classifier.py` | 実績判定と分類 |
| `tag_classifier.py` | 変身タグ分類 |

## 永続化モデル

| モデル | 主なデータ |
| --- | --- |
| `User` | UI/生成/TTS/メモリ設定 |
| `Session` | 現在画像、active、変身回数、セッションプレイメモ |
| `History` | 指示、指示タイプ、画像、情景画像、心境、前後記述、seed |
| `SessionStats` | bloom、shame、adaptation、臨界点、難易度 |
| `Conversation` | セッション会話 |
| `TransformationTag` | 衣装、露出、年齢印象 |
| `SessionAttribute` | 現実改変属性 |
| `AdventureRun` | シナリオ状態、現在/初期/背景/立ち絵画像、設定 |
| `AdventureTurn` | 入力、語り、状態差分、画像、立ち絵、画像状態 |
| `SessionCharacter` | セッション人物の外見、位置、ロック、主人公フラグ |
| `CharacterPreset` | 再利用可能な人物定義 |
| `FavoriteOutfit` | UserとHistoryを結ぶお気に入り |
| `PlaySummary` | セッション要約とタイムライン |
| `UserAchievement`、`AchievementCount`、`AchievedEnding` | 実績/エンディング進捗 |
| `ParameterChangeLog` | パラメータ変更監査 |

DB変更では `backend` で Alembic を実行する。既存SQLiteを使うテストでは外部キー設定を確認し、永続化の真偽はレスポンスだけでなくDB行でも検証する。
