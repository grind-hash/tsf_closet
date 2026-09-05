# プロジェクトガイドライン

> **📋 Constitution**: このプロジェクトの開発原則は `.specify/memory/constitution.md` に定義されています。  
> このファイルは、実装レベルの具体的なガイドラインを補完するものです。

## 開発環境 (Constitution 準拠)

- 開発環境は Windows11 であり、基本的には PowerShell の利用を想定してください。
- Python の実行には、**uv を利用してください** (Constitution: Development Environment)
  - alembic マイグレーション作成時: `uv run alembic revision --autogenerate -m migration_comment`
  - Python スクリプト実行時: `uv run python script.py`
- フロントエンド(React)はポート 3000 で起動されます (Constitution 規定)
  - 起動コマンド: `npm run dev` または `npm start`
- バックエンド(FastAPI)はポート 8000 で起動されます (Constitution 規定)
  - 起動コマンド: `uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

## 情報源の優先順位 (Constitution Principle I 準拠)

tavily-remote MCP を利用してライブラリ選定を行う際は、以下を優先順としてください：

1. **公式ドキュメント・公式リリースノート** (最優先)
2. **GitHub Issues / Discussions / RFC など一次情報**
3. **ブログや Qiita 記事は補助とし、投稿日・更新日が古い場合はその旨を明示すること**
4. **非公式ソースのみを根拠に「ベストプラクティス」と断定しないこと**

## コード品質 (Constitution Principle III 準拠)

- フロントエンド(React)の Linter/Formatter は **Biome** を利用し、warn や error とならないよう適切に対応してください
- Markdown の Formatter のみ **Prettier** を利用してください（Biome は Markdown 非対応）
- バックエンド(Python)の Formatter は**Ruff を利用してください**

## 命名規則

- フロントエンドの型定義や変数定義は、基本的には**キャメルケース**の利用を想定しています
- ただし、バックエンドや外部 API から受け取る値がスネークケースを前提としている場合、フロントエンド側の項目名はバックエンド側に準じることとし、**スネークケースで書くことを許容します**

## Copilot / Agent 作業効率化ガイドライン

### 基本方針

* まず最小限の探索で、変更対象レイヤーと触る予定のファイルを特定してください。
* リポジトリ全体を広く探索する前に、既存の実装パターンを1〜2箇所だけ確認してください。
* 同じファイルを何度も全文読みしないでください。必要な関数・コンポーネント・型定義の周辺だけを確認してください。
* 実装前に「触る予定のファイル一覧」と「想定する変更内容」を短く提示してください。
* 実装は差分中心で行い、ユーザーが依頼していない大規模リファクタリングは避けてください。

### 探索範囲の制限

* `.github/skills/tsf-closet-navigator/SKILL.md` は、対象領域が不明な場合のみ確認してください。
* `backend-map.md` / `frontend-map.md` などの詳細資料は、対象ファイルが特定できない場合のみ参照してください。
* 既存実装の確認は、同種パターンを最大2例までにしてください。
* 3例以上を確認したくなった場合は、先に「なぜ追加調査が必要か」を短く説明してください。
* grep/search は目的を明確にして実行し、曖昧な広域検索を繰り返さないでください。

### 実装計画の粒度

* 大きな機能は、以下の単位に分割してください。

  1. Backend model / service / router
  2. Frontend API / Context
  3. UI component / i18n / CSS
  4. Prompt injection / LLM integration
  5. Validation
* いきなり全体実装せず、まずMVPの差分を優先してください。
* 「後で拡張できるが、今は不要」な要素はスコープ外として明記してください。

### 検証範囲の制限

* lint / format / test は、原則として変更ファイルに絞って実行してください。
* 全体lint、全体test、広範囲E2Eは、以下の場合のみ実行してください。

  * 共有基盤を変更した場合
  * Context / Router / DB migration など影響範囲が広い場合
  * ユーザーが明示的に要求した場合
* UI変更時のPlaywright確認は必要ですが、対象画面・対象操作・期待結果を絞って実行してください。
* Playwrightで無関係な画面探索をしないでください。

### よく使う検証コマンド

* Frontend lint / format check:
  `cd frontend; npx @biomejs/biome check <changed-files>`

* Frontend lint / format fix:
  `cd frontend; npx @biomejs/biome check --write <changed-files>`

* Frontend Markdown format check:
  `cd frontend; npx prettier --check <changed-md-files>`

* Frontend unit test (vitest, jsdom):
  `cd frontend; npm run test`（単一ファイルは `npx vitest run src/path/File.test.ts`）

* Backend lint:
  `cd backend; uv run ruff check <changed-files>`

* Backend format:
  `cd backend; uv run ruff format <changed-files>`

* Backend import sanity:
  `cd backend; uv run python -c "from gateway.routes import game_router; print('ok')"`

* Backend unit test:
  `cd backend; uv run pytest tests/unit/test_target.py`

* Backend の DB を使うテスト:
  `tests/conftest.py` の `isolated_db` フィクスチャを使う（一時 SQLite・FK 有効。実 DB `backend/data/database.sqlite` には接続しない）

* CI: `.github/workflows/ci.yml` が develop への push / PR で ruff・pytest・Biome・tsc・vitest を実行する（E2E は含まない）

### Alembic 注意

* Alembicは必ず `backend` ディレクトリで実行してください。

  * 正: `cd backend; uv run alembic revision --autogenerate -m migration_comment`
  * 誤: リポジトリルートで `uv run alembic ...`
* autogenerateで無関係な差分が大量に出た場合、目的の変更だけにmigrationを手で整理してください。
* DB migrationを作成した場合は、upgrade / downgrade が目的の差分だけになっているか確認してください。

### MCP利用方針

* MCPは必要な場合に限定して使用してください。
* 「接続されているから最大限使う」のではなく、公式情報確認・UI確認・外部仕様確認など、目的が明確な場合に使ってください。
* ライブラリ・設定ファイル・外部API仕様を変更する場合は、公式情報を確認してください。
* 既存プロジェクト内の実装パターンで判断できる場合、外部検索を優先しないでください。


#### 禁止事項

- ❌ 学習データの知識のみで「この形式は古い/非推奨」と断定して変更する
- ❌ 裏取りなしで設定ファイルの構文を別形式に書き換える
- ❌ ユーザーが意図していない設定変更を「改善」として勝手に行う

## フロントエンドアーキテクチャ: 状態管理方針

### Context 優先原則 (Props Drilling 防止)

> **⚠️ 重要**: 複数コンポーネントで共有される状態は、**props バケツリレーではなく React Context 経由で提供すること**

#### 既存 Context 一覧と責務

| Context                 | 責務                                                                         | ファイル                           |
| ----------------------- | ---------------------------------------------------------------------------- | ---------------------------------- |
| **SettingsContext**     | アプリ設定全般（難易度, 言語, NSFW, 画像プロバイダ, 変更設定, フォント等）   | `contexts/SettingsContext.tsx`     |
| **GameContext**         | ゲームセッション状態（sessionId, 画像, stats, 履歴, 属性, 変身状態等）       | `contexts/GameContext.tsx`         |
| **ChatContext**         | チャットUI状態（メッセージ一覧, 入力テキスト, 指示タイプ, ストリーミング等） | `contexts/ChatContext.tsx`         |
| **NotificationContext** | 通知・実績表示                                                               | `contexts/NotificationContext.tsx` |

#### 必須ルール

1. **新しい共有状態を追加する場合**、まず既存の Context に収まるか検討すること。既存 Context のどれにも属さない場合のみ新規 Context の作成を検討する
2. **子コンポーネントが必要とするデータ**は、親から props で受け渡すのではなく、Context (`useGame()`, `useChat()`, `useSettings()`) 経由で直接取得させること
3. **コールバック props** は、Context のアクション関数として提供できないか検討すること。イベントハンドラの中間転送（A → B → C にコールバックを渡すだけ）は避けること
4. **props は原則として「そのコンポーネント固有の設定」のみ**に使用する（例: `className`, `onClose`, `variant` 等のUI制御用）

#### 禁止パターン

- ❌ **props → useEffect → Context 同期**: 親から props で受け取った値を `useEffect` で Context に書き戻すパターン。状態の二重管理になるため、最初から Context に状態を持たせること
- ❌ **セッション状態を props で中継**: セッション開始/復元の結果を `App.tsx` で受け取り、子コンポーネントの props として丸ごと渡すパターン（旧 `useSession` hook の使い方）。セッション状態は `GameContext` 経由で取得させること
- ❌ **未使用 props の放置**: コンポーネントの props インターフェースに定義されているが `_` プレフィックスで受け取って使用していない props は、速やかに削除すること

#### 推奨パターン

- ✅ `useGame()` で sessionId, currentImage, stats, history, attributes 等を取得
- ✅ `useChat()` で messages, inputText, instructionType 等を取得
- ✅ `useSettings()` で imageProvider, inpaintSettings, nsfw 等を取得
- ✅ API 呼び出しと状態更新は Context 内のアクション関数で完結させる

#### リファクタリング観点

新機能追加やバグ修正の際に、以下に該当する場合は Context への移行を検討すること：

- 同じ状態が **2つ以上の場所で管理**されている
- props が **3階層以上**をバケツリレーで通過している
- コンポーネントの props が **15個を超えている**
- `useEffect` で **props を Context に同期**しているコードがある

## 言語設定

- **コミュニケーション**: 回答は常に日本語で行ってください
