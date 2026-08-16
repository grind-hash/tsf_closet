# 非推奨機能と削除予定

UI 上で「Deprecated」チップを付与した機能と、その削除作業に必要な対象箇所をまとめる。

チップは `data-removal-version="vX.Y.Z"` を持つため、削除作業時は次のコマンドで対象を洗い出せる。

```
cd frontend; npx rg 'data-removal-version="v0.8.0"' src
```

---

## v0.8.0 で削除予定

### 右パネル「保持する要素」セクション

- 非推奨化: v0.7.0
- 削除予定: v0.8.0
- 代替手段: プレイメモの「ユーザーメモ」に、保持したい内容を自由記述で指定する
  （プレイメモは設定画面の「プレイメモ」を有効にすると右パネルに表示される）

対象はセクション全体。保持要素チェックボックス、保持要素プリセット、「変更対象」セレクト、
「その他の保持指定」入力、プリセット保存ボタンを含む。

#### 削除対象

**フロントエンド UI (`frontend/src/components/layout/RightPanel.tsx`)**

- 「保持する要素」セクション本体（`rightPanel.sectionPreserve` の `<section>` 全体）
- リクエスト組み立ての `preserve_elements`
- 「現在の設定」サマリー内の保持要素表示（`rightPanel.preserveElementsLabel` / `preserveLabel`）
- 定数 `PRESERVE_ELEMENTS` / `CHANGE_SCOPES`
- ハンドラ `getPreserveElementLabel` / `getChangeScopeLabel` / `handleTogglePreserveElement` /
  `handleChangeScopeChange` / `handleCustomPreserveTextChange`
- 保持要素プリセット関連（`handleLoadPreservePreset` / `handleDeletePreservePreset` /
  保存モーダル、localStorage キー `preserve_presets`）

**フロントエンド 状態・型**

- `frontend/src/types/index.ts`: `PreserveElement` / `ChangeScope` / `ChangeSettings` /
  `DEFAULT_CHANGE_SETTINGS`
- `frontend/src/contexts/SettingsContext.tsx`: `changeSettings` の型定義・既定値・
  `SET_CHANGE_SETTINGS` リデューサ・`setChangeSettings`
- `frontend/src/components/GamePlayScreen.tsx`: `changeSettings` の受け渡し
- `frontend/src/App.tsx`: `preserve_elements` / `change_scope` / `custom_preserve_text` の送信
- `frontend/src/apis/game.ts`: `preserve_elements`

**フロントエンド i18n (`frontend/src/i18n.ts`, ja / en 両方)**

`rightPanel` 配下の以下のキー:

- `sectionPreserve`
- `preserveDeprecatedNotice`（本非推奨表示用。削除時に一緒に除去する）
- `preserveElements.*`
- `preserveElementsLabel` / `preserveLabel`
- `changeScope` / `changeScopes.*`
- `otherPreserve` / `preservePlaceholder`
- 保持要素プリセット関連（`savePreservePresetTitle` 等）

**フロントエンド CSS**

- `frontend/src/components/layout/RightPanel.css`: `.right-panel__preserve-checkboxes` ほか
  保持要素セクション専用のセレクタ
- `frontend/src/index.css`: `.feature-chip-deprecated`（他に非推奨表示が残っていない場合のみ）
- `frontend/src/components/layout/RightPanel.css`: `.right-panel__hint--deprecated`（同上）

**バックエンド**

`preserve_elements` / `change_scope` / `custom_preserve_text` を扱う箇所:

- `backend/gateway/models.py`
- `backend/gateway/routes/game_router.py`
- `backend/gateway/services/prompts.py`（プロンプトへの「保持する要素」注入を含む）
- `backend/gateway/services/game_service.py`
- `backend/gateway/services/llm_service.py`
- `backend/gateway/services/litellm_client.py`

**テスト**

- `frontend/tests/e2e/preserve-elements-deprecation.spec.ts`（本非推奨表示の E2E。機能削除時に除去する）
