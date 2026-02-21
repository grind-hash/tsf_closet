# Research: プロンプトのパーソナリティ対応・行動機能・自分自身モード

**日付**: 2026-02-21  
**ブランチ**: `001-prompt-persona-actions`

## 研究課題と結論

### R-001: 一人称(pronoun)のテンプレート化アプローチ

**課題**: prompts.py 内にハードコードされた「僕」を pronoun 引数で動的に置換する方法

**調査結果**:

ハードコード箇所は合計6箇所:

- `FIRST_TRANSFORMATION_STAGE.openings`: 2箇所 (index 0, 1)
- `CRITICAL_POINT_SPEECHES[75]`: 2箇所 (index 1, 3)
- `CRITICAL_POINT_SPEECHES[100]`: 2箇所 (index 1, 2)

なお、`PSYCHOLOGICAL_STAGES`（通常・NSFW）の openings には「僕」は含まれていない。
関数デフォルト引数 (`pronoun: str = "僕"`) は呼び出し側で正しく上書きされている。

**決定**: Python の `.format()` メソッドによる遅延展開を採用

- openings を `"えっ？何これ...{pronoun}の体が..."` のようなテンプレート文字列に変更
- 選択後に `.format(pronoun=pronoun)` で展開
- CRITICAL_POINT_SPEECHES も同様にテンプレート化し、`get_critical_speech()` に `pronoun` 引数を追加

**根拠**: 既存の `FEELING_USER_PROMPT_TEMPLATE` が同じ `.format()` パターンを使用しており、コードベース内の一貫性が保たれる

**代替案**: f-string（不可: 定数定義時に展開される）、jinja2（過剰: 単純な文字列置換に外部ライブラリは不要）

---

### R-002: 性格(personality)のプロンプト注入パターン

**課題**: LLM プロンプトにキャラクター性格情報をどのように注入するか

**調査結果**:

現在の `build_enhanced_feeling_prompt()` は `attributes` パラメータ（`list[str]`）を受け取り、ユーザープロンプト末尾に「キャラクターの特殊属性」セクションとして追加している。

性格情報はこれとは異なり、LLM の語調・反応スタイル全体を制御する必要があるため、**システムプロンプト**に注入するのが適切。

**決定**: システムプロンプトの末尾に性格セクションを動的に追加

```
【このキャラクターの性格】
- 性格: {personality}
- 説明: {description}
- このキャラクターの性格特性に合わせて、語調・反応・思考パターンを調整してください。
```

**根拠**:

- システムプロンプトへの注入は、LLM が全体的な語調を調整するのに最も効果的
- 既存の `attributes` セクション（ユーザープロンプト末尾）は「追加情報」として機能し、性格とは役割が異なる
- `build_enhanced_feeling_prompt()` に `personality` と `description` の引数を追加する

**代替案**: ユーザープロンプトに注入（非採用: 語調制御はシステムプロンプトの方が効果的）

---

### R-003: オープニングセリフのバリエーション設計

**課題**: 現在各ステージ4-5個のセリフを10個以上に拡充し、性格タイプ別にグループ化する方法

**調査結果**:

現状の構造:

```python
"openings": ["セリフ1", "セリフ2", ...]  # flat list, random.choice()
```

**決定**: openings を性格タイプ別辞書 + 汎用リストの2層構造に変更

```python
"openings": {
    "default": ["汎用セリフ1", "汎用セリフ2", ...],  # 10個以上
    "bold": ["強気セリフ1", "強気セリフ2", ...],      # 5個以上
    "gentle": ["おっとりセリフ1", ...],                # 5個以上
    "cheerful": ["明るいセリフ1", ...],                # 5個以上
}
```

選択ロジック:

1. キャラクターの personality からタイプをヒューリスティックに判定（キーワードマッチ）
2. 該当タイプのリスト + default リストを結合
3. 最近使用されたセリフ（セッション内の直近N件の履歴から抽出）を除外
4. 残りからランダム選択

**根拠**: 既存の openings 構造を完全に置き換えるのではなく、default を後方互換として残しつつ拡張できる。性格タイプの判定は LLM 呼び出しなしでキーワードマッチで十分（LLM 呼び出しのレイテンシを避ける）

**代替案**: LLM にセリフを都度生成させる（非採用: レイテンシ増加、品質のばらつき）

---

