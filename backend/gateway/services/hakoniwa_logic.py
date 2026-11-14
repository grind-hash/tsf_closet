"""AI箱庭モードの世界の状態遷移(純粋関数)。

世界の状態は dict で持ち、各関数は引数を書き換えずに新しい状態を返す。乱数は呼び出し側が
random.Random を渡す。状態の形:

    {version, day, image_model, active_rules[], swap_pair, last_pair,
     custom_rules: [{id, name, text, appearance_text, appearance_tags,
                     body_gender(掟の姿の体の性別。None は住民それぞれのまま)}],
     residents: [{id, source, preset_id?, character_preset_id?, name, gender, age, job,
                  personality, pronoun, speech_style, address_style, appearance_text,
                  base_tags,
                  dress_text, dress_tags, avatar_image, dress_image, mood, affinities,
                  transformation, transformation_history,
                  rule_images: {掟 id: {image, tags, source_tags, source_body}},
                  combo_images: {組み合わせ: {image, tags, source_tags, source_body}}}],
     events: [{id, day, title, narration, lines, participants, mood_delta,
               affinity_delta, source, kind?, change_text?, instruction?, favorite}]}

プリセット住民の名前・性格などは、状態に値が無ければ consts の ja / en から言語で引く。
世界の違和感・適応と名残・記憶・物語の弧の項目は hakoniwa_story を参照。
"""

from __future__ import annotations

import hashlib
import random
import re
import uuid
from copy import deepcopy
from typing import Any

from ..consts.hakoniwa import (
    CUSTOM_RESIDENT_LABELS,
    DEFAULT_AREA_ID,
    DEFAULT_BASE_TAGS,
    GENDERS,
    HAKONIWA_ADDRESS_ELDER_GAP,
    HAKONIWA_ADDRESS_STYLE_DEFAULT,
    HAKONIWA_ADDRESS_STYLES,
    HAKONIWA_AFFINITY_MAX,
    HAKONIWA_AFFINITY_MIN,
    HAKONIWA_APPEARANCE_TEXT_MAX,
    HAKONIWA_AREA_MAP,
    HAKONIWA_AREAS,
    HAKONIWA_CUSTOM_RESIDENT_INITIAL_MOOD,
    HAKONIWA_CUSTOM_RULE_NAME_MAX,
    HAKONIWA_CUSTOM_RULE_TEXT_MAX,
    HAKONIWA_CUSTOM_RULES_MAX,
    HAKONIWA_DIRECTED_EVENT_PARTNERS_MAX,
    HAKONIWA_DIRECTED_EVENT_TEXT_MAX,
    HAKONIWA_EVENT_AREA_MOVE_CHANCE,
    HAKONIWA_EVENT_LOG_MAX,
    HAKONIWA_EVENT_SCOPES,
    HAKONIWA_EVENTS_PER_DAY,
    HAKONIWA_FURNITURE_MAP,
    HAKONIWA_FURNITURE_SLOTS,
    HAKONIWA_IMAGE_MODEL_DEFAULT,
    HAKONIWA_LOCATION_MAP,
    HAKONIWA_MAX_ACTIVE_RULES,
    HAKONIWA_MAX_RESIDENTS,
    HAKONIWA_MIN_RESIDENTS,
    HAKONIWA_MOOD_MAX,
    HAKONIWA_MOOD_MIN,
    HAKONIWA_PERSONALITY_MAX,
    HAKONIWA_PRESET_CHARACTER_REVISIONS,
    HAKONIWA_PRESET_MAP,
    HAKONIWA_PRESET_REVISIONS,
    HAKONIWA_REALITIES_MAX,
    HAKONIWA_REALITY_TEXT_MAX,
    HAKONIWA_RESIDENT_AREA_MOVE_CHANCE,
    HAKONIWA_RESIDENT_NAME_MAX,
    HAKONIWA_RULE_APPEARANCE_TEXT_MAX,
    HAKONIWA_RULE_MAP,
    HAKONIWA_SOLO_GROUP_CHANCE,
    HAKONIWA_TRANSFORM_TEXT_MAX,
    HAKONIWA_TRANSFORMATION_HISTORY_MAX,
    HAKONIWA_TRIO_GROUP_CHANCE,
    ROMANCE_RULE_IDS,
)
from . import hakoniwa_play as play
from . import hakoniwa_story as story
from .hakoniwa_errors import HakoniwaError

__all__ = ["HakoniwaError"]

STATE_VERSION = 1
# 出来事に付いていれば年代記へそのまま写す項目
EVENT_EXTRA_KEYS = (
    "web_search",
    "kind",
    "change_text",
    "instruction",
    "location",
    "continues",
    "scene_image",
    "arc_id",
    "arc_climax",
    # 出来事を見せる間の BGM のキー(LLM が選んだときだけ)
    "bgm",
)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _lang(language: str) -> str:
    return "ja" if language == "ja" else "en"


# --- 住民の表示文 ---


def resident_text(resident: dict[str, Any], language: str) -> dict[str, Any]:
    """住民の名前・年齢・職業・性格・定型の一言を言語に合わせて返す。

    プリセット住民は状態に値が無い項目を consts から引く(編集した項目は状態の値を使う)。
    """
    lang = _lang(language)
    preset = HAKONIWA_PRESET_MAP.get(str(resident.get("preset_id") or ""))
    base = preset["text"][lang] if preset else {}
    labels = CUSTOM_RESIDENT_LABELS[lang]
    return {
        "name": resident.get("name") or base.get("name") or "",
        "age": resident.get("age") or base.get("age") or labels["age"],
        "job": resident.get("job") or base.get("job") or labels["job"],
        "personality": resident.get("personality") or base.get("personality") or "",
        "pronoun": resident.get("pronoun") or base.get("pronoun") or "",
        "greetings": list(base.get("greetings") or []),
    }


def resident_name(resident: dict[str, Any], language: str) -> str:
    return resident_text(resident, language)["name"]


# --- 住民どうしの呼び方 ---


def resident_address_style(resident: dict[str, Any]) -> str:
    """住民がほかの住民を呼ぶときのくせ。状態の値、無ければプリセットの値、既定の順。"""
    own = str(resident.get("address_style") or "")
    if own in HAKONIWA_ADDRESS_STYLES:
        return own
    preset = HAKONIWA_PRESET_MAP.get(str(resident.get("preset_id") or ""))
    style = str(preset.get("address_style") or "") if preset else ""
    return style if style in HAKONIWA_ADDRESS_STYLES else HAKONIWA_ADDRESS_STYLE_DEFAULT


def clean_address_style(value: Any) -> str:
    """呼び方のくせの入力を整える(知らない値は空 = プリセットか既定に任せる)。"""
    style = str(value or "")
    return style if style in HAKONIWA_ADDRESS_STYLES else ""


# かなり年上の相手に向けるときの、くせの言い換え(敬称を付ける)
_ELDER_ADDRESS_STYLES = {
    "given_chan": "given_san",
    "given": "given_san",
    "family": "family_san",
}
_AGE_NUMBER = re.compile(r"(\d+)\s*(代|s)?")


def age_years(text: str) -> int | None:
    """年齢の表示文(「20代後半」「27歳」「late 20s」)からおおよその年齢。読めなければ None。"""
    match = _AGE_NUMBER.search(text or "")
    if match is None:
        return None
    years = int(match.group(1))
    if match.group(2) is None:
        return years
    lowered = text.lower()
    if "前半" in text or "early" in lowered:
        return years + 2
    if "後半" in text or "late" in lowered:
        return years + 8
    return years + 5


def address_name(
    speaker: dict[str, Any], listener: dict[str, Any], language: str
) -> str:
    """speaker が listener を呼ぶときの呼び方(話す側のくせ・相手の名前と性別・年の差から作る)。

    名前は日本語なら「苗字 名前」、英語なら「Given Family」として分ける(区切りが無ければ
    名前全体を使う)。性別は心の性別で見る(入れ替わり・変身でも呼び方は変わらない)。
    相手が HAKONIWA_ADDRESS_ELDER_GAP 以上年上なら、ちゃん/くん・呼び捨ては さん にする。
    """
    lang = _lang(language)
    style = resident_address_style(speaker)
    name = resident_name(listener, lang)
    parts = name.split()
    if len(parts) >= 2:
        family, given = (parts[0], parts[-1]) if lang == "ja" else (parts[-1], parts[0])
    else:
        family = given = name
    own_age = age_years(str(resident_text(speaker, lang)["age"]))
    their_age = age_years(str(resident_text(listener, lang)["age"]))
    if (
        own_age is not None
        and their_age is not None
        and their_age - own_age >= HAKONIWA_ADDRESS_ELDER_GAP
    ):
        style = _ELDER_ADDRESS_STYLES.get(style, style)
    male = resident_gender(listener) == "male"
    if lang == "en":
        if style == "family_san":
            return f"{'Mr.' if male else 'Ms.'} {family}"
        return family if style == "family" else given
    if style == "given_chan":
        return given + ("くん" if male else "ちゃん")
    if style == "given_san":
        return given + "さん"
    if style == "family_san":
        return family + "さん"
    return family if style == "family" else given


def find_resident(state: dict[str, Any], resident_id: str) -> dict[str, Any]:
    resident = next(
        (item for item in state["residents"] if item["id"] == resident_id), None
    )
    if resident is None:
        raise HakoniwaError("resident_not_found", "住民が見つかりません")
    return resident


# --- 性別と姿 ---

