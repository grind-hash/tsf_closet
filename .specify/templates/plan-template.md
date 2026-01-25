# 実装計画: [機能名]

**ブランチ**: `[###-feature-name]` | **日付**: [YYYY-MM-DD] | **仕様書**: [リンク]
**入力元**: 機能仕様書 `/specs/[###-feature-name]/spec.md`

**注記**: このテンプレートは `/speckit.plan` コマンドによって入力されます。実行フローについては `.specify/templates/commands/plan.md` を参照してください。

## 概要

[機能仕様書からの抜粋: 主要要件 + 調査に基づく技術的アプローチ]

## 技術的コンテキスト

**言語/バージョン**: [例: Python 3.11, Swift 5.9, Rust 1.75 または 要確認]  
**主要依存関係**: [例: FastAPI, UIKit, LLVM または 要確認]  
**ストレージ**: [該当する場合 例: PostgreSQL, CoreData, files または なし]  
**テスト**: [例: pytest, XCTest, cargo test または 要確認]  
**ターゲットプラットフォーム**: [例: Linux server, iOS 15+, WASM または 要確認]
**プロジェクトタイプ**: [single/web/mobile - ソース構造を決定します]  
**パフォーマンス目標**: [ドメイン固有 例: 1000 req/s, 10k lines/sec, 60 fps または 要確認]  
**制約事項**: [ドメイン固有 例: <200ms p95, <100MB memory, オフライン対応 または 要確認]  
**規模/スコープ**: [ドメイン固有 例: 10k users, 1M LOC, 50 screens または 要確認]

## 憲章チェック（Constitution Check）

_ゲート: フェーズ0（調査）前に合格必須。フェーズ1（設計）後に再チェック。_

参照: `.specify/memory/constitution.md`

**原則 I:情報の検証**

- [ ] すべての依存関係が公式ドキュメントと照合されている
- [ ] 外部ライブラリのバージョン/ソース情報が文書化されている
- [ ] 正当な理由なく非公式/非推奨のAPIを使用していない

**原則 II: UI/UXのためのテスト駆動開発**

- [ ] UI/UX変更に対するE2Eテストが計画されている（該当する場合）
- [ ] テストカバレッジのために重要なユーザージャーニーが特定されている
- [ ] テストフレームワークが設定されている（フロントエンド変更の場合は vitest/playwright）

**原則 III: 型安全性とコード品質**

- [ ] TypeScript strict mode が有効になっている
- [ ] 明示的な正当化なしに `any` 型を使用していない
- [ ] Biome 設定が検証されている（フロントエンド）
- [ ] Ruff 設定が検証されている（バックエンド）

**原則 IV: 集約化されたAPIアーキテクチャ**

- [ ] 新しいエンドポイントが `consts/apiEndpoint.ts` に追加されている（該当する場合）
- [ ] API関数が `src/apis/` ディレクトリに実装されている
- [ ] コンポーネント内で直接 axios/fetch を呼び出していない
- [ ] APIレイヤーの分離が維持されている

## プロジェクト構造

### ドキュメント (本機能)

```text
specs/[###-feature]/
├── plan.md              # このファイル (/speckit.plan コマンド出力)
├── research.md          # フェーズ 0 出力 (/speckit.plan コマンド)
├── data-model.md        # フェーズ 1 出力 (/speckit.plan コマンド)
├── quickstart.md        # フェーズ 1 出力 (/speckit.plan コマンド)
├── contracts/           # フェーズ 1 出力 (/speckit.plan コマンド)
└── tasks.md             # フェーズ 2 出力 (/speckit.tasks コマンド - planでは作成されません)
```

### ソースコード (リポジトリルート)

```text
# [未使用なら削除] オプション 1: 単一プロジェクト (デフォルト)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [未使用なら削除] オプション 2: Webアプリケーション ("frontend" + "backend" 検出時)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [未使用なら削除] オプション 3: モバイル + API ("iOS/Android" 検出時)
api/
└── [上記 backend と同様]

ios/ または android/
└── [プラットフォーム固有の構造: 機能モジュール, UIフロー, プラットフォームテスト]
```

**構造の決定**: [選択した構造を文書化し、上記の実際のディレクトリを参照してください]

## 複雑性の追跡

> **憲章チェック（Constitution Check）に違反があり、正当化が必要な場合のみ記入してください**

| 違反内容                  | 必要性         | より単純な代替案を却下した理由       |
| ------------------------- | -------------- | ------------------------------------ |
| [例: 4番目のプロジェクト] | [現在の必要性] | [なぜ3プロジェクトでは不十分なのか]  |
| [例: リポジトリパターン]  | [特定の問題]   | [なぜ直接DBアクセスでは不十分なのか] |