### R-004: 行動機能の SSE イベント設計

**課題**: 変身を伴わない「行動」指示を既存の SSE ストリーミングパイプラインにどう統合するか

**調査結果**:

既存の SSE イベント型: `text | image | stats | tags | critical | ending | achievement | cost | complete | error | status`

行動機能では:

- テキスト生成は必要（場面転換テキスト）
- 画像生成は不要（衣装変更なし）
- パラメータ計算はスキップ可能（行動は開花度に影響しない想定）
- タグ分類は不要（衣装変更なし）

**決定**: 既存の `play_with_stream()` 内に `instruction_type == "action"` 分岐を追加

新しいフローの概要:

1. セッション取得（通常と同じ）
2. 現在の画像を Vision LLM で説明取得（キャラクターの現在の外見情報として使用）
3. 行動用プロンプト生成（新しい `action_prompts.py` に定義）
4. テキストストリーミング生成 → SSE `text` イベント
5. 会話履歴に保存 (`instruction_type = "action"`)
6. **`image` イベントは送信しない**
7. **`stats`, `tags`, `critical` 処理はスキップ**
8. `complete` イベントを送信

instruction_type の追加:

- フロントエンド: `InstructionType = "dress_up" | "reality_alter" | "conversation" | "action"`
- バックエンド: PlayStreamRequest の instruction_type に "action" を追加
- `INSTRUCTION_TYPE_LABELS` に `action: "行動"` を追加

**根拠**: 既存の SSE インフラをそのまま再利用できる。パイプラインの画像生成・パラメータ計算部分をスキップするだけで実装できるため、新しいエンドポイントは不要。

**代替案**: 新しい `/api/game/action` エンドポイント（非採用: SSE インフラの重複になる）

---

### R-005: 行動機能のプロンプト設計

**課題**: 行動用のシステムプロンプト・ユーザープロンプトをどのように設計するか

**決定**: `action_prompts.py` を新規作成し、以下のプロンプト構造を定義

システムプロンプト（開花度別の4段階 + NSFW 版）:

- 心理段階に応じた周囲への反応パターン
- 場面転換テキストとしての構成（場所描写→キャラクターの心理→周囲の反応）

ユーザープロンプト:

- 行動指示内容
- キャラクターの現在の外見/衣装（Vision LLM 出力を利用）
- キャラクターの性格情報
- これまでの行動履歴（直近N件）
- 生成する文字数: 300〜500字

**根拠**: `reality_prompts.py` と同じパターンに倣い、ステージ別プロンプト + NSFW 版の2セットを提供する

---

### R-006: 自分自身モードのデータモデル

**課題**: 自分自身モードの有効/無効とプロフィール情報をどこに保存するか

**調査結果**:

現在のセッション関連テーブル:

- `Session`: `user_id`, `character_id`, `current_image_path`, `transformation_count`, `is_active`
- `SessionStats`: `bloom`, `shame`, `adaptation`, `difficulty`, `nsfw_mode`
- `User`: `nsfw_mode`, `difficulty`, `language`

**決定**: Session テーブルに `self_mode` (bool) カラムを追加。自分自身プロフィールは `User` テーブルに `self_profile_json` (JSON text) カラムとして保存。

```
# Session テーブル追加
self_mode: Boolean, default=False

# User テーブル追加
self_profile_json: Text, nullable=True
  → JSON: { "personality": "...", "reaction_style": "...", "pronoun": "..." }
```

マイグレーション: `008_add_self_mode.py`

**根拠**:

- `self_mode` はセッション単位のフラグ（同一ユーザーが通常モードと自分自身モードを使い分ける）
- プロフィールはユーザー単位で保存（セッションが変わっても流用可能）
- JSON 形式で保存することで、スキーマ変更なしにフィールドを柔軟に追加できる

**代替案**: 新テーブル `self_profiles` を作成（非採用: 1ユーザー1プロフィールの現時点の要件にはオーバースペック）

---

### R-007: 自分自身モードのプロンプト設計

**課題**: パラメータ計算をスキップし、性格ベースの反応を生成するプロンプト

**決定**: `self_mode_prompts.py` を新規作成

システムプロンプト:

