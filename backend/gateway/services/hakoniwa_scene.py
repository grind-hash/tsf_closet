"""AI箱庭の場面絵(年代記の出来事を1枚の絵にする)の組み立て。

参加者のいまの姿(表示と同じ優先順位・入れ替わりを反映)を NovelAI のキャラクター枠に入れ、
場所の情景と場面の動作・構図のタグを土台にする。場面絵は自動では生成せず、絵にする価値の
ある出来事にだけ「おすすめ」を出す。
"""

from __future__ import annotations

import re
from typing import Any

from ..consts.hakoniwa import (
    HAKONIWA_SCENE_ATTIRES,
    HAKONIWA_SCENE_COVERED_NEGATIVE,
    event_location,
)
from .hakoniwa_logic import (
    ensure_gender_token,
    find_resident,
    own_look,
    resident_gender,
    swap_partner_id,
    tags_gender,
)
from .identity_signature import cross_identity_negative

# 参加者同士の接触・接近を表す語(日本語・英語)。出来事の文に含まれていれば場面絵をすすめる
SCENE_CONTACT_WORDS = (
    "抱きしめ",
    "抱き合",
    "抱擁",
    "手を握",
    "手をつな",
    "手を取",
    "手が触",
    "触れ合",
    "寄り添",
    "寄りかか",
    "肩を抱",
    "頬に触",
    "キス",
    "接吻",
    "密着",
    "見つめ合",
    "もたれか",
    "耳元で",
    "近づき",
    "間近に",
    "腕の中",
    "hug",
    "embrace",
    "held hands",
    "holding hands",
    "hold hands",
    "took her hand",
    "took his hand",
    "kiss",
    "leaned on",
    "leaning on",
    "snuggl",
    "cuddl",
    "in each other's arms",
    "in her arms",
    "in his arms",
    "gazed at each other",
    "whispered in",
)

SCENE_REASONS = {
    "contact": {
        "ja": "参加者同士の接触や接近が描かれた出来事です",
        "en": "Residents touch or come close to each other in this event",
    },
    "confrontation": {
        "ja": "住民たちが書き手へ呼びかけた、物語の転機です",
        "en": "The residents called out to the writer; a turning point of the story",
    },
    "arc_climax": {
        "ja": "続いてきた物語の山場です",
        "en": "The climax of an ongoing story",
    },
}

# 場面のタグを作れなかったときの定型
SCENE_TAGS_FALLBACK = (
    "cinematic scene, interacting with each other, expressive poses, detailed scene"
)
# 場面絵の中の人物の位置(人数ごと、左から)
SCENE_POSITIONS: dict[int, list[tuple[float, float]]] = {
    1: [(0.5, 0.5)],
    2: [(0.3, 0.5), (0.7, 0.5)],
    3: [(0.2, 0.5), (0.5, 0.5), (0.8, 0.5)],
}
SCENE_EXTRA_NEGATIVE = "split screen, comparison, multiple views, panels"
_SOLO_TAG = re.compile(r"^\s*solo( focus)?\s*$", re.IGNORECASE)


def scene_suggestion(event: dict[str, Any], language: str) -> dict[str, str] | None:
    """場面絵をすすめる出来事なら {level, reason} を返す。既に場面絵があれば None。"""
    if event.get("scene_image"):
        return None
    key = "ja" if language == "ja" else "en"
    # 物語の転機は強くすすめる(1人の出来事でも)
    if event.get("kind") == "confrontation":
        return {"level": "strong", "reason": SCENE_REASONS["confrontation"][key]}
    if event.get("arc_climax"):
        return {"level": "strong", "reason": SCENE_REASONS["arc_climax"][key]}
    if len(event.get("participants") or []) < 2:
        return None
    haystack = " ".join(
        [
            str(event.get("title") or ""),
            str(event.get("narration") or ""),
            *(str(line.get("text") or "") for line in event.get("lines") or []),
        ]
    ).lower()
    if any(word in haystack for word in SCENE_CONTACT_WORDS):
        return {"level": "normal", "reason": SCENE_REASONS["contact"][key]}
    return None


def look_tags(state: dict[str, Any], resident: dict[str, Any]) -> str:
    """住民のいま見えている姿のタグ。表示と同じく 変身 → 複合の姿 → 掟の姿 → ドレス →
    通常の順で、入れ替わり中は相手の姿。"""
    partner_id = swap_partner_id(state, resident["id"])
    owner = find_resident(state, partner_id) if partner_id else resident
    tags = str(own_look(state, owner).get("tags") or "")
    if not tags and "dress" in state.get("active_rules", []):
        tags = str(owner.get("dress_tags") or "")
    if not tags:
        tags = str(owner.get("base_tags") or "")
    return ensure_gender_token(tags, resident_gender(owner))


