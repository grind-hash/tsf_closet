# 非推奨機能と削除予定

UI 上で「Deprecated」チップを付与した機能と、その削除作業に必要な対象箇所をまとめる。

チップは `data-removal-version="vX.Y.Z"` を持つため、削除作業時は次のコマンドで対象を洗い出せる。

```
cd frontend; npx rg 'data-removal-version="v0.8.0"' src
```

非推奨化する際は、対象機能ごとに次の項目を記載する。

- 非推奨化したバージョン / 削除予定バージョン
- 代替手段
- 削除対象（フロントエンド UI・状態・型・i18n・CSS、バックエンド、テスト）

---

## 削除予定

### 新規プレイ「または自分の画像を使用」

- 非推奨化: v0.11.0
- 削除予定: v0.12.0
- 代替手段: キャラクター画面（`/characters`）。キャラクター詳細の「画像をアップロード」で立ち絵を置き、
  一覧・詳細の「このキャラでプレイ」から自分自身モード・依頼モードを選んで始める
- 移行: キャラクター一覧の「このキャラクター画面へ取り込む」で、保存済みの「作成したキャラクター」
  （`history_images/custom/{id}.png` / `.json`）をキャラクターへ写す。取り込んだものは JSON に
  `imported_preset_id` が付き、新規プレイの一覧とサロンの来店候補から外れる

削除前にやること:

- チャットのプレイ提案（`backend/gateway/services/character_chat_play_proposal.py` の `build_play_catalog`）の
  候補を custom からキャラクター（preset）へ移す。フロントの `CharacterChatPlayProposalCard` / `GameContext.startNewSession` の
  `source: "custom"` も合わせて外す
- サロンの来店候補（`salon_service._customer_pool`）から custom を外す。予約済みの `customer_source="custom"` の来店が
  残っている run の扱い（始められないときのエラー表示）を決める
- 取り込まれていない custom が残るユーザー向けに、起動時の自動取り込みを入れるか決める

削除対象:

- フロントエンド: `WelcomeScreen.tsx` のカスタム画像の節（アップロード・作成したキャラクター・Prompt Expander から選択・
  人物欄・タグ自動生成）と関連 state、`CustomImageSizeWarningModal` の WelcomeScreen からの利用、
  `WelcomeScreen.css` の `welcome-screen__custom*` / `welcome-screen__upload-btn` / `welcome-screen__deprecated-notice`、
  i18n `chat.welcome.customImageSection` 〜 `customCharacterDefaultName`・`customImageDeprecated`・`customImageOpenCharacters`、
  `apis/game.ts` の `startCustomGame`、キャラクター一覧の取り込みの案内（`characters.legacy.*`、`importCustomCharacterPresets`）
- バックエンド: `POST /game/start-custom`・`GET /game/custom-characters`・`POST /game/generate-base-tags`（他に使い道が無ければ）・
  `POST /game/character-presets/import-custom`、`game_service.start_custom_session`、`custom_sessions.py` の
  カスタムキャラクター保存（`save_custom_character` 等。セッションごとの `session_{id}.json` はキャラクターから始めた
  セッションも使うので残す）、`schemas/session.py` の `CustomStartRequest`
- テスト: `tests/integration/test_game_start_api.py` の start-custom、`tests/unit/test_custom_session_tsf_attitude.py`、
  `tests/unit/test_preset_sessions.py` の取り込み

---

## 削除済み

### Experimental 設定「エンディング」「TSFシナリオ」

- 廃止: v0.9.0
- エンディング: 常時表示（メニューと通知）。`experimentalEndingEnabled` は削除
- TSFシナリオ: 設定画面の「TSFシナリオ」セクションの `adventureEnabled`（既定 ON）へ移動。`experimentalAdventureEnabled` は削除
- localStorage `app_settings` に残る旧キーは `SettingsContext.loadInitialState` で読み捨てる（既定 ON に揃えるため引き継がない）

### 右パネル「保持する要素」セクション

- 非推奨化: v0.7.0
- 削除: v0.8.0
- 代替手段: プレイメモの「ユーザーメモ」に、保持したい内容を自由記述で指定する
  （プレイメモは設定画面の「プレイメモ」を有効にすると右パネルに表示される）

保持要素チェックボックス、保持要素プリセット、「変更対象」セレクト、「その他の保持指定」入力と、
それらをプロンプトへ注入するバックエンド経路（`preserve_elements` / `change_scope` /
`custom_preserve_text`）を削除した。旧バージョンが localStorage に残した
`app_settings.changeSettings` と `preserve_presets` は、設定の初期読み込み時に破棄する。