```
あなたは物語の主人公の心の声を書く作家です。
これは「自分自身」モードです。主人公は実在の人物の性格を反映しています。

【主人公の性格プロフィール】
{self_profile}

重要な指示:
- キャラクター的な「驚き」「葛藤」「堕落」の定型パターンは使わないでください
- 性格プロフィールに基づいた、自然で素直な反応を書いてください
- 性格がポジティブなら前向きに、慎重なら控えめに反応してください
```

**根拠**: 既存の心理段階プロンプト (`PSYCHOLOGICAL_STAGES`) をバイパスし、性格情報のみで制御する。`build_enhanced_feeling_prompt()` で `self_mode=True` の場合に分岐させる。

---

### R-008: 性格自動生成プロンプト設計

**課題**: 入力テキストから性格プロフィールをワンクリックで生成する LLM プロンプト

**決定**: 既存の LLM サービス (`llm_service.generate_text()`) を使い、以下のプロンプトで生成

システムプロンプト:

```
あなたは性格分析の専門家です。ユーザーの自己紹介テキストから、
ゲーム内で使用する性格プロフィールを生成してください。

出力形式（JSON）:
{
  "personality": "性格を1-2文で要約",
  "reaction_style": "bold|gentle|cheerful|calm|shy|passionate",
  "pronoun": "一人称（僕/私/俺/わたし/あたし等）",
  "interests": ["興味・関心のキーワード"],
  "tsf_attitude": "TSFに対する態度を1文で"
}
```

**根拠**: 構造化された JSON 出力を LLM に指示することで、確実にパース可能な結果を得られる。reaction_style はオープニングセリフの選択にも利用可能。

---

### R-009: セリフ重複回避メカニズム

**課題**: 同一セッション内でオープニングセリフの重複を避ける方法

**決定**: メモリ内の軽量キャッシュ方式

- `build_enhanced_feeling_prompt()` に `used_openings: list[str] | None` パラメータを追加
- 呼び出し側 (`game_service._generate_feeling_stream`) がセッション内の直近の History から `feeling_text` の冒頭文字列を抽出し、`used_openings` として渡す
- セリフプールから `used_openings` に含まれるものを除外してランダム選択
- すべて使用済みの場合は全プールにリセット

**根拠**: DB に使用済みセリフ専用カラムを追加するのはオーバースペック。直近の feeling_text から冒頭を抽出すれば十分な精度が得られる。

**代替案**: DB に `used_openings` JSON カラムを追加（非採用: 過剰設計、メモリ内で十分）

---

### R-010: 性格タイプのヒューリスティック判定

**課題**: personality 文字列からオープニングセリフの性格タイプをどう判定するか

**決定**: キーワードマッチングによるルールベース判定

```python
PERSONALITY_TYPE_KEYWORDS = {
    "bold": ["気が強い", "強気", "勝ち気", "ツンデレ", "反抗的", "攻撃的"],
    "gentle": ["おっとり", "穏やか", "優しい", "温厚", "おとなしい", "控えめ"],
    "cheerful": ["明るい", "元気", "活発", "陽気", "楽天的", "テンション高い"],
    "shy": ["恥ずかしがり", "内気", "臆病", "人見知り", "引っ込み思案"],
    "calm": ["冗静", "クール", "落ち着いた", "理知的", "淡々とした", "クールビューティー"],
    "passionate": ["情熱的", "熱い", "一生懸命", "全力", "アツい", "燃える"],
}
```

判定フロー:

1. キャラクターの `personality` と `description` を結合
2. 各タイプのキーワードとマッチ
3. マッチ数が最も多いタイプを選択
4. マッチなしなら `"default"` にフォールバック

**根拠**: LLM 呼び出しなしで即座に判定可能。プロンプト生成のレイテンシに影響しない。

**代替案**: LLM で判定（非採用: 毎回の追加 API コールによるレイテンシ増加）

---

## 技術スタック確認

| 項目                         | 確認状態                                                    |
| ---------------------------- | ----------------------------------------------------------- |
| Python 3.12+ / FastAPI       | 既存バージョンで対応可能                                    |
| SQLAlchemy async + Alembic   | 既存パターンでマイグレーション対応                          |
| SSE (sse-starlette)          | 既存パターンで行動イベント対応                              |
| React 19 + TypeScript strict | 既存パターンで UI 対応                                      |
| Playwright E2E               | 既存設定で新機能テスト対応                                  |
| LLM (openai client)          | 既存の generate_text/generate_feeling_stream をそのまま利用 |