_FEMALE_TOKEN = re.compile(r"\b\d*girls?\b|\b(?:woman|female)\b", re.IGNORECASE)
_MALE_TOKEN = re.compile(r"\b\d*boys?\b|\b(?:man|male)\b", re.IGNORECASE)


def tags_gender(tags: str) -> str | None:
    """タグ列の性別トークンから性別を返す(無ければ None)。"""
    text = str(tags or "")
    female = _FEMALE_TOKEN.search(text)
    male = _MALE_TOKEN.search(text)
    if female and (not male or female.start() < male.start()):
        return "female"
    if male:
        return "male"
    return None


def resident_gender(resident: dict[str, Any]) -> str:
    gender = resident.get("gender")
    return gender if gender in GENDERS else "female"


def swap_partner_id(state: dict[str, Any], resident_id: str) -> str | None:
    """入れ替わりの朝で入れ替わっている相手の id(入れ替わっていなければ None)。"""
    pair = state.get("swap_pair")
    if "swap" not in state.get("active_rules", []) or not pair:
        return None
    if resident_id == pair[0]:
        return pair[1]
    if resident_id == pair[1]:
        return pair[0]
    return None


def own_body_gender(state: dict[str, Any], resident: dict[str, Any]) -> str:
    """入れ替わりを考えない、本人の今の体の性別。

    変身中は変身のタグの性別、変身していなければ掟の姿が定める体の性別、どちらも
    無ければ本来の性別。
    """
    transformation = resident.get("transformation") or {}
    if transformation:
        return tags_gender(str(transformation.get("tags") or "")) or resident_gender(
            resident
        )
    return (
        active_look_body_gender(state)
        or memo_look_body_gender(state)
        or resident_gender(resident)
    )


def body_gender(state: dict[str, Any], resident: dict[str, Any]) -> str:
    """いま見えている体の性別。入れ替わり中は相手の体になる。"""
    partner_id = swap_partner_id(state, resident["id"])
    if partner_id:
        partner = next(
            (item for item in state["residents"] if item["id"] == partner_id), None
        )
        if partner is not None:
            return own_body_gender(state, partner)
    return own_body_gender(state, resident)


def appearance_kind(state: dict[str, Any], resident: dict[str, Any]) -> str | None:
    """物語に効く目立つ姿の種類: transform / combo / rule / memo / dress / None。

    表示と同じ優先順位。文章の文脈に使うので、画像の有無は見ない(掟の見た目のタグで決める)。
    """
    if current_transformation(state, resident) is not None:
        return "transform"
    if active_combo(state) is not None:
        return "combo"
    if look_rule_ids(state):
        return "rule"
    if active_memo_look(state) is not None:
        return "memo"
    if "dress" in state.get("active_rules", []):
        return "dress"
    return None


def is_male_in_feminine_form(state: dict[str, Any], resident: dict[str, Any]) -> bool:
    """本来は男性の住民が、いま女性的な姿(女性の体・ドレス・女性的な変身)かどうか。"""
    if resident_gender(resident) != "male":
        return False
    if body_gender(state, resident) == "female":
        return True
    kind = appearance_kind(state, resident)
    if kind == "dress":
        return True
    if kind == "transform":
        return is_feminine_transformation(state, resident)
    if kind in ("combo", "rule"):
        return has_feminine_marker(look_rules_tags(state, kind))
    if kind == "memo":
        return has_feminine_marker((active_memo_look(state) or {}).get("tags", ""))
    return False


_FEMININE_MARKERS = (
    "1girl",
    "dress",
    "skirt",
    "gown",
    "lingerie",
    "maid",
    "女装",
    "ドレス",
    "スカート",
    "女性",
    "女の子",
)


def has_feminine_marker(text: str) -> bool:
    haystack = str(text or "").lower()
    return any(marker in haystack for marker in _FEMININE_MARKERS)


def body_of(state: dict[str, Any], resident: dict[str, Any]) -> dict[str, Any]:
    """住民がいまいる体のエントリ(入れ替わり中は相手)。変身はこの体に付く。"""
    return story.body_of(state, resident)


def current_transformation(
    state: dict[str, Any], resident: dict[str, Any]
) -> dict[str, Any] | None:
    """住民がいまいる体の変身。文章も表示も、この変身を「いまの姿」として扱う。"""
    return story.current_transformation(state, resident)


def is_feminine_transformation(state: dict[str, Any], resident: dict[str, Any]) -> bool:
    transformation = current_transformation(state, resident) or {}
    return has_feminine_marker(
        f"{transformation.get('tags', '')} {transformation.get('description', '')}"
    )


# --- 掟の姿と複合の姿 ---


# 世界の常識の書き換えで決まる姿(掟の姿・複合の姿・世界のメモの姿)。本人も周りも
# 「昔からそう」と受け止める姿で、変身のような驚きの反応は描かせない
REALITY_LOOK_KINDS = frozenset({"rule", "combo", "memo"})


def is_reality_look(state: dict[str, Any], resident: dict[str, Any]) -> bool:
    """いまの姿が、世界の常識の書き換え(掟・メモ・住民の改変)で決まった姿か。"""
    kind = appearance_kind(state, resident)
    if kind == "transform":
        return (current_transformation(state, resident) or {}).get("kind") == "reality"
    return kind in REALITY_LOOK_KINDS


def custom_rule(state: dict[str, Any], rule_id: str) -> dict[str, Any] | None:
    return next(
        (rule for rule in state.get("custom_rules", []) if rule["id"] == rule_id), None
    )


def active_custom_rule_ids(state: dict[str, Any]) -> list[str]:
    """有効な自作の掟の id(有効にした順)。"""
    ids = set(custom_rule_ids(state))
    return [rule_id for rule_id in state.get("active_rules", []) if rule_id in ids]


def is_look_rule(rule: dict[str, Any] | None) -> bool:
    """住民の見た目を変える自作の掟か(見た目のタグか、体の性別の指定がある)。"""
    return bool(str((rule or {}).get("appearance_tags") or "").strip()) or (
        rule_body_gender(rule) is not None
    )


def look_rule_ids(state: dict[str, Any]) -> list[str]:
    """見た目を変える、有効な自作の掟の id(有効にした順)。"""
    return [
        rule_id
        for rule_id in active_custom_rule_ids(state)
        if is_look_rule(custom_rule(state, rule_id))
    ]


def combo_digest(rule_ids: list[str], includes_dress: bool) -> str:
    components = sorted([*rule_ids, *(["dress"] if includes_dress else [])])
    return hashlib.sha1(",".join(components).encode("utf-8")).hexdigest()[:10]


def active_combo(state: dict[str, Any]) -> dict[str, Any] | None:
    """いま重なっている見た目の掟の組み合わせ(複合の姿の対象)。

    見た目を変える自作の掟が1つ以上あり、ドレスの掟と合わせて2つ以上のときだけ。
    """
    rule_ids = look_rule_ids(state)
    includes_dress = "dress" in state.get("active_rules", [])
    if not rule_ids or len(rule_ids) + (1 if includes_dress else 0) < 2:
        return None
    return {
        "digest": combo_digest(rule_ids, includes_dress),
        "rule_ids": rule_ids,
        "includes_dress": includes_dress,
    }


def combo_tags(state: dict[str, Any], rule_ids: list[str]) -> str:
    """組み合わせの掟の見た目のタグを、有効にした順につなげる。"""
    return ", ".join(
        str((custom_rule(state, rule_id) or {}).get("appearance_tags") or "").strip()
        for rule_id in rule_ids
        if str((custom_rule(state, rule_id) or {}).get("appearance_tags") or "").strip()
    )


def look_rules_tags(state: dict[str, Any], kind: str) -> str:
    """いまの掟の姿(combo / rule)を決めている見た目のタグ。"""
    if kind == "combo":
        combo = active_combo(state)
        if combo is None:
            return ""
        tags = combo_tags(state, combo["rule_ids"])
        return f"{tags}, dress" if combo["includes_dress"] else tags
    ids = look_rule_ids(state)
    return combo_tags(state, ids[-1:]) if ids else ""


def rule_body_gender(rule: dict[str, Any] | None) -> str | None:
    """自作の掟が掟の姿で住民の体をする性別(None は住民それぞれのまま)。"""
    gender = (rule or {}).get("body_gender")
    return gender if gender in GENDERS else None


def look_body_gender(state: dict[str, Any], rule_ids: list[str]) -> str | None:
    """掟の組み合わせが定める体の性別。後から有効にした掟が勝つ。"""
    for rule_id in reversed(rule_ids):
        gender = rule_body_gender(custom_rule(state, rule_id))
        if gender:
            return gender
    return None


def active_look_body_gender(state: dict[str, Any]) -> str | None:
    """いまの掟の姿(複合の姿か、最後に有効にした見た目の掟)が定める体の性別。"""
    combo = active_combo(state)
    rule_ids = combo["rule_ids"] if combo else look_rule_ids(state)[-1:]
    return look_body_gender(state, rule_ids)


def look_entry_is_current(entry: dict[str, Any], tags: str, body: str | None) -> bool:
    """生成済みの姿が、今の見た目のタグと体の性別で作ったものか。"""
    return bool(tags or body) and (
        entry.get("source_tags") == tags and entry.get("source_body") == body
    )


