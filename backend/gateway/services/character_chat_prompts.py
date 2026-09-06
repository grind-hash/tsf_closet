"""キャラチャットのプロンプト(純関数)。

判定 LLM(何を調べるか / 着替え要求か)、返答本文、着替え時の外見タグ更新、
スレッド要約の 4 種。会話そのものは user/assistant のメッセージ列で渡すため、
system prompt には人物設定・記憶・調べた結果だけを載せる。
"""

from __future__ import annotations

import json
from typing import Any

from ..consts.character_chat import (
    APP_OVERVIEW,
    BASE_CHARACTER_PERSONA,
    LOOKUP_KINDS,
    SUMMARY_MAX_CHARS,
)
from .conversation import (
    get_language_rules,
    get_psychological_description,
    get_stage_display_name,
    get_stage_name,
)


def _lang(language: str) -> str:
    return "en" if language == "en" else "ja"


# ---------------------------------------------------------------------------
# 判定 LLM(planner)
# ---------------------------------------------------------------------------

_LOOKUP_DESCRIPTIONS = {
    "recent_sessions": "the user's most recent play sessions (date, character, how many transformations, last instruction). Use for 'what did I do recently', 'last time'.",
    "session_detail": "one session's timeline, mental stage and attributes. Needs session_id from session_candidates. Use when the user refers to a specific past session.",
    "search_sessions": "free-word search across all past instructions, conversations and summaries. Needs query (short keywords). Use for 'did I ever ...', 'the time with the maid outfit'.",
    "tendencies": "aggregate statistics: total sessions, instruction type counts, common costume categories, achievements. Use for 'what are my tendencies / habits / favorites'.",
    "recent_adventures": "recent TSF scenario (adventure) runs: title, preset, status, progress. Use when the user asks about scenarios they played.",
}
assert set(_LOOKUP_DESCRIPTIONS) == set(LOOKUP_KINDS)


def planner_system_prompt(language: str) -> str:
    """判定 LLM の system prompt。JSON だけを返させる。"""
    lookups = "\n".join(
        f'- "{kind}": {description}'
        for kind, description in _LOOKUP_DESCRIPTIONS.items()
    )
    return (
        "You are the retrieval planner for a character chat inside a dress-up / TSF "
        "game app. Before the character answers, decide whether the character should "
        "look something up about the user's past play, and whether the user asked the "
        "character to change their appearance. Output JSON only, no prose, no code fence.\n\n"
        "Available lookups:\n"
        f"{lookups}\n\n"
        "Output schema:\n"
        '{"lookups": [{"kind": "<kind>", "query": "<keywords or null>", '
        '"session_id": "<id from session_candidates or null>", "limit": <1-10>}], '
        '"appearance_request": "<the requested change in the user\'s own words, or null>"}\n\n'
        "Rules:\n"
        "- Choose lookups ONLY when the latest user message asks about, or clearly "
        "benefits from, the user's past sessions, scenarios, tendencies, statistics or a "
        "specific past event. Small talk, questions about the character, and questions "
        "about how the app works need no lookups: return an empty list.\n"
        "- At most 3 lookups. Prefer the single most relevant kind.\n"
        "- For session_detail, copy session_id exactly from session_candidates; if none "
        "fits, use recent_sessions or search_sessions instead.\n"
        "- appearance_request: when the user asks the character to change clothes, "
        "outfit, hairstyle, accessories or overall look (e.g. 'put on a dress', 'tie your "
        "hair up'), put the request as a short phrase in the user's language. Otherwise "
        "null. Compliments or questions about the current look are not requests.\n"
        f"- The conversation language is {'Japanese' if _lang(language) == 'ja' else 'English'}."
    )


def planner_user_prompt(
    *,
    kind: str,
    character_name: str,
    recent_messages: list[dict[str, str]],
    session_candidates: list[dict[str, str]],
    message: str,
) -> str:
    payload = {
        "character_kind": kind,
        "character_name": character_name,
        "recent_messages": recent_messages,
        "session_candidates": session_candidates,
        "latest_user_message": message,
    }
    return json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 返答本文
# ---------------------------------------------------------------------------


def memory_block(memory_text: str | None, language: str) -> str:
    """ユーザーメモリを会話向けの弱い枠で包む。空なら空文字。

    画像・心境生成向けの build_memory_priority_instruction(「最優先指示」)は
    人格や口調まで上書きしてしまうため使わない。
    """
    text = str(memory_text or "").strip()
    if not text:
        return ""
    if _lang(language) == "en":
        return (
            "[What you know about this person]\n"
            f"{text}\n"
            "Use this to choose topics and to be considerate. It does not change your "
            "personality or tone, and you must not recite it verbatim unless asked."
        )
    return (
        "[この人について知っていること]\n"
        f"{text}\n"
        "話題選びと気遣いに使ってください。あなたの人格や口調はキャラクター設定を優先し、"
        "聞かれない限りこの内容をそのまま読み上げないでください。"
    )


def base_persona_block(language: str) -> str:
    """拠点キャラ(セレナ)の人物設定 + アプリ概要。"""
    lang = _lang(language)
    return f"{BASE_CHARACTER_PERSONA[lang]}\n\n{APP_OVERVIEW[lang]}"


