# CONSTITUTION（プロジェクト原則）

> **Attention**
> すべての仕様・出力・ドキュメント・生成コンテンツは原則として日本語で記述しなければならない（MUST）。
> ユーザーが明示的に要求した場合のみ、英語出力を許可する。

このドキュメントは、TSF Closet プロジェクトにおける開発の基本原則を定義する。
すべての開発者、AI エージェント、ツールは本憲章に従う必要がある。

## Core Principles

### I. 情報源の信頼性（NON-NEGOTIABLE）

- 技術選定・実装判断は、公式ドキュメント、公式リポジトリ、公式リリースノート等の一次情報を最優先とする（MUST）。
- 非公式ソースは補助情報として扱い、採用前に必ず公式情報または一次情報で cross-check する（MUST）。
- 参照情報の鮮度（確認日・バージョン）を明示する（SHOULD）。

### II. 品質保証（UI/UX テスト必須）

- UI/UX の変更は自動 E2E テストで検証する（MUST）。
- テストなしでのマージは原則として禁止する（MUST）。
- リグレッション防止のため、重要機能には必ず自動テストを追加する（MUST）。

### III. 型安全性とコード品質

- React/TypeScript の型安全性を最優先し、strict モードを維持する（MUST）。
- `any` 型の使用は極力避け、必要時は明確な理由を残す（SHOULD）。
- 型エラー・lint エラーは無視せず、根本原因を解消する（MUST）。
- フロントエンドの Linter/Formatter は Biome、Markdown の整形は Prettier、バックエンドの整形は Ruff を用い、警告/エラーをゼロに保つ（MUST）。

### IV. API 設計とエラーハンドリング

- API 呼び出しエラーは適切にハンドリングし、利用者に理解可能なメッセージを返す（MUST）。
- API 層の責務分離を維持し、UI コンポーネントからの無秩序な直接通信を避ける（SHOULD）。

### V. データ・セキュリティ・運用

- スキーマ変更は Alembic マイグレーション経由で実施し、マイグレーションは必ずバージョン管理する（MUST）。
- 手動 SQL 実行によるスキーマ変更は原則禁止とする（MUST）。
- 機密情報は環境変数で管理し、ソースコードへハードコーディングしない（MUST）。
- `.env` はバージョン管理へ含めず、`.env.example` のみを管理対象とする（MUST）。

## Environment Standards

- OS: Windows 11
- シェル: PowerShell
- Python 実行: `uv` を使用（`pip` を直接使用しない）
- Node.js: Volta で管理（推奨バージョン: 24）
- フロントエンド（React）: port 3000
- バックエンド（FastAPI）: port 8000
- Frontend Linter/Formatter: Biome
- Markdown Formatter: Prettier（Biome 非対応のため）

## Deployment & Dependencies

- デプロイ前に `uv sync` を実行する（MUST）。
- `requirements.txt` の整合を維持する（MUST）。
- 依存関係更新履歴を記録する（SHOULD）。
- Docker Compose を用いた環境構築を基本とし、本番とローカルの差異を最小化する（SHOULD）。

## Documentation & Spec-Driven Development

- README には概要、セットアップ手順、Constitution と AGENTS.md への参照を含める（MUST）。
- 機能追加は仕様作成から開始し、実装前に仕様レビューを行う（MUST）。
- spec-kit を活用し、仕様・計画・タスクのトレーサビリティを維持する（SHOULD）。

## Governance

- 本憲章は、個別の spec、plan、tasks、運用メモより優先される（MUST）。
- すべての PR・レビューで本憲章への準拠を確認する（MUST）。
- 本憲章の改定は、変更理由・影響範囲・移行方針を明記した上で実施する（MUST）。

**Version**: 1.1.0 | **Ratified**: 2026-01-20 | **Last Amended**: 2026-07-26
