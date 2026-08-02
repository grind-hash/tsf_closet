"""
Summary generation prompts

LLM prompts for generating play session summaries and titles.
"""

from __future__ import annotations

SUMMARY_SYSTEM_PROMPT_JA = """\
あなたはTSFゲーム（変身・着せ替えゲーム）のプレイ日記を書くライターです。
プレイヤーの一連の行動履歴を受け取り、以下のJSON形式で要約を作成してください。

出力形式（JSONのみ、他のテキスト不可）:
{
  "title": "称号（10文字以内の二つ名）",
  "summary": "プレイの要約（200文字以内）",
  "timeline": [
    {"label": "行動の要約（15文字以内）", "type": "dress_up|reality_alter|action|conversation"}
  ]
}

ルール:
- titleはプレイの全体像を象徴する称号・二つ名にすること
- summaryはプレイの流れを簡潔に要約すること
- timelineは各行動を短くラベル付けしたリスト（最大20件）
- typeは元の行動タイプをそのまま使うこと
- JSON以外のテキストを出力しないこと
"""

SUMMARY_SYSTEM_PROMPT_EN = """\
You are a writer creating play diary entries for a TSF (transformation/dress-up) game.
Given a player's action history, create a summary in the following JSON format.

Output format (JSON only, no other text):
{
  "title": "A title/epithet (max 5 words)",
  "summary": "Play summary (max 200 characters)",
  "timeline": [
    {"label": "Action summary (max 8 words)", "type": "dress_up|reality_alter|action|conversation"}
  ]
}

Rules:
- title should be an epithet that symbolizes the overall play
- summary should concisely describe the play flow
- timeline is a short-labeled list of each action (max 20 entries)
- type should use the original action type as-is
- Do not output anything other than JSON
"""


def build_summary_user_prompt(
    timeline: list[tuple[str, str]],
    language: str = "ja",
) -> str:
    """Build the user prompt for summary generation.

    Args:
        timeline: List of (instruction_type, instruction_text) tuples
        language: "ja" or "en"
    """
    if not timeline:
        return "No actions recorded."

    lines = []
    for i, (itype, text) in enumerate(timeline, 1):
        lines.append(f"{i}. [{itype}] {text}")

    action_list = "\n".join(lines)

    if language == "ja":
        return f"以下のプレイ履歴を要約してください:\n\n{action_list}"
    else:
        return f"Please summarize the following play history:\n\n{action_list}"


def get_summary_system_prompt(language: str = "ja") -> str:
    """Get the system prompt for the given language."""
    if language == "en":
        return SUMMARY_SYSTEM_PROMPT_EN
    return SUMMARY_SYSTEM_PROMPT_JA


# ---------------------------------------------------------------------------
# Branch-session situation summary (not PlaySummary diary format)
# ---------------------------------------------------------------------------

BRANCH_SITUATION_SYSTEM_PROMPT_JA = """\
あなたはTSFゲーム（変身・着せ替えゲーム）の状況を引き継ぐためのライターです。
プレイヤーが途中の画像状態から新規セッションを開始するため、分岐点までの経緯を状況要約してください。

出力ルール:
- 状況要約のみを出力する（JSON・見出し・前置き・箇条書き記号は不要）
- 200文字以内、1〜3文程度
- 含める: ここまでの経緯、場所・状況、心理状態、重要な関係性
- 含めない: 外見や服装の詳細タグ列挙（別途管理）、開花度などの数値、分岐点より後の出来事の捏造
- 新規プレイの「初期状態」文として自然に読める文体にする
"""

BRANCH_SITUATION_SYSTEM_PROMPT_EN = """\
You write situation handoff text for a TSF (transformation/dress-up) game.
The player will start a new session from a mid-play image, so summarize the situation up to the branch point.

Output rules:
- Output only the situation summary (no JSON, headings, preamble, or bullet markers)
- Max about 200 characters, 1-3 sentences
- Include: what led here, location/situation, mindset, important relationships
- Exclude: detailed appearance/clothing tag lists (managed separately), numeric stats, events after the branch point
- Write it so it can replace an "initial state" blurb for a new session
"""


def get_branch_situation_system_prompt(language: str = "ja") -> str:
    if language == "en":
        return BRANCH_SITUATION_SYSTEM_PROMPT_EN
    return BRANCH_SITUATION_SYSTEM_PROMPT_JA


def build_branch_situation_user_prompt(
    timeline: list[tuple[str, str]],
    appearance_description: str | None = None,
    language: str = "ja",
) -> str:
    """Build user prompt for branch-point situation summary."""
    if timeline:
        lines = [
            f"{i}. [{itype}] {text}" for i, (itype, text) in enumerate(timeline, 1)
        ]
        action_list = "\n".join(lines)
    else:
        action_list = (
            "(no actions recorded)" if language == "en" else "（行動履歴なし）"
        )

    appearance = (appearance_description or "").strip()
    if language == "en":
        parts = [
            "Summarize the situation up to this branch point for continuing play.",
            "",
            f"Play history:\n{action_list}",
        ]
        if appearance:
            parts.extend(
                ["", f"Appearance / scene description at branch point:\n{appearance}"]
            )
        return "\n".join(parts)

    parts = [
        "以下は分岐点までのプレイ履歴です。新規セッション開始用の状況要約を作成してください。",
        "",
        f"プレイ履歴:\n{action_list}",
    ]
    if appearance:
        parts.extend(["", f"分岐点の外見・場面説明:\n{appearance}"])
    return "\n".join(parts)