def _timeline_label(event_type: str, language: str) -> str:
    labels_ja = {
        "dress_up": "着替",
        "reality_alter": "改変",
        "action": "行動",
        "conversation": "会話",
        "image_only": "画像",
    }
    labels_en = {
        "dress_up": "dress-up",
        "reality_alter": "alter",
        "action": "action",
        "conversation": "talk",
        "image_only": "image",
    }
    table = labels_en if _lang(language) == "en" else labels_ja
    return table.get(str(event_type), str(event_type))


def session_persona_block(persona: dict[str, Any], language: str) -> str:
    """セッション由来キャラの人物設定(作成時点のスナップショット)。"""
    lang = _lang(language)
    name = str(persona.get("character_name") or "キャラクター")
    pronoun = str(persona.get("pronoun") or "僕")
    stats = persona.get("stats") or {}
    bloom = int(stats.get("bloom") or 0)
    transformation_count = int(persona.get("transformation_count") or 0)
    nsfw_mode = bool(persona.get("nsfw_mode"))
    stage = "pre_transform" if transformation_count == 0 else get_stage_name(bloom)
    psychological = get_psychological_description(
        bloom, nsfw_mode, pronoun, transformation_count
    )
    attributes = [str(item) for item in persona.get("attributes") or [] if item]
    timeline = persona.get("timeline") or []
    outfit = str(persona.get("outfit_description") or "").strip()
    play_memory = str(persona.get("play_memory_context") or "").strip()

    lines: list[str] = []
    if lang == "en":
        lines.append(
            f"You are {name}, a character from one of the user's past play sessions "
            f"of this dress-up / TSF game, talking with the user (the one who gave you "
            f"those instructions) outside the story. Your first-person pronoun is "
            f'"{pronoun}". Stay in character; your feelings below are your own memory.'
        )
        lines.append(f"Transformations so far: {transformation_count}")
        if transformation_count:
            lines.append(
                f"Mental stage: {stage} (bloom {bloom}, shame {stats.get('shame', 0)}, "
                f"adaptation {stats.get('adaptation', 0)})"
            )
        lines.append(f"Current state of mind: {psychological}")
        if outfit:
            lines.append(f"Current appearance / outfit: {outfit}")
        if attributes:
            lines.append("Reality-altered attributes (true facts about you):")
            lines.extend(f"- {item}" for item in attributes)
        if timeline:
            lines.append("What happened to you, oldest first:")
            lines.extend(
                f"- [{_timeline_label(item.get('type', ''), lang)}] {item.get('text', '')}"
                for item in timeline
                if isinstance(item, dict)
            )
        if play_memory:
            lines.append(f"Notes about that session:{play_memory}")
    else:
        lines.append(
            f"あなたは「{name}」。この着せ替え/TSF ゲームで相手が過去に遊んだセッションの"
            f"登場人物で、物語の外で相手(あなたに指示を出していた本人)と話しています。"
            f"一人称は「{pronoun}」。役柄を保ち、以下の心境と経緯はあなた自身の記憶です。"
        )
        lines.append(f"これまでの変身回数: {transformation_count}")
        if transformation_count:
            lines.append(
                f"心理段階: {get_stage_display_name(stage)}"
                f"(開花{bloom} / 羞恥{stats.get('shame', 0)} / 適応{stats.get('adaptation', 0)})"
            )
        lines.append(f"現在の心境: {psychological}")
        if outfit:
            lines.append(f"現在の姿・服装: {outfit}")
        if attributes:
            lines.append("現実改変で付与された属性(あなたにとっての事実):")
            lines.extend(f"- {item}" for item in attributes)
        if timeline:
            lines.append("あなたに起きたこと(古い順):")
            lines.extend(
                f"- [{_timeline_label(item.get('type', ''), lang)}] {item.get('text', '')}"
                for item in timeline
                if isinstance(item, dict)
            )
        if play_memory:
            lines.append(f"そのセッションのメモ:{play_memory}")
    return "\n".join(lines)


def lookup_block(rendered: str, language: str) -> str:
    text = str(rendered or "").strip()
    if not text:
        return ""
    if _lang(language) == "en":
        return (
            "[What you just looked up about the user's past play]\n"
            f"{text}\n"
            "Answer using only these results. If something the user asks about is not "
            "here, say you have no record of it instead of guessing."
        )
    return (
        "[相手の過去のプレイについて、いま調べた結果]\n"
        f"{text}\n"
        "この結果だけを根拠に答えてください。聞かれたことがここに無ければ、"
        "推測せず「記録にはありません」と伝えてください。"
    )


