# 実装計画: プロンプトのパーソナリティ対応・行動機能・自分自身モード

**ブランチ**: `001-prompt-persona-actions` | **日付**: 2026-02-21 | **仕様書**: [spec.md](spec.md)
**入力元**: 機能仕様書 `/specs/001-prompt-persona-actions/spec.md`

**注記**: このテンプレートは `/speckit.plan` コマンドによって入力されます。実行フローについては `.specify/templates/commands/plan.md` を参照してください。

## 概要

既存の心境テキスト生成システムに以下の改善・拡張を行う:

1. **P1 バグ修正**: prompts.py 内のハードコード「僕」6箇所をテンプレート化し、キャラクターの pronoun 引数で動的置換
2. **P1 品質向上**: キャラクターの personality/description をシステムプロンプトに注入し、性格に応じた語調・反応パターンを実現
3. **P2 バリエーション**: 各心理段階のオープニングセリフを性格タイプ別辞書構造に拡張（各10個以上）、重複回避メカニズム追加
4. **P2 新機能 - 行動**: `instruction_type: "action"` を追加し、衣装変更なしの場面転換テキスト生成を可能に（画像・パラメータ処理スキップ）
5. **P2 新機能 - 自分自身モード**: Session.self_mode フラグで心理段階・パラメータ計算をバイパスし、性格プロフィールベースの自然な反応を生成
6. **P2 新機能 - 性格自動生成**: LLM で入力テキストから構造化 SelfProfile を生成する API エンドポイント

## 技術的コンテキスト

**言語/バージョン**: Python 3.12+ (バックエンド), TypeScript 5.9 + React 19 (フロントエンド)
**主要依存関係**: FastAPI, SQLAlchemy[asyncio], sse-starlette, openai, Vite, react-router-dom
**ストレージ**: SQLite (aiosqlite) + Alembic マイグレーション
**テスト**: pytest (バックエンド), Vitest (フロント単体), Playwright (E2E)
**ターゲットプラットフォーム**: Windows 11 ローカル + Docker Compose
**プロジェクトタイプ**: web (frontend/ + backend/)
**パフォーマンス目標**: 心境テキスト初回チャンク 3秒以内、性格自動生成 3秒以内
**制約事項**: 既存の SSE ストリーミングパイプラインを再利用、新規外部ライブラリの追加なし
**規模/スコープ**: バックエンド変更ファイル12個、フロントエンド変更ファイル10個、新規ファイル5個

## 憲章チェック（Constitution Check）

_ゲート: フェーズ0（調査）前に合格必須。フェーズ1（設計）後に再チェック。_

参照: `.specify/memory/constitution.md`

**原則 I:情報の検証**

- [x] すべての依存関係が公式ドキュメントと照合されている — 新規外部ライブラリの追加なし。既存の FastAPI, SQLAlchemy, openai パッケージのみ使用
- [x] 外部ライブラリのバージョン/ソース情報が文書化されている — pyproject.toml, package.json で管理済み
- [x] 正当な理由なく非公式/非推奨のAPIを使用していない — 全て既存APIパターンの拡張

**原則 II: UI/UXのためのテスト駆動開発**

- [x] UI/UX変更に対するE2Eテストが計画されている — action-mode.spec.ts, self-mode.spec.ts を新規作成予定
- [x] テストカバレッジのために重要なユーザージャーニーが特定されている — 仕様書の6ストーリーそれぞれに受け入れシナリオ定義済み
- [x] テストフレームワークが設定されている — Playwright (E2E), pytest (バックエンド単体) 設定済み

**原則 III: 型安全性とコード品質**

- [x] TypeScript strict mode が有効になっている — tsconfig.app.json で strict: true 確認済み
- [x] 明示的な正当化なしに `any` 型を使用していない — SelfProfile 型を明示的に定義予定
- [x] ESLint 設定が検証されている — eslint.config.js (flat config v9) 確認済み、Prettier 併用
- [x] Ruff 設定が検証されている — pyproject.toml で Ruff dev dependency 確認済み

**原則 IV: 集約化されたAPIアーキテクチャ**

- [x] 新しいエンドポイントが適切に配置される — settings_router.py に self-profile 系3エンドポイント追加
- [x] API関数が `src/apis/` ディレクトリに実装される — 既存パターンに従い settings.ts に追加予定
- [x] コンポーネント内で直接 axios/fetch を呼び出していない — useSSE フックを経由
- [x] APIレイヤーの分離が維持されている — routes → services → databases の3層を維持

## プロジェクト構造

### ドキュメント (本機能)

```text
specs/001-prompt-persona-actions/
├── spec.md              # 機能仕様書
├── plan.md              # このファイル
├── research.md          # フェーズ 0 出力: 技術調査・設計判断
├── data-model.md        # フェーズ 1 出力: データモデル設計
├── quickstart.md        # フェーズ 1 出力: 実装ガイド
├── contracts/           # フェーズ 1 出力: API契約
│   ├── game-api.md      # HTTP API (変更・追加分)
│   └── prompt-modules.md # 内部モジュールインターフェース
├── checklists/
│   └── requirements.md  # 仕様品質チェックリスト
└── tasks.md             # フェーズ 2 出力 (/speckit.tasks コマンド)
```

### ソースコード (変更対象)

```text
backend/
├── gateway/
│   ├── models.py                            # SelfProfile Pydantic モデル追加
│   ├── databases/
│   │   └── models.py                        # Session.self_mode, User.self_profile_json 追加
│   ├── routes/
│   │   ├── game_router.py                   # GameStartRequest に self_mode 追加
│   │   └── settings_router.py               # self-profile CRUD 3エンドポイント追加
│   └── services/
│       ├── prompts.py                       # pronoun テンプレート化, personality 注入, openings 拡充
│       ├── action_prompts.py                # [新規] 行動機能用プロンプト
│       ├── self_mode_prompts.py             # [新規] 自分自身モード用プロンプト
│       ├── game_service.py                  # action 分岐, self_mode 分岐, personality 伝播
│       ├── session.py                       # create_session に self_mode 引数追加
│       └── settings_service.py              # self_profile 読み書き追加
├── migrations/versions/
│   └── 008_add_self_mode.py                 # [新規] マイグレーション
└── tests/
    └── unit/
        ├── test_prompts.py                  # [新規/変更] pronoun, personality, openings テスト
        ├── test_action_prompts.py           # [新規] 行動プロンプトテスト
        └── test_self_mode_prompts.py        # [新規] 自分自身モードテスト

frontend/
├── src/
│   ├── types/index.ts                       # InstructionType 拡張, SelfProfile 型追加
│   ├── apis/                                # self-profile API 関数追加
│   ├── contexts/
│   │   ├── SettingsContext.tsx               # selfMode, selfProfile 状態管理追加
│   │   └── GameContext.tsx                   # selfMode を session に含める
│   └── components/
│       ├── chat/ChatInput.tsx               # 「行動」タイプ追加
│       ├── chat/WelcomeScreen.tsx           # 自分自身モード選択UI
│       ├── settings/SettingsScreen.tsx       # 性格プロフィール設定UI
│       └── settings/SelfProfileEditor.tsx   # [新規] 性格プロフィール編集
└── tests/e2e/
    ├── action-mode.spec.ts                  # [新規] 行動機能 E2E
    └── self-mode.spec.ts                    # [新規] 自分自身モード E2E
```

**構造の決定**: Webアプリケーション構造 (frontend/ + backend/) を使用。既存の `backend/gateway/services/` にプロンプトモジュールを追加する既存パターンに従う。

## 複雑性の追跡

> 憲章チェックはすべてパスしており、違反事項はありません。

該当なし。
