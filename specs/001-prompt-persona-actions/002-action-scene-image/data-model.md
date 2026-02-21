# データモデル: 行動モード画像生成

**機能**: 002-action-scene-image  
**日付**: 2026-02-21

## 既存エンティティへの影響

### PersistedHistory (変更なし)

行動で生成された画像は既存の `PersistedHistory` テーブルにそのまま保存する。  
新しいカラムは不要。

| フィールド           | 型       | 行動モードでの値                         |
| -------------------- | -------- | ---------------------------------------- |
| `id`                 | UUID     | 新規生成                                 |
| `session_id`         | str      | 現在のセッションID                       |
| `instruction`        | str      | 行動指示テキスト (例: "カフェに行く")    |
| `image_path`         | str      | 生成された場面画像のファイルパス         |
| `feeling_text`       | str      | 行動時の心境モノローグ                   |
| `before_description` | str      | 行動前の画像説明                         |
| `after_description`  | str      | 行動後の画像説明 (背景変更後のタグ/記述) |
| `created_at`         | datetime | 作成日時                                 |

**注記**: 通常の変身履歴と同じ構造。`instruction` の内容で「変身」か「行動」かを判別可能。

### PersistedSession (変更なし)

- `transformation_count`: 行動時には**インクリメントしない**
- `current_image_path`: 行動で生成された画像パスに**更新する** (次回の行動/変身のベースになる)

### TransformationTag (行動時は作成しない)

行動は外見変更を伴わないため、`save_transformation_tag()` は呼び出さない。

### SessionStats (行動時は変更しない)

- `bloom`, `shame`, `adaptation` パラメータは行動時に変更しない
- `update_session_stats()` は呼び出さない

---

## 新規エンティティ

### なし

DBスキーマの変更は不要。既存のテーブル構造で行動画像を完全に表現可能。

---

## プロンプトテンプレート (新規追加)

### 場面変更用画像編集プロンプト

**ファイル**: `backend/gateway/services/action_prompts.py` に追加

| テンプレート                                   | 用途                                               | プロバイダー   |
| ---------------------------------------------- | -------------------------------------------------- | -------------- |
| `ACTION_IMAGE_EDIT_SYSTEM_PROMPT`              | 場面変更専用の画像編集システムプロンプト           | Qwen (ComfyUI) |
| `ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI`      | NovelAI タグ形式の場面変更プロンプト               | NovelAI        |
| `ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI_NSFW` | NovelAI NSFW タグ形式                              | NovelAI        |
| `ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NSFW`         | NSFW 場面変更プロンプト                            | Qwen (ComfyUI) |
| `ACTION_NOVELAI_PROMPT_GENERATION_SYSTEM`      | GLM-4.6 用: 場面変更タグ生成専用システムプロンプト | NovelAI GLM    |
| `ACTION_NOVELAI_PROMPT_GENERATION_SYSTEM_NSFW` | GLM-4.6 用 NSFW版                                  | NovelAI GLM    |

### テンプレート設計原則

1. キャラクター外見保持の明示的指示を含む
2. 変更対象は背景・場所・環境・照明のみと制約
3. NovelAI: キャラクタータグは `{}` で強調維持
4. Qwen: "Keep the person exactly as they are" を必ず含む

---

## 状態遷移

```
[行動指示受信]
    │
    ├─ NovelAI Opus? ──Yes──> previous_prompt 取得
    │                          │
    │                          ├─ GLM-4.6 で場面変更タグ生成
    │                          │  (キャラクタータグ維持 + 背景タグ変更)
    │                          │
    │                          └─> img2img (低 strength) で画像生成
    │
    └─ No (ComfyUI等) ──> Vision LLM で現在画像分析
                           │
                           ├─ 場面変更用編集プロンプト生成
                           │  (人物記述維持 + 背景指示)
                           │
                           └─> Qwen Image Edit で画像生成

[両パスとも並行してテキスト生成 (心境モノローグ)]

[完了]
    ├─ 履歴保存 (画像 + テキスト)
    ├─ 変身回数: 変更なし
    ├─ パラメータ: 変更なし
    ├─ タグ分類: なし
    └─ SSE: text + image + complete イベント送信
```
