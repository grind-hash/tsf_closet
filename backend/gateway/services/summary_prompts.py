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
