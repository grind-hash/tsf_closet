# API コントラクト: 行動モード画像生成

**機能**: 002-action-scene-image  
**日付**: 2026-02-21

## 変更なし: 既存エンドポイントの拡張

行動モードの画像生成は、**新しい API エンドポイントを追加しない**。  
既存の `POST /game/play/stream` エンドポイントに `instruction_type=action` を渡すことで動作する。

---

## POST /game/play/stream

### リクエスト (変更なし)

既にフロントエンドから送信されているリクエストボディで完全に動作する。

```json
{
  "instruction": "カフェに行く",
  "instruction_type": "action",
  "costume_image": null,
  "session_id": "uuid-string",
  "base_history_id": "uuid-string-or-null",
  "prompt_override": null,
  "negative_prompt": null,
  "inpaint_strength": 0.85,
  "inpaint_noise": null,
  "character_references": null
}
```

| パラメータ         | 型      | 行動モードでの扱い                                                           |
| ------------------ | ------- | ---------------------------------------------------------------------------- |
| `instruction`      | string  | 行動内容 (例: "カフェに行く")                                                |
| `instruction_type` | string  | `"action"` 固定                                                              |
| `costume_image`    | string? | 不使用 (null)                                                                |
| `inpaint_strength` | float?  | 行動モード用デフォルト値 (0.85) を使用。フロントエンドからのオーバーライド可 |
| `inpaint_noise`    | float?  | 環境変数デフォルト (0.0) をそのまま使用                                      |

### レスポンス (SSE ストリーム)

行動モードでは以下のイベントを送信する (通常の変身と同様):

#### text イベント (変更なし)

```json
{ "type": "text", "data": { "chunk": "カフェの..." } }
```

行動時の心境モノローグをチャンク単位でストリーミング。

#### image イベント (新規追加 ← 行動モードで送信されるようになる)

```json
{
  "type": "image",
  "data": { "image": "base64-encoded-png", "history_id": "uuid" }
}
```

場面変更後の画像。人物の外見は変更なし、背景のみ新しい場面。

#### cost イベント (該当する場合のみ)

```json
{ "type": "cost", "data": { "cost_usd": 0.0035 } }
```

画像生成 + プロンプト生成のコスト合計。NovelAI Anlas ベースの場合は送信されない。

#### complete イベント (変更なし)

```json
{
  "type": "complete",
  "data": { "history_id": "uuid", "transformation_count": 3 }
}
```

`transformation_count` は行動前と同じ値 (インクリメントなし)。

#### 行動モードで送信しないイベント

| イベント      | 理由                                              |
| ------------- | ------------------------------------------------- |
| `stats`       | bloom/shame/adaptation パラメータを変更しないため |
| `critical`    | 臨界点判定をスキップするため                      |
| `ending`      | エンディング判定をスキップするため                |
| `achievement` | 実績判定をスキップするため                        |

---

## 内部コントラクト: プロンプトモジュール

### action_prompts.py — 新規追加関数

#### `get_action_image_edit_system_prompt(image_provider, nsfw_mode) -> str`

場面変更専用の画像編集システムプロンプトを返す。

| パラメータ       | 型   | 説明                    |
| ---------------- | ---- | ----------------------- |
| `image_provider` | str  | `"novelai"` or `"qwen"` |
| `nsfw_mode`      | bool | NSFW モード             |

**戻り値**: 場面変更に特化したシステムプロンプト文字列

#### `build_action_image_edit_prompt(instruction, current_description) -> str`

行動指示と現在の画像説明から、場面変更用のユーザープロンプトを構築する。

| パラメータ            | 型  | 説明                            |
| --------------------- | --- | ------------------------------- |
| `instruction`         | str | 行動指示 (例: "カフェに行く")   |
| `current_description` | str | Vision LLM による現在の画像説明 |

**戻り値**: 場面変更用ユーザープロンプト文字列

#### `get_action_novelai_prompt_generation_system(nsfw_mode, language) -> str`

GLM-4.6 による場面変更タグ生成の専用システムプロンプトを返す。

| パラメータ  | 型   | 説明                            |
| ----------- | ---- | ------------------------------- |
| `nsfw_mode` | bool | NSFW モード                     |
| `language`  | str  | 指示言語 (`"ja"`, `"en"`, etc.) |

**戻り値**: 場面変更用タグ生成システムプロンプト文字列

### game_service.py — 変更箇所

#### `stream_play()` の action mode セクション

**現在**: テキスト生成のみ → 早期 return  
**変更後**: テキスト + 画像を並列生成 → 履歴保存 → complete

変更の要点:

1. 早期 return を削除
2. NovelAI Opus / 非 NovelAI の分岐を追加
3. 場面変更専用プロンプトテンプレートを使用
4. 画像生成を通常パイプラインと同じ `_generate_image()` で実行
5. タグ分類・パラメータ更新・変身回数インクリメントは省略
6. 行動専用のデフォルト i2i_strength (0.85) を適用 (R-001 実測ベース)
