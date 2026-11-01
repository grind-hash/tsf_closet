"""Prompts for request mode (依頼モード): generating a request, judging a turn,
and the request block added to the character's feeling prompt."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from ..consts.sensitive_desires import SensitiveDesire
from ..consts.session_request import REQUEST_HINT_MARK_CLOSE, REQUEST_HINT_MARK_OPEN


def _response_language(language: str) -> str:
    return "Japanese" if language == "ja" else "English"


# 成人向けの依頼(サロンの過激施術)で、どの文章にも添える守り
ADULT_CONTENT_RULE = "Everyone involved is an adult (18 or older) and takes part willingly. Never describe minors, child-like bodies, or anyone who does not consent."


def build_request_generation_prompt(
    profile: dict[str, Any],
    appearance: str,
    language: str,
    previous_visit: dict[str, Any] | None = None,
    *,
    sensitive: bool = False,
    desires: Sequence[SensitiveDesire] | None = None,
    motive: str = "self",
) -> tuple[str, str]:
    """依頼生成の (system, user) を返す。

    previous_visit({wish, review})は、前回の施術の姿のまま来たお客様の前回の来店。
    今の姿を土台にした追加の要望を願いにさせる。
    sensitive なら成人向けの願いにし、その姿でしたいこと(experience)も書かせる。
    願う行為は desires(Python が選んだテーマの候補)から、キャラクターの TSF への態度と
    性格に合う1つを選ばせ、言葉にさせる。motive が crush なら意中の相手の好みを理由にさせる。
    """
    if sensitive and not desires:
        raise ValueError("成人向けの依頼には desires が要ります")
    pronoun = str(profile.get("pronoun") or "").strip()
    pronoun_rule = (
        f" Use the first-person pronoun {pronoun} for the character." if pronoun else ""
    )
    # 分類は画面にそのまま出るので、依頼の言語で書かせる(英語の例だけだと日本語でも英語になる)
    category_examples = (
        "for example, 色合い, 丈, 小物"
        if language == "ja"
        else "for example, color, length, accessory"
    )
    if sensitive:
        schema = '{"desire_id":"...","wish":"...","preferences":[{"text":"...","hint":"..."}],"experience":"..."}'
        wish_rule = "It has the shape \"make me into <the look they want, with a body of the chosen desire's target_body>, I want to <the chosen desire's act>\": it asks for the look and then names that sexual act plainly, in the character's own words (everyday or slang words for the act are fine). A shy character may hesitate or blush, but must still name the act; a hug, a kiss, or being held is never enough on its own, and never soften the act into something vaguer. Do not list every detail of the look."
        preference_examples = "such as a body trait (breast size, figure), lingerie or a revealing outfit, a color family, an accessory, or a hairstyle. At least one of them is about lingerie, exposure, or a body trait that suits the chosen act (its look_hint is a good candidate)"
        content_rule = f"Write the sexual content of wish and experience explicitly. Never pair a male body with a male partner. {ADULT_CONTENT_RULE}"
        experience_rule = """