def _look_status(
    state: dict[str, Any], field: str, key: str, tags: str, body: str | None
) -> dict[str, Any]:
    ready = stale = 0
    pending: list[str] = []
    for resident in state["residents"]:
        entry = (resident.get(field) or {}).get(key)
        if not entry or not entry.get("image"):
            pending.append(resident["id"])
            continue
        if look_entry_is_current(entry, tags, body):
            ready += 1
        else:
            stale += 1
            pending.append(resident["id"])
    return {
        "ready": ready,
        "stale": stale,
        "total": len(state["residents"]),
        "pending": pending,
    }


def rule_look_status(state: dict[str, Any], rule_id: str) -> dict[str, Any]:
    """掟の姿の生成状況。ready は今の見た目で生成済み、stale は見た目を変える前の姿。"""
    rule = custom_rule(state, rule_id)
    tags = str((rule or {}).get("appearance_tags") or "")
    return _look_status(state, "rule_images", rule_id, tags, rule_body_gender(rule))


def combo_look_status(state: dict[str, Any], combo: dict[str, Any]) -> dict[str, Any]:
    return _look_status(
        state,
        "combo_images",
        combo["digest"],
        combo_tags(state, combo["rule_ids"]),
        look_body_gender(state, combo["rule_ids"]),
    )


# 世界のメモの姿: メモから LLM が作った、住民全員に効く見た目の変化
# state["memo_look"] = {memo: 作った元のメモ, tags, body_gender}、住民の memo_images[MEMO_LOOK_KEY]
MEMO_LOOK_KEY = "memo"
_LOOK_IMAGE_FIELDS = {
    "rule": "rule_images",
    "combo": "combo_images",
    "memo": "memo_images",
}


def look_image_field(kind: str) -> str:
    """掟の姿・複合の姿・メモの姿の画像を持つ住民の項目名。"""
    return _LOOK_IMAGE_FIELDS[kind]


