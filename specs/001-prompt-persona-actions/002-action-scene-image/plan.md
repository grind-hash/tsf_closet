# 実装計画: 行動モード画像生成

**ブランチ**: `001-prompt-persona-actions` | **日付**: 2026-02-21 | **仕様書**: [spec.md](spec.md)
**入力元**: 機能仕様書 `specs/001-prompt-persona-actions/002-action-scene-image/spec.md`

## 概要

行動モード (`instruction_type=action`) で画像を生成する機能を実装する。  
現在は行動モードでテキスト（心境モノローグ）のみ生成し画像は変更しないが、  
本計画により「人物の外見を保持したまま背景・場面のみ変更する画像」を並列で生成する。

**主要なアプローチ:**

- 既存の img2img パイプラインを活用 (新規 API エンドポイント不要)
- 場面変更専用のプロンプトテンプレートを新規追加
- NovelAI (GLM-4.6 タグ生成) / 非 NovelAI (Vision LLM + Qwen Image Edit) 両対応
- 変身回数・心理パラメータ・タグ分類は変更しない
- DB スキーマ変更なし (既存の PersistedHistory で完全に表現可能)

## 技術的コンテキスト

**言語/バージョン**: Python 3.12+, TypeScript 5.9 (strict)  
**主要依存関係**: FastAPI, React 19.2, NovelAI API, LiteLLM/OpenRouter, ComfyUI  
**ストレージ**: SQLite (aiosqlite) + ファイルシステム (画像)  
**テスト**: pytest (backend), Playwright (E2E)  
**ターゲットプラットフォーム**: Windows 11 (開発), Docker (デプロイ)  
**プロジェクトタイプ**: web (frontend + backend)  
**パフォーマンス目標**: 行動画像生成が変身と同等の時間 (概ね 10 秒以内) で完了  
**制約事項**: i2i_strength 0.85 (デフォルト) で背景変更を実現。低値 (0.45以下) では元画像がほぼそのまま再現されるため不可 (R-001 実測済み)  
**規模/スコープ**: バックエンド 3 ファイル変更, フロントエンド変更なし, テスト追加

## 憲章チェック（Constitution Check）

_ゲート: フェーズ0（調査）前に合格。フェーズ1（設計）後に再チェック済み。_

参照: `.specify/memory/constitution.md`

**原則 I:情報の検証**

