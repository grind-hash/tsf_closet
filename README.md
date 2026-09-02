🌐 **日本語** | **[English](README_en.md)**

[![License](https://img.shields.io/badge/license-MIT-green.svg)](License.txt)

<p align="center">
  <img src="repo_resources/brand_image.jpg" alt="TSF Closet" width="720" />
</p>

# TSF Closet

> **TSF Closet** は [nata-water/wakuwaku-transform-magic](https://github.com/nata-water/wakuwaku-transform-magic) を fork し、TSF (性転換) テーマに特化させたインタラクティブ着せ替えゲームです。

キャラクター画像に対して自然言語で衣装変更を指示すると、AI が画像を変換し、キャラクターの心理変化をリアルタイムに描写します。パラメータの変動、臨界点イベントなど、ビジュアルノベル風のゲームシステムを搭載しています。

---

## スクリーンショット

### ゲームプレイ

|                       初期画面                        |                          着せ替え後                           |
| :---------------------------------------------------: | :-----------------------------------------------------------: |
| ![ゲーム画面 (初期状態)](repo_resources/screen01.png) | ![着せ替え後 (プリンセスドレス)](repo_resources/screen02.png) |

### プレイ要約 & 称号

|                  称号生成前                  |                  称号生成後                  |                      共有用プレビュー                      |
| :------------------------------------------: | :------------------------------------------: | :--------------------------------------------------------: |
| ![称号生成前](repo_resources/screen05_0.png) | ![称号生成後](repo_resources/screen05_1.png) | ![共有用プレビューで保存](repo_resources/screen05_1_2.png) |

### インペイント (部分変更)

|                     マスク編集                     |                        生成中                        |                        結果                        |
| :------------------------------------------------: | :--------------------------------------------------: | :------------------------------------------------: |
| ![インペイント編集](repo_resources/screen05_2.png) | ![インペイント生成中](repo_resources/screen05_3.png) | ![インペイント結果](repo_resources/screen05_4.png) |

### ギャラリー

|                       セッション一覧                        |                       画像一覧                        |
| :---------------------------------------------------------: | :---------------------------------------------------: |
| ![ギャラリー (セッション一覧)](repo_resources/screen04.png) | ![ギャラリー (画像一覧)](repo_resources/screen05.png) |

### 初回セットアップ (NovelAI)

|                     APIキー同意                     |                 サブスクリプション警告                 |
| :-------------------------------------------------: | :----------------------------------------------------: |
| ![APIキー同意モーダル](repo_resources/screen06.png) | ![サブスクリプション警告](repo_resources/screen07.png) |

---

## 主な機能

| 機能                      | 説明                                                            |
| ------------------------- | --------------------------------------------------------------- |
| **キャラクター選択**      | プリセットキャラクター or カスタム画像アップロード              |
| **着せ替え実行**          | 自然言語で衣装変更を指示 (例:「バニーレオタードに着替えて」)    |
| **AI 画像生成**           | ComfyUI / OpenRouter / NovelAI の 3 プロバイダーを切り替え可能  |
| **心境セリフ生成**        | Vision LLM + Text LLM でキャラクターの反応をストリーミング表示  |
| **パラメータシステム**    | 開花度・羞恥心・順応度が衣装に応じて変動                        |
| **臨界点イベント**        | 開花度が閾値に達すると特別な演出セリフが発火                    |
| **実績システム**          | 12 種類の実績を自動判定                                         |
| **ギャラリー**            | 過去の変身画像・達成エンディングを閲覧                          |
| **プレイ要約 & 称号**     | LLM がプレイ履歴から要約と称号 (二つ名) を自動生成              |
| **共有プレビュー**        | 要約カードを OGP 風画像 (1200×630) で保存・クリップボードコピー |
| **インペイント / マスク** | 部分的な衣装変更に対応 (システム / 履歴 / プリセットマスク)     |
| **キャラクター会話**      | 着せ替え以外にもキャラクターとチャット可能                      |
| **TSFシナリオ**           | 変身後の状態から始まるノベルゲーム。恋愛シミュレーション等 5 種のミッション (実験的機能) |
| **対面会話モード**        | 攻略対象と 1 ターン = 1 往復で会話。3Dモデル (VRM) の表示と音声入力に対応 (実験的機能) |
| **Prompt Expander**       | 自然文の指示を NovelAI 用プロンプトへ拡張し、ゲームと独立に画像を生成 (実験的機能) |
| **音声合成**              | AivisSpeech によるセリフの読み上げ (実験的機能)                 |
| **NAI Diffusion V5 対応** | NSFW / 非 NSFW ごとのモデル選択と残り利用量の表示               |
| **メモリ**                | 好みメモリ (プレイ横断) とプレイメモ (プレイ内) を生成へ反映    |
| **お気に入り衣装**        | 履歴画像の☆登録・ラベル付け・一覧からの再開                    |
| **分岐 / 比較**           | 履歴画像から別セッションを開始、Before/After スライダーで変身を比較 |
| **エクスポート**          | チャット履歴を Markdown / 小説形式 HTML の ZIP で保存           |
| **複数キャラクター**      | セッションを跨ぐ容姿の永続化とキャラクタープリセット (実験的機能) |
| **多言語対応**            | 日本語 / English 切り替え (会話言語バリデーション付き)          |

---

## アーキテクチャ

```
┌────────────────────┐
│  Browser (React)   │
│  :3000 (dev)       │
└────────┬───────────┘
         │ /api/*
         ▼
┌────────────────────┐     ┌──────────────────────────────────┐
│  FastAPI Backend   │────▶│  Image Generation                │
│  :8000             │     │  ├ ComfyUI (selfhost, GPU)       │
│                    │     │  ├ OpenRouter API (cloud)         │
│  ├ Game / Chars    │     │  └ NovelAI Image API             │
│  ├ Adventure       │     └──────────────────────────────────┘
│  ├ Prompt Expander │     ┌──────────────────────────────────┐
│  ├ Gallery / Favs  │────▶│  LLM / Vision                   │
│  ├ Achievements    │     │  ├ LiteLLM → Ollama (selfhost)  │
│  ├ Memory          │     │  ├ OpenRouter Vision / LLM      │
│  ├ Avatars (VRM)   │     │  └ NovelAI Text API              │
│  ├ AivisSpeech     │     └──────────────────────────────────┘
│  ├ Settings        │     ┌──────────────────────────────────┐
│  └ Health          │────▶│  Speech Synthesis                │
└────────────────────┘     │  └ AivisSpeech Engine (TTS)      │
                           └──────────────────────────────────┘
```

### 技術スタック

| レイヤー       | 技術                                               |
| -------------- | -------------------------------------------------- |
| フロントエンド | React 19 + TypeScript + Vite                       |
| バックエンド   | FastAPI + Python 3.12                              |
| データベース   | SQLite (aiosqlite + SQLAlchemy + Alembic)          |
| 画像生成       | ComfyUI (Qwen Image Edit) / OpenRouter / NovelAI   |
| テキスト生成   | LiteLLM Proxy → Ollama / OpenRouter / NovelAI Text |
| 国際化         | i18next (ja / en)                                  |
| コンテナ       | Docker Compose (6 サービス)                        |

---

## クイックスタート

### 前提条件

- Python 3.12+
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) (Python パッケージマネージャー)
- 画像生成プロバイダー (いずれか 1 つ):
  - ComfyUI + NVIDIA GPU (セルフホスト)
  - OpenRouter API キー
  - NovelAI API キー (Opus 推奨)

### 1. セットアップ

```powershell
# バックエンド依存パッケージ
cd backend
uv sync

# フロントエンド依存パッケージ
cd ../frontend
npm install
```

### 2. 環境変数の設定

`.env.example` をコピーして `.env` を作成し、利用するプロバイダーに応じて設定します:

```powershell
Copy-Item .env.example .env
```

### 3. アプリケーション起動

```powershell
# バックエンド (ポート 8000)
cd backend
uv run uvicorn gateway.app:app --host 0.0.0.0 --port 8000 --reload

# フロントエンド (ポート 3000) ※別ターミナル
cd frontend
npm run dev
```

ブラウザで `http://localhost:3000/` にアクセスしてください。

---

## Docker デプロイ

```powershell
docker compose up -d
# バックエンドのデータベースマイグレーション適用
docker compose exec backend bash -c "uv run alembic upgrade head"
```

> **注意**: ComfyUI のモデルダウンロード完了まで 1 時間以上かかる場合があります。`docker compose logs -f comfyui` で進行状況を確認してください。

| サービス     | 説明               | ポート |
| ------------ | ------------------ | ------ |
| `frontend`   | React + nginx      | 80     |
| `backend`    | FastAPI            | (内部) |
| `litellm`    | LiteLLM Proxy      | 4000   |
| `litellm_db` | PostgreSQL 16      | 5432   |
| `ollama`     | ローカル LLM (GPU) | —      |
| `comfyui`    | 画像生成 (GPU)     | 8188   |

**システム要件** (Docker):

- NVIDIA GPU (ollama, comfyui)
- ストレージ: 100 GB 以上の空き容量
- メモリ: 64 GB 以上推奨

---

## ポータブル版ビルド

GPU 環境がないユーザー向けに、Windows ポータブル配布パッケージを作成できます:

```powershell
.\scripts\build_portable.ps1 -Version "0.1.0" -Provider novelai
```

| パラメータ      | 説明                                  | デフォルト |
| --------------- | ------------------------------------- | ---------- |
| `-Version`      | バージョン文字列                      | `dev`      |
| `-Provider`     | `novelai` / `selfhost` / `openrouter` | `novelai`  |
| `-Force`        | 既存出力を上書き                      | —          |
| `-NoZip`        | ZIP 作成をスキップ                    | —          |
| `-SkipFrontend` | フロントエンドビルドをスキップ        | —          |
| `-SkipPython`   | Python 環境構築をスキップ             | —          |

出力先: `dist/tsf_closet_portable_v{Version}_{Provider}/`

---

## 画像生成プロバイダー

環境変数 `IMAGE_PROVIDER` で切り替え:

| プロバイダー | 環境変数例                               | 必要なもの                   |
| ------------ | ---------------------------------------- | ---------------------------- |
| `selfhost`   | `COMFYUI_BASE_URL=http://127.0.0.1:8188` | NVIDIA GPU + ComfyUI         |
| `openrouter` | `OPENROUTER_API_KEY=sk-...`              | OpenRouter API キー          |
| `novelai`    | `NOVELAI_API_KEY=pst-...`                | NovelAI API キー (Opus 推奨) |

テキスト生成 (心境セリフ) も同様に `FEELING_PROVIDER` で切り替え可能です。

> **OpenRouter 利用時の注意**
>
> - R18 / NSFW モードの画像生成・画像編集には**対応していません** (対応モデルが現時点で見つかっていないため)。
> - 内部で nano banana を利用しているため、「バニーガール」など一部のプロンプトがコンテンツフィルターに抵触し、画像生成エラーになる場合があります。

> **NAI Diffusion V5**
>
> - NSFW / 非 NSFW それぞれで使用する画像生成モデル (V4.5 Full / V5 Full / V4.5 Curated / V5 Curated) を設定画面から選択できます。
> - V5 の残り利用量を表示します (上限到達後の生成は Anlas を消費します)。
> - 精密参照は V4.5 モデル選択時のみ利用可能です。

---

## ゲームシステム

### パラメータ

| パラメータ          | 範囲       | 説明                                           |
| ------------------- | ---------- | ---------------------------------------------- |
| 開花度 (bloom)      | 0 〜 100   | 女性化への順応度。衣装の露出度・カテゴリで増加 |
| 羞恥心 (shame)      | 0 〜 100   | 露出度の高い衣装で上昇。開花速度に影響         |
| 順応度 (adaptation) | -50 〜 +50 | 正は積極的、負は抵抗的な心理状態               |

### 難易度

| 難易度              | 羞恥心初期値 | 開花倍率 | 順応倍率 |
| ------------------- | ------------ | -------- | -------- |
| easy (抵抗しやすい) | 70           | 0.5x     | 1.0x     |
| normal (普通)       | 50           | 1.0x     | 1.0x     |
| hard (堕ちやすい)   | 30           | 1.5x     | 1.2x     |

### 臨界点イベント

開花度が閾値に達すると、キャラクターが特別な演出セリフを発します:

| 閾値 | 内容                             |
| ---- | -------------------------------- |
| 25%  | 女性化への違和感を自覚           |
| 50%  | 抵抗と快楽の狭間で揺れる         |
| 75%  | 女性としての感覚を受け入れ始める |
| 100% | 完全に女性として順応             |

### エンディング (4 種類)

| エンディング       | 条件概要                        |
| ------------------ | ------------------------------- |
| 快楽開花エンド     | 開花度 100 + 露出系変身が最多   |
| 自己受容エンド     | 開花度 100 + 可愛い系変身が最多 |
| 抵抗の限界エンド   | 変身 15 回 + 開花度 50 未満     |
| 好奇心の暴走エンド | 開花度 100 + タグ分散           |

### 実績システム (12 種類)

変身回数、女装回数、コレクション数、開花度などの条件に応じて自動的にアンロックされます。

---

## TSFシナリオ (アドベンチャーモード)

変身後の状態 (セッションの任意の時点) を起点に、独立したノベルゲーム形式のシナリオをプレイできる実験的機能です。設定画面の「Experimental」から「TSFシナリオ」を有効にすると、メインメニューに表示されます。

- **ミッション**: 「恋愛シミュレーション」「潜入」「脱出・帰還」「交渉」「なりすまし・着替え」の 5 種類。舞台・ゴール・制約は AI による自動生成のほか、直接入力や用意された作品シナリオ (「女装してプリンセスにならないと出られない部屋」) からの選択に対応
- **恋愛シミュレーション**: 日数制 (昼・夜) の進行、好感度、所持金、バイト、ギフトショップ、告白、エンディング後のエピローグ。主人公には別セッションの姿を使用でき、攻略対象が主人公を呼ぶ「呼び名」も指定可能
- **現実改変**: 「現実改変：〜」で世界ルールを宣言し、以降のすべての判定に適用 (手番を消費しない属性付与も可能)
- **トーク**: 手番を消費しない雑談。好感度・所持金・日数は変わらず、会話の内容は次の手番の物語に引き継がれる
- **BGM 自動選曲**: 場面に合わせて BGM を自動選曲 (楽曲は Suno AI 製)。BGM テスト画面で試聴可能
- **語りと口調**: 語りの人称 (一人称 / 二人称 / 三人称) と、主人公・攻略対象の口調を指定可能
- **その他**: 手番の巻き戻し、場面画像のプロンプト編集・再生成、ログ表示、Anlas 消費の見積もり表示に対応
- NovelAI に加えて OpenRouter / セルフホスト (ComfyUI) でもプレイ可能 (プロバイダーにより一部機能が制限されます)

処理フローの詳細は [docs/adventure-flow.md](docs/adventure-flow.md) を参照してください。

<!-- TODO: screenshot repo_resources/screen08_adventure_title.png (ミッション選択) / repo_resources/screen09_adventure_sim.png (恋愛シミュレーションの HUD) -->

### 対面会話モード

恋愛シミュレーションで有効化できるモードです (既定 OFF)。攻略対象が目の前に立ち、1 ターン = 1 往復の会話になります。昼・夜の区切りは無く、設定したターン数の往復で結果が確定します。

- 画像は攻略対象の立ち絵と背景 (場所が変わったときだけ) のみを生成します。セルフホスト (ComfyUI) では背景を txt2img 用ワークフロー (`COMFYUI_TXT2IMG_WORKFLOW_PATH`) で生成します
- セリフ読み上げに対応。本文の「名前「セリフ」」行だけを AivisSpeech で自動再生し、再生中は BGM の音量を下げます
- マイクによる音声入力に対応 (Chrome / Edge)。ブラウザの音声認識を使うため、Chrome では音声が Google のサーバーへ送られます

<!-- TODO: screenshot repo_resources/screen10_adventure_companion.png (対面会話モード + 3Dモデル) -->

---

## 3Dモデル (VRM) アバター

対面会話モードで、攻略対象の立ち絵の代わりに 3D モデル (VRM 0.x / 1.0) を表示できます。設定画面の「3Dモデル (VRM)」からドラッグ＆ドロップで登録します。

- 読み上げの音素タイミングに合わせて口が動き、返答ごとに表情と身振りが変わります
- ファイル名が「キャラクター名_衣装_髪型Ver.vrm」の形なら、キャラクターと衣装差分を自動で分類します。同じキャラクターの差分が 2 つ以上あると、着替えの場面に合わせてモデルが切り替わります
- 登録済みモデルのプレビューで、表情と身振りの見え方を確認できます
- FBX や PMX は VRM に変換してから登録してください。モデルの利用条件は各配布元の規約に従ってください

<!-- TODO: screenshot repo_resources/screen13_avatar_preview.png (3Dモデルプレビュー) -->

---

## Prompt Expander

自然文の指示を LLM で NovelAI 用プロンプトに拡張し、ゲームとは独立に画像を生成・保存できる実験的機能です。設定画面の「Experimental」から「Prompt Expander」を有効にすると、メインメニューに表示されます。

- 出力形式は「日本語文」「タグ」から選択。セッション単位で履歴を管理し、「欄へ復元」「このプロンプトで再生成」「i2i元にする」「通常プレイで使う」「TSFシナリオで使う」が行えます
- キャラクタープロンプトに対応 (V5 系は最大 22 件、V4.5 系は最大 6 件)。メモリから好みのキャラクター像を提案してスロットへ挿入できます
- 漫画 (コマ割り) モード (NAI Diffusion V5 系専用): コマ数・コマ割り・読み順 (既定は日本式の右→左)・セリフの言語を指定。あらすじから記法付きネームの下書きにも対応
- インペイント (部分修正)、精密参照 (V4.5 系専用、参照 1 枚あたり追加の Anlas を消費)、画像の背景透過、画面へのドラッグ＆ドロップに対応

<!-- TODO: screenshot repo_resources/screen11_prompt_expander.png (漫画モード) -->

---

## 音声合成 (AivisSpeech)

AivisSpeech エンジンによるセリフの読み上げに対応した実験的機能です。設定画面の「音声合成 (AivisSpeech)」から有効化します。

- 通常プレイのチャット読み上げと、TSFシナリオ (対面会話モード) のセリフ自動再生に対応
- VOICEVOX 互換エンジンへの接続にも対応
- 音声の初期音量は 50% で、音量と再生速度を調整できます

<!-- TODO: screenshot repo_resources/screen12_settings_tts.png (音声合成設定) -->

---

## メモリ (好みメモリ / プレイメモ)

- **好みメモリ**: 過去のプレイログを分析し、好みのシチュエーションを自動生成します。生成されたメモリは自由に編集でき、プレイを跨いで着せ替え・現実改変・行動などの指示、指示文の提案、画像生成に反映されます
- **プレイメモ (実験的機能)**: プレイごとの経緯を自動的に要約し、そのプレイ内の生成に反映します。維持したい設定や希望はユーザーメモとして手動設定できます。有効時はチャットごとに自動メモを生成するため、応答完了までの時間が長くなる場合があります

---

## API エンドポイント

### Game (`/api/game`)

| メソッド | パス            | 説明                              |
| -------- | --------------- | --------------------------------- |
| `POST`   | `/start`        | ゲームセッション開始              |
| `POST`   | `/start-custom` | カスタム画像でセッション開始      |
| `POST`   | `/play/stream`  | 着せ替え実行 (SSE ストリーミング) |
| `GET`    | `/characters`   | キャラクター一覧取得              |
| `GET`    | `/session`      | アクティブセッション取得          |
| `GET`    | `/sessions`     | セッション一覧 (ページネーション) |
| `DELETE` | `/session`      | セッションリセット                |
| `POST`   | `/chat`         | キャラクターとの会話              |
| `GET`    | `/endings`      | エンディング一覧                  |
| `GET`    | `/masks`        | マスク一覧取得                    |

### Gallery (`/api/gallery`)

| メソッド | パス                             | 説明                                  |
| -------- | -------------------------------- | ------------------------------------- |
| `GET`    | `/`                              | ギャラリーアイテム一覧                |
| `GET`    | `/sessions`                      | セッション別ギャラリー                |
| `GET`    | `/{item_id}`                     | アイテム詳細 (前後ナビ付き)           |
| `DELETE` | `/{item_id}`                     | アイテム削除                          |
| `GET`    | `/sessions/{session_id}/summary` | プレイ要約・称号の取得                |
| `POST`   | `/sessions/{session_id}/summary` | プレイ要約・称号の生成 (`?language=`) |

### Achievements (`/api/achievements`)

| メソッド | パス                | 説明         |
| -------- | ------------------- | ------------ |
| `GET`    | `/`                 | 実績一覧取得 |
| `GET`    | `/{achievement_id}` | 実績詳細取得 |

### Settings (`/api/settings`)

| メソッド | パス    | 説明               |
| -------- | ------- | ------------------ |
| `GET`    | `/`     | セッション設定取得 |
| `PUT`    | `/`     | セッション設定更新 |
| `GET`    | `/user` | ユーザー設定取得   |
| `PUT`    | `/user` | ユーザー設定更新   |

### その他のルーター (概要)

| プレフィックス         | 説明                                                                                    |
| ---------------------- | --------------------------------------------------------------------------------------- |
| `/api/adventure`       | TSFシナリオ (Run / テンプレート / 手番 SSE / トーク SSE / 現実改変 / 巻き戻し / BGM)     |
| `/api/prompt-expander` | Prompt Expander (セッション / エントリ / 拡張 / 生成 / 漫画ネーム / 設定)                |
| `/api/avatars`         | 3Dモデル (VRM) の登録・自動分類・配信                                                    |
| `/api/aivisspeech`     | 音声合成 (`/synthesize`、viseme タイムライン付き `/synthesize-timed`、エンジン管理)      |
| `/api/memory`          | 好みメモリの生成ジョブ・本文編集                                                         |
| `/api/favorites`       | お気に入り衣装の一覧・登録・ラベル変更                                                   |
| `/api/game` (複数人物) | セッション人物の管理とキャラクタープリセット                                             |

### SSE イベント (`/api/game/play/stream`)

| イベント      | データ                                  |
| ------------- | --------------------------------------- |
| `feeling`     | キャラクターの心境セリフ (チャンク形式) |
| `image`       | 生成画像の Base64 データ                |
| `tags`        | 衣装タグ情報 (カテゴリ・露出度)         |
| `stats`       | パラメータ変動値                        |
| `critical`    | 臨界点到達時の演出セリフ                |
| `ending`      | エンディング判定結果                    |
| `achievement` | 実績アンロック通知                      |
| `done`        | 処理完了                                |

---

## 環境変数一覧

<details>
<summary>クリックで展開</summary>

### 共通

| 変数名                       | 説明                                                         | デフォルト |
| ---------------------------- | ------------------------------------------------------------ | ---------- |
| `PORT`                       | サーバーポート                                               | `8000`     |
| `LOG_LEVEL`                  | ログレベル                                                   | `info`     |
| `IMAGE_PROVIDER`             | 画像生成プロバイダー (`selfhost` / `openrouter` / `novelai`) | `selfhost` |
| `IMAGE_DESCRIPTION_PROVIDER` | 画像説明プロバイダー                                         | `selfhost` |
| `FEELING_PROVIDER`           | 心境生成プロバイダー                                         | `selfhost` |
| `ENABLE_PROMPT_PREVIEW`      | TSFシナリオのプロンプト確認機能                              | `false`    |

### ComfyUI (selfhost)

| 変数名                    | デフォルト                                |
| ------------------------- | ----------------------------------------- |
| `COMFYUI_BASE_URL`        | `http://127.0.0.1:8188`                   |
| `COMFYUI_WORKFLOW_PATH`   | `workflows/qwen_image_edit_template.json` |
| `COMFYUI_TXT2IMG_WORKFLOW_PATH` | 未設定時は `COMFYUI_WORKFLOW_PATH` のファイル名の `image_edit` を `image_txt2img` に置き換えたもの (無ければ `workflows/qwen_image_txt2img_template_local.json`) |
| `COMFYUI_REQUEST_TIMEOUT` | `180`                                     |

### LiteLLM (selfhost)

| 変数名                  | デフォルト (.env.example)                     |
| ----------------------- | --------------------------------------------- |
| `LITELLM_BASE_URL`      | `http://127.0.0.1:4000`                       |
| `LITELLM_LLAVA_MODEL`   | `ollama/ministral-3:14b-instruct-2512-q4_K_M` |
| `LITELLM_LLM_MODEL`     | `ollama/ministral-3:14b-instruct-2512-q4_K_M` |
| `LITELLM_FEELING_MODEL` | `ollama/ministral-3:14b-instruct-2512-q4_K_M` |

セルフホスト構成 (`.env.example.selfhost`) では 3 つのモデルの既定値は `gemma4:e4b` です。

### OpenRouter

| 変数名                    | デフォルト (.env.example)       |
| ------------------------- | ------------------------------- |
| `OPENROUTER_API_KEY`      | (必須)                          |
| `OPENROUTER_IMAGE_MODEL`  | `google/gemini-2.5-flash-image` |
| `OPENROUTER_VISION_MODEL` | `google/gemini-3-flash-preview` |
| `OPENROUTER_LLM_MODEL`    | `google/gemini-3-flash-preview` |

### NovelAI

| 変数名                          | デフォルト                             |
| ------------------------------- | -------------------------------------- |
| `NOVELAI_API_KEY`               | (必須)                                 |
| `NOVELAI_MODEL`                 | `nai-diffusion-4-5-full`               |
| `NOVELAI_INPAINT_MODEL`         | `nai-diffusion-4-5-full-inpainting`    |
| `NOVELAI_CURATED_MODEL`         | `nai-diffusion-4-5-curated`            |
| `NOVELAI_CURATED_INPAINT_MODEL` | `nai-diffusion-4-5-curated-inpainting` |
| `NOVELAI_STEPS`                 | `28`                                   |
| `NOVELAI_SCALE`                 | `5.0`                                  |
| `NOVELAI_I2I_STRENGTH`          | `0.9`                                  |
| `NOVELAI_TEXT_MODEL`            | `glm-4-6`                              |

### データ永続化

| 変数名               | デフォルト             |
| -------------------- | ---------------------- |
| `DATABASE_PATH`      | `data/database.sqlite` |
| `HISTORY_IMAGES_DIR` | `data/history_images`  |
| `HISTORY_MAX_COUNT`  | `50`                   |
| `CHARACTERS_DIR`     | `images/characters`    |

</details>

---

## キャラクターの追加

[backend/images/characters/characters.json](backend/images/characters/characters.json) を編集し、同ディレクトリに画像を配置します:

```json
{
  "characters": [
    {
      "id": "char1",
      "name": "主人公",
      "description": "普通の男子高校生",
      "image_path": "char1.png",
      "pronoun": "僕",
      "personality": "内気で真面目"
    }
  ]
}
```

カスタム画像はゲーム開始時に UI からアップロードすることも可能です。

---

## フロントエンド画面

| パス               | 画面                                       |
| ------------------ | ------------------------------------------ |
| `/` `/play`        | メインゲーム画面                           |
| `/gallery`         | ギャラリー                                 |
| `/achievements`    | 実績一覧                                   |
| `/endings`         | エンディング一覧 (実験的機能で有効化)      |
| `/adventure`       | TSFシナリオ (実験的機能で有効化)           |
| `/bgm-test`        | BGM テスト (TSFシナリオ有効時)             |
| `/prompt-expander` | Prompt Expander (実験的機能で有効化)       |
| `/settings`        | 設定                                       |

---

## 開発

```powershell
# バックエンド (ホットリロード)
cd backend
uv run alembic upgrade head
uv run uvicorn gateway.app:app --host 0.0.0.0 --port 8000 --reload

# フロントエンド (Vite dev server)
cd frontend
npm run dev

# Lint
cd frontend; npm run lint
cd backend; uv run ruff check .

# テスト
cd frontend; npm run e2e:test
cd backend; uv run pytest
```

### マイグレーション

```powershell
cd backend
uv run alembic revision --autogenerate -m "migration_comment"
uv run alembic upgrade head
```

---

## fork 元との差分

本プロジェクトは nata-waterさんが開発された[wakuwaku-transform-magic](https://github.com/nata-water/wakuwaku-transform-magic) (子供向け変身ごっこアプリ) を fork し、以下の変更を加えています:

- TSF (性転換) テーマへの全面的な書き換え
- パラメータシステムの再設計 (ワクワク度 → 開花度 / 羞恥心 / 順応度)
- エンディング条件の再設計
- NovelAI プロバイダーの追加 (NAI Diffusion V5 対応を含む)
- インペイント / マスク機能の追加
- 実績システムの追加
- ギャラリー機能の拡張 (お気に入り衣装、変身の比較、キーワード検索、履歴分岐)
- 会話 (チャット) 機能の追加
- 多言語対応 (i18next)
- ポータブル版ビルドスクリプト
- 画質改善機能
- TSFシナリオ (アドベンチャーモード) の追加
- 対面会話モードと 3Dモデル (VRM) アバターの追加
- Prompt Expander の追加
- 音声合成 (AivisSpeech) の追加
- 好みメモリ / プレイメモの追加
- 複数キャラクターの永続化とキャラクタープリセットの追加

---

## ライセンス

[MIT License](License.txt) - Copyright (c) 2026 nata-water
