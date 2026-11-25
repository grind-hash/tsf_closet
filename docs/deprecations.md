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

あわせて、遊び方ガイド（`frontend/src/i18n/{ja,en}/guide.ts`）の該当項目に、非推奨であること・削除予定バージョン・
代替手段を書く。案内役のセレナはガイドの文面だけを機能の知識にするため、ここに無いと非推奨を知らずに答える。

---

## 削除予定

（なし）

---

## 削除済み

### 新規プレイ「または自分の画像を使用」

- 非推奨化: v0.11.0
- 削除: v0.12.0
- 代替手段: キャラクター画面（`/characters`）。キャラクター詳細で立ち絵に画像をアップロードし、
  一覧・詳細の「このキャラでプレイ」から自分自身モード・依頼モードを選んで始める。
  Prompt Expander のエントリは「キャラクターにする」で立ち絵にしたキャラクターを作れる
- 移行: 起動時（`gateway/app.py` の lifespan）に、取り込まれていない旧カスタムキャラクター
  （`history_images/custom/{id}.png` / `.json`）をキャラクターへ写す（`import_custom_characters`）。
  取り込んだものは JSON に `imported_preset_id` が付き、次の起動では飛ばす。失敗したものは次の起動で取り込み直す
- 残した旧データの扱い:
  - `history_images/custom/{id}.png` は過去セッションの元画像として参照されるため消さない。
    `session_{id}.json`（セッションごとのプロフィール）はキャラクターから始めたセッションも使う
  - サロンで予約済みの `customer_source="custom"` の来店は、接客開始時に `imported_preset_id` から
    取り込み先のキャラクターで始める。読み替えられないときは `customer_unavailable` を返す
  - キャラチャットに残る `source: "custom"` の提案カードは開始できず、キャラクター画面から始めるよう案内する
- 削除したもの: `POST /game/start-custom`・`GET /game/custom-characters`・`POST /game/generate-base-tags`・
  `POST /game/character-presets/import-custom`、`game_service.start_custom_session`、`CustomStartRequest`・
  `GenerateBaseTagsRequest`、新規プレイのカスタム画像の節と Prompt Expander の「通常プレイで使う」（`/play/new?pe_entry=`）、
  キャラクター一覧の取り込みの案内

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