- [x] すべての依存関係が公式ドキュメントと照合されている
  - NovelAI img2img: [公式ドキュメント](https://docs.novelai.net/en/image/controltools/) で確認
  - Qwen Image Edit: 公式リポジトリで確認
- [x] 外部ライブラリのバージョン/ソース情報が文書化されている
  - 新規ライブラリ追加なし
- [x] 正当な理由なく非公式/非推奨のAPIを使用していない

**原則 II: UI/UXのためのテスト駆動開発**

- [x] UI/UX変更に対するE2Eテストが計画されている
  - Playwright で行動モードの画像表示を確認
- [x] テストカバレッジのために重要なユーザージャーニーが特定されている
  - US1 (変身後行動), US2 (初期状態行動), US3 (NovelAI)
- [x] テストフレームワークが設定されている
  - pytest (backend unit), Playwright (E2E)

**原則 III: 型安全性とコード品質**

- [x] TypeScript strict mode が有効 (フロントエンド変更は最小限)
- [x] 明示的な正当化なしに `any` 型を使用していない
- [x] ESLint/Prettier 設定が検証されている（フロントエンド）
- [x] Ruff 設定が検証されている（バックエンド）

**原則 IV: 集約化されたAPIアーキテクチャ**

- [x] 新しいエンドポイントは追加しない (既存 `/game/play/stream` を使用)
- [x] API関数は既存のまま (フロントエンドから変更不要)
- [x] コンポーネント内で直接 axios/fetch を呼び出していない
- [x] APIレイヤーの分離が維持されている

## プロジェクト構造

### ドキュメント (本機能)

```text
specs/001-prompt-persona-actions/002-action-scene-image/
├── plan.md              # このファイル
├── research.md          # Phase 0 リサーチ結果
├── data-model.md        # Phase 1 データモデル
├── quickstart.md        # Phase 1 クイックスタート
├── contracts/           # Phase 1 API コントラクト
│   └── game-api.md
├── checklists/
│   └── requirements.md
└── spec.md              # 元の仕様書
```

### ソースコード (変更対象)

```text
backend/
├── gateway/
│   └── services/
│       ├── action_prompts.py   # 場面変更用プロンプトテンプレート追加
│       └── game_service.py     # action mode セクション改修
└── tests/
    └── unit/
        └── test_action_prompts.py  # プロンプトテストケース追加
```

**構造の決定**: オプション 2 (Web アプリケーション: frontend + backend)。  
フロントエンドは変更不要 — SSE ハンドリングが既に `image` イベントをサポートしているため。

## 実装フェーズ

### Phase A: プロンプトテンプレート (action_prompts.py)

**変更ファイル**: `backend/gateway/services/action_prompts.py`

1. **場面変更用画像編集システムプロンプト** (4種):
   - `ACTION_IMAGE_EDIT_SYSTEM_PROMPT` — Qwen 用 SFW
   - `ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NSFW` — Qwen 用 NSFW
   - `ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI` — NovelAI タグ形式 SFW
   - `ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI_NSFW` — NovelAI タグ形式 NSFW

2. **NovelAI GLM-4.6 タグ生成用システムプロンプト** (2種):
   - `ACTION_NOVELAI_PROMPT_GENERATION_SYSTEM` — SFW
   - `ACTION_NOVELAI_PROMPT_GENERATION_SYSTEM_NSFW` — NSFW

3. **ヘルパー関数** (3種):
   - `get_action_image_edit_system_prompt(image_provider, nsfw_mode) -> str`
   - `build_action_image_edit_prompt(instruction, current_description) -> str`
   - `get_action_novelai_prompt_generation_system(nsfw_mode, language) -> str`

**テンプレート設計原則:**

- 人物外見保持の制約を明示的に含む
- NovelAI: キャラクタータグを `{}` で強調維持する指示
- Qwen: "Keep the person exactly as they are" を含む
- 背景・環境・照明のみを変更対象とする

### Phase B: game_service.py の改修

**変更ファイル**: `backend/gateway/services/game_service.py`

action mode セクション (L1005–L1098) の改修:

1. **共通処理** (変更なし):
   - `current_desc` の取得
   - `recent_actions` の抽出
   - `build_action_prompt()` によるテキスト用プロンプト生成

2. **画像生成パイプライン追加** (新規):

   ```
   if is_novelai_opus_mode:
       # previous_prompt 取得 (last_history.after_description)
       # action 専用システムプロンプトで GLM-4.6 タグ生成
       # llm_service.generate_novelai_image_prompt() に専用テンプレート使用
   else:
       # Vision LLM で現在画像分析
       # action 専用テンプレートで編集プロンプト生成
   ```

3. **i2i_strength のデフォルト** (新規):
   - action mode のデフォルト: 0.85 (背景変更には高めの値が必要 — R-001 実測に基づく)
   - `inpaint_strength` が明示指定されていない場合のみ適用
   - 人物の細部変化リスクをキャラクタータグ `{}` 強調で緩和

4. **テキスト + 画像の並列生成** (変更):
   - 現在: テキストのみストリーミング → return
   - 変更後: テキスト + 画像を `asyncio.gather()` で並列生成

5. **SSE イベント送信** (拡張):
   - `text` イベント: 変更なし
   - `image` イベント: 新規追加 (生成された場面画像)
   - `cost` イベント: 画像生成コストを含める
   - `complete` イベント: `transformation_count` は変更なし

6. **スキップする処理**:
   - `save_transformation_tag()` — 呼び出さない
   - `update_session_stats()` — 呼び出さない
   - `increment_transformation_count()` — 呼び出さない
   - 臨界点判定 — スキップ
   - エンディング判定 — スキップ
   - 実績判定 — スキップ

7. **履歴保存** (変更):
   - `image_data`: 生成された場面画像 (現在は before_image をそのまま保存)
   - `after_description`: 生成されたプロンプト/タグ (NovelAI Opus) or 編集プロンプト (非NovelAI)

8. **セッション更新** (追加):
   - `current_image_path`: 新しい画像パスに更新
   - 次回の行動/変身のベース画像になる

9. **self_mode 対応** (確認):
   - self_mode 有効時も画像生成ロジックは通常モードと同一
   - テキスト生成のみ self_profile の性格情報を反映（既に action_prompts.py で対応済み）
   - FR-012 準拠

### Phase C: テスト

1. **ユニットテスト** (`test_action_prompts.py`):
   - `get_action_image_edit_system_prompt()` の SFW/NSFW/NovelAI/Qwen テスト
   - `build_action_image_edit_prompt()` の出力検証
   - `get_action_novelai_prompt_generation_system()` のテスト
   - 全テンプレートに「人物保持」の制約文言が含まれることの検証

2. **E2E テスト** (Playwright):
   - 行動モードで画像が生成・表示されることの確認
   - 変身回数が変化しないことの確認

3. **self_mode テスト** (手動/E2E):
   - self_mode 有効時の行動画像生成が正常に動作することの確認 (FR-012)

### Phase D: 品質チェック

1. `uv run ruff check .` — lint エラーゼロ
2. `uv run python -m pytest -v` — 全テストパス
3. `npx eslint .` — フロントエンド lint エラーゼロ
4. Playwright E2E — 行動画像の表示確認

## 複雑性の追跡

| 違反内容 | 必要性 | より単純な代替案を却下した理由                                                           |
| -------- | ------ | ---------------------------------------------------------------------------------------- |
| なし     | —      | 既存パイプラインを最大限活用し、新規エンドポイント・DB変更・フロントエンド変更を全て回避 |

## リスクと軽減策

| リスク                               | 影響度 | 軽減策                                                                                                                                                      |
| ------------------------------------ | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| img2img でのキャラクター外見変化     | 中     | i2i_strength 0.85 + キャラクタータグ `{}` 強調で緩和。高 strength は背景変更に必須だが人物細部への影響あり。将来的に Inpainting (マスク反転) への移行を検討 |
| GLM-4.6 のタグ生成で背景タグが不十分 | 低     | 専用システムプロンプトで具体的な背景描写を要求                                                                                                              |
| 行動で API コスト増加                | 低     | 既存の anlas 確認フローで対応済み。行動も変身と同じコスト確認 UI を通る                                                                                     |

## フェーズ対応表（plan.md ↔ tasks.md）

| plan.md | tasks.md     | 内容                                         |
| ------- | ------------ | -------------------------------------------- |
| Phase A | フェーズ 2   | プロンプトテンプレート (action_prompts.py)   |
| Phase B | フェーズ 3-5 | game_service.py 改修 + フォールバック + 履歴 |
| Phase C | フェーズ 6   | テスト (ユニット + E2E + self_mode)          |
| Phase D | フェーズ 7   | 品質チェック (Lint/Test/検証)                |