# 場面の服装に着替えさせるとき外す、服・靴・帽子・持ち物のタグ。髪・体・眼鏡などは残す。
# 合成語(sundress, swimsuit, underwear)も拾うよう、長い語は前の境界を問わない
_CLOTHING_TAG = re.compile(
    r"(?:dress|shirt|skirt|wear|coat|suit|jacket|sweater|uniform|kimono|yukata|"
    r"apron|hoodie|cardigan|blouse|pants|jeans|shorts|trousers|boots|shoes|"
    r"sneakers|sandals|heels|socks|stockings|thighhighs|pantyhose|gloves|"
    r"leotard|lingerie|panties|bikini|pajamas|outfit|costume|clothes|clothing|"
    r"collar|sleeves?|necktie|scarf|overalls|crossdressing)\b"
    r"|\b(?:cap|hat|top|bra|tie|vest|belt|beret|holding)\b",
    re.IGNORECASE,
)


def strip_clothing_tags(tags: str) -> str:
    """姿のタグから服・靴・帽子・持ち物のタグを外す(場面の服装に差し替えるため)。"""
    return ", ".join(
        tag.strip()
        for tag in str(tags or "").split(",")
        if tag.strip() and not _CLOTHING_TAG.search(tag)
    )


def dress_for_scene(tags: str, attire: str | None, gender: str, *, nsfw: bool) -> str:
    """場面の服装(HAKONIWA_SCENE_ATTIRES)に着替えさせたタグ。as_is や不明な値はそのまま。"""
    if attire == "nude" and not nsfw:
        attire = "towel"
    if not attire or attire == "as_is" or attire not in HAKONIWA_SCENE_ATTIRES:
        return tags
    worn = HAKONIWA_SCENE_ATTIRES[attire]["male" if gender == "male" else "female"]
    return ", ".join(part for part in (strip_clothing_tags(tags), worn) if part)


def scene_attire_negative(attire: str | None, gender: str, *, nsfw: bool) -> str:
    """裸以外の服装に選ばれた人物のネガティブ(服を着たまま描かせる)。選ばれていなければ空。"""
    if attire not in HAKONIWA_SCENE_ATTIRES or (attire == "nude" and nsfw):
        return ""
    return HAKONIWA_SCENE_COVERED_NEGATIVE["male" if gender == "male" else "female"]


def _strip_solo(tags: str) -> str:
    return ", ".join(
        tag.strip()
        for tag in tags.split(",")
        if tag.strip() and not _SOLO_TAG.match(tag)
    )


def _count_tokens(genders: list[str]) -> str:
    girls = sum(1 for gender in genders if gender == "female")
    boys = len(genders) - girls
    tokens = []
    if girls:
        tokens.append("1girl" if girls == 1 else f"{girls}girls")
    if boys:
        tokens.append("1boy" if boys == 1 else f"{boys}boys")
    return ", ".join(tokens)


def scene_request(
    state: dict[str, Any],
    event: dict[str, Any],
    scene_tags: str,
    attire: dict[str, str] | None = None,
    *,
    nsfw: bool = False,
) -> dict[str, Any]:
    """場面絵の生成に渡す土台のプロンプトとキャラクター枠を組み立てる。

    戻り値 {prompt, characters, flat_prompt}。characters は NovelAI のキャラクター枠
    (左から順、2人以上は位置を固定)、flat_prompt は NovelAI 以外へ送る1行のプロンプト。
    attire は住民 id ごとの場面の服装(浴室なら裸・タオルなど)。住民の姿そのものは変えない。
    """
    participants = [
        find_resident(state, resident_id)
        for resident_id in (event.get("participants") or [])[:3]
    ]
    if not participants:
        raise ValueError("event has no participants")
    tags = [_strip_solo(look_tags(state, resident)) for resident in participants]
    genders = [
        tags_gender(item) or resident_gender(resident)
        for item, resident in zip(tags, participants, strict=True)
    ]
    if attire:
        tags = [
            dress_for_scene(item, attire.get(resident["id"]), gender, nsfw=nsfw)
            for item, resident, gender in zip(tags, participants, genders, strict=True)
        ]
    # 背景は出来事の場所(浴室・商店街など)。無ければ起きたエリア
    place = event_location(event)
    scene = scene_tags.strip() or SCENE_TAGS_FALLBACK
    prompt = ", ".join(
        part
        for part in (
            _count_tokens(genders),
            place["scene_tags"],
            scene,
            "cinematic composition",
        )
        if part
    )
    positions = SCENE_POSITIONS[len(participants)]
    characters = []
    for index, own in enumerate(tags):
        others = [item for other, item in enumerate(tags) if other != index]
        frame: dict[str, Any] = {"prompt": own, "position": positions[index]}
        negative = ", ".join(
            part
            for part in (
                cross_identity_negative(own, others) if others else "",
                scene_attire_negative(
                    (attire or {}).get(participants[index]["id"]),
                    genders[index],
                    nsfw=nsfw,
                ),
            )
            if part
        )
        if negative:
            frame["negative_prompt"] = negative
        if len(participants) >= 2:
            frame["fixed_position"] = True
        characters.append(frame)
    flat_prompt = ", ".join([prompt, *tags])
    return {"prompt": prompt, "characters": characters, "flat_prompt": flat_prompt}
