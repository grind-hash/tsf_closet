# 変更レシピ集

> 最終検証: 2026-08-10 | 最初に必要なファイルだけを開くための対応表

## 共通手順

1. `git status --short` で既存変更を確認する。
2. 対象レイヤーを決め、下表のコアファイルと同種実装を1〜2例だけ読む。
3. 変更予定ファイルと変更内容を提示する。
4. 小さい差分で実装する。
5. 変更ファイルのlint/format、対象unit/E2E、必要時buildを順に実行する。

## バックエンド

### APIを追加する

| 順序 | ファイル |
| --- | --- |
| 1. Pydanticモデル | `backend/gateway/models.py` または対象router内の局所モデル |
| 2. サービス | `backend/gateway/services/{feature}_service.py` |
| 3. ルート | `backend/gateway/routes/{feature}_router.py` |
| 4. 新規router公開 | `backend/gateway/routes/__init__.py`、`backend/gateway/app.py` |
| 5. DBが必要 | `backend/gateway/databases/models.py`、必要なrepo、Alembic |
| 6. テスト | `backend/tests/unit/` または `backend/tests/integration/`（DB を使う場合は `tests/conftest.py` の `isolated_db` フィクスチャ） |

プロバイダー（selfhost / openrouter / novelai）の判定は `services/providers.py` の `resolve_*_provider` を通し、`settings.*_provider` を直接比較しない。

ルーターは原則 `/api` 配下にマウントする。`app.py` にはエンドポイントを書かない（互換 API も `routes/system_router.py` / `novelai_router.py` / `openai_images_router.py` にある）。

### 通常ゲームの指示タイプを追加/変更する

| レイヤー | ファイル |
| --- | --- |
| FE型/ラベル | `frontend/src/types/index.ts` |
| FE送信UI | `frontend/src/components/chat/ChatInput.tsx` |
| FE送信ボディ | `frontend/src/App.tsx` |
| BE APIモデル | `backend/gateway/models.py` |
| BE分岐 | `backend/gateway/services/game_service.py` |
| Prompt | 対象 `*_prompts.py` |
| 履歴遡及 | `backend/gateway/services/history_context.py`、`frontend/src/utils/historyLookback.ts` |
| E2E/unit | `frontend/tests/e2e/`、`backend/tests/unit/test_*mode.py` |

`image_only` を基準に副作用の有無を明示する。画像のみの失敗ではHistoryを保存せず、通常モードの心境、stats、実績、人物更新へ落ちないことをテストする。

### プロンプト/履歴/メモリを変更する

| 目的 | ファイル |
| --- | --- |
| 心境/着せ替え/NovelAI | `services/prompts.py` |
| 現実改変 | `services/reality_prompts.py` |
| セルフモード | `services/self_mode_prompts.py` |
| 画像のみ | `services/image_only_prompts.py` |
| 指示候補 | `services/instruction_suggestion_prompts.py`、`instruction_suggestion_service.py` |
| 履歴遡及 | `services/history_context.py`、`services/session.py` |
| セッションプレイメモ | `services/play_memory_service.py` |
| ユーザー長期メモリ | `services/memory_prompts.py`、`memory_job_service.py`、`routes/memory_router.py` |
| 衣装レイヤー | `services/clothing_layers.py` |

`original_instruction`、心境用instruction、画像用instructionを分ける。`prompt_override` に自動履歴を足さず、画像メモリはopt-in時だけ有効メモを足す。

### DBモデルを追加する

1. `backend/gateway/databases/models.py` を変更する。
2. 必要ならrepo/serviceを追加する。
3. `backend` で `uv run alembic revision --autogenerate -m "description"` を実行する。
4. migrationのupgrade/downgradeから無関係な差分を除く。
5. `isolated_db` フィクスチャ（FK 有効の一時 SQLite）で保存と削除を検証する。

### AivisSpeechを変更する

- Router: `backend/gateway/routes/aivisspeech_router.py`
- Lifecycle/合成: `backend/gateway/services/aivisspeech_service.py`
- FE API: `frontend/src/apis/speechSynthesis.ts`
- UI: `frontend/src/components/settings/SpeechSynthesisSettings.tsx`
- 設定: `frontend/src/contexts/SettingsContext.tsx`、`backend/gateway/services/settings_service.py`

起動要求の受付とHTTP readinessを区別し、長文はチャンクWAV結合まで検証する。

## フロントエンド

### 画面を追加する

1. `frontend/src/components/{feature}/FeatureScreen.tsx` と必要なCSSを追加する。
2. `frontend/src/routes/index.tsx` に定数を追加する。
3. 現行方式では `frontend/src/App.tsx` の `useLocation()` 分岐を追加する。
4. `SideMenu.tsx` と `i18n/ja/menu.ts`・`i18n/en/menu.ts` を更新する。
5. 対象Playwrightを追加する。