def reply_system_prompt(
    language: str,
    *,
    name: str,
    pronoun: str,
    persona_block: str,
    memory_block_text: str,
    summary_text: str | None,
    lookup_block_text: str,
    appearance_description: str,
    appearance_change_request: str | None,
) -> str:
    """返答本文の system prompt。"""
    lang = _lang(language)
    sections: list[str] = [persona_block]
    if appearance_description:
        sections.append(
            f"[Your current appearance]\n{appearance_description}"
            if lang == "en"
            else f"[あなたの今の姿]\n{appearance_description}"
        )
    if memory_block_text:
        sections.append(memory_block_text)
    if summary_text:
        sections.append(
            f"[Summary of this conversation so far]\n{summary_text}"
            if lang == "en"
            else f"[これまでの会話の要約]\n{summary_text}"
        )
    if lookup_block_text:
        sections.append(lookup_block_text)
    if appearance_change_request:
        sections.append(
            (
                "[Appearance change in progress]\n"
                f"The user asked: {appearance_change_request}\n"
                "You are changing into it right now; react to the request naturally "
                "and describe briefly how you look after the change. The portrait will "
                "be redrawn after your reply."
            )
            if lang == "en"
            else (
                "[着替え中]\n"
                f"相手の依頼: {appearance_change_request}\n"
                "いままさにその姿に変わるところです。依頼に自然に反応し、変わった後の姿を"
                "短く描写してください。立ち絵は返答の後に描き直されます。"
            )
        )
    if lang == "en":
        rules = (
            "Conversation rules:\n"
            "- The messages in this chat are the actual conversation so far, oldest first; "
            "the last user message is what they just said. Continue that conversation, "
            "remember what was said, and never restart as if meeting for the first time.\n"
            f"- Reply as {name} in the first person ('{pronoun}'), as spoken words only: "
            "usually one to four sentences. You may add at most one brief action in "
            "parentheses. No narration, no name prefix, no corner brackets, no markdown, "
            "no JSON.\n"
            "- Do not invent facts about the user's past play beyond what you were given.\n"
            f"{get_language_rules('en')}"
        )
    else:
        rules = (
            "会話のルール:\n"
            "- このチャットのメッセージはこれまでの実際の会話(古い順)で、最後の user "
            "メッセージが相手のいまの発言です。その続きとして答え、言われたことを覚え、"
            "初対面のように仕切り直さないでください。\n"
            f"- 「{name}」として一人称「{pronoun}」で、話し言葉だけを返してください。"
            "通常は 1〜4 文。丸括弧の短い仕草を 1 つまで添えてもかまいません。"
            "地の文・名前のプレフィックス・かぎ括弧で全体を囲む・Markdown・JSON は禁止。\n"
            "- 相手の過去のプレイについて、渡された情報に無いことを作らないでください。\n"
            f"{get_language_rules('ja')}"
        )
    sections.append(rules)
    return "\n\n".join(section for section in sections if section)


# ---------------------------------------------------------------------------
# 着替え(外見タグ更新)
# ---------------------------------------------------------------------------


def appearance_change_system_prompt(language: str) -> str:
    return (
        "You update a character's appearance tags for an anime-style image generator "
        "(Danbooru-style English tags, comma separated). Given the current identity tags "
        "(body, hair, eyes, face, gender) and clothing tags, and the user's request, "
        "output JSON only:\n"
        '{"identity_tags": "...", "clothing_tags": "...", "description": "..."}\n'
        "Rules:\n"
        "- clothing_tags: replace or adjust the outfit, hairstyle accessories and "
        "footwear to satisfy the request; keep unrelated items. Describe garments "
        "concretely (color, type, length).\n"
        "- identity_tags: keep them unchanged unless the request explicitly asks to "
        "change hair color/length/style, eye color, body or gender. Always keep the "
        "gender token (1girl/1boy/female/male) and solo.\n"
        "- No scene, pose or background tags. No text other than the JSON.\n"
        "- description: one short sentence describing the new look, written in "
        f"{'Japanese' if _lang(language) == 'ja' else 'English'}."
    )


def appearance_change_user_prompt(
    *, identity_tags: str, clothing_tags: str, request: str
) -> str:
    return json.dumps(
        {
            "identity_tags": identity_tags,
            "clothing_tags": clothing_tags,
            "request": request,
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# スレッド要約
# ---------------------------------------------------------------------------


def summary_system_prompt(language: str) -> str:
    if _lang(language) == "en":
        return (
            "Update a concise memory of a chat between a user and a character. Output "
            "plain text with exactly these headings: Topics so far, What you learned "
            "about the user, Things to keep in mind. Preserve established facts, fold in "
            "the new messages, never invent details, and keep the whole text under "
            f"{SUMMARY_MAX_CHARS} characters."
        )
    return (
        "ユーザーとキャラクターのチャットの記憶を簡潔に更新してください。出力はプレーンテキストで、"
        "「これまでの話題」「相手について分かったこと」「続けるべき事項」の3見出しを必ず使ってください。"
        "確定済みの事実を維持し、新しいメッセージを反映し、存在しない内容を補わず、"
        f"全体を{SUMMARY_MAX_CHARS}文字以内にしてください。"
    )


def summary_user_prompt(
    *, previous: str | None, messages: list[dict[str, str]], character_name: str
) -> str:
    lines = [f"Previous memory:\n{previous or '(none)'}", "New messages:"]
    for item in messages:
        speaker = "user" if item.get("role") == "user" else character_name
        lines.append(f"- {speaker}: {item.get('content', '')}")
    return "\n".join(lines)
