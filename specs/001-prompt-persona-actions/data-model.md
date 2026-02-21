# Data Model: プロンプトのパーソナリティ対応・行動機能・自分自身モード

**日付**: 2026-02-21  
**ブランチ**: `001-prompt-persona-actions`

## 既存エンティティの変更

### Session テーブル (変更)

| カラム | 型 | 制約 | 変更内容 |
|--------|-----|------|----------|
| self_mode | Boolean | NOT NULL, DEFAULT FALSE | **新規追加**: 自分自身モードフラグ |

### User テーブル (変更)

| カラム | 型 | 制約 | 変更内容 |
|--------|-----|------|----------|
| self_profile_json | Text | NULLABLE | **新規追加**: 自分自身プロフィール (JSON) |

### History テーブル (変更なし)

行動機能の結果は既存の History テーブルに保存可能。
- `instruction`: 行動指示テキスト
- `feeling_text`: 場面転換テキスト
- `image_path`: NULL（画像変更なしの場合）

### Conversation テーブル (変更なし)

行動の会話は既存の `instruction_type` カラムに `"action"` 値を追加するのみ。

---

## 新規エンティティ

### SelfProfile (論理エンティティ / JSON構造)

`User.self_profile_json` に格納される JSON 構造。新テーブルは作成しない。

```json
{
  "personality": "明るく元気。好奇心旺盛。",
  "reaction_style": "cheerful",
  "pronoun": "僕",
  "interests": ["アニメ", "女装"],
  "tsf_attitude": "TSFにワクワクする。変身を楽しみたい。",
  "raw_input": "アニメオタクの会社員。女装に興味あり。"
}
```

| フィールド | 型 | 説明 |
|------------|-----|------|
| personality | string | 性格を1-2文で要約 |
| reaction_style | enum string | `"bold"` \| `"gentle"` \| `"cheerful"` \| `"calm"` \| `"shy"` \| `"passionate"` \| `"default"` |
| pronoun | string | 一人称 (`"僕"`, `"私"`, `"俺"`, etc.) |
| interests | string[] | 興味・関心のキーワード |
| tsf_attitude | string | TSF/変身に対する態度を1文で |
| raw_input | string | 自動生成の元になった入力テキスト |

**バリデーションルール**:
- `personality`: 必須、最大 200 文字
- `reaction_style`: 必須、上記 enum 値のいずれか
- `pronoun`: 必須、最大 10 文字
- `interests`: 任意、最大 10 要素
- `tsf_attitude`: 任意、最大 200 文字
- `raw_input`: 任意、最大 1000 文字

---

## 拡張される列挙体

### InstructionType (拡張)

**現在**: `"dress_up"` | `"reality_alter"` | `"conversation"`  
**追加後**: `"dress_up"` | `"reality_alter"` | `"conversation"` | **`"action"`**

### PersonalityType (新規)

オープニングセリフの性格タイプ別グループ選択に使用。

値: `"default"` | `"bold"` | `"gentle"` | `"cheerful"` | `"shy"` | `"calm"` | `"passionate"`

---

## エンティティ関係図

```
User (1) ──── (N) Session
  │                  │
  │ self_profile     │ self_mode (bool)
  │ _json            │
  │                  ├── (N) History
  │                  │       └── instruction_type: "action" (新値)
  │                  │
  │                  ├── (1) SessionStats
  │                  │       (self_mode時はパラメータ更新スキップ)
  │                  │
  │                  └── (N) Conversation
  │                          └── instruction_type: "action" (新値)
  │
  └── Character
        ├── personality: str
        ├── description: str
        └── pronoun: str
            (心境テキスト・オープニングセリフに反映)
```

---

## マイグレーション計画

**マイグレーション番号**: `008_add_self_mode.py`

```sql
-- Session テーブル
ALTER TABLE sessions ADD COLUMN self_mode BOOLEAN NOT NULL DEFAULT 0;

-- User テーブル
ALTER TABLE users ADD COLUMN self_profile_json TEXT;
```

**ロールバック**:
```sql
ALTER TABLE sessions DROP COLUMN self_mode;
ALTER TABLE users DROP COLUMN self_profile_json;
```

---

## 状態遷移

### 行動指示の処理フロー

```
[ユーザー入力: instruction_type = "action"]
  │
  ├─ instruction_type が "action" → 行動フロー
  │   ├── 画像説明（Vision LLM: 現在の外見取得）
  │   ├── 行動用プロンプト生成（action_prompts.py）
  │   ├── テキストストリーミング生成
  │   ├── 会話履歴保存（instruction_type = "action"）
  │   ├── [画像生成スキップ]
  │   ├── [パラメータ計算スキップ]
  │   └── complete
  │
  └─ instruction_type が "dress_up" / "reality_alter" → 既存フロー
```

### 自分自身モードの処理分岐

```
[セッション: self_mode = True]
  │
  ├─ プロンプト生成: self_mode_prompts.py を使用
  │   └── SelfProfile を注入（心理段階は不使用）
  │
  ├─ 画像生成: 通常通り実行
  │
  ├─ パラメータ計算: スキップ（bloom/shame/adaptation 不変）
  │
  └─ 臨界点チェック: スキップ
```
