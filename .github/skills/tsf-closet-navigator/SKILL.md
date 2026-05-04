---
name: tsf-closet-navigator
description: "tsf_closet_base project navigator for context-efficient investigation and modification. Use when: exploring project architecture, locating files for a feature change, tracing data flow between frontend and backend, understanding API contracts, modifying game logic, adding new routes/contexts/components, debugging session or image generation issues. Reduces context window usage by providing pre-mapped architecture references instead of broad file exploration."
argument-hint: "Describe what you want to investigate or modify (e.g., 'add a new API endpoint', 'fix stats calculation', 'trace image generation flow')"
---

# TSF Closet ナビゲーター

tsf_closet_base のコンテキスト効率的なプロジェクト調査・変更スキル。

## 使用する場面

- 大量のファイルを読まずに機能の仕組みを調査したい場合
- 新機能やバグ修正でどこを変更すべきか計画する場合
- フロントエンド ↔ バックエンド間のデータフローをトレースする場合
- 特定の変更に必要なファイルを特定する場合
- コードベースの不慣れな部分にオンボーディングする場合

## 手順

### ステップ 1: タスクの分類

変更カテゴリを判定する:

| カテゴリ              | 説明                                                     | 読み込むリファレンス                            |
| --------------------- | -------------------------------------------------------- | ----------------------------------------------- |
| **バックエンド API**  | エンドポイントの新規/変更、リクエスト/レスポンスモデル   | [backend-map.md](./references/backend-map.md)   |
| **フロントエンド UI** | コンポーネント、Context、Hook、ページ                    | [frontend-map.md](./references/frontend-map.md) |
| **データフロー**      | エンドツーエンドの機能トレース (FE → API → Service → DB) | [data-flow.md](./references/data-flow.md)       |
| **フルスタック**      | フロントエンドとバックエンド両方にまたがる変更           | backend-map + frontend-map の両方を読み込み     |

### ステップ 2: 変更レシピの参照

タスクに基づいて、[変更レシピ集](./references/modification-recipes.md)を使用し、読むべき/変更すべき**最小限のファイルセット**を特定する。ファイルツリーを広範に探索するのではなく、レシピのテーブルを使うこと。

### ステップ 3: 必要なものだけ読む

レシピに従い、記載されたファイル**のみ**を読む。各ファイルについて関連箇所のみ読むこと（grep_search やターゲットを絞った行範囲を使用）。

### ステップ 4: 変更の実装

AGENTS.md の規約に従って変更を実装する（Context 優先の状態管理、Python は uv、ESLint/Prettier/Ruff 等）。

### ステップ 5: セルフメンテナンスチェック

構造的な変更（新規ファイル、リネーム、新規ルート/Context/Hook）を完了した後、影響を受けるリファレンスファイルを更新する:

**更新のトリガー条件:**

- 新しいルート/エンドポイントを追加した → [backend-map.md](./references/backend-map.md) を更新
- 新しいコンポーネント/Context/Hook を追加した → [frontend-map.md](./references/frontend-map.md) を更新
- 新しいデータフローパターンを導入した → [data-flow.md](./references/data-flow.md) を更新
- 新しい変更パターンを発見した → [modification-recipes.md](./references/modification-recipes.md) を更新

リファレンスが全体的に古くなった場合は[更新ガイド](./references/refresh-guide.md)を使用してフル再生成する。

## アーキテクチャ クイックリファレンス（常時読み込み）

### 技術スタック

- **フロントエンド**: React 19 + TypeScript 5.9 + Vite 7 + React Router 7 (ポート 3000)
- **バックエンド**: FastAPI 0.115 + SQLAlchemy 2.0 (async) + aiosqlite (ポート 8000)
- **画像生成**: ComfyUI (inpaint/variation ワークフロー) / OpenRouter マルチモーダル / NovelAI
- **LLM**: OpenAI 互換 API (LiteLLM/OpenRouter/ローカル経由)
- **ストリーミング**: Server-Sent Events (SSE) によるリアルタイムゲーム応答
- **マイグレーション**: Alembic
- **パッケージ管理**: uv (Python), npm (Node.js)

### コアディレクトリ

```
backend/gateway/
  routes/          ← FastAPI ルーター（game, settings, achievements, gallery）
  services/        ← ビジネスロジック（game_service, llm_service, image_generation, summary_service 等）
  databases/       ← SQLAlchemy モデル + ORM クエリ
  models.py        ← Pydantic リクエスト/レスポンススキーマ
  consts/          ← 定数（言語コード等）
backend/migrations/
  versions/        ← Alembic マイグレーション履歴

frontend/src/
  apis/            ← API クライアントモジュール（game, settings, achievements, gallery, anlas）
  components/      ← React コンポーネント（chat/, settings/, gallery/, achievements/, endings/, layout/, panel/, notifications/, ui/）
  contexts/        ← 4つの Context: Game, Chat, Settings, Notification
  hooks/           ← カスタム Hook（useSession, useSSE, useGameSSE, useAchievements, useGallery, useTagSuggest）
  routes/          ← ルート定数 / ヘルパー (`getGameSessionPath`)
  types/           ← TypeScript 型定義（types/index.ts）
  utils/           ← 汎用ユーティリティ（API_BASE 等）
```

### Context プロバイダ（フロントエンド状態管理）

| Context             | Hook                | 主な状態                                                                                                                        |
| ------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| GameContext         | `useGame()`         | sessionId, character(s), currentImage, stats, history, attributes, ending, selfMode, transformationCount, lastSurroundingsImage |
| ChatContext         | `useChat()`         | messages, inputText, instructionType, attachedImage, isStreaming, pendingIdentities                                             |
| SettingsContext     | `useSettings()`     | difficulty, language, nsfwMode, imageProvider, inpaintSettings, changeSettings, anlasBalance, totalCost, novelaiTier 他多数     |
| NotificationContext | `useNotification()` | notifications[]、`showNotification` / `showAchievementNotification` ヘルパー                                                    |

### API エンドポイント概要

| プレフィックス  | ルーター               | 主な操作                                                             |
| --------------- | ---------------------- | -------------------------------------------------------------------- |
| `/game`         | game_router.py         | play (SSE), start, session/:id, masks, attributes, history削除 他    |
| `/settings`     | settings_router.py     | settings GET/PUT/DELETE, user GET/PUT (互換), self-profile           |
| `/achievements` | achievements_router.py | list (進捗含む), detail                                              |
| `/gallery`      | gallery_router.py      | sessions list, items list (ページ), detail, delete, summary GET/POST |