RouterProviderへ部分移行しない。既存の画面切替方式を保つ。

### 共有状態を追加する

| 状態 | Context |
| --- | --- |
| 通常ゲーム、履歴、人物、セッションプレイメモ | `GameContext` |
| チャット入力、メッセージ、一時ID、音声再生 | `ChatContext` |
| 設定、トグル、localStorage/サーバー保存 | `SettingsContext` |
| 通知 | `NotificationContext` |
| Adventure Run/ストリーム | `AdventureContext` |

既存Contextに収まる場合は新規Contextを作らない。props中継やprops→effect→Context同期を追加しない。

### 設定トグルを追加する

1. `SettingsContext.tsx` のstate/action/default/load/saveを更新する。
2. `SettingsScreen.tsx` または対象設定コンポーネントを更新する。
3. `i18n/ja/` と `i18n/en/` の該当する名前空間ファイルを更新する。
4. APIに必要なら `backend/gateway/models.py` と `settings_service.py` を更新する。
5. 挙動を使う全送信経路へ伝播する。

互換性へ影響する実験設定はdefault OFFにする。操作種別ごとの設定は明示的な対象マップを持ち、`localStorage` 復元もテストする。

### SSEイベントを追加する

| 順序 | ファイル |
| --- | --- |
| 1. BE送出 | `backend/gateway/services/game_service.py`、必要ならrouter |
| 2. FE型/解析 | `frontend/src/hooks/useSSE.ts` |
| 3. Context接続 | `frontend/src/hooks/useGameSSE.ts` |
| 4. 表示/状態 | 対象Contextとコンポーネント |
| 5. テスト | BE unit + FE E2E |

Adventureイベントは `apis/adventure.ts` の専用パーサを変更し、通常ゲームの `useSSE` と混ぜない。

## 横断機能

### Adventureを変更する

| レイヤー | ファイル |
| --- | --- |
| DB | `backend/gateway/databases/models.py` (`AdventureRun`、`AdventureTurn`) |
| シナリオ | `backend/gateway/scenarios/*.json`、`adventure_template_loader.py` |
| サービス | `backend/gateway/services/adventure_service.py` |
| Router | `backend/gateway/routes/adventure_router.py` |
| FE API/型 | `frontend/src/apis/adventure.ts` |
| FE状態 | `frontend/src/contexts/AdventureContext.tsx` |
| UI | `frontend/src/components/adventure/` |
| 検証 | `backend/tests/unit/test_adventure_service.py`、`frontend/tests/e2e/adventure*.spec.ts` |

ターン画像は開始画像から時系列に実効画像を引き継ぎ、背景/立ち絵/合成画像のURL正規化と透過表示を確認する。

### 複数人物を変更する

- BE: `character_router.py`、`character_service.py`、`databases/character_repo.py`、`SessionCharacter` / `CharacterPreset`
- FE: `apis/characters.ts`、`GameContext.tsx`、`panel/CharacterPanel.tsx`、`CharacterPresetPicker.tsx`
- Prompt: `game_service.py`、`llm_service.py`
- E2E/unit: 人物上限、主人公の冪等確保、lock/exclude、preset CRUD、画像プロンプト反映

`enableMultiplePeople` と `multiCharacterPanelEnabled` の意味を分け、OFF時の従来挙動を保つ。

### ギャラリー/お気に入り/エクスポートを変更する

| 機能 | BE | FE |
| --- | --- | --- |
| Gallery | `gallery_router.py` | `apis/gallery.ts`、`components/gallery/`、`useGallery.ts` |
| Favorite | `favorites_router.py`、`favorite_service.py`、`FavoriteOutfit` | `apis/favorites.ts`、Gallery UI |
| Export | `export_service.py`、gallery export endpoint | `apis/gallery.ts`、download UI |

エクスポートは永続化済みフィールドを情報源にし、HistoryとConversationを時系列に統合する。

## 検証コマンド

```powershell
# Frontend: 変更ファイルだけ
cd frontend
npx @biomejs/biome check src/path/File.tsx
npx vitest run src/path/File.test.ts
npm run build
npx playwright test tests/e2e/target.spec.ts

# Backend: 変更ファイルだけ
cd backend
uv run ruff check gateway/path/file.py tests/unit/test_target.py
uv run ruff format --check gateway/path/file.py tests/unit/test_target.py
uv run pytest tests/unit/test_target.py

# Markdown
npx prettier --check ../.github/skills/tsf-closet-navigator/**/*.md ../.claude/skills/tsf-closet-navigator/**/*.md
```

共有基盤、Context、Router、migrationを変更した場合だけ検証範囲を広げる。サーバー未起動、依存欠落、Windows sandboxの失敗を製品不具合と断定しない。
