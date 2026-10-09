"""複数人表示の登場人物に持たせる性格プロフィール。

自分自身モードの SelfProfile と同じ項目（性格・反応スタイル・一人称・性別・趣味・
TSF への態度）を人物ごとに持たせる。ここには正規化・プロンプト用の 1 行要約・
LLM による自動生成と、姿を選んだソースから外見を取り出す処理を置く。

character_service から format_profile_line_ja を import するため、このモジュールは
重い依存（llm_service / session_store / source_snapshot）を関数内で遅延 import する。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..consts.character_limits import (
    APPEARANCE_NATURAL_MAX_LEN,
    APPEARANCE_TAGS_MAX_LEN,
)
from ..consts.character_profile import (
    DEFAULT_REACTION_STYLE,
    GENDERS,
    PROFILE_INTEREST_MAX_LEN,
    PROFILE_INTERESTS_MAX_COUNT,
    PROFILE_MEMO_MAX_LEN,
    PROFILE_PERSONALITY_MAX_LEN,
    PROFILE_PRONOUN_MAX_LEN,
    PROFILE_TSF_ATTITUDE_MAX_LEN,
    PROMPT_INTERESTS_MAX_COUNT,
    PROMPT_PERSONALITY_MAX_LEN,
    PROMPT_TSF_ATTITUDE_MAX_LEN,
    REACTION_STYLE_LABELS_JA,
    REACTION_STYLES,
)

logger = logging.getLogger(__name__)


class CharacterProfileGenerationError(RuntimeError):
    """LLM の呼び出し、または出力 JSON の解析に失敗した。"""


class CharacterSourceNotFoundError(LookupError):
    """姿のソース（セッション・履歴・Prompt Expander エントリ）が見つからない。"""


def _text(value: Any, max_len: int) -> str:
    return str(value or "").strip()[:max_len]


def normalize_character_profile(raw: dict[str, Any]) -> dict[str, Any]:
    """LLM 出力や保存値を CharacterProfile の形に揃える。

    範囲外の列挙値は既定値に戻し、文字列で返った趣味は配列に直し、長さを切り詰める。
    """
    reaction = str(raw.get("reaction_style") or "").strip()
    if reaction not in REACTION_STYLES:
        reaction = DEFAULT_REACTION_STYLE
    gender = str(raw.get("gender") or "").strip()
    if gender not in GENDERS:
        gender = ""
    interests_raw = raw.get("interests") or []
    if isinstance(interests_raw, str):
        interests_raw = interests_raw.replace("、", ",").split(",")
    interests = [
        _text(item, PROFILE_INTEREST_MAX_LEN)
        for item in interests_raw
        if isinstance(item, str) and item.strip()
    ][:PROFILE_INTERESTS_MAX_COUNT]
    return {
        "personality": _text(raw.get("personality"), PROFILE_PERSONALITY_MAX_LEN),
        "reaction_style": reaction,
        "pronoun": _text(raw.get("pronoun"), PROFILE_PRONOUN_MAX_LEN),
        "gender": gender,
        "interests": interests,
        "tsf_attitude": _text(raw.get("tsf_attitude"), PROFILE_TSF_ATTITUDE_MAX_LEN),
        "memo": _text(raw.get("memo"), PROFILE_MEMO_MAX_LEN),
    }


def format_profile_line_ja(profile: dict[str, Any] | None) -> str:
    """登場人物一覧に載せる 1 行の人物設定。設定が空なら空文字。"""
    if not profile:
        return ""
    parts: list[str] = []
    gender = profile.get("gender")
    if gender == "man":
        parts.append("性別=男性")
    elif gender == "woman":
        parts.append("性別=女性")
    pronoun = str(profile.get("pronoun") or "").strip()
    if pronoun:
        parts.append(f"一人称={pronoun}")
    personality = str(profile.get("personality") or "").strip()
    if personality:
        parts.append(f"性格={personality[:PROMPT_PERSONALITY_MAX_LEN]}")
    reaction = profile.get("reaction_style")
    if reaction and reaction != DEFAULT_REACTION_STYLE:
        parts.append(f"反応={REACTION_STYLE_LABELS_JA.get(reaction, reaction)}")
    interests = [
        str(item).strip()
        for item in profile.get("interests") or []
        if str(item).strip()
    ][:PROMPT_INTERESTS_MAX_COUNT]
    if interests:
        parts.append(f"趣味={'、'.join(interests)}")
    tsf_attitude = str(profile.get("tsf_attitude") or "").strip()
    if tsf_attitude:
        parts.append(f"TSFへの態度={tsf_attitude[:PROMPT_TSF_ATTITUDE_MAX_LEN]}")
    return " / ".join(parts)


# ── 自動生成 ──

CHARACTER_PROFILE_GEN_SYSTEM_PROMPT = """あなたはキャラクター設定の専門家です。
物語の登場人物の名前・外見・メモから、ゲーム内で使う性格プロフィールを作ってください。

出力形式（JSON のみ、余計なテキストは不要）:
{
  "personality": "性格を1-2文で要約",
  "reaction_style": "bold|gentle|cheerful|calm|shy|passionate",
  "pronoun": "一人称（僕/私/俺/わたし/あたし/うち等）",
  "gender": "man|woman",
  "interests": ["趣味・興味のキーワード"],
  "tsf_attitude": "性転換・変身（TSF）に対する態度を1文で"
}

