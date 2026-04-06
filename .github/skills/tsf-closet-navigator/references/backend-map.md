# バックエンド アーキテクチャマップ

> 最終検証: 2026-03-22 | 更新条件: ルート、サービス、DBモデルの追加・リネーム・削除時

## FastAPI アプリケーション

- **エントリーポイント**: `backend/gateway/app.py` — CORS ミドルウェア、静的ファイル、DBライフサイクル、ルーターマウント
- **モデル (Pydantic)**: `backend/gateway/models.py` — リクエスト/レスポンススキーマ

## API ルート

### `/game` — [backend/gateway/routes/game_router.py](../../backend/gateway/routes/game_router.py)

| #     | メソッド | パス                                | 目的                                    |
| ----- | -------- | ----------------------------------- | --------------------------------------- |
| 1     | GET      | `/game/characters`                  | キャラクター一覧                         |
| 2     | GET      | `/game/session/{id}`                | セッション状態取得                       |
| 3     | POST     | `/game/play`                        | 変身実行（非ストリーミング）              |
| 4     | POST     | `/game/play/stream`                 | 変身実行（SSE ストリーム）               |
| 5     | GET      | `/game/session`                     | 現在のアクティブセッション取得            |
| 6     | GET      | `/game/session/image/{id}`          | セッション PNG 画像取得                  |
| 7     | GET      | `/game/difficulties`                | 難易度プリセット一覧                     |
| 8     | POST     | `/game/start`                       | 新規セッション開始                       |
| 9     | POST     | `/game/start-custom`                | カスタム画像でセッション開始              |
| 10    | GET      | `/game/custom-characters`           | カスタムキャラクター一覧                  |
| 11    | DELETE   | `/game/session`                     | セッションリセット                       |
| 12    | POST     | `/game/history/{id}/select`         | 履歴項目の選択                           |
| 13    | GET      | `/game/sessions`                    | セッション一覧（ページネーション）        |
| 14    | GET      | `/game/sessions/{id}`               | セッション詳細                           |
| 15    | POST     | `/game/sessions/{id}/restore`       | セッション復元                           |
| 16    | GET      | `/game/gallery`                     | ギャラリー一覧                           |
| 17    | GET      | `/game/endings`                     | エンディング一覧                         |
| 18    | GET      | `/game/ending/{id}`                 | エンディング詳細                         |
| 19    | POST     | `/game/chat`                        | キャラクターチャット                     |
| 20    | GET      | `/game/chat/stream`                 | キャラクターチャット（ストリーミング）    |
| 21    | GET      | `/game/conversation/{id}`           | 会話履歴取得                             |
| 22    | GET      | `/game/improve-quality/stream`      | 画像再生成（SSE）                        |
| 23    | POST     | `/game/attributes`                  | 現実改変属性の追加                       |
| 24    | DELETE   | `/game/attributes/{id}`             | 属性の削除                               |
| 25    | GET      | `/game/attributes/{id}`             | セッション属性の取得                     |
| 26    | POST     | `/game/preview/prompt`              | プロンプトプレビュー                     |
| 27    | GET      | `/game/masks`                       | マスク一覧（システム/履歴/プリセット）   |
| 28    | POST     | `/game/masks`                       | マスク保存                               |
| 29-31 | GET      | `/game/masks/{type}/{id}`           | マスク画像取得                           |
| 32    | DELETE   | `/game/masks/preset/{id}`           | プリセットマスク削除                     |
| 33    | GET      | `/game/anlas`                       | NovelAI Anlas 残高                       |
| 34    | POST     | `/game/generate-base-tags`          | ベースタグ生成                           |
| 35    | DELETE   | `/game/conversation/{history_id}`   | 指定履歴に紐づく会話テキストのみ削除     |
| 36    | DELETE   | `/game/history/{history_id}`        | 履歴エントリを完全削除（画像・会話含む） |
| 37    | DELETE   | `/game/session/{id}/latest-history` | 最新履歴の削除                           |

### `/settings` — [backend/gateway/routes/settings_router.py](../../backend/gateway/routes/settings_router.py)

| メソッド | パス                              | 目的                            |
| -------- | --------------------------------- | ------------------------------- |
| GET      | `/settings/user`                  | ユーザー設定取得                 |
| PUT      | `/settings/user`                  | ユーザー設定更新                 |
| GET      | `/settings/self-profile`          | セルフモードプロファイル取得     |
| POST     | `/settings/self-profile/generate` | LLMによるプロファイル自動生成    |
| PUT      | `/settings/self-profile`          | セルフモードプロファイル更新     |