experience: one sentence of at most 80 Japanese characters or 40 English words, written as a stage direction of the scene where the character, in the finished look, does the chosen act. Name the act and the position or pose explicitly. When the chosen desire's partner is man or woman, describe that partner only as a faceless adult of that sex (a faceless adult man or a faceless adult woman; in Japanese, 顔の見えない男性 or 顔の見えない女性, never 無表情) and keep the character the focus. When its partner is none, no one else appears."""
        choice_rule = """
desire_id: the id of the one candidate in desire_candidates that best fits the character. target_body is the body they ask for (gender man matches male, woman matches female): different from gender means becoming the other sex, the same as gender means staying their own sex in an ideal body. Choose by tsf_attitude and personality: a character who longs to become the other sex takes that body, and one who has never wished to change sex stays their own sex. partner is who they do it with (none means alone)."""
        if motive == "crush":
            choice_rule += """
motive is crush: the character wants this look to become the ideal of someone they love, and the wish gives that person's taste as the reason (for example, that the person likes huge breasts). That person is the partner in experience."""
        else:
            choice_rule += """
motive is self: the wish grows out of the character's own longing or curiosity."""
        experience_rule = choice_rule + experience_rule
    else:
        schema = '{"wish":"...","preferences":[{"text":"...","hint":"..."}]}'
        wish_rule = "It names the overall look or mood they want (for example, a princess at a ball, a cool office worker, a shrine maiden) without listing every detail."
        preference_examples = "such as a color family, a skirt or dress length, a fabric or decoration, an accessory, or a hairstyle"
        content_rule = "Never write sexual content."
        experience_rule = ""
    system = f"""You write a request for a dress-up game. The character described by the user comes to a stylist (the player) and tells them the look they long to have.
Return one JSON object only, in {_response_language(language)}, matching this schema:
{schema}
wish: what the character says to the stylist, in their own voice, at most 120 Japanese characters or 40 English words.{pronoun_rule} {wish_rule}
preferences: 2 or 3 concrete conditions the character secretly cares about but does not say, {preference_examples}. Each must be checkable from a written description of the finished look, and they must not contradict the wish or each other. text states the condition plainly in at most 40 Japanese characters or 12 English words. hint names only its category, written in {_response_language(language)}, in at most 8 Japanese characters or 3 English words ({category_examples}), so the player has something to guess from.{experience_rule}
Keep everything consistent with the character's personality and background. {content_rule} When tsf_attitude is given, let the wish grow out of that attitude toward transformation (for example, a hidden longing to look like a princess, or curiosity about living as the other sex), without stating the attitude itself."""
    payload: dict[str, Any] = {
        "character": {
            "name": profile.get("name") or "",
            "gender": profile.get("gender") or "",
            "personality": profile.get("personality") or "",
            "description": profile.get("description") or "",
            "tsf_attitude": profile.get("tsf_attitude") or "",
        },
        "current_look": appearance,
    }
    if sensitive and desires:
        payload["desire_candidates"] = [
            {
                "id": desire.id,
                "act": desire.act,
                "target_body": desire.body,
                "partner": desire.partner,
                "look_hint": desire.look_hint,
            }
            for desire in desires
        ]
        payload["motive"] = motive
    if previous_visit:
        system += """
previous_visit is given: on that visit the character was styled into current_look, loved it, and came back still in it (current_look may differ from the character's original sex; gender is the original one). Make the wish an additional request that builds on current_look, such as taking it further or adding something new, and never a request to undo it. The wish may refer to the last visit."""
        if sensitive:
            system += (
                " In this look, the character now longs for the chosen desire's act."
            )
        payload["previous_visit"] = {
            "wish": previous_visit.get("wish") or "",
            "review": previous_visit.get("review") or "",
        }
    user = json.dumps(payload, ensure_ascii=False)
    return system, user


