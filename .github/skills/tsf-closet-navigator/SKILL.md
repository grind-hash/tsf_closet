---
name: tsf-closet-navigator
description: Navigate and modify the tsf_closet_base repository with minimal exploration. Use when locating frontend or backend files, tracing REST or SSE data flows, changing gameplay, image generation, play memory, Adventure mode, favorites, multi-character state, settings, exports, or validating a cross-layer change in this repository.
---

# TSF Closet ナビゲーター

リポジトリ全体を広く読む前に、タスクに必要なレイヤーと最小ファイルセットを特定する。

## 開始手順

1. ルートの `AGENTS.md` と、作業ディレクトリにより近い `AGENTS.md` があれば先に読む。
2. `git status --short` で既存変更を確認し、ユーザーの未コミット変更を保護する。
3. タスクを次の表で分類し、必要な参照だけ読む。
4. 同種実装は最大2例まで確認し、変更予定ファイルと変更内容を短く示してから編集する。
5. 変更ファイルに絞って検証し、構造変更があればこのスキルの対応表も更新する。

| タスク | 読む参照 |
| --- | --- |
| FastAPI、サービス、DB、Alembic | [backend-map.md](./references/backend-map.md) |
| React、Context、Hook、API、画面 | [frontend-map.md](./references/frontend-map.md) |
| REST/SSE、画像生成、メモリ、Adventure の経路 | [data-flow.md](./references/data-flow.md) |
| 変更箇所と検証コマンドの特定 | [modification-recipes.md](./references/modification-recipes.md) |
| マップ自体の再検証 | [refresh-guide.md](./references/refresh-guide.md) |

## 現行アーキテクチャ

- フロントエンド: React 19、TypeScript 5.9、Vite 7、React Router 7、Biome、Playwright。開発ポートは 3000。
- バックエンド: FastAPI、SQLAlchemy async、aiosqlite、Alembic、Ruff、pytest。開発ポートは 8000。
- 通信: 通常操作は REST、メインプレイと Adventure の逐次応答は POST + SSE。
- 生成: selfhost/ComfyUI、OpenRouter、NovelAI を設定に応じて切り替える。
- 永続化: ゲームセッション、履歴、会話、プレイメモ、複数人物、Adventure、お気に入りを SQLite に保存する。

## コアディレクトリ

```text
backend/gateway/
  app.py                 FastAPI 構築、ルーターマウント、互換画像API
  models.py              Pydantic APIモデル
  routes/                game、adventure、favorites、memory 等のルーター
  services/              ゲーム、画像、LLM、Adventure、メモリ等のロジック
  databases/             SQLAlchemyモデル、DB初期化、リポジトリ
  scenarios/             Adventureシナリオ定義
backend/migrations/      Alembic

frontend/src/
  apis/                  REST/SSEクライアント
  components/            game、adventure、gallery、settings 等のUI
  contexts/              Game、Chat、Settings、Notification、Adventure
  hooks/                 useSSE、useGameSSE、useSession 等
  routes/                画面パス定数
  types/                 共有TypeScript型
  utils/                 API、履歴遡及、画像アルファ等
frontend/tests/e2e/      Playwright
```

## 重要な境界

- 共有状態は既存 Context に置く。複数階層の props 中継や props から Context への同期を追加しない。
- `AdventureContext` は `/adventure` 配下だけで提供され、他4 Context は `main.tsx` で全体提供される。
- 指示タイプは `dress_up`、`reality_alter`、`conversation`、`action`、`image_only`。追加時は型、送信UI、APIモデル、サービス分岐、履歴、E2Eを同時に確認する。
- `image_only` は画像履歴だけを更新し、心境・パラメータ・実績・人物状態を更新しない。失敗時は履歴を残さない。
- `original_instruction`、心境用の展開済み指示、画像用 `image_instruction` を混同しない。画像メモリは明示的な opt-in 時だけ注入する。
- `prompt_override` を送る経路へ履歴遡及を自動注入しない。
- プレイメモはセッション単位、設定画面のメモリ本文はユーザー単位。用途と保存先を分ける。
- 複数人物の共有状態は `GameContext.sessionCharacters`、APIは `apis/characters.ts`、永続化は `SessionCharacter` を使用する。
- Adventure は通常ゲームと別の Context、API、サービス、DBモデル、SSE契約を持つ。

## 検証原則

- フロントエンド: `frontend` で変更TS/TSXを `npx @biomejs/biome check <files>`、必要に応じて `npm run build` と対象Playwrightを実行する。
- バックエンド: `backend` で変更Pythonを `uv run ruff check <files>` と `uv run ruff format --check <files>`、対象pytestを実行する。
- Markdown: Prettier対象の設定を確認し、少なくとも差分とリンクを確認する。
- DB変更: `backend` で Alembic を実行し、生成差分を目的の変更だけに整理する。
- 環境失敗と実装失敗を分け、未実施の検証を成功扱いしない。

## セルフメンテナンス

- ルーター、サービス、DBモデルを追加・削除・改名したら `backend-map.md` を更新する。
- 画面、Context、Hook、APIモジュールを追加・削除・改名したら `frontend-map.md` を更新する。
- REST/SSEや永続化の経路を変えたら `data-flow.md` を更新する。
- 新しい横断変更パターンや検証手順を確立したら `modification-recipes.md` を更新する。
- 全体が古い場合は `refresh-guide.md` に従い、ソースを根拠に再生成する。
