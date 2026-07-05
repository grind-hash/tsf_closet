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
- 300文字から400文字以内を目安に、ユーザーが好む展開・シチュエーション・性的嗜好を具体的に記述する
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


# 1チャンクあたりのユーザープロンプトの目安文字数上限。
# NovelAI等のLLM APIはリクエストサイズ上限があり、セッション数が多いと
# ユーザープロンプトが数万文字に肥大化して400エラーになるため、
# 安全側に寄せた保守的な値を設定する。
MEMORY_CHUNK_CHAR_BUDGET = 6000


def _estimate_entry_length(entry: dict) -> int:
    """1セッション分の要約エントリがプロンプト中で占めるおおよその文字数を見積もる。"""
    title = entry.get("title", "") or ""
    summary = entry.get("summary", "") or ""
    timeline = entry.get("timeline") or []
    timeline_len = sum(
        len(str(item.get("label", ""))) for item in timeline if isinstance(item, dict)
    )
    # 見出しや改行等の定型文分の余裕
    return len(title) + len(summary) + timeline_len + 32


def chunk_summaries(
    summaries: list[dict],
    char_budget: int = MEMORY_CHUNK_CHAR_BUDGET,
) -> list[list[dict]]:
    """要約リストを、1リクエストあたりの文字数がchar_budgetを超えないように分割する。

    Args:
        summaries: PlaySummary辞書のリスト
        char_budget: 1チャンクあたりの目安文字数上限

    Returns:
        分割された要約リストのリスト（各要素が1回のLLM呼び出し分）
    """
    if not summaries:
        return []

    chunks: list[list[dict]] = []
    current: list[dict] = []
    current_len = 0

    for entry in summaries:
        entry_len = _estimate_entry_length(entry)
        if current and current_len + entry_len > char_budget:
            chunks.append(current)
            current = []
            current_len = 0
        current.append(entry)
        current_len += entry_len

    if current:
        chunks.append(current)

    return chunks


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


# =============================================================================
# 部分分析結果の統合（マージ）用プロンプト
# 要約件数が多く chunk_summaries で複数チャンクに分割された場合、
# 各チャンクの分析結果（部分テキスト）をさらに1つに統合する際に使用する。
# =============================================================================

MEMORY_MERGE_SYSTEM_PROMPT_JA = """\
あなたはTSFゲームのプレイ傾向分析結果を統合する編集者です。
同一ユーザーの異なるセッション群からそれぞれ抽出された複数の部分的な分析結果を受け取り、
重複を除きながら一つの一貫したテキストに統合してください。

出力ルール:
- 出力はプレーンテキストのみ（JSON化やMarkdown装飾は不要）
- 300文字から400文字以内を目安に、複数の分析結果に共通する、あるいは特に顒著な傾向を優先してまとめる
- 一部の分析結果にしか現れない些末な要素は省略してよい
- 断定口調で簡潔に書く
"""

MEMORY_MERGE_SYSTEM_PROMPT_EN = """\
You are an editor consolidating multiple partial play-tendency analyses
of the same user (each extracted from a different group of sessions) into
a single coherent text.

Output rules:
- Output must be plain text only (no JSON, no Markdown formatting)
- Aim for around 400 characters or fewer, prioritizing tendencies that are
  common across multiple analyses or especially prominent
- Minor details that appear in only one analysis may be omitted
- Write concisely in a declarative style
"""


def get_memory_merge_system_prompt(language: str = "ja") -> str:
    """Get the system prompt used to merge partial memory analyses."""
    if language == "en":
        return MEMORY_MERGE_SYSTEM_PROMPT_EN
    return MEMORY_MERGE_SYSTEM_PROMPT_JA


def build_memory_merge_user_prompt(
    partial_texts: list[str],
    language: str = "ja",
) -> str:
    """Build the user prompt that merges several partial memory analyses.

    Args:
        partial_texts: List of partial memory texts (one per chunk)
        language: "ja" or "en"
    """
    blocks = [f"[{i}]\n{text}" for i, text in enumerate(partial_texts, 1)]
    joined = "\n\n".join(blocks)

    if language == "en":
        return (
            "Consolidate the following partial analyses as described "
            f"above:\n\n{joined}"
        )
    return f"以下の部分的な分析結果を、上記の指示に従って一つに統合してください:\n\n{joined}"
