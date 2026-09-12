"""おすすめのプレイ(案内役キャラの提案カード)の材料と保存形。LLM は呼ばない。

提案に使ってよいキャラクターの一覧(カタログ)はバックエンドのデータだけから作り、
提案 JSON の検証 context にもそのまま使う。LLM が一覧に無いキャラクターを返しても
採用しない。保存形は kind で種類を分け、後から TSF シナリオの提案を足せるようにする。
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Any, Literal

from ..consts.character_chat import (
    PLAY_PROPOSAL_CUSTOM_MAX,
    PLAY_PROPOSAL_KIND,
    PLAY_PROPOSAL_RECENT_SESSIONS,
)
from .character_chat_models import CharacterChatPlan, CharacterChatPlayProposal
from .characters import character_manager
from .custom_sessions import list_custom_character_profiles, normalize_gender

PlayCharacterSource = Literal["template", "custom"]

# プロンプトに載せる項目の上限
_DESCRIPTION_MAX = 120
_PERSONALITY_MAX = 80
_PROFILE_TEXT_MAX = 120
_INTEREST_MAX = 40
_INTERESTS_MAX = 5


@dataclass(frozen=True)
class PlayCatalogEntry:
    """提案に使ってよいキャラクター 1 人。ref はプロンプトと検証で使う参照キー。"""

    ref: str
    source: PlayCharacterSource
    id: str
    name: str
    gender: str
    personality: str
    description: str


@dataclass
class PlayProposalOutcome:
    """提案の結果。meta は保存形(失敗時は None)、reply_block は返答に差し込む枠。

    grounding_text / grounding_details は提案のために追加で調べた過去プレイの本文と
    引用表示用の明細。返答の調べ物に合流させ、根拠をセレナと画面の両方に揃える。
    """

    meta: dict[str, Any] | None
    reply_block: str
    grounding_text: str = ""
    grounding_details: list[dict[str, Any]] = field(default_factory=list)


def _short(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_play_catalog() -> dict[str, PlayCatalogEntry]:
    """テンプレートキャラと作成済みキャラ(新しい順に上限まで)のカタログ。

    作成済みキャラの参照キーは、uuid を写し間違えないよう custom:1 からの連番にする。
    """
    catalog: dict[str, PlayCatalogEntry] = {}
    for character in character_manager.get_all():
        ref = f"template:{character.id}"
        catalog[ref] = PlayCatalogEntry(
            ref=ref,
            source="template",
            id=character.id,
            name=character.name,
            gender=normalize_gender(character.gender),
            personality=character.personality or "",
            description=character.description or "",
        )
    profiles = list_custom_character_profiles(PLAY_PROPOSAL_CUSTOM_MAX)
    for index, profile in enumerate(profiles, start=1):
        ref = f"custom:{index}"
        catalog[ref] = PlayCatalogEntry(
            ref=ref,
            source="custom",
            id=str(profile["id"]),
            name=str(profile.get("name") or ""),
            gender=normalize_gender(profile.get("gender")),
            personality=str(profile.get("personality") or ""),
            description=str(profile.get("description") or ""),
        )
    return catalog


def catalog_names(catalog: dict[str, PlayCatalogEntry]) -> dict[str, str]:
    """検証 context 用の参照キー → キャラクター名。"""
    return {ref: entry.name for ref, entry in catalog.items()}


def catalog_prompt_items(catalog: dict[str, PlayCatalogEntry]) -> list[dict[str, str]]:
    """プロンプトに載せるカタログ。説明と性格は短くする。"""
    items: list[dict[str, str]] = []
    for entry in catalog.values():
        item = {
            "ref": entry.ref,
            "kind": "preset" if entry.source == "template" else "saved custom",
            "name": entry.name,
            "starting_gender": entry.gender,
        }
        if entry.description:
            item["description"] = _short(entry.description, _DESCRIPTION_MAX)
        if entry.personality:
            item["personality"] = _short(entry.personality, _PERSONALITY_MAX)
        items.append(item)
    return items


def grounding_plan(already_run: Collection[str]) -> CharacterChatPlan:
    """提案の根拠に読む過去プレイ(傾向と最近のセッション)。

    判定 LLM がこの手番ですでに実行した種類は除く(同じ本文を二重に載せない)。
    """
    lookups = [
        {"kind": "tendencies"},
        {"kind": "recent_sessions", "limit": PLAY_PROPOSAL_RECENT_SESSIONS},
    ]
    return CharacterChatPlan.model_validate(
        {"lookups": [item for item in lookups if item["kind"] not in already_run]}
    )


def self_profile_hint(profile: dict[str, Any] | None) -> dict[str, Any] | None:
    """自分自身モードを提案するための自プロフィールの要約。使える項目が無ければ None。"""
    if not profile:
        return None
    hint: dict[str, Any] = {}
    for key in ("display_name", "gender", "personality", "tsf_attitude"):
        value = _short(profile.get(key), _PROFILE_TEXT_MAX)
        if value:
            hint[key] = value
    raw_interests = profile.get("interests")
    if isinstance(raw_interests, str):
        raw_interests = [raw_interests]
    interests = [
        _short(item, _INTEREST_MAX)
        for item in raw_interests or []
        if str(item or "").strip()
    ][:_INTERESTS_MAX]
    if interests:
        hint["interests"] = interests
    return hint or None


def play_proposal_meta(
    proposal: CharacterChatPlayProposal, entry: PlayCatalogEntry
) -> dict[str, Any]:
    """meta_json に保存する提案。キャラクターの ID と名前は LLM の出力ではなくカタログから写す。"""
    return {
        "kind": PLAY_PROPOSAL_KIND,
        "title": proposal.title,
        "reason": proposal.reason,
        "character": {"source": entry.source, "id": entry.id, "name": entry.name},
        "self_mode": proposal.self_mode,
        "first_instruction": {
            "instruction_type": proposal.instruction_type,
            "text": proposal.instruction,
        },
    }
