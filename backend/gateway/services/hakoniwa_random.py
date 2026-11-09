"""AI箱庭: おまかせの住民(ランダムな住民構成)の決定的な組み立て。

LLM で作れなかったときの代わりで、語彙プールの組み合わせから住民の定義を作る。
定義は {name, gender, age, job, personality, pronoun, appearance_text, base_tags}。
名前は exclude_names や、同じ呼び出しで作った住民と重ねない。
"""

from __future__ import annotations

import random
from typing import Any

from ..consts.hakoniwa_random import (
    AGES,
    APPEARANCE_TEMPLATES,
    EXPRESSIONS,
    EYES,
    FEATURES,
    GIVEN_NAMES,
    HAIR_COLORS,
    HAIR_STYLES,
    HAKONIWA_RANDOM_COUNT_MAX,
    HAKONIWA_RANDOM_COUNT_MIN,
    JOBS,
    OUTFITS,
    PERSONALITY_CORES,
    PERSONALITY_QUIRKS,
    PRONOUNS,
    SURNAMES,
)
from .hakoniwa_errors import HakoniwaError

GENDERS = ("female", "male")


def _lang_index(language: str) -> int:
    return 0 if language == "ja" else 1


def name_key(name: str) -> str:
    """名前の照合用(空白を除き、小文字にそろえる)。"""
    return "".join(str(name or "").split()).lower()


def validate_count(count: Any) -> int:
    if (
        not isinstance(count, int)
        or isinstance(count, bool)
        or not HAKONIWA_RANDOM_COUNT_MIN <= count <= HAKONIWA_RANDOM_COUNT_MAX
    ):
        raise HakoniwaError(
            "invalid_count",
            f"人数は{HAKONIWA_RANDOM_COUNT_MIN}〜{HAKONIWA_RANDOM_COUNT_MAX}人で指定してください",
        )
    return count


def _name(gender: str, language: str, rng: random.Random, used: set[str]) -> str:
    index = _lang_index(language)
    for _ in range(40):
        family = rng.choice(SURNAMES)[index]
        given = rng.choice(GIVEN_NAMES[gender])[index]
        name = f"{family} {given}" if language == "ja" else f"{given} {family}"
        if name_key(name) not in used:
            return name
    # 語彙を使い切るほど重なったときだけ、苗字を2つ重ねて作る
    family = rng.choice(SURNAMES)[index]
    other = rng.choice(SURNAMES)[index]
    given = rng.choice(GIVEN_NAMES[gender])[index]
    return (
        f"{family}{other} {given}" if language == "ja" else f"{given} {other}-{family}"
    )


def template_resident(
    language: str,
    rng: random.Random,
    used_names: set[str],
    gender: str | None = None,
) -> dict[str, Any]:
    """住民1人分を組み立てる。used_names(照合用のキー)に名前を足す。"""
    index = _lang_index(language)
    gender = gender if gender in GENDERS else rng.choice(GENDERS)
    name = _name(gender, language, rng, used_names)
    used_names.add(name_key(name))
    age_ja, age_en, years, female_subject, male_subject = rng.choice(AGES)
    hair_color = rng.choice(HAIR_COLORS)
    hair_style = rng.choice(HAIR_STYLES[gender])
    eyes = rng.choice(EYES)
    feature = rng.choice(FEATURES)
    outfit = rng.choice(OUTFITS[gender])
    core = rng.choice(PERSONALITY_CORES)
    quirk = rng.choice(PERSONALITY_QUIRKS)
    if language == "ja":
        feature_text = f"{feature[0]}。" if feature[0] else ""
        personality = f"{core[0]}。{quirk[0]}。"
        pronoun = rng.choice(PRONOUNS[gender])
    else:
        feature_text = (
            f"{feature[1][0].upper()}{feature[1][1:]}. " if feature[1] else ""
        )
        personality = (
            f"{core[1][0].upper()}{core[1][1:]}. {quirk[1][0].upper()}{quirk[1][1:]}."
        )
        pronoun = "I"
    appearance = APPEARANCE_TEMPLATES["ja" if language == "ja" else "en"].format(
        hair_color=hair_color[index],
        hair_style=hair_style[index],
        eyes=eyes[index],
        feature=feature_text,
        outfit=outfit[index],
    )
    tags = [
        "1girl" if gender == "female" else "1boy",
        "solo",
        female_subject if gender == "female" else male_subject,
        years,
        hair_style[2],
        hair_color[2],
        eyes[2],
        feature[2],
        outfit[2],
        rng.choice(EXPRESSIONS),
    ]
    return {
        "name": name,
        "gender": gender,
        "age": age_ja if language == "ja" else age_en,
        "job": rng.choice(JOBS)[index],
        "personality": personality,
        "pronoun": pronoun,
        "appearance_text": appearance,
        "base_tags": ", ".join(tag for tag in tags if tag),
    }


def template_residents(
    count: int,
    language: str,
    rng: random.Random,
    exclude_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """住民の構成を組み立てる。rng が違えば構成も変わる(組み直しの仕組み)。"""
    validate_count(count)
    used = {name_key(name) for name in exclude_names or []}
    # 2人以上なら女性と男性を少なくとも1人ずつ入れ、残りは気ままに選ぶ
    genders = [rng.choice(GENDERS) for _ in range(count)]
    if count >= 2:
        genders[:2] = ["female", "male"]
        rng.shuffle(genders)
    return [template_resident(language, rng, used, gender) for gender in genders]
