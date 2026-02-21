# API Contracts: Prompt Module (内部インターフェース)

**日付**: 2026-02-21  
**ブランチ**: `001-prompt-persona-actions`

> 以下はバックエンドの内部モジュール間インターフェースであり、HTTP APIではない。

## prompts.py の変更

### build_enhanced_feeling_prompt() (シグネチャ変更)

```python
def build_enhanced_feeling_prompt(
    before_desc: str,
    after_desc: str,
    instruction: str,
    bloom: int = 0,
    pronoun: str = "僕",
    attributes: list[str] | None = None,
    nsfw_mode: bool = False,
    transformation_count: int = 0,
    # --- 新規引数 ---
    personality: str = "",
    description: str = "",
    used_openings: list[str] | None = None,
) -> tuple[str, str]:
    """強化版心境生成用プロンプトを構築

    self_mode の場合は game_service.py が直接 build_self_mode_feeling_prompt() を
    呼び出すため、この関数には self_mode/self_profile 引数を含めない。

    新規引数:
        personality: キャラクターの性格特性
        description: キャラクターの説明
        used_openings: 最近使用済みのオープニングセリフ（重複回避用）

    Returns:
        (システムプロンプト, ユーザープロンプト) のタプル
    """
```

### get_critical_speech() (シグネチャ変更)

```python
def get_critical_speech(threshold: int, pronoun: str = "僕") -> str:
    """臨界点用の特別セリフをランダムに取得

    Args:
        threshold: 臨界点の閾値 (25, 50, 75, 100)
        pronoun: キャラクターの一人称

    Returns:
        一人称が適用された特別セリフ
    """
```

### 新規関数: classify_personality_type()

```python
def classify_personality_type(personality: str, description: str = "") -> str:
    """性格文字列からオープニングセリフの性格タイプを判定

    Args:
        personality: キャラクターの性格文字列
        description: キャラクターの説明文字列

    Returns:
        性格タイプ: "bold" | "gentle" | "cheerful" | "shy" | "calm" | "passionate" | "default"
    """
```

### 新規関数: select_opening()

```python
def select_opening(
    openings: dict[str, list[str]],
    personality_type: str = "default",
    pronoun: str = "僕",
    used_openings: list[str] | None = None,
) -> str:
    """性格タイプと使用履歴を考慮してオープニングセリフを選択

    Args:
        openings: 性格タイプ別オープニング辞書
        personality_type: 判定された性格タイプ
        pronoun: 一人称（テンプレート置換用）
        used_openings: 最近使用されたセリフリスト

    Returns:
        選択されたオープニングセリフ文字列
    """
```

---

## 新規モジュール: action_prompts.py

### build_action_prompt()

```python
def build_action_prompt(
    action_instruction: str,
    current_appearance: str,
    bloom: int = 0,
    pronoun: str = "僕",
    personality: str = "",
    description: str = "",
    nsfw_mode: bool = False,
    recent_actions: list[str] | None = None,
    self_mode: bool = False,
    self_profile: dict | None = None,
) -> tuple[str, str]:
    """行動機能用のプロンプトを構築

    生成されるプロンプトは 300-500 文字の場面転換テキストを想定する。

    Args:
        action_instruction: ユーザーの行動指示
        current_appearance: 現在のキャラクター外見説明
        bloom: 開花度
        pronoun: 一人称
        personality: キャラクター性格
        description: キャラクター説明
        nsfw_mode: NSFWモード
        recent_actions: 直近の行動履歴
        self_mode: 自分自身モード
        self_profile: 自分自身プロフィール

    Returns:
        (システムプロンプト, ユーザープロンプト) のタプル
    """
```

---

## 新規モジュール: self_mode_prompts.py

### build_self_mode_feeling_prompt()

```python
def build_self_mode_feeling_prompt(
    before_desc: str,
    after_desc: str,
    instruction: str,
    self_profile: dict,
    nsfw_mode: bool = False,
) -> tuple[str, str]:
    """自分自身モード用の心境プロンプトを構築

    心理段階やパラメータに依存せず、self_profileの性格情報のみでプロンプトを生成する。

    Args:
        before_desc: 変身前の外見説明
        after_desc: 変身後の外見説明
        instruction: ユーザーの変身指示
        self_profile: 自分自身プロフィール辞書
        nsfw_mode: NSFWモード

    Returns:
        (システムプロンプト, ユーザープロンプト) のタプル
    """
```

### build_self_profile_generation_prompt()

```python
def build_self_profile_generation_prompt(input_text: str) -> tuple[str, str]:
    """入力テキストから性格プロフィール生成用のプロンプトを構築

    Args:
        input_text: ユーザーの自由入力テキスト

    Returns:
        (システムプロンプト, ユーザープロンプト) のタプル
    """
```

---

## game_service.py の変更

### play_with_stream() 内の分岐追加

```python
# 行動フロー（instruction_type == "action"の場合）
if instruction_type == "action":
    # 1. 画像説明取得（現在の外見情報として）
    # 2. Conversation から直近の action 履歴を抽出し recent_actions に渡す
    # 3. 行動用プロンプト生成
    # 4. テキストストリーミング生成のみ
    # 5. 会話履歴保存
    # 6. 画像生成・パラメータ計算・タグ分類スキップ
    # 7. complete イベント送信

# 自分自身モード分岐（self_mode == True の場合）
if session.self_mode:
    # build_enhanced_feeling_prompt() の代わりに
    # build_self_mode_feeling_prompt() を直接呼び出す
    # self_profile が null の場合は通常プロンプトにフォールバック
    # パラメータ計算をスキップ
    # 臨界点チェックをスキップ
    # self_mode_prompts.py のプロンプトを使用
```