def build_request_evaluation_prompt(
    *,
    wish: str,
    preferences: list[dict[str, Any]],
    current_look: str,
    instruction: str,
    language: str,
    previous_look: str | None = None,
    questions: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """手番評価の (system, user) を返す。

    previous_look は、current_look がこの手番の変更しか書いていない経路(画像を読む
    プロバイダー)で、手番前の姿を補うために渡す。questions はカウンセリングのやり取りで、
    答えを汲んだ姿をヒアリングの反映として加点するために渡す。
    """
    counselling = [
        {
            "index": index,
            "question": item.get("question"),
            "answer": item.get("answer"),
        }
        for index, item in enumerate(questions or [], start=1)
    ]
    counselling_schema = (
        ',"reflected_answers":[{"index":1,"evidence":"..."}]' if counselling else ""
    )
    counselling_rule = (
        "\nreflected_answers lists the counselling answers whose wishes the look "
        "follows, even partly or in spirit (for example, an answer longing for a soft, "
        "spring-sky color is reflected by pale blue dress or pastel colors). For each, "
        "index is the answer's index and evidence copies, word for word, the tag or "
        "phrase of the look that reflects it, under the same evidence rules as "
        "met_preferences. Leave out an answer that only talks about feelings with "
        "nothing in the look to show for it."
        if counselling
        else ""
    )
    previous_rule = (
        " previous_look describes the look before this turn, read from the image, and "
        "current_look states only this turn's change: judge the look as previous_look "
        "updated by that change."
        if previous_look
        else ""
    )
    system = f"""You judge how well a finished look fulfils a character's request in a dress-up game.
Return one JSON object only, matching this schema:
{{"fit":"none|partial|good|perfect","met_preferences":[{{"id":"p1","evidence":"..."}}]{counselling_schema},"hint":"..."}}
current_look describes the look after this turn.{previous_rule}
fit rates how well the look as a whole matches wish: none when it is unrelated, partial when it captures only some of the mood, good when it is clearly the requested look, perfect when it is exactly the requested look with nothing out of place.
met_preferences lists the preferences that the look actually satisfies. For each one, evidence must copy, word for word and in its original language, the tag or phrase of the look that describes that same attribute of the clothing or accessory, such as its color tone, length, material, or decoration; a close synonym counts (for example, pale blue dress or pastel colors for a soft, pale color). Tags about hair, eyes, skin, or face never count for clothing: a short hairstyle says nothing about the length of a dress. If no words in the look show the attribute, the preference is not met: never assume a default length, color, or accessory. player_instruction is what the player asked for, not proof that it happened, so never quote it as evidence.{counselling_rule}
hint is one short sentence in {_response_language(language)}, at most 50 Japanese characters or 20 English words, that nudges toward one preference that is not met, phrased as something the stylist could notice about the character's reaction, without stating the preference outright. Use an empty string when every preference is met."""
    user = json.dumps(
        {
            "wish": wish,
            "preferences": [
                {"id": item.get("id"), "text": item.get("text")} for item in preferences
            ],
            **({"previous_look": previous_look} if previous_look else {}),
            "current_look": current_look,
            "player_instruction": instruction,
            **({"counselling": counselling} if counselling else {}),
        },
        ensure_ascii=False,
    )
    return system, user


def build_request_question_prompt(
    *,
    profile: dict[str, Any],
    wish: str,
    preferences: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    question: str,
    language: str,
    sensitive: bool = False,
) -> tuple[str, str]:
    """カウンセリングの質問に、依頼主本人として答える (system, user) を返す。"""
    pronoun = str(profile.get("pronoun") or "").strip()
    pronoun_rule = (
        f" Use the first-person pronoun {pronoun} if you refer to yourself."
        if pronoun
        else ""
    )
    content_rule = (
        f"Sexual content is allowed when the wish calls for it. {ADULT_CONTENT_RULE}"
        if sensitive
        else "Never write sexual content."
    )
    system = f"""You play the customer described by the user, talking with the stylist (the player) during a counselling before a dress-up.
Reply in {_response_language(language)}, in the character's own voice and personality, with one to three short sentences (at most 120 Japanese characters or 40 English words).{pronoun_rule}
Answer the stylist's question honestly but indirectly. When it touches on one of hidden_preferences, let a clue slip through feelings, associations, or memories (for example, a favorite color appearing in a memory) without ever stating the preference itself. When it does not, answer naturally and stay in character.
Stay consistent with previous_counselling. Never mention ids, lists, scores, or game mechanics, and never invent new preferences. {content_rule} Output only the reply, without quotation marks."""
    user = json.dumps(
        {
            "character": {
                "name": profile.get("name") or "",
                "personality": profile.get("personality") or "",
                "description": profile.get("description") or "",
                "tsf_attitude": profile.get("tsf_attitude") or "",
            },
            "wish": wish,
            "hidden_preferences": [
                {"text": item.get("text"), "category": item.get("hint")}
                for item in preferences
            ],
            "previous_counselling": [
                {"question": item.get("question"), "answer": item.get("answer")}
                for item in previous
            ],
            "stylist_question": question,
        },
        ensure_ascii=False,
    )
    return system, user


_FIT_LABELS: dict[str, dict[str, str]] = {
    "ja": {
        "none": "まだ願いとは違う姿",
        "partial": "願いに少し近づいた姿",
        "good": "願いにかなり近い姿",
        "perfect": "願いそのものの姿",
    },
    "en": {
        "none": "not yet the look they wished for",
        "partial": "a little closer to their wish",
        "good": "close to their wish",
        "perfect": "exactly the look they wished for",
    },
}


def build_request_feeling_context(
    *,
    wish: str,
    met_texts: list[str],
    unmet_texts: list[str],
    fit: str | None,
    language: str,
    questions: list[dict[str, Any]] | None = None,
    emphasize_hints: bool = False,
) -> str:
    """心境プロンプトの user prompt に添える依頼ブロック。

    まだ満たされていない好みは本人の反応でほのめかすだけにし、名指しさせない。
    emphasize_hints なら、ほのめかす一文を目印の記号で囲ませる(画面が強調表示する)。
    """
    labels = _FIT_LABELS["ja" if language == "ja" else "en"]
    if language == "ja":
        lines = [
            "",
            "【依頼】",
            f"このキャラクターは着せ替えの前に、次の願いを伝えています:「{wish}」",
        ]
        if fit in labels:
            lines.append(f"・いまの姿: {labels[fit]}")
        if met_texts:
            lines.append(f"・満たされた好み: {'、'.join(met_texts)}")
        if unmet_texts:
            lines.append(
                "・まだ満たされていない好み（口に出して名指しせず、反応の中でそれとなく"
                f"ほのめかす）: {'、'.join(unmet_texts)}"
            )
            if emphasize_hints:
                lines.append(
                    "・ほのめかしている一文だけを"
                    f"{REQUEST_HINT_MARK_OPEN}と{REQUEST_HINT_MARK_CLOSE}で囲んでください"
                    "（1か所だけ。囲んだ中でも好みを名指ししない。ほかの文には使わない）"
                )
        if questions:
            # 本人がカウンセリングで言ったことと、反応が食い違わないようにする
            lines.append("・カウンセリングで本人が答えたこと:")
            lines.extend(
                f"  - 「{item.get('question')}」→「{item.get('answer')}」"
                for item in questions
            )
        lines.append(
            "願いにどれだけ近づいたかを、本人の反応として自然に表してください。"
        )
        return "\n".join(lines)
    lines = [
        "",
        "[Request]",
        f'Before the dress-up, this character told the stylist their wish: "{wish}"',
    ]
    if fit in labels:
        lines.append(f"- Current look: {labels[fit]}")
    if met_texts:
        lines.append(f"- Preferences now satisfied: {'; '.join(met_texts)}")
    if unmet_texts:
        lines.append(
            "- Preferences not yet satisfied (never name them outright; only hint "
            f"at them through the reaction): {'; '.join(unmet_texts)}"
        )
        if emphasize_hints:
            lines.append(
                "- Wrap only the one sentence that hints at them in "
                f"{REQUEST_HINT_MARK_OPEN} and {REQUEST_HINT_MARK_CLOSE} (exactly one "
                "place; still never name the preference; use these marks nowhere else)"
            )
    if questions:
        # Keep the reaction consistent with what the character said in counselling
        lines.append("- What the character said in counselling:")
        lines.extend(
            f'  - "{item.get("question")}" -> "{item.get("answer")}"'
            for item in questions
        )
    lines.append(
        "Let the reaction show naturally how close the look has come to the wish."
    )
    return "\n".join(lines)