ルール:
- メモに書かれた内容を最優先し、書かれていない項目は名前と外見から自然に補う
- reaction_style は必ず bold, gentle, cheerful, calm, shy, passionate のいずれか
- gender は必ず man または woman。外見タグの 1girl / 1boy / girl / boy などや名前から推測する
- pronoun は性別と性格に合う一人称にする
- interests は最大5個のキーワード
- tsf_attitude はメモに無ければ、性格から想像できる態度を中立寄りに書く
- 必ず有効なJSONのみを出力すること"""


def build_character_profile_generation_prompt(
    *,
    name: str,
    appearance_natural: str,
    appearance_tags: str,
    memo: str,
) -> tuple[str, str]:
    """登場人物の性格プロフィールを生成するための (system, user) プロンプト。"""
    lines = ["以下の登場人物の性格プロフィールを生成してください。", ""]
    lines.append(f"名前: {name.strip() or '（未設定）'}")
    if appearance_natural.strip():
        lines.append(f"外見: {appearance_natural.strip()[:APPEARANCE_NATURAL_MAX_LEN]}")
    if appearance_tags.strip():
        lines.append(f"外見タグ: {appearance_tags.strip()[:APPEARANCE_TAGS_MAX_LEN]}")
    memo_text = memo.strip()[:PROFILE_MEMO_MAX_LEN]
    lines.append("")
    lines.append("メモ:")
    lines.append(memo_text or "（なし）")
    return CHARACTER_PROFILE_GEN_SYSTEM_PROMPT, "\n".join(lines)


async def generate_character_profile(
    *,
    name: str,
    appearance_natural: str,
    appearance_tags: str,
    memo: str,
) -> dict[str, Any]:
    """LLM で登場人物の性格プロフィールを生成する。

    プロバイダは本文生成と同じ FEELING_PROVIDER に従い、NovelAI のときは
    ユーザー設定のテキストモデルを使う（別プロバイダへの振り替えはしない）。

    Raises:
        CharacterProfileGenerationError: LLM 呼び出し・JSON 解析の失敗
    """
    from .llm_json import extract_json_object
    from .llm_service import llm_service
    from .session import session_store

    system_prompt, user_prompt = build_character_profile_generation_prompt(
        name=name,
        appearance_natural=appearance_natural,
        appearance_tags=appearance_tags,
        memo=memo,
    )
    user_settings = await session_store.get_user_settings()
    try:
        result = await llm_service.generate_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            novelai_model_override=user_settings.get("novelai_text_model"),
        )
    except Exception as exc:
        logger.warning(
            "character profile generation failed: %s: %s", type(exc).__name__, exc
        )
        raise CharacterProfileGenerationError(str(exc) or type(exc).__name__) from exc

    try:
        data = json.loads(extract_json_object(result.content), strict=False)
    except ValueError as exc:
        logger.warning(
            "character profile JSON parse failed: %s", (result.content or "")[:300]
        )
        raise CharacterProfileGenerationError("invalid_json") from exc
    if not isinstance(data, dict):
        raise CharacterProfileGenerationError("invalid_json")
    return normalize_character_profile({**data, "memo": memo})


# ── 姿のソース解決 ──


def _merge_tags(*groups: str) -> str:
    merged: list[str] = []
    for group in groups:
        for raw in (group or "").split(","):
            tag = raw.strip()
            if not tag or tag.lower() == "solo" or tag in merged:
                continue
            merged.append(tag)
    return ", ".join(merged)


async def resolve_character_source(
    *,
    session_id: str | None,
    history_id: str | None,
    prompt_expander_entry_id: str | None,
) -> dict[str, Any]:
    """セッション・お気に入り・Prompt Expander の選択から名前と外見を取り出す。

    外見がタグ列として読めない履歴（日本語の記述）は自然文として返す。

    Raises:
        CharacterSourceNotFoundError: ソースや画像が見つからない
    """
    from .character_service import extract_protagonist_tags_from_history
    from .session import session_store
    from .source_snapshot import (
        SourceSnapshotError,
        build_source_snapshot,
        resolve_session_identity,
    )

    try:
        snapshot, _image_path, _tags, _nsfw = await build_source_snapshot(
            session_id,
            history_id,
            source_prompt_expander_entry_id=prompt_expander_entry_id,
        )
    except SourceSnapshotError as exc:
        raise CharacterSourceNotFoundError(exc.code) from exc

    name: str | None = None
    if not prompt_expander_entry_id and session_id:
        session = await session_store.get_session_by_id(session_id)
        if session is not None:
            name, _pronoun = await resolve_session_identity(session)

    appearance = str(snapshot.get("appearance") or "").strip()
    clothing = str(snapshot.get("clothing") or "").strip()
    if (
        not clothing
        and appearance
        and not extract_protagonist_tags_from_history(appearance)
    ):
        return {
            "name": name,
            "appearance_natural": appearance[:APPEARANCE_NATURAL_MAX_LEN],
            "appearance_tags": "",
        }
    return {
        "name": name,
        "appearance_natural": "",
        "appearance_tags": _merge_tags(appearance, clothing),
    }


__all__ = [
    "CharacterProfileGenerationError",
    "CharacterSourceNotFoundError",
    "build_character_profile_generation_prompt",
    "format_profile_line_ja",
    "generate_character_profile",
    "normalize_character_profile",
    "resolve_character_source",
]
