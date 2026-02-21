# API Contracts: Game Endpoints (変更・追加分)

**日付**: 2026-02-21  
**ブランチ**: `001-prompt-persona-actions`

## 変更されるエンドポイント

### POST /api/game/play/stream (変更)

既存のSSEストリーミングエンドポイント。`instruction_type: "action"` の受付を追加。

#### Request Body (変更箇所のみ)

```json
{
  "instruction_type": "dress_up | reality_alter | conversation | action",
  "instruction": "コンビニに行く",
  "session_id": "uuid-string",
  "...": "既存フィールドは変更なし"
}
```

| フィールド         | 変更       | 説明                  |
| ------------------ | ---------- | --------------------- |
| `instruction_type` | **値追加** | `"action"` を新規追加 |

#### SSE Response (instruction_type = "action" の場合)

行動指示の場合、以下のイベントのみ送信:

```
event: status
data: {"message": "場面転換テキストを生成中..."}

event: text
data: {"chunk": "メイド服のまま、コンビニの自動ドアをくぐった瞬間..."}

event: text
data: {"chunk": "（テキストチャンク続き）"}

event: complete
data: {"session_id": "uuid", "transformation_count": 3}
```

**送信されないイベント**: `image`, `stats`, `tags`, `critical`, `ending`, `achievement`, `cost`

---

### POST /api/game/start (変更)

セッション開始時に自分自身モードを指定可能に。

#### Request Body (変更箇所のみ)

```json
{
  "character_id": "char1",
  "difficulty": "normal",
  "nsfw_mode": 0,
  "self_mode": false
}
```

| フィールド  | 型      | 必須 | デフォルト | 説明                                    |
| ----------- | ------- | ---- | ---------- | --------------------------------------- |
| `self_mode` | boolean | No   | `false`    | **新規追加**: 自分自身モードの有効/無効 |

#### Response (変更箇所のみ)

```json
{
  "session_id": "uuid",
  "character_id": "char1",
  "current_image_url": "/history/...",
  "transformation_count": 0,
  "stats": { "...": "既存" },
  "self_mode": false
}
```

---

### GET /api/game/session/{session_id} (変更)

レスポンスに `self_mode` を追加。

#### Response (追加フィールド)

```json
{
  "...": "既存フィールド",
  "self_mode": false
}
```

---

## 新規エンドポイント

### POST /api/settings/self-profile/generate

入力テキストからLLMで性格プロフィールを自動生成する。

#### Request Body

```json
{
  "input_text": "アニメオタクの会社員。女装に興味あり。"
}
```

| フィールド   | 型     | 必須 | 制約       | 説明                               |
| ------------ | ------ | ---- | ---------- | ---------------------------------- |
| `input_text` | string | Yes  | 1-1000文字 | 性格生成の元になる自由入力テキスト |

#### Response (200 OK)

```json
{
  "profile": {
    "personality": "好奇心旺盛で明るい性格。新しい体験にオープン。",
    "reaction_style": "cheerful",
    "pronoun": "僕",
    "interests": ["アニメ", "女装", "コスプレ"],
    "tsf_attitude": "TSFにワクワクする。変身を楽しみたい。",
    "raw_input": "アニメオタクの会社員。女装に興味あり。"
  }
}
```

#### Error Responses

| Code | 条件                              | Body                                                        |
| ---- | --------------------------------- | ----------------------------------------------------------- |
| 400  | `input_text` が空または1000文字超 | `{"detail": "入力テキストは1〜1000文字で入力してください"}` |
| 500  | LLM 生成失敗                      | `{"detail": "性格プロフィールの生成に失敗しました"}`        |

---

### PUT /api/settings/self-profile

自分自身プロフィールを保存（手動編集後の保存を含む）。

#### Request Body

```json
{
  "profile": {
    "personality": "好奇心旺盛で明るい性格。新しい体験にオープン。",
    "reaction_style": "cheerful",
    "pronoun": "僕",
    "interests": ["アニメ", "女装", "コスプレ"],
    "tsf_attitude": "TSFにワクワクする。変身を楽しみたい。",
    "raw_input": "アニメオタクの会社員。女装に興味あり。"
  }
}
```

#### Response (200 OK)

```json
{
  "message": "プロフィールを保存しました",
  "profile": { "...": "保存されたプロフィール" }
}
```

#### Validation

| フィールド       | ルール                                                                    |
| ---------------- | ------------------------------------------------------------------------- |
| `personality`    | 必須、1-200文字                                                           |
| `reaction_style` | 必須、`bold\|gentle\|cheerful\|calm\|shy\|passionate\|default` のいずれか |
| `pronoun`        | 必須、1-10文字                                                            |
| `interests`      | 任意、最大10要素、各要素50文字以下                                        |
| `tsf_attitude`   | 任意、最大200文字                                                         |
| `raw_input`      | 任意、最大1000文字。自動生成時にサーバー側で付与                          |

---

### GET /api/settings/self-profile

保存済みの自分自身プロフィールを取得。

#### Response (200 OK)

```json
{
  "profile": {
    "personality": "...",
    "reaction_style": "cheerful",
    "pronoun": "僕",
    "interests": ["..."],
    "tsf_attitude": "..."
  }
}
```

プロフィール未設定の場合:

```json
{
  "profile": null
}
```