def _normalize_memo_look(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    tags = str(value.get("tags") or "").strip()
    body = rule_body_gender(value)
    if not tags and body is None:
        return None
    return {"memo": str(value.get("memo") or ""), "tags": tags, "body_gender": body}


def active_memo_look(state: dict[str, Any]) -> dict[str, Any] | None:
    """いまの世界のメモから作った姿の指定 {tags, body_gender}(メモを変えたあとは無効)。"""
    look = _normalize_memo_look(state.get("memo_look"))
    if look is None or look["memo"] != play.world_memo(state):
        return None
    return {"tags": look["tags"], "body_gender": look["body_gender"]}


def memo_look_planned(state: dict[str, Any]) -> bool:
    """いまの世界のメモについて、姿に関わるかをもう確かめたか(関わらないと分かった場合も含む)。"""
    planned = state.get("memo_look_planned_for")
    return planned is not None and planned == play.world_memo(state)


def memo_look_body_gender(state: dict[str, Any]) -> str | None:
    return (active_memo_look(state) or {}).get("body_gender")


def set_memo_look(
    state: dict[str, Any], tags: str, body_gender: str | None
) -> dict[str, Any]:
    """いまの世界のメモから作った姿の指定を保存する。タグも体の性別も無ければ消す。"""
    new_state = deepcopy(state)
    memo = play.world_memo(new_state)
    look = _normalize_memo_look(
        {"memo": memo, "tags": tags, "body_gender": body_gender}
    )
    new_state["memo_look"] = look
    new_state["memo_look_planned_for"] = memo
    return new_state


def memo_look_status(state: dict[str, Any]) -> dict[str, Any] | None:
    """メモの姿の生成状況(メモが姿を変えていなければ None)。"""
    look = active_memo_look(state)
    if look is None:
        return None
    return _look_status(
        state, "memo_images", MEMO_LOOK_KEY, look["tags"], look["body_gender"]
    )


def current_memo_look_tags(state: dict[str, Any], resident: dict[str, Any]) -> str:
    """住民のメモの姿のタグ(いまのメモで生成済みのときだけ。掟の姿の元にする)。"""
    look = active_memo_look(state)
    if look is None:
        return ""
    entry = (resident.get("memo_images") or {}).get(MEMO_LOOK_KEY) or {}
    if entry.get("image") and look_entry_is_current(
        entry, look["tags"], look["body_gender"]
    ):
        return str(entry.get("tags") or "")
    return ""


def set_look_image(
    state: dict[str, Any],
    resident_id: str,
    *,
    kind: str,
    key: str,
    entry: dict[str, Any],
) -> dict[str, Any]:
    """住民の掟の姿(kind=rule, key=掟 id)・複合の姿(kind=combo, key=組み合わせ)・
    メモの姿(kind=memo, key=MEMO_LOOK_KEY)を設定する。"""
    new_state = deepcopy(state)
    target = find_resident(new_state, resident_id)
    field = look_image_field(kind)
    images = dict(target.get(field) or {})
    images[key] = {
        "image": str(entry["image"]),
        "tags": str(entry.get("tags") or ""),
        "source_tags": str(entry.get("source_tags") or ""),
        "source_body": rule_body_gender({"body_gender": entry.get("source_body")}),
    }
    target[field] = images
    return new_state


# --- 表示する姿 ---


def own_look(state: dict[str, Any], resident: dict[str, Any]) -> dict[str, Any]:
    """入れ替わりを考えない、本人の今の姿。

    戻り値 {kind: transform | combo | rule | memo | dress | base, file: 世界フォルダの画像名 | None,
    bundled: 同梱素材を使うか, tags?: その姿のタグ}。優先順位は 変身 → 複合の姿 →
    掟の姿(後から有効にした掟が勝つ) → 世界のメモの姿 → ドレス(掟が有効で画像あり) → 通常。
    複合の姿・掟の姿・メモの姿は、その住民の画像が生成済みのときだけ。
    """
    transformation = resident.get("transformation") or {}
    if transformation.get("image"):
        return {
            "kind": "transform",
            "file": transformation["image"],
            "bundled": False,
            "tags": str(transformation.get("tags") or ""),
        }
    combo = active_combo(state)
    if combo is not None:
        entry = (resident.get("combo_images") or {}).get(combo["digest"])
        if entry and entry.get("image"):
            return {
                "kind": "combo",
                "file": entry["image"],
                "bundled": False,
                "tags": str(entry.get("tags") or ""),
            }
    for rule_id in reversed(active_custom_rule_ids(state)):
        entry = (resident.get("rule_images") or {}).get(rule_id)
        if entry and entry.get("image"):
            return {
                "kind": "rule",
                "file": entry["image"],
                "bundled": False,
                "tags": str(entry.get("tags") or ""),
                "rule_id": rule_id,
            }
    if active_memo_look(state) is not None:
        entry = (resident.get("memo_images") or {}).get(MEMO_LOOK_KEY)
        if entry and entry.get("image"):
            return {
                "kind": "memo",
                "file": entry["image"],
                "bundled": False,
                "tags": str(entry.get("tags") or ""),
            }
    is_preset = resident.get("source") == "preset"
    if "dress" in state.get("active_rules", []):
        if resident.get("dress_image"):
            return {"kind": "dress", "file": resident["dress_image"], "bundled": False}
        if is_preset:
            return {"kind": "dress", "file": None, "bundled": True}
    if resident.get("avatar_image"):
        return {"kind": "base", "file": resident["avatar_image"], "bundled": False}
    return {"kind": "base", "file": None, "bundled": is_preset}


def display_look(state: dict[str, Any], resident: dict[str, Any]) -> dict[str, Any]:
    """表示する姿。入れ替わり中は相手の姿(相手自身の優先順位で決めた姿)になる。

    戻り値は own_look に owner(姿の持ち主の住民 id)を足したもの。
    """
    partner_id = swap_partner_id(state, resident["id"])
    owner = resident
    if partner_id:
        partner = next(
            (item for item in state["residents"] if item["id"] == partner_id), None
        )
        if partner is not None:
            owner = partner
    return {**own_look(state, owner), "owner": owner["id"]}


# --- 世界の作成 ---


def _base_resident(**fields: Any) -> dict[str, Any]:
    resident = {
        "id": "",
        "source": "custom",
        "preset_id": None,
        "character_preset_id": None,
        "name": "",
        "gender": "female",
        "age": "",
        "job": "",
        "personality": "",
        "pronoun": "",
        "speech_style": "",
        # 空ならプリセットのくせか既定(resident_address_style)
        "address_style": "",
        "appearance_text": "",
        "base_tags": "",
        "dress_text": "",
        "dress_tags": "",
        # プレイヤーがタグを書き換えたか。プリセットの描き直しの版でタグを上書きしない
        "base_tags_manual": False,
        "dress_tags_manual": False,
        "avatar_image": None,
        "dress_image": None,
        "mood": HAKONIWA_CUSTOM_RESIDENT_INITIAL_MOOD,
        "affinities": {},
        # プレイヤーへの好感度(-50..50)。会話の中身で動き、一言・タッチ・会話の口調に効く
        "player_affinity": 0,
        "transformation": None,
        "transformation_history": [],
        # 住民の改変: その住民についての世界の常識 [{id, text, day}]。本人も周りも昔からそうだと受け止める
        "realities": [],
        "rule_images": {},
        "combo_images": {},
        "memo_images": {},
        "current_area": DEFAULT_AREA_ID,
        "adaptation": None,
        "remnant": None,
        # プリセット住民の設定の版(HAKONIWA_PRESET_REVISIONS)。自作の住民は 1 のまま
        "preset_revision": 1,
    }
    resident.update(fields)
    return resident


def upgrade_preset_resident(entry: dict[str, Any]) -> dict[str, Any]:
    """作り直したプリセット住民(版が上がったもの)を、既存の世界でも新しい設定にする。

    人物そのものを変えた版(HAKONIWA_PRESET_CHARACTER_REVISIONS)をまたぐときは、性別・画像
    タグを新しい設定にし、古い姿で生成した画像(通常・ドレス・掟の姿・複合の姿)を外して
    同梱の立ち絵に戻す。描き直しだけの版では、プレイヤーが外見を書き換えていない住民の
    画像タグだけを新しくする(生成した画像は残す)。名前・性格の書き換えはどちらも残す。
    """
    preset_id = str(entry.get("preset_id") or "")
    revision = HAKONIWA_PRESET_REVISIONS.get(preset_id)
    if entry.get("source") != "preset" or revision is None:
        return entry
    try:
        current = int(entry.get("preset_revision") or 1)
    except (TypeError, ValueError):
        current = 1
    if current >= revision:
        return entry
    preset = HAKONIWA_PRESET_MAP[preset_id]
    if current < HAKONIWA_PRESET_CHARACTER_REVISIONS.get(preset_id, 0):
        # 人物そのものが変わる版では、手で直したタグも新しい人物のタグに戻す
        entry.update(
            gender=preset["gender"],
            base_tags=preset["base_tags"],
            dress_tags=preset["dress_tags"],
            base_tags_manual=False,
            dress_tags_manual=False,
            avatar_image=None,
            dress_image=None,
            rule_images={},
            combo_images={},
        )
    else:
        # 手で直したタグは、描き直しの版でも残す
        if not str(entry.get("appearance_text") or "").strip() and not entry.get(
            "base_tags_manual"
        ):
            entry["base_tags"] = preset["base_tags"]
        if not str(entry.get("dress_text") or "").strip() and not entry.get(
            "dress_tags_manual"
        ):
            entry["dress_tags"] = preset["dress_tags"]
    entry["preset_revision"] = revision
    return entry


def preset_resident(preset_id: str) -> dict[str, Any]:
    """プリセット住民の初期エントリ(名前などの表示文は空にして言語で引く)。"""
    preset = HAKONIWA_PRESET_MAP.get(preset_id)
    if preset is None:
        raise HakoniwaError("preset_not_found", "プリセットの住民が見つかりません")
    return _base_resident(
        id=preset_id,
        source="preset",
        preset_id=preset_id,
        gender=preset["gender"],
        base_tags=preset["base_tags"],
        dress_tags=preset["dress_tags"],
        mood=int(preset["initial_mood"]),
        current_area=str(preset.get("initial_area") or DEFAULT_AREA_ID),
        preset_revision=HAKONIWA_PRESET_REVISIONS.get(preset_id, 1),
    )


def character_resident(
    character_preset_id: str,
    profile: dict[str, Any],
    *,
    gender: str,
    avatar_image: str | None,
) -> dict[str, Any]:
    """TSF Closet のキャラクターから住民エントリを作る(人物像はその時点の写し)。"""
    if gender not in GENDERS:
        raise HakoniwaError("invalid_gender", "性別を選んでください")
    name = str(profile.get("name") or "").strip()[:HAKONIWA_RESIDENT_NAME_MAX]
    if not name:
        raise HakoniwaError("empty_name", "キャラクターの名前がありません")
    # 性格が無いキャラクターだけ、人物メモ(無ければ外見の説明)で補う
    combined = (
        str(profile.get("personality") or "").strip()
        or str(profile.get("description") or "").strip()
    )
    return _base_resident(
        id="chr_" + uuid.uuid4().hex[:10],
        source="character",
        character_preset_id=character_preset_id,
        name=name,
        gender=gender,
        personality=combined[:HAKONIWA_PERSONALITY_MAX],
        pronoun=str(profile.get("pronoun") or "")[:20],
        base_tags=ensure_gender_token(str(profile.get("base_tags") or ""), gender),
        avatar_image=avatar_image,
    )


def _clean_text(value: Any, max_length: int, *, required: bool, code: str) -> str:
    text = " ".join(str(value or "").split()) if value is not None else ""
    if required and not text:
        raise HakoniwaError(code, "必須の項目が空です")
    if len(text) > max_length:
        raise HakoniwaError(code, f"{max_length}文字以内で入力してください")
    return text


def ensure_gender_token(tags: str, gender: str) -> str:
    """画像タグに性別トークンが無ければ先頭に補う(無いと女性寄りに描かれる)。"""
    cleaned = str(tags or "").strip().strip(",").strip()
    if not cleaned:
        return DEFAULT_BASE_TAGS.get(gender, DEFAULT_BASE_TAGS["female"])
    if tags_gender(cleaned) is not None:
        return cleaned
    token = "1boy" if gender == "male" else "1girl"
    return f"{token}, {cleaned}"


# 体の性別を差し替えるとき外す、性別のタグ(人数を表す 2girls なども含む)
_GENDER_TAG = re.compile(
    r"^(?:\d*\+?(?:girl|boy)s?|woman|man|female|male|(?:male|female) focus)$",
    re.IGNORECASE,
)


def set_gender_token(tags: str, gender: str) -> str:
    """画像タグの性別トークンを、指定した体の性別のものに差し替えて先頭に置く。"""
    cleaned = str(tags or "").strip().strip(",").strip()
    if not cleaned:
        return DEFAULT_BASE_TAGS.get(gender, DEFAULT_BASE_TAGS["female"])
    kept = [
        tag.strip()
        for tag in cleaned.split(",")
        if tag.strip() and not _GENDER_TAG.match(tag.strip())
    ]
    token = "1boy" if gender == "male" else "1girl"
    return ", ".join([token, *kept])


def custom_resident(
    *,
    name: str,
    personality: str,
    gender: str,
    appearance_text: str,
    base_tags: str,
    dress_text: str = "",
    dress_tags: str = "",
    age: str = "",
    job: str = "",
    pronoun: str = "",
    address_style: str = "",
) -> dict[str, Any]:
    """プレイヤーが書いた住民(おまかせの住民を含む)のエントリ。

    base_tags / dress_tags は変換済みの派生値。age / job / pronoun は空なら表示の既定値になる。
    """
    if gender not in GENDERS:
        raise HakoniwaError("invalid_gender", "性別の指定が正しくありません")
    return _base_resident(
        id="custom_" + uuid.uuid4().hex[:10],
        source="custom",
        name=_clean_text(
            name, HAKONIWA_RESIDENT_NAME_MAX, required=True, code="invalid_name"
        ),
        gender=gender,
        personality=_clean_text(
            personality,
            HAKONIWA_PERSONALITY_MAX,
            required=True,
            code="invalid_personality",
        ),
        appearance_text=_clean_text(
            appearance_text,
            HAKONIWA_APPEARANCE_TEXT_MAX,
            required=False,
            code="invalid_appearance",
        ),
        base_tags=ensure_gender_token(base_tags, gender),
        dress_text=_clean_text(
            dress_text,
            HAKONIWA_APPEARANCE_TEXT_MAX,
            required=False,
            code="invalid_appearance",
        ),
        dress_tags=ensure_gender_token(dress_tags, gender) if dress_tags else "",
        age=str(age or "").strip(),
        job=str(job or "").strip(),
        pronoun=str(pronoun or "").strip(),
        address_style=clean_address_style(address_style),
    )


def new_world_state(
    residents: list[dict[str, Any]], *, dissonance_enabled: bool = True
) -> dict[str, Any]:
    """住民の一覧から新しい世界を作る。プリセット同士は初期の好感度、他は 0 で結ぶ。

    dissonance_enabled は「世界の違和感」を使うか(世界ごと、既定 ON)。
    """
    if len(residents) < HAKONIWA_MIN_RESIDENTS:
        raise HakoniwaError(
            "too_few_residents", f"住民は{HAKONIWA_MIN_RESIDENTS}人以上必要です"
        )
    if len(residents) > HAKONIWA_MAX_RESIDENTS:
        raise HakoniwaError(
            "too_many_residents", f"住民は{HAKONIWA_MAX_RESIDENTS}人までです"
        )
    entries = [deepcopy(resident) for resident in residents]
    ids = [entry["id"] for entry in entries]
    if len(set(ids)) != len(ids):
        raise HakoniwaError("duplicate_resident", "同じ住民が重複しています")
    for entry in entries:
        preset = HAKONIWA_PRESET_MAP.get(str(entry.get("preset_id") or ""))
        initial = preset["initial_affinities"] if preset else {}
        entry["affinities"] = {
            other: int(initial.get(other, 0)) for other in ids if other != entry["id"]
        }
    return {
        "version": STATE_VERSION,
        "day": 1,
        "image_model": HAKONIWA_IMAGE_MODEL_DEFAULT,
        "web_search_enabled": False,
        "active_rules": [],
        "swap_pair": None,
        "last_pair": None,
        "custom_rules": [],
        "residents": entries,
        "events": [],
        "furniture_layout": empty_furniture_layout(),
        "last_digest": None,
        **story.initial_story_state(dissonance_enabled=dissonance_enabled),
        **play.initial_play_state(),
    }


def empty_furniture_layout() -> dict[str, list[str | None]]:
    return {area["id"]: [None] * HAKONIWA_FURNITURE_SLOTS for area in HAKONIWA_AREAS}


def _normalize_furniture_layout(layout: Any) -> dict[str, list[str | None]]:
    """家具の配置をエリアとスロットの数にそろえ、知らない家具・重複を外す。"""
    normalized = empty_furniture_layout()
    seen: set[str] = set()
    source = layout if isinstance(layout, dict) else {}
    for area_id, slots in normalized.items():
        for index, furniture_id in enumerate(
            list(source.get(area_id) or [])[: len(slots)]
        ):
            if furniture_id in HAKONIWA_FURNITURE_MAP and furniture_id not in seen:
                slots[index] = furniture_id
                seen.add(furniture_id)
    return normalized


def normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    """読み込んだ状態の欠けた項目を既定値で補う。"""
    normalized = {
        "version": STATE_VERSION,
        "day": max(1, int(state.get("day") or 1)),
        "image_model": str(state.get("image_model") or HAKONIWA_IMAGE_MODEL_DEFAULT),
        "web_search_enabled": state.get("web_search_enabled") is True,
        "active_rules": list(state.get("active_rules") or []),
        "swap_pair": list(state["swap_pair"]) if state.get("swap_pair") else None,
        "last_pair": list(state["last_pair"]) if state.get("last_pair") else None,
        "custom_rules": [
            {
                "appearance_text": "",
                "appearance_tags": "",
                "body_gender": None,
                **dict(rule),
            }
            for rule in state.get("custom_rules") or []
        ],
        "residents": [],
        "events": [dict(event) for event in state.get("events") or []],
        "furniture_layout": _normalize_furniture_layout(state.get("furniture_layout")),
        "last_digest": state.get("last_digest")
        if isinstance(state.get("last_digest"), dict)
        else None,
        "memo_look": _normalize_memo_look(state.get("memo_look")),
        "memo_look_planned_for": state.get("memo_look_planned_for")
        if isinstance(state.get("memo_look_planned_for"), str)
        else None,
    }
    for resident in state.get("residents") or []:
        entry = _base_resident(**resident)
        if entry.get("current_area") not in HAKONIWA_AREA_MAP:
            entry["current_area"] = DEFAULT_AREA_ID
        entry["affinities"] = {
            str(key): int(value)
            for key, value in (resident.get("affinities") or {}).items()
        }
        entry["player_affinity"] = _clamp(
            _int_or_zero(resident.get("player_affinity")),
            HAKONIWA_AFFINITY_MIN,
            HAKONIWA_AFFINITY_MAX,
        )
        entry["transformation_history"] = list(
            resident.get("transformation_history") or []
        )
        entry["realities"] = [
            {
                "id": str(item["id"]),
                "text": str(item.get("text") or ""),
                "day": int(item.get("day") or 1),
            }
            for item in resident.get("realities") or []
            if isinstance(item, dict) and item.get("id") and item.get("text")
        ][-HAKONIWA_REALITIES_MAX:]
        for field in ("rule_images", "combo_images", "memo_images"):
            images = resident.get(field)
            entry[field] = {
                str(key): dict(value)
                for key, value in (images.items() if isinstance(images, dict) else [])
                if isinstance(value, dict) and value.get("image")
            }
        entry = upgrade_preset_resident(entry)
        normalized["residents"].append(entry)
    ids = {resident["id"] for resident in normalized["residents"]}
    if normalized["swap_pair"] and not set(normalized["swap_pair"]) <= ids:
        normalized["swap_pair"] = None
    story.normalize_story(state, normalized)
    play.normalize_play(state, normalized)
    return normalized


# --- 掟 ---


def custom_rule_ids(state: dict[str, Any]) -> list[str]:
    return [rule["id"] for rule in state.get("custom_rules", [])]


def set_rule(
    state: dict[str, Any], card_id: str, active: bool, rng: random.Random
) -> dict[str, Any]:
    """掟の有効化・解除を適用した状態を返す。同時に有効にできるのは3枚まで。"""
    if card_id not in HAKONIWA_RULE_MAP and card_id not in custom_rule_ids(state):
        raise HakoniwaError("rule_not_found", "掟が見つかりません")
    new_state = deepcopy(state)
    rules = new_state["active_rules"]
    if active:
        if card_id in rules:
            return new_state
        if len(rules) >= HAKONIWA_MAX_ACTIVE_RULES:
            raise HakoniwaError(
                "too_many_rules",
                f"有効にできる掟は{HAKONIWA_MAX_ACTIVE_RULES}枚までです",
            )
        rules.append(card_id)
        if card_id == "swap":
            ids = [resident["id"] for resident in new_state["residents"]]
            new_state["swap_pair"] = rng.sample(ids, 2)
            # 入れ替わった二人は、新しい体への適応を始める
            for resident in new_state["residents"]:
                if resident["id"] in new_state["swap_pair"]:
                    story.start_adaptation(resident, "swap", int(new_state["day"]))
    else:
        if card_id in rules:
            rules.remove(card_id)
        if card_id == "swap":
            former = list(state.get("swap_pair") or [])
            new_state["swap_pair"] = None
            # 入れ替わりが解けた二人には、適応の進み具合に応じた名残が残る
            for resident in new_state["residents"]:
                if resident["id"] in former:
                    partner = next(
                        (pid for pid in former if pid != resident["id"]), None
                    )
                    story.end_adaptation(
                        resident, "swap", int(new_state["day"]), partner
                    )
                    _resume_transform_adaptation(resident, int(new_state["day"]))
    return new_state


def _resume_transform_adaptation(resident: dict[str, Any], day: int) -> None:
    """入れ替わりから戻った体が変身していれば、その変身への適応を始める(名残は残す)。"""
    if resident.get("transformation") and not resident.get("adaptation"):
        resident["adaptation"] = story.new_adaptation("transform", day)


def validate_custom_rule(
    name: Any, text: Any, appearance_text: Any = ""
) -> dict[str, str]:
    return {
        "name": _clean_text(
            name, HAKONIWA_CUSTOM_RULE_NAME_MAX, required=True, code="invalid_rule_name"
        ),
        "text": _clean_text(
            text, HAKONIWA_CUSTOM_RULE_TEXT_MAX, required=True, code="invalid_rule_text"
        ),
        "appearance_text": _clean_text(
            appearance_text,
            HAKONIWA_RULE_APPEARANCE_TEXT_MAX,
            required=False,
            code="invalid_rule_appearance",
        ),
    }


def add_custom_rule(
    state: dict[str, Any],
    name: Any,
    text: Any,
    appearance_text: Any = "",
    appearance_tags: str = "",
    body_gender: str | None = None,
) -> dict[str, Any]:
    """自作の掟を足す。appearance_tags は整えたタグ(空なら見た目のタグ無し)。"""
    if len(state.get("custom_rules", [])) >= HAKONIWA_CUSTOM_RULES_MAX:
        raise HakoniwaError(
            "too_many_custom_rules", f"自作の掟は{HAKONIWA_CUSTOM_RULES_MAX}個までです"
        )
    rule = {
        "id": "custom_rule_" + uuid.uuid4().hex[:10],
        **validate_custom_rule(name, text, appearance_text),
        "appearance_tags": str(appearance_tags or ""),
        "body_gender": rule_body_gender({"body_gender": body_gender}),
    }
    new_state = deepcopy(state)
    new_state["custom_rules"].append(rule)
    return new_state


def update_custom_rule(
    state: dict[str, Any],
    rule_id: str,
    name: Any,
    text: Any,
    appearance_text: Any = "",
    appearance_tags: str | None = None,
    body_gender: str | None = None,
) -> dict[str, Any]:
    """自作の掟を書き換える。appearance_tags が None なら見た目のタグは変えない。

    body_gender は掟の姿の体の性別(None は住民それぞれのまま)で、毎回書き換える。
    """
    new_state = deepcopy(state)
    target = custom_rule(new_state, rule_id)
    if target is None:
        raise HakoniwaError("rule_not_found", "掟が見つかりません")
    target.update(validate_custom_rule(name, text, appearance_text))
    target["body_gender"] = rule_body_gender({"body_gender": body_gender})
    if appearance_tags is not None:
        target["appearance_tags"] = str(appearance_tags)
    return new_state


def delete_custom_rule(state: dict[str, Any], rule_id: str) -> dict[str, Any]:
    if rule_id not in custom_rule_ids(state):
        raise HakoniwaError("rule_not_found", "掟が見つかりません")
    new_state = deepcopy(state)
    new_state["custom_rules"] = [
        rule for rule in new_state["custom_rules"] if rule["id"] != rule_id
    ]
    new_state["active_rules"] = [
        card_id for card_id in new_state["active_rules"] if card_id != rule_id
    ]
    # 消した掟の姿は使われなくなる(複合の姿は組み合わせが変わるので自然に外れる)
    for resident in new_state["residents"]:
        (resident.get("rule_images") or {}).pop(rule_id, None)
    return new_state


def active_custom_rules(state: dict[str, Any]) -> list[dict[str, Any]]:
    """有効な自作の掟(有効にした順)。"""
    by_id = {rule["id"]: rule for rule in state.get("custom_rules", [])}
    return [
        by_id[card_id] for card_id in state.get("active_rules", []) if card_id in by_id
    ]


# --- 住民の追加・編集・削除 ---


def add_resident(state: dict[str, Any], resident: dict[str, Any]) -> dict[str, Any]:
    """住民を加え、既存の全住民と好感度 0 で結ぶ。"""
    if len(state["residents"]) >= HAKONIWA_MAX_RESIDENTS:
        raise HakoniwaError(
            "too_many_residents", f"住民は{HAKONIWA_MAX_RESIDENTS}人までです"
        )
    if any(item["id"] == resident["id"] for item in state["residents"]):
        raise HakoniwaError("duplicate_resident", "同じ住民がすでにいます")
    new_state = deepcopy(state)
    entry = deepcopy(resident)
    entry["affinities"] = {item["id"]: 0 for item in new_state["residents"]}
    for item in new_state["residents"]:
        item["affinities"][entry["id"]] = 0
    new_state["residents"].append(entry)
    return new_state


def update_resident(
    state: dict[str, Any], resident_id: str, fields: dict[str, Any]
) -> dict[str, Any]:
    """住民の名前・性格・外見などを書き換えた状態を返す(fields は検証済みの値)。"""
    new_state = deepcopy(state)
    target = find_resident(new_state, resident_id)
    allowed = {
        "name",
        "personality",
        "gender",
        "appearance_text",
        "base_tags",
        "dress_text",
        "dress_tags",
        "avatar_image",
        "dress_image",
        "address_style",
        "base_tags_manual",
        "dress_tags_manual",
    }
    for key, value in fields.items():
        if key in allowed:
            target[key] = value
    return new_state


def validate_resident_fields(
    *,
    name: Any,
    personality: Any,
    gender: Any,
    appearance_text: Any,
    dress_text: Any,
    address_style: Any = "",
) -> dict[str, str]:
    if gender not in GENDERS:
        raise HakoniwaError("invalid_gender", "性別の指定が正しくありません")
    return {
        "address_style": clean_address_style(address_style),
        "name": _clean_text(
            name, HAKONIWA_RESIDENT_NAME_MAX, required=True, code="invalid_name"
        ),
        "personality": _clean_text(
            personality,
            HAKONIWA_PERSONALITY_MAX,
            required=True,
            code="invalid_personality",
        ),
        "gender": str(gender),
        "appearance_text": _clean_text(
            appearance_text,
            HAKONIWA_APPEARANCE_TEXT_MAX,
            required=False,
            code="invalid_appearance",
        ),
        "dress_text": _clean_text(
            dress_text,
            HAKONIWA_APPEARANCE_TEXT_MAX,
            required=False,
            code="invalid_appearance",
        ),
    }


def remove_resident(state: dict[str, Any], resident_id: str) -> dict[str, Any]:
    """住民を外す。好感度の参照を消し、入れ替わり中なら入れ替わりを解く。"""
    find_resident(state, resident_id)
    if len(state["residents"]) <= HAKONIWA_MIN_RESIDENTS:
        raise HakoniwaError(
            "too_few_residents", f"住民は{HAKONIWA_MIN_RESIDENTS}人以上必要です"
        )
    new_state = deepcopy(state)
    new_state["residents"] = [
        item for item in new_state["residents"] if item["id"] != resident_id
    ]
    for item in new_state["residents"]:
        item["affinities"].pop(resident_id, None)
    if new_state.get("swap_pair") and resident_id in new_state["swap_pair"]:
        # 残った相手は自分の体へ戻る
        for item in new_state["residents"]:
            if item["id"] in new_state["swap_pair"]:
                story.end_adaptation(item, "swap", int(new_state["day"]), resident_id)
                _resume_transform_adaptation(item, int(new_state["day"]))
        new_state["swap_pair"] = None
        new_state["active_rules"] = [
            card_id for card_id in new_state["active_rules"] if card_id != "swap"
        ]
    if new_state.get("last_pair") and resident_id in new_state["last_pair"]:
        new_state["last_pair"] = None
    return play.forget_chat(story.forget_resident(new_state, resident_id), resident_id)


# --- 主役の組の選出 ---


def _romance_active(state: dict[str, Any]) -> bool:
    return bool(ROMANCE_RULE_IDS.intersection(state.get("active_rules", [])))


def _male_bodies(state: dict[str, Any], *residents: dict[str, Any]) -> bool:
    """組の全員が男性の体かどうか(恋愛の題材にしない組の判定)。"""
    return all(body_gender(state, resident) == "male" for resident in residents)


def _pair_weights(
    state: dict[str, Any],
) -> tuple[list[tuple[dict, dict]], list[float]]:
    """全ペアと選出の重み。好感度の振れが大きいペアを少し優先する。

    恋愛を主題にしやすい掟が有効な間は、男性の体同士のペアの重みを 0 にする。
    """
    residents = state["residents"]
    romance = _romance_active(state)
    pairs: list[tuple[dict, dict]] = []
    weights: list[float] = []
    for index, a in enumerate(residents):
        for b in residents[index + 1 :]:
            pairs.append((a, b))
            if romance and _male_bodies(state, a, b):
                weights.append(0.0)
                continue
            affinity = a["affinities"].get(b["id"], 0)
            weights.append(1.0 + abs(affinity) / 12.0)
    return pairs, weights


def _swap_guaranteed_pair(state: dict[str, Any]) -> tuple[dict, dict] | None:
    pair = state.get("swap_pair")
    if "swap" not in state.get("active_rules", []) or not pair:
        return None
    by_id = {resident["id"]: resident for resident in state["residents"]}
    if pair[0] in by_id and pair[1] in by_id:
        return (by_id[pair[0]], by_id[pair[1]])
    return None


def _fill_pairs(
    state: dict[str, Any],
    rng: random.Random,
    count: int,
    chosen: list[tuple],
    used_keys: set[frozenset],
) -> None:
    """chosen へペアを count 組まで加える(同日の重複と直前のペアを避ける)。"""
    pairs, weights = _pair_weights(state)
    last_key = frozenset(state["last_pair"]) if state.get("last_pair") else None
    while len(chosen) < count:
        candidates = [
            (pair, weight)
            for pair, weight in zip(pairs, weights, strict=True)
            if weight > 0
            and frozenset((pair[0]["id"], pair[1]["id"])) not in used_keys
            and frozenset((pair[0]["id"], pair[1]["id"])) != last_key
        ]
        if not candidates:
            candidates = [
                (pair, weight)
                for pair, weight in zip(pairs, weights, strict=True)
                if weight > 0
                and frozenset((pair[0]["id"], pair[1]["id"])) not in used_keys
            ]
        if not candidates:
            break
        picked = rng.choices(
            [item[0] for item in candidates],
            weights=[item[1] for item in candidates],
            k=1,
        )[0]
        chosen.append(picked)
        used_keys.add(frozenset((picked[0]["id"], picked[1]["id"])))


def _pick_trio(
    state: dict[str, Any], rng: random.Random, used_keys: set[frozenset]
) -> tuple[dict, dict, dict] | None:
    residents = state["residents"]
    if len(residents) < 3:
        return None
    pairs, pair_weights = _pair_weights(state)
    weight_by_key = {
        frozenset((a["id"], b["id"])): weight
        for (a, b), weight in zip(pairs, pair_weights, strict=True)
    }
    trios: list[tuple[dict, dict, dict]] = []
    weights: list[float] = []
    for i, a in enumerate(residents):
        for j in range(i + 1, len(residents)):
            for k in range(j + 1, len(residents)):
                b, c = residents[j], residents[k]
                if frozenset((a["id"], b["id"], c["id"])) in used_keys:
                    continue
                parts = [
                    weight_by_key[frozenset((x["id"], y["id"]))]
                    for x, y in ((a, b), (a, c), (b, c))
                ]
                if any(part <= 0 for part in parts):
                    continue
                trios.append((a, b, c))
                weights.append(sum(parts))
    if not trios:
        return None
    return rng.choices(trios, weights=weights, k=1)[0]


def _pick_solo(state: dict[str, Any], rng: random.Random) -> tuple[dict] | None:
    """1人の主役。直前のペアは少し避け、気分が振れている住民を少し優先する。"""
    residents = state["residents"]
    if not residents:
        return None
    last_ids = set(state.get("last_pair") or [])
    weights = []
    for resident in residents:
        weight = 0.4 if resident["id"] in last_ids else 1.0
        weight += abs(int(resident.get("mood") or 50) - 50) / 100.0
        weights.append(weight)
    return (rng.choices(residents, weights=weights, k=1)[0],)


def choose_groups(
    state: dict[str, Any], rng: random.Random, count: int = HAKONIWA_EVENTS_PER_DAY
) -> list[tuple[dict, ...]]:
    """その日の出来事の主役の組(1〜3人)を count 組選ぶ。

    原則はペアで、確率で1件だけ3人または単独に差し替える。入れ替わりの朝が有効なら
    当事者のペアを必ず含める。
    """
    residents = state["residents"]
    chosen: list[tuple] = []
    used_keys: set[frozenset] = set()
    swap = _swap_guaranteed_pair(state)
    if swap is not None and count >= 1:
        chosen.append(swap)
        used_keys.add(frozenset((swap[0]["id"], swap[1]["id"])))
    if len(chosen) < count and len(residents) >= 2:
        roll = rng.random()
        special: tuple[dict, ...] | None = None
        if roll < HAKONIWA_TRIO_GROUP_CHANCE:
            special = _pick_trio(state, rng, used_keys)
        elif roll < HAKONIWA_TRIO_GROUP_CHANCE + HAKONIWA_SOLO_GROUP_CHANCE:
            special = _pick_solo(state, rng)
        if special is not None:
            chosen.append(special)
            used_keys.add(frozenset(resident["id"] for resident in special))
    _fill_pairs(state, rng, count, chosen, used_keys)
    while len(chosen) < count and residents:
        # ペアが尽きた(男性の体同士しか残らない等)ときは単独の出来事で埋める
        solo = _pick_solo(state, rng)
        if solo is None:
            break
        chosen.append(solo)
    # 違和感が「探り合い」以上なら、調べ役がどこかの組に入るよう寄せる
    return story.ensure_investigator(state, chosen)


def custom_rule_focus_assignments(
    state: dict[str, Any], groups: list[tuple[dict, ...]]
) -> dict[int, str]:
    """自作の掟を場面の中心にする出来事の割り当て {出来事の位置: 掟の id}。

    入れ替わりの当事者ペアの出来事は入れ替わりに譲り、男性の体だけの組(2人以上)も
    候補から外す。掟が出来事より多い日は、日数で開始位置を回して順番を巡らせる。
    """
    rules = [rule["id"] for rule in active_custom_rules(state)]
    if not rules or not groups:
        return {}
    indices = [
        index
        for index, group in enumerate(groups)
        if not (len(group) >= 2 and _male_bodies(state, *group))
    ]
    pair = state.get("swap_pair")
    if pair and "swap" in state.get("active_rules", []):
        non_swap = [
            index
            for index in indices
            if {resident["id"] for resident in groups[index]} != set(pair)
        ]
        indices = non_swap or indices[:1]
    if not indices:
        return {}
    offset = (max(int(state.get("day") or 1), 1) - 1) % len(rules)
    ordered = rules[offset:] + rules[:offset]
    return dict(zip(indices, ordered, strict=False))


# --- 出来事の適用 ---


def apply_event(
    state: dict[str, Any], event: dict[str, Any], rng: random.Random
) -> dict[str, Any]:
    """出来事を適用した状態を返す。気分・好感度を足してクランプし、年代記に積む。

    event の participants / mood_delta / lines の speaker は住民 id。全住民の気分に
    小さな揺らぎ(-2〜+2)も加える。
    """
    new_state = deepcopy(state)
    by_id = {resident["id"]: resident for resident in new_state["residents"]}
    for resident_id, delta in (event.get("mood_delta") or {}).items():
        if resident_id in by_id:
            by_id[resident_id]["mood"] = _clamp(
                by_id[resident_id]["mood"] + int(delta),
                HAKONIWA_MOOD_MIN,
                HAKONIWA_MOOD_MAX,
            )
    participants = [pid for pid in event.get("participants") or [] if pid in by_id]
    area_id = event.get("area") if event.get("area") in HAKONIWA_AREA_MAP else None
    if area_id is None:
        area_id = DEFAULT_AREA_ID
    # 出来事の参加者は、その場所に集まる
    for participant_id in participants:
        by_id[participant_id]["current_area"] = area_id
    if len(participants) >= 2:
        delta = int(event.get("affinity_delta") or 0)
        for index, a_id in enumerate(participants):
            for b_id in participants[index + 1 :]:
                for x, y in ((a_id, b_id), (b_id, a_id)):
                    current = by_id[x]["affinities"].get(y, 0)
                    by_id[x]["affinities"][y] = _clamp(
                        current + delta, HAKONIWA_AFFINITY_MIN, HAKONIWA_AFFINITY_MAX
                    )
    if len(participants) == 2:
        new_state["last_pair"] = list(participants)
    for resident in new_state["residents"]:
        resident["mood"] = _clamp(
            resident["mood"] + rng.randint(-2, 2), HAKONIWA_MOOD_MIN, HAKONIWA_MOOD_MAX
        )
    record = {
        "id": uuid.uuid4().hex,
        "day": int(state["day"]),
        "title": str(event.get("title") or ""),
        "narration": str(event.get("narration") or ""),
        "lines": [
            {"speaker": str(line["speaker"]), "text": str(line["text"])}
            for line in event.get("lines") or []
        ],
        "participants": participants,
        "mood_delta": {
            str(key): int(value)
            for key, value in (event.get("mood_delta") or {}).items()
        },
        "affinity_delta": int(event.get("affinity_delta") or 0),
        "source": str(event.get("source") or "template"),
        "area": area_id,
        "favorite": False,
    }
    for key in EVENT_EXTRA_KEYS:
        if event.get(key):
            record[key] = event[key]
    new_state["events"].append(record)
    new_state["events"] = trim_events(new_state["events"])
    # 大きな出来事(変身・対面・関係の大きな動き)は参加者の記憶に残る
    return story.record_event_memories(new_state, record)


def trim_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """年代記を上限まで古い順に削る(お気に入りは残す)。"""
    overflow = len(events) - HAKONIWA_EVENT_LOG_MAX
    if overflow <= 0:
        return events
    kept: list[dict[str, Any]] = []
    for event in events:
        if overflow > 0 and not event.get("favorite"):
            overflow -= 1
            continue
        kept.append(event)
    return kept


def finish_day(
    state: dict[str, Any], rng: random.Random | None = None
) -> dict[str, Any]:
    """日を1つ進める。rng があれば、住民がときどき別の場所へ移っている。"""
    new_state = deepcopy(state)
    new_state["day"] = int(state["day"]) + 1
    if rng is not None:
        for resident in new_state["residents"]:
            if rng.random() < HAKONIWA_RESIDENT_AREA_MOVE_CHANCE:
                others = [
                    area["id"]
                    for area in HAKONIWA_AREAS
                    if area["id"] != resident.get("current_area")
                ]
                resident["current_area"] = rng.choice(others)
    return new_state


# --- エリアと家具 ---


def pick_event_area(
    state: dict[str, Any], group: tuple[dict[str, Any], ...], rng: random.Random
) -> str:
    """出来事の場所。ときどき別の場所で、ふだんは参加者のいる場所のどれか。"""
    if rng.random() < HAKONIWA_EVENT_AREA_MOVE_CHANCE:
        return rng.choice([area["id"] for area in HAKONIWA_AREAS])
    areas = sorted(
        {
            resident.get("current_area")
            for resident in group
            if resident.get("current_area") in HAKONIWA_AREA_MAP
        }
    )
    return rng.choice(areas) if areas else DEFAULT_AREA_ID


def placed_furniture(state: dict[str, Any], area_id: str) -> list[str]:
    """その場所に置かれている家具の id(スロット順)。"""
    layout = state.get("furniture_layout") or {}
    return [item for item in layout.get(area_id) or [] if item]


def place_furniture(
    state: dict[str, Any], area_id: str, slot: int, furniture_id: str | None
) -> dict[str, Any]:
    """家具をスロットに置く(None で片付ける)。1点物なので、別の場所にあれば移す。"""
    if area_id not in HAKONIWA_AREA_MAP:
        raise HakoniwaError("area_not_found", "場所が見つかりません")
    if not 0 <= int(slot) < HAKONIWA_FURNITURE_SLOTS:
        raise HakoniwaError("invalid_slot", "置く場所が正しくありません")
    if furniture_id is not None and furniture_id not in HAKONIWA_FURNITURE_MAP:
        raise HakoniwaError("furniture_not_found", "家具が見つかりません")
    new_state = deepcopy(state)
    layout = _normalize_furniture_layout(new_state.get("furniture_layout"))
    if furniture_id is not None:
        for slots in layout.values():
            for index, item in enumerate(slots):
                if item == furniture_id:
                    slots[index] = None
    layout[area_id][int(slot)] = furniture_id
    new_state["furniture_layout"] = layout
    return new_state


def set_event_scene_image(
    state: dict[str, Any], event_id: str, filename: str
) -> dict[str, Any]:
    new_state = deepcopy(state)
    target = next(
        (event for event in new_state["events"] if event["id"] == event_id), None
    )
    if target is None:
        raise HakoniwaError("event_not_found", "出来事が見つかりません")
    target["scene_image"] = filename
    return new_state


def set_event_look_plan(
    state: dict[str, Any], event_id: str, plan: list[dict[str, str]]
) -> dict[str, Any]:
    """出来事の結果として姿が変わる参加者ごとの変化後の姿を、出来事に保存した状態を返す。

    plan は [{resident_id, tags, description}]。画像は1人ずつ、この計画のタグから作る
    (服の交換のように、相手の出来事の前の姿が要る変化を、後から作っても崩さないため)。
    """
    new_state = deepcopy(state)
    target = next(
        (event for event in new_state["events"] if event["id"] == event_id), None
    )
    if target is None:
        raise HakoniwaError("event_not_found", "出来事が見つかりません")
    target["look_plan"] = [
        {
            "resident_id": str(item["resident_id"]),
            "tags": str(item["tags"]),
            "description": str(item.get("description") or ""),
        }
        for item in plan
    ]
    return new_state


def event_look_entry(
    state: dict[str, Any], event_id: str, resident_id: str
) -> dict[str, str]:
    """出来事に保存した、その住民の変化後の姿({resident_id, tags, description})。"""
    event = next((item for item in state["events"] if item["id"] == event_id), None)
    if event is None:
        raise HakoniwaError("event_not_found", "出来事が見つかりません")
    entry = next(
        (
            item
            for item in event.get("look_plan") or []
            if item.get("resident_id") == resident_id
        ),
        None,
    )
    if entry is None:
        raise HakoniwaError(
            "event_look_not_planned", "この出来事では、この住民の姿は変わりません"
        )
    return entry


def toggle_favorite(
    state: dict[str, Any], event_id: str, favorite: bool
) -> dict[str, Any]:
    new_state = deepcopy(state)
    target = next(
        (event for event in new_state["events"] if event["id"] == event_id), None
    )
    if target is None:
        raise HakoniwaError("event_not_found", "出来事が見つかりません")
    target["favorite"] = bool(favorite)
    return new_state


# --- その場で変身 ---


def validate_transform_text(text: Any) -> str:
    return _clean_text(
        text, HAKONIWA_TRANSFORM_TEXT_MAX, required=True, code="invalid_transform_text"
    )


def validate_reality_text(text: Any) -> str:
    return _clean_text(
        text, HAKONIWA_REALITY_TEXT_MAX, required=True, code="invalid_reality_text"
    )


def realities(resident: dict[str, Any]) -> list[dict[str, Any]]:
    """住民の改変(その住民についての世界の常識)。古い順。"""
    return list(resident.get("realities") or [])


def add_reality(
    state: dict[str, Any], resident_id: str, text: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """住民の改変を1件積む。戻り値は (状態, 積んだ改変)。上限を超えるなら断る。"""
    new_state = deepcopy(state)
    resident = find_resident(new_state, resident_id)
    current = realities(resident)
    if len(current) >= HAKONIWA_REALITIES_MAX:
        raise HakoniwaError(
            "too_many_realities",
            f"改変は1人{HAKONIWA_REALITIES_MAX}件までです。先に消してください",
        )
    entry = {
        "id": "reality_" + uuid.uuid4().hex[:10],
        "text": validate_reality_text(text),
        "day": int(new_state["day"]),
    }
    resident["realities"] = [*current, entry]
    return new_state, entry


def remove_reality(
    state: dict[str, Any], resident_id: str, reality_id: str
) -> dict[str, Any]:
    """住民の改変を消す。その改変で変えた姿がいまの姿なら、それも解く。"""
    new_state = deepcopy(state)
    person = find_resident(new_state, resident_id)
    current = realities(person)
    if not any(item["id"] == reality_id for item in current):
        raise HakoniwaError("reality_not_found", "改変が見つかりません")
    person["realities"] = [item for item in current if item["id"] != reality_id]
    body = body_of(new_state, person)
    transformation = body.get("transformation") or {}
    if transformation.get("reality_id") == reality_id:
        body["transformation"] = None
    return new_state


def validate_event_instruction(text: Any) -> str:
    return _clean_text(
        text, HAKONIWA_DIRECTED_EVENT_TEXT_MAX, required=True, code="invalid_event_text"
    )


def set_transformation(
    state: dict[str, Any], resident_id: str, transformation: dict[str, Any]
) -> dict[str, Any]:
    """住民がいまいる体に変身を設定し、その体の履歴(最大10件)に積んだ状態を返す。

    変身は体に付く。入れ替わり中なら相手の体(本人がいま入っている体)が変わり、
    適応はその体にいる本人に付く。kind="reality" は住民の改変で変えた姿で、
    本人も周りも昔からそうだと受け止めるので、慣れの段階は始めない。
    """
    new_state = deepcopy(state)
    person = find_resident(new_state, resident_id)
    body = body_of(new_state, person)
    entry = {
        "description": str(transformation["description"]),
        "tags": str(transformation["tags"]),
        "image": str(transformation["image"]),
        "day": int(transformation["day"]),
    }
    reality = transformation.get("kind") == "reality"
    if reality:
        entry["kind"] = "reality"
        entry["reality_id"] = str(transformation.get("reality_id") or "")
    body["transformation"] = entry
    history = [
        item
        for item in body.get("transformation_history") or []
        if item.get("image") != entry["image"]
    ]
    history.append(dict(entry))
    body["transformation_history"] = history[-HAKONIWA_TRANSFORMATION_HISTORY_MAX:]
    if not reality:
        story.start_adaptation(person, "transform", int(new_state["day"]))
    return new_state


def clear_transformation(state: dict[str, Any], resident_id: str) -> dict[str, Any]:
    """住民がいまいる体の変身を解く。"""
    new_state = deepcopy(state)
    person = find_resident(new_state, resident_id)
    body = body_of(new_state, person)
    if not body.get("transformation"):
        raise HakoniwaError("not_transformed", "変身していません")
    body["transformation"] = None
    story.end_adaptation(person, "transform", int(new_state["day"]))
    return new_state


def reapply_transformation(
    state: dict[str, Any], resident_id: str, image: str
) -> dict[str, Any]:
    """住民がいまいる体の履歴から、変身をもう一度今の姿にする。"""
    new_state = deepcopy(state)
    person = find_resident(new_state, resident_id)
    body = body_of(new_state, person)
    entry = next(
        (
            item
            for item in body.get("transformation_history") or []
            if item.get("image") == image
        ),
        None,
    )
    if entry is None:
        raise HakoniwaError("transformation_not_found", "変身の履歴が見つかりません")
    body["transformation"] = dict(entry)
    story.start_adaptation(person, "transform", int(new_state["day"]))
    return new_state


def bystanders(
    state: dict[str, Any], resident_id: str, rng: random.Random, limit: int = 2
) -> list[dict[str, Any]]:
    """変身に居合わせる住民(本人と同じ場所にいる住民から最大 limit 人)。"""
    target = find_resident(state, resident_id)
    others = [
        item
        for item in state["residents"]
        if item["id"] != resident_id
        and item.get("current_area") == target.get("current_area")
    ]
    if len(others) <= limit:
        return others
    return rng.sample(others, limit)


def directed_event_cast(
    state: dict[str, Any],
    resident_id: str,
    scope: str,
    partner_ids: list[str] | None,
    rng: random.Random,
) -> tuple[dict[str, Any], ...]:
    """書き手が指示して起こす出来事の参加者(先頭が本人、最大で本人＋2人)。

    solo は本人だけ、selected は選んだ住民(本人と重複は除く)、room は本人と同じ部屋の
    住民から最大 2 人。
    """
    if scope not in HAKONIWA_EVENT_SCOPES:
        raise HakoniwaError("invalid_event_scope", "巻き込み方が正しくありません")
    target = find_resident(state, resident_id)
    if scope == "solo":
        return (target,)
    if scope == "room":
        others = bystanders(
            state, resident_id, rng, limit=HAKONIWA_DIRECTED_EVENT_PARTNERS_MAX
        )
        if not others:
            raise HakoniwaError("event_room_empty", "同じ部屋にほかの住民がいません")
        return (target, *others)
    chosen: list[dict[str, Any]] = []
    for partner_id in partner_ids or []:
        if partner_id == resident_id or any(
            item["id"] == partner_id for item in chosen
        ):
            continue
        chosen.append(find_resident(state, partner_id))
    if not chosen:
        raise HakoniwaError("event_partners_required", "一緒に出る住民を選んでください")
    if len(chosen) > HAKONIWA_DIRECTED_EVENT_PARTNERS_MAX:
        raise HakoniwaError(
            "event_too_many_partners",
            f"一緒に出る住民は{HAKONIWA_DIRECTED_EVENT_PARTNERS_MAX}人までです",
        )
    return (target, *chosen)


def continuation_source(state: dict[str, Any], event_id: str) -> dict[str, Any]:
    """続きを指示できる出来事(今日起きたもの)を返す。

    前の日の出来事は、住民の姿や居場所が変わっているため続けられない。
    """
    event = next((item for item in state["events"] if item["id"] == event_id), None)
    if event is None:
        raise HakoniwaError("event_not_found", "出来事が見つかりません")
    if int(event.get("day") or 0) != int(state["day"]):
        raise HakoniwaError(
            "event_not_today", "続きを指示できるのは今日の出来事だけです"
        )
    return event


def continuation_cast(
    state: dict[str, Any], event: dict[str, Any]
) -> tuple[dict[str, Any], ...]:
    """続きの出来事の参加者。元の出来事の参加者のうち、いまも住んでいる住民(最大3人)。"""
    by_id = {resident["id"]: resident for resident in state["residents"]}
    group = tuple(
        by_id[resident_id]
        for resident_id in event.get("participants") or []
        if resident_id in by_id
    )[: HAKONIWA_DIRECTED_EVENT_PARTNERS_MAX + 1]
    if not group:
        raise HakoniwaError("event_cast_gone", "この出来事の住民がもういません")
    return group


def validate_event_location(location: Any) -> str | None:
    """指示した出来事の場所。空ならおまかせ(None)。"""
    text = str(location or "").strip()
    if not text:
        return None
    if text not in HAKONIWA_LOCATION_MAP:
        raise HakoniwaError("invalid_location", "出来事の場所が正しくありません")
    return text


def settle_event_location(
    event: dict[str, Any],
    area_id: str | None,
    location: Any,
    *,
    fallback: str | None = None,
) -> dict[str, Any]:
    """出来事の場所を決める。3つのエリアならそこで起き(参加者もそこへ移る)、
    エリアの外の場所なら area はそのままで location に残す。

    fallback は location が一覧に無いときに使う場所(続きの出来事なら前の場面の場所)。
    """
    settled = {**event}
    settled.pop("location", None)
    place = str(location or "")
    if place not in HAKONIWA_LOCATION_MAP:
        place = str(fallback or "")
    if place in HAKONIWA_AREA_MAP:
        settled["area"] = place
    else:
        settled["area"] = area_id
        if place in HAKONIWA_LOCATION_MAP:
            settled["location"] = place
    return settled


def male_body_pairs(
    state: dict[str, Any], group: tuple[dict[str, Any], ...]
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """いま見えている体がどちらも男性の組(入れ替わり・変身のタグを考える)。"""
    males = [resident for resident in group if body_gender(state, resident) == "male"]
    return [(a, b) for index, a in enumerate(males) for b in males[index + 1 :]]
