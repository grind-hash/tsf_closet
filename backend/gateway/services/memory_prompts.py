"""
Memory generation prompts

LLM prompts for analyzing multiple play summaries and extracting the
user's preferences/kinks as free-form memory text, and for building the
highest-priority instruction block injected into other prompts.
"""

from __future__ import annotations

MEMORY_SYSTEM_PROMPT_JA = """\
あなたはTSFゲーム（変身・着せ替えゲーム）のプレイ履歴分析者です。
複数のプレイセッションの称号・要約・タイムラインを受け取り、
このユーザーが好むシチュエーション、性的嗜好、繰り返し好んでいる展開パターンを
分析し、自由記述のテキストとして抽出してください。

出力ルール:
- 出力はプレーンテキストのみ（JSON化やMarkdown装飾は不要）
- 400文字以内を目安に、ユーザーが好む展開・シチュエーション・性的嗜好を具体的に記述する
- 複数セッションで繰り返し現れる傾向を優先して記述する
- 一回限りの偶発的な行動は除外し、傾向として安定しているものを優先する
- 断定口調で簡潔に書く（「〜を好む」「〜の展開を繰り返し選んでいる」等）
"""

MEMORY_SYSTEM_PROMPT_EN = """\
You are a play-history analyst for a TSF (transformation/dress-up) game.
Given the titles, summaries, and timelines of multiple play sessions,
analyze the situations, sexual preferences, and recurring patterns that
this user tends to favor, and extract them as free-form text.

Output rules:
- Output must be plain text only (no JSON, no Markdown formatting)
- Aim for around 400 characters or fewer, describing concrete preferences
  and situations the user favors
- Prioritize patterns that recur across multiple sessions
- Exclude one-off incidental actions; prioritize stable tendencies
- Write concisely in a declarative style
"""


def get_memory_generation_system_prompt(language: str = "ja") -> str:
    """Get the system prompt for memory generation, for the given language."""
    if language == "en":
        return MEMORY_SYSTEM_PROMPT_EN
    return MEMORY_SYSTEM_PROMPT_JA


def build_memory_generation_user_prompt(
    summaries: list[dict],
    language: str = "ja",
) -> str:
    """Build the user prompt for memory generation.

    Args:
        summaries: List of dicts with keys "title", "summary", "timeline"
        language: "ja" or "en"
    """
    if not summaries:
        return (
            "No play summaries recorded."
            if language != "ja"
            else "プレイ要約がありません。"
        )

    blocks = []
    for i, entry in enumerate(summaries, 1):
        title = entry.get("title", "")
        summary = entry.get("summary", "")
        timeline = entry.get("timeline") or []
        timeline_labels = ", ".join(
            str(item.get("label", "")) for item in timeline if isinstance(item, dict)
        )
        if language == "en":
            blocks.append(
                f"[Session {i}] Title: {title}\nSummary: {summary}\nTimeline: {timeline_labels}"
            )
        else:
            blocks.append(
                f"[セッション{i}] 称号: {title}\n要約: {summary}\nタイムライン: {timeline_labels}"
            )

    joined = "\n\n".join(blocks)

    if language == "en":
        return (
            "Analyze the following play summaries and extract the user's "
            f"preferences as described above:\n\n{joined}"
        )
    return f"以下のプレイ要約を分析し、ユーザーの好みを上記の指示に従って抽出してください:\n\n{joined}"


MEMORY_PRIORITY_INSTRUCTION_TEMPLATE_JA = """

【ユーザーの好み・性的嗜好メモリ（最優先指示）】
以下はユーザー自身が生成・編集した好みの情報です。
他のどの指示よりも優先して、この嗜好・傾向に沿うように解釈・生成してください。
{memory_text}
"""

MEMORY_PRIORITY_INSTRUCTION_TEMPLATE_EN = """

【User Preference/Kink Memory (HIGHEST PRIORITY)】
Below is preference information generated/edited by the user themselves.
Prioritize this above any other instruction when interpreting and generating content.
{memory_text}
"""


def build_memory_priority_instruction(memory_text: str, language: str = "ja") -> str:
    """Build the highest-priority instruction block to append to a system prompt.

    Args:
        memory_text: The user's saved memory text (preferences/kinks)
        language: "ja" or "en"

    Returns:
        A formatted block to append to a system prompt. Empty string if
        memory_text is empty/whitespace only.
    """
    if not memory_text or not memory_text.strip():
        return ""
    template = (
        MEMORY_PRIORITY_INSTRUCTION_TEMPLATE_EN
        if language == "en"
        else MEMORY_PRIORITY_INSTRUCTION_TEMPLATE_JA
    )
    return template.format(memory_text=memory_text.strip())
