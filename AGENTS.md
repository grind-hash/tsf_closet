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

- フロントエンド(React)の Linterは **ESLint** Formatter は**Prettier を利用し、warn や error とならないよう適切に対応してください**
- バックエンド(Python)の Formatter は**Ruff を利用してください**

## 命名規則

- フロントエンドの型定義や変数定義は、基本的には**キャメルケース**の利用を想定しています
- ただし、バックエンドや外部 API から受け取る値がスネークケースを前提としている場合、フロントエンド側の項目名はバックエンド側に準じることとし、**スネークケースで書くことを許容します**

## UI/UX テスト (Constitution Principle II 準拠)

> **📋 Constitution Principle II**: UI/UX の変更は自動 E2E テストで検証してください (NON-NEGOTIABLE)

- フロントエンド(React)の画面を修正した場合、playwright(MCP)で UI が適切に実装されているかどうかを確認すること
- playwright の MCP を利用したタスクの後、ブラウザを閉じる必要はない
- playwright の MCP を利用する場合、ウェイトなども playwright の MCP を利用すること

## MCP 利用ガイドライン

- MCP が接続されている場合はその恩恵を最大限享受するように振る舞ってください

### ライブラリ・設定変更時の裏取り義務 (NON-NEGOTIABLE)

> **⚠️ 重要**: 設定ファイルの構文変更やライブラリの API 変更を行う前に、**必ず公式ドキュメントで裏取りしてください**

以下のケースでは、**変更を実施する前**に `tavily-remote` または `deepwiki` MCP で公式情報を確認してください：

1. **設定ファイルの構文・プロパティ変更**
   - 例: Biome, ESLint, Prettier, tsconfig 等の設定変更
   - 「このプロパティは非推奨」「この書き方が新しい形式」等の判断は、公式ドキュメントで確認してから行う

2. **ライブラリのバージョンアップに伴う API 変更**
   - Breaking Changes の有無を公式 Changelog/Migration Guide で確認

3. **「ベストプラクティス」として提案する場合**
   - 公式ドキュメントまたは公式 GitHub の一次情報を根拠とすること

#### 確認手順

```
1. tavily-remote: 公式ドキュメントサイトを include_domains で指定して検索
   例: include_domains: ["biomejs.dev"], query: "Biome files configuration includes ignore"

2. deepwiki: GitHub リポジトリのドキュメント構造を確認
   例: repoName: "biomejs/biome", question: "How to configure file exclusion patterns?"
```

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
- ❌ **useSession の値を props で中継**: `useSession` hook の返却値を `App.tsx` で受け取り、子コンポーネントの props として丸ごと渡すパターン。セッション状態は `GameContext` 経由で取得させること
- ❌ **未使用 props の放置**: コンポーネントの props インターフェースに定義されているが `_` プレフィックスで受け取って使用していない props は、速やかに削除すること

#### 推奨パターン

- ✅ `useGame()` で sessionId, currentImage, stats, history, attributes 等を取得
- ✅ `useChat()` で messages, inputText, instructionType 等を取得
- ✅ `useSettings()` で imageProvider, changeSettings, nsfw 等を取得
- ✅ API 呼び出しと状態更新は Context 内のアクション関数で完結させる

#### リファクタリング観点

新機能追加やバグ修正の際に、以下に該当する場合は Context への移行を検討すること：

- 同じ状態が **2つ以上の場所で管理**されている
- props が **3階層以上**をバケツリレーで通過している
- コンポーネントの props が **15個を超えている**
- `useEffect` で **props を Context に同期**しているコードがある

## 言語設定

- **コミュニケーション**: 回答は常に日本語で行ってください
