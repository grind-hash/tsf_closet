# Quickstart: 001-prompt-persona-actions

**日付**: 2026-02-21

## 概要

この機能は6つの要素で構成される:

1. **pronoun 動的反映** — ハードコード「僕」の排除
2. **personality プロンプト注入** — キャラクター性格の心境テキスト反映
3. **オープニングセリフ拡充** — バリエーション10個以上 + 性格別 + 重複回避
4. **行動機能** — 衣装を変えない場面転換テキスト生成
5. **自分自身モード** — パラメータなしの性格ベース反応
6. **性格自動生成** — 入力テキストからLLMでプロフィール生成

## ファイル変更マップ

### バックエンド

| ファイル                                   | 種別     | 変更内容                                                                               |
| ------------------------------------------ | -------- | -------------------------------------------------------------------------------------- |
| `gateway/services/prompts.py`              | **変更** | pronoun テンプレート化, personality 注入, openings 拡充・辞書化, select_opening() 追加 |
| `gateway/services/action_prompts.py`       | **新規** | 行動機能用プロンプト定義                                                               |
| `gateway/services/self_mode_prompts.py`    | **新規** | 自分自身モード用プロンプト定義                                                         |
| `gateway/services/game_service.py`         | **変更** | action 分岐追加, self_mode 分岐追加, personality パラメータ伝播                        |
| `gateway/models.py`                        | **変更** | SelfProfile Pydantic モデル追加                                                        |
| `gateway/databases/models.py`              | **変更** | Session.self_mode, User.self_profile_json カラム追加                                   |
| `gateway/databases/orm.py` (該当する場合)   | **変更** | 新カラムの ORM マッピング（既存 ORM で自動対応済みの場合は変更不要）                   |
| `gateway/routes/game_router.py`            | **変更** | GameStartRequest に self_mode 追加, session レスポンスに self_mode 追加                |
| `gateway/routes/settings_router.py`        | **変更** | self-profile CRUD エンドポイント3個追加                                                |
| `gateway/services/settings_service.py`     | **変更** | self_profile の読み書きロジック追加                                                    |
| `gateway/services/session.py`              | **変更** | create_session に self_mode 引数追加                                                   |
| `migrations/versions/008_add_self_mode.py` | **新規** | self_mode + self_profile_json マイグレーション                                         |

### フロントエンド

| ファイル                                        | 種別     | 変更内容                                                                           |
| ----------------------------------------------- | -------- | ---------------------------------------------------------------------------------- |
| `src/types/index.ts`                            | **変更** | InstructionType に "action" 追加, SelfProfile 型追加, INSTRUCTION_TYPE_LABELS 更新 |
| `src/apis/settings.ts` (or equivalent)          | **変更** | self-profile API 関数追加                                                          |
| `src/contexts/SettingsContext.tsx`              | **変更** | selfMode 状態管理, selfProfile 状態管理追加                                        |
| `src/contexts/GameContext.tsx`                  | **変更** | selfMode を session 状態に含める, GameStartRequest に self_mode 追加               |
| `src/components/chat/ChatInput.tsx`             | **変更** | instruction_type 選択肢に「行動」追加                                              |
| `src/components/chat/WelcomeScreen.tsx`         | **変更** | 自分自身モード選択UI追加                                                           |
| `src/components/settings/SettingsScreen.tsx`    | **変更** | 性格プロフィール設定UI追加（テキスト入力 + 生成ボタン + 編集フォーム）             |
| `src/components/settings/SelfProfileEditor.tsx` | **新規** | 性格プロフィール編集コンポーネント                                                 |

### テスト

| ファイル                                       | 種別          | テスト内容                                              |
| ---------------------------------------------- | ------------- | ------------------------------------------------------- |
| `backend/tests/unit/test_prompts.py`           | **新規/変更** | pronoun 置換, personality 注入, openings 選択, 重複回避 |
| `backend/tests/unit/test_action_prompts.py`    | **新規**      | 行動プロンプト生成                                      |
| `backend/tests/unit/test_self_mode_prompts.py` | **新規**      | 自分自身モードプロンプト生成                            |
| `frontend/tests/e2e/action-mode.spec.ts`       | **新規**      | 行動機能 E2E                                            |
| `frontend/tests/e2e/self-mode.spec.ts`         | **新規**      | 自分自身モード E2E                                      |

## 実装順序（推奨）

```
Phase 1: P1 既存バグ修正・即効改善
  ├── Task 1: pronoun テンプレート化 (prompts.py)
  ├── Task 2: personality プロンプト注入 (prompts.py + game_service.py)
  └── Task 3: オープニングセリフ拡充 (prompts.py)

Phase 2: P2 行動機能
  ├── Task 4: action_prompts.py 新規作成
  ├── Task 5: game_service.py に action 分岐追加
  ├── Task 6: フロントエンド instruction_type 追加
  └── Task 7: E2E テスト

Phase 3: P2 自分自身モード
  ├── Task 8: DB マイグレーション (008)
  ├── Task 9: self_mode_prompts.py 新規作成
  ├── Task 10: game_service.py に self_mode 分岐追加
  ├── Task 11: settings API + フロントエンド UI
  ├── Task 12: 性格自動生成 API
  └── Task 13: E2E テスト
```

## 起動・テスト手順

```powershell
# マイグレーション適用
cd backend
uv run alembic upgrade head

# バックエンド起動
uv run uvicorn gateway.app:app --host 0.0.0.0 --port 8000 --reload

# フロントエンド起動
cd ../frontend
npm run dev

# バックエンド単体テスト
cd ../backend
uv run pytest tests/unit/test_prompts.py -v
uv run pytest tests/unit/test_action_prompts.py -v
uv run pytest tests/unit/test_self_mode_prompts.py -v

# フロントエンド E2E テスト
cd ../frontend
npx playwright test tests/e2e/action-mode.spec.ts
npx playwright test tests/e2e/self-mode.spec.ts
```
