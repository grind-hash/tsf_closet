# リファレンス更新ガイド

このスキルをソースコードの現状へ追従させる。最終検証日は 2026-08-10。

## 更新条件

- ルーター、サービス、DBモデル、Context、Hook、APIモジュール、画面を追加・削除・改名した。
- REST/SSE、プロンプト、メモリ、永続化の責務境界を変更した。
- 記載パスが存在しない、または最終検証から2週間以上経過した。
- スキルを参照した探索が、マップ不足のため広域検索へ戻った。

## クイック更新

構造変更が限定される場合は、対応する1ファイルだけを更新する。

| 変更 | 更新先 |
| --- | --- |
| Backend router/service/model | `backend-map.md` |
| Frontend route/context/hook/API/component | `frontend-map.md` |
| REST/SSE/DB書込/プロンプト経路 | `data-flow.md` |
| 再利用できる変更・検証手順 | `modification-recipes.md` |

## フル再検証

### 1. 差分境界を決める

```powershell
git status --short
git log -1 --format="%H %cI %s" -- .github/skills/tsf-closet-navigator
git diff --name-status <last-skill-commit>..HEAD -- backend/gateway frontend/src backend/tests frontend/tests
```

既存の未コミット変更を所有者不明のまま編集しない。

### 2. Backendを棚卸しする

```powershell
rg --files backend/gateway/routes backend/gateway/services backend/gateway/databases
rg -n "^router =|^@router\.|^class " backend/gateway/routes backend/gateway/services backend/gateway/databases/models.py
rg -n "include_router|^@app\." backend/gateway/app.py
```

次をソースで確認する。

1. `routes/__init__.py` と `app.py` の全ルーターマウント
2. 各routerのprefixと主要操作
3. 新規/削除サービスの責務
4. SQLAlchemyモデル、repo、migration
5. 通常ゲーム、Adventure、メモリ、人物、エクスポートの境界

### 3. Frontendを棚卸しする

```powershell
rg --files frontend/src/apis frontend/src/contexts frontend/src/hooks frontend/src/components
rg -n "export (async )?(function|const)|export interface|export type" frontend/src/apis frontend/src/hooks
rg -n "interface .*State|interface .*Context|export function use" frontend/src/contexts
rg -n "ROUTES|pathname|Provider" frontend/src/App.tsx frontend/src/main.tsx frontend/src/routes/index.tsx
```

次をソースで確認する。

1. `main.tsx` のProvider順序と `App.tsx` の画面分岐
2. 全Contextの責務と公開アクション
3. API/Hook/主要コンポーネントの追加・削除
4. 指示タイプと設定既定値
5. 対応するunit/E2E

### 4. データフローを照合する

- `ChatInput` → `App.tsx` → `useGameSSE` → `/api/game/play/stream` → `GameService` → Context
- `PlayMemorySettings` → `GameContext` → play-memory endpoint → `Session.play_memory_*`
- `AdventureScreen` → `AdventureContext` → `apis/adventure.ts` → Adventure SSE → `AdventureService`
- `CharacterPanel` → `apis/characters.ts` → `SessionCharacter` → 画像プロンプト
- `GalleryScreen` → gallery/favorites/export endpoint → 永続化モデル

### 5. 日付と互換入口を更新する

- 実際に再確認した参照だけ `最終検証` 日付を更新する。
- `.claude/skills/tsf-closet-navigator/SKILL.md` が `.github/skills/tsf-closet-navigator/SKILL.md` を正規情報源として案内していることを確認する。
- `SKILL.md` のfrontmatterは `name` と `description` を基本とし、両環境で不要な専用フィールドを追加しない。

## 検証

```powershell
# Agent Skills構文
$env:PYTHONUTF8 = "1"
$skillValidator = Join-Path $env:USERPROFILE ".codex/skills/.system/skill-creator/scripts/quick_validate.py"
uv run --project backend python $skillValidator .github/skills/tsf-closet-navigator
uv run --project backend python $skillValidator .claude/skills/tsf-closet-navigator

# Markdownと差分
cd frontend
npx prettier --check ../.github/skills/tsf-closet-navigator/**/*.md ../.claude/skills/tsf-closet-navigator/**/*.md
cd ..
git diff --check
git diff -- .github/skills/tsf-closet-navigator .claude/skills/tsf-closet-navigator
```

`quick_validate.py` の場所が利用環境に存在しない場合は、frontmatter、フォルダ名、相対リンクを手動検証し、その制約を報告する。
