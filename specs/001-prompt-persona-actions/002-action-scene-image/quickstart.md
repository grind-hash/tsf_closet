# クイックスタート: 行動モード画像生成

**機能**: 002-action-scene-image  
**日付**: 2026-02-21

## 前提条件

- 001-prompt-persona-actions の全コミット済みの変更が適用済み
- Python 3.12+, uv, Node.js 24
- バックエンドの依存関係が `uv sync` 済み
- フロントエンドの依存関係が `npm install` 済み

## 実装ステップ概要

### Step 1: 場面変更用プロンプトテンプレートの作成

**ファイル**: `backend/gateway/services/action_prompts.py`

1. 4つのシステムプロンプトテンプレートを追加:
   - Qwen 用 (SFW / NSFW)
   - NovelAI タグ形式 (SFW / NSFW)
2. NovelAI GLM-4.6 用の場面変更システムプロンプト (SFW / NSFW) を追加
3. ヘルパー関数を追加:
   - `get_action_image_edit_system_prompt()`
   - `build_action_image_edit_prompt()`
   - `get_action_novelai_prompt_generation_system()`

### Step 2: game_service.py の action mode 改修

**ファイル**: `backend/gateway/services/game_service.py`

1. action mode の早期 return を削除
2. NovelAI Opus / 非 NovelAI 分岐を追加
3. 場面変更専用プロンプト生成を呼び出し
4. テキストと画像の並列生成
5. 履歴保存 (画像込み)
6. 変身回数/パラメータ更新をスキップ
7. image + text + complete の SSE イベント送信

### Step 3: i2i_strength デフォルト値の調整

**ファイル**: `backend/gateway/services/game_service.py`

1. 行動モード専用のデフォルト i2i_strength (0.85) を設定 (R-001 実測に基づく)
2. フロントエンドからのオーバーライドは引き続き有効

### Step 4: ユニットテストの追加

**ファイル**: `backend/tests/unit/test_action_prompts.py`

1. 場面変更プロンプト生成関数のテスト
2. NovelAI / Qwen 両モードのテスト
3. SFW / NSFW モードのテスト

### Step 5: E2E テスト (Playwright)

1. 行動モードで画像が生成されることを確認
2. 変身回数が変化しないことを確認

## 変更不要な箇所

- **DB スキーマ**: Alembic マイグレーション不要
- **API エンドポイント**: 新規エンドポイント不要
- **フロントエンド**: SSE ハンドリングは既存のまま動作 (image イベントは既にサポート済み)
- **フロントエンドの送信ロジック**: `instruction_type=action` は既に送信されている (001 で実装済み)

## 検証手順

```powershell
# バックエンドテスト
cd backend
uv run python -m pytest tests/unit/test_action_prompts.py -v

# 全テスト
uv run python -m pytest -v

# Lint
uv run ruff check .

# フロントエンド lint
cd ../frontend
npx eslint .
```

## リスク・注意点

1. **i2i_strength のチューニング**: 0.85 を初期値とする (R-001 実測: 0.45 では背景変化が発生せず、元画像と同一の出力になる)。高 strength による人物細部変化はキャラクタータグ `{}` 強調で緩和
2. **NovelAI の背景変更品質**: img2img 方式ではキャラクターの微細な変化が避けられない (R-001 参照)。将来的に Inpainting (マスク反転) への移行を検討
3. **コスト**: 行動モードで画像生成が追加されるため、API コストが増加する