### `/achievements` — [backend/gateway/routes/achievements_router.py](../../backend/gateway/routes/achievements_router.py)

| メソッド | パス                     | 目的                  |
| -------- | ------------------------ | --------------------- |
| GET      | `/achievements`          | 実績一覧              |
| GET      | `/achievements/{id}`     | 実績詳細              |
| GET      | `/achievements/unlocked` | 解除済み実績一覧      |

### `/gallery` — [backend/gateway/routes/gallery_router.py](../../backend/gateway/routes/gallery_router.py)

| メソッド | パス            | 目的                    |
| -------- | --------------- | ----------------------- |
| GET      | `/gallery`      | ギャラリー（ページ付き） |
| GET      | `/gallery/{id}` | ギャラリー項目詳細       |
| DELETE   | `/gallery/{id}` | ギャラリー項目削除       |

## サービス

| ファイル                    | クラス/モジュール        | 主な責務                                                          |
| --------------------------- | ----------------------- | ----------------------------------------------------------------- |
| `game_service.py`           | `GameService`           | メインプレイループ: 指示 → LLM → 画像生成 → SSE レスポンス        |
| `llm_service.py`            | `LLMService`            | LLM API呼び出し（OpenAI/OpenRouter/LiteLLM）                      |
| `image_generation.py`       | `OpenRouterImageClient` | OpenRouter/Gemini マルチモーダル経由の画像生成                     |
| `conversation_service.py`   |                         | セッション毎のチャット履歴管理                                     |
| `achievement_service.py`    |                         | 実績解除条件の判定                                                 |
| `achievement_classifier.py` |                         | 指示テキスト → 実績カテゴリの分類                                  |
| `settings_service.py`       |                         | ユーザー設定 CRUD                                                  |
| `summary_service.py`        |                         | エンディング条件の評価                                             |
| `session.py`                |                         | インメモリセッション状態ストア                                     |
| `characters.py`             |                         | キャラクターメタデータ（一覧、選択、初期化）                       |
| `comfy.py`                  |                         | ComfyUI APIクライアント（ワークフロー実行）                        |
| `litellm_client.py`         |                         | ローカルLLM用 LiteLLM 統合                                        |
| `anlas_service.py`          |                         | NovelAI Anlas（トークン）残高                                      |
| `tag_classifier.py`         |                         | NLPタグ付け（衣装/露出度/年齢印象）                                |
| `action_prompts.py`         |                         | 着せ替え指示プロンプトテンプレート                                  |
| `reality_prompts.py`        |                         | 現実改変プロンプトテンプレート                                     |
| `self_mode_prompts.py`      |                         | セルフモードプロンプトテンプレート                                  |
| `summary_prompts.py`        |                         | サマリー/エンディングプロンプトテンプレート                        |
| `prompts.py`                |                         | 共通プロンプトユーティリティ                                       |
| `endings.py`                |                         | エンディング定義データ                                             |
| `conversation.py`           |                         | 会話データ構造                                                     |

## データベース (SQLAlchemy)

- **モデル定義**: `backend/gateway/databases/models.py`
- **ORM/エンジン**: `backend/gateway/databases/orm.py` (base.py の再エクスポート)
- **マイグレーション**: `backend/migrations/versions/` (Alembic)

### テーブル

| モデル                           | 主要フィールド                                                                                 |
| -------------------------------- | --------------------------------------------------------------------------------------------- |
| `User`                           | id, nsfw_mode, difficulty, language, self_profile_json                                        |
| `Session`                        | id, user FK, character_id, active, transformation_count                                       |
| `SessionStats`                   | session FK, bloom, shame, adaptation, passed_critical_points (JSON), difficulty, nsfw_mode    |
| `History`                        | session FK, instruction, image_path, feeling_text, before/after descriptions, instruction_type|
| `Conversation`                   | session FK, role, content, timestamp                                                          |
| `Achievement` / `AchievedEnding` | ユーザーの解除済み項目（タイムスタンプ付き）                                                   |
| `SessionAttribute`               | session FK, text（現実改変属性）                                                               |
| `TransformationTag`              | history FK, costume_category, exposure_level, age_impression                                  |

## 定数

- `backend/gateway/consts/language.py`: `LanguageCode` enum (ja/en)、正規化、デフォルト=ja
