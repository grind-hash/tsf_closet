"""SessionCharacter / CharacterPreset business logic (spec 005).

Distinct from existing ``services/characters.py`` which handles single-person
mode profiles. This module manages persisted multi-character state.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..consts.character_limits import (
    MAX_REGISTERED_CHARACTERS,
)
from ..databases.character_repo import (
    delete_character_group_preset,
    delete_character_preset,
    delete_non_protagonist_session_characters,
    delete_session_character,
    fetch_character_group_preset,
    fetch_character_group_presets,
    fetch_character_preset,
    fetch_character_presets,
    fetch_latest_character_states,
    fetch_protagonist_session_character,
    fetch_session_character,
    fetch_session_characters,
    insert_character_group_preset,
    insert_character_preset,
    insert_session_character,
    update_character_group_preset,
    update_character_preset,
    update_session_character,
)
from ..databases.models import CharacterGroupPreset, CharacterPreset, SessionCharacter
from .character_profile import format_profile_line_ja

logger = logging.getLogger(__name__)


# 主人公以外に登録できる人数（主人公を含めて MAX_REGISTERED_CHARACTERS 人）
CHARACTER_LIMIT = MAX_REGISTERED_CHARACTERS - 1
ALLOWED_POSITIONS = (
    "left",
    "center-left",
    "center",
    "center-right",
    "right",
)


class CharacterLimitExceededError(ValueError):
    """Raised when adding would exceed CHARACTER_LIMIT for the session."""

    def __init__(self) -> None:
        super().__init__("character_limit_exceeded")


def dump_profile(profile: dict[str, Any] | None) -> str | None:
    """性格プロフィール dict を profile_json 列の値にする。"""
    if not profile:
        return None
    return json.dumps(profile, ensure_ascii=False)


def record_profile(record: Any) -> dict[str, Any] | None:
    """profile_json 列を dict に戻す。壊れた JSON や未設定は None。"""
    raw = getattr(record, "profile_json", None)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _profile_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """API の ``profile`` キーを DB の ``profile_json`` 列へ置き換える。"""
    if "profile" not in patch:
        return patch
    converted = dict(patch)
    profile = converted.pop("profile")
    if profile is not None:
        converted["profile_json"] = dump_profile(profile) or ""
    return converted


# ---------------------------------------------------------------------------
# SessionCharacterService
# ---------------------------------------------------------------------------


def _changes_drawn_setting(current: SessionCharacter, patch: dict[str, Any]) -> bool:
    """画像に使う設定（タグ、タグが空なら自然文）が変わる更新か。

    自然文だけの修正では、タグが入っている限り描く姿は変わらないため False。
    """
    old_tags = (current.appearance_tags or "").strip()
    new_tags = (patch.get("appearance_tags", old_tags) or "").strip()
    if new_tags != old_tags:
        return True
    if new_tags or "appearance_natural" not in patch:
        return False
    old_natural = (current.appearance_natural or "").strip()
    return (patch["appearance_natural"] or "").strip() != old_natural


class SessionCharacterService:
    """Application service for SessionCharacter rows."""

    @staticmethod
    async def list_for_session(
        db: AsyncSession, session_id: str
    ) -> Sequence[SessionCharacter]:
        return await fetch_session_characters(db, session_id)

    @staticmethod
    async def create_in_session(
        db: AsyncSession,
        session_id: str,
        *,
        name: str,
        appearance_natural: str = "",
        appearance_tags: str = "",
        position: str = "center",
        slot_index: int | None = None,
        source_preset_id: str | None = None,
        appearance_lock: bool = False,
        exclude_from_effects: bool = False,
        negative_tags: str = "",
        profile: dict[str, Any] | None = None,
        on_stage: bool = True,
        thumbnail_url: str | None = None,
    ) -> SessionCharacter:
        existing = list(await fetch_session_characters(db, session_id))
        non_protagonist_count = sum(1 for r in existing if not r.is_protagonist)
        if non_protagonist_count >= CHARACTER_LIMIT:
            raise CharacterLimitExceededError()
        if position not in ALLOWED_POSITIONS:
            raise ValueError(f"invalid_position:{position}")
        if slot_index is None:
            slot_index = len(existing)
        record = await insert_session_character(
            db,
            session_id=session_id,
            slot_index=slot_index,
            name=name,
            appearance_natural=appearance_natural,
            appearance_tags=appearance_tags,
            position=position,
            source_preset_id=source_preset_id,
            appearance_lock=appearance_lock,
            exclude_from_effects=exclude_from_effects,
            negative_tags=negative_tags,
            profile_json=dump_profile(profile),
            on_stage=on_stage,
            thumbnail_url=thumbnail_url,
        )
        await SessionCharacterService.reassign_positions(db, session_id)
        return record

    @staticmethod
    async def update(
        db: AsyncSession,
        character_id: str,
        **patch: Any,
    ) -> SessionCharacter | None:
        if (
            "position" in patch
            and patch["position"] is not None
            and patch["position"] not in ALLOWED_POSITIONS
        ):
            raise ValueError(f"invalid_position:{patch['position']}")
        patch = _profile_patch(patch)
        reset_look = bool(patch.pop("reset_look", False))
        needs_current = (
            reset_look
            or patch.get("on_stage") is False
            or "appearance_tags" in patch
            or "appearance_natural" in patch
        )
        current = (
            await fetch_session_character(db, character_id) if needs_current else None
        )
        if current is not None:
            if patch.get("on_stage") is False and current.is_protagonist:
                # 主人公は常に登場扱い。OFF への変更だけ無視する
                patch = {k: v for k, v in patch.items() if k != "on_stage"}
            if reset_look or _changes_drawn_setting(current, patch):
                # 画像に使う設定が変わった: 次の手番は履歴の姿ではなく設定の姿で描く
                patch["appearance_spec_rev"] = int(current.appearance_spec_rev or 0) + 1
        record = await update_session_character(db, character_id, **patch)
        if record is not None and "slot_index" in patch:
            await SessionCharacterService.reassign_positions(db, record.session_id)
        return record

    @staticmethod
    async def delete(db: AsyncSession, character_id: str) -> bool:
        record = await fetch_session_character(db, character_id)
        if record is None:
            return False
        session_id = record.session_id
        await delete_session_character(db, character_id)
        await SessionCharacterService.reassign_positions(db, session_id)
        return True

    @staticmethod
    async def reassign_positions(db: AsyncSession, session_id: str) -> None:
        """Re-pack ``slot_index`` to be 0..N-1 ordered by current slot_index ASC.

        Implements R-005 last-write-wins re-numbering.
        Protagonist (is_protagonist=True) is always placed at slot 0;
        non-protagonist records follow in their existing relative order.
        """
        records = list(await fetch_session_characters(db, session_id))
        # protagonist first, then others by current slot_index
        protagonist = [r for r in records if r.is_protagonist]
        others = [r for r in records if not r.is_protagonist]
        ordered = protagonist + others
        for new_index, record in enumerate(ordered):
            if record.slot_index != new_index:
                record.slot_index = new_index
        await db.flush()

    @staticmethod
    async def apply_preset_to_session(
        db: AsyncSession,
        session_id: str,
        preset_id: str,
        *,
        on_stage: bool = True,
    ) -> SessionCharacter:
        preset = await fetch_character_preset(db, preset_id)
        if preset is None:
            raise LookupError("preset_not_found")
        return await SessionCharacterService.create_in_session(
            db,
            session_id,
            name=preset.name,
            appearance_natural=preset.appearance_natural,
            appearance_tags=preset.appearance_tags,
            position=preset.default_position,
            source_preset_id=preset.id,
            negative_tags=preset.negative_tags or "",
            profile=record_profile(preset),
            on_stage=on_stage,
            thumbnail_url=preset.thumbnail_url,
        )


# ---------------------------------------------------------------------------
# CharacterPresetService
# ---------------------------------------------------------------------------


class CharacterPresetService:
    """Application service for CharacterPreset rows (global)."""

    @staticmethod
    async def list_presets(
        db: AsyncSession,
    ) -> Sequence[CharacterPreset]:
        return await fetch_character_presets(db)

    @staticmethod
    async def create_preset_raw(
        db: AsyncSession,
        *,
        name: str,
        appearance_natural: str = "",
        appearance_tags: str = "",
        default_position: str = "center",
        negative_tags: str = "",
        profile: dict[str, Any] | None = None,
        thumbnail_url: str | None = None,
    ) -> CharacterPreset:
        if default_position not in ALLOWED_POSITIONS:
            raise ValueError(f"invalid_position:{default_position}")
        return await insert_character_preset(
            db,
            name=name,
            appearance_natural=appearance_natural,
            appearance_tags=appearance_tags,
            default_position=default_position,
            negative_tags=negative_tags,
            profile_json=dump_profile(profile),
            thumbnail_url=thumbnail_url,
        )

    @staticmethod
    async def create_preset_from_character(
        db: AsyncSession,
        *,
        from_character_id: str,
        name: str,
    ) -> CharacterPreset:
        source = await fetch_session_character(db, from_character_id)
        if source is None:
            raise LookupError("session_character_not_found")
        return await insert_character_preset(
            db,
            name=name,
            appearance_natural=source.appearance_natural,
            appearance_tags=source.appearance_tags,
            default_position=source.position,
            negative_tags=source.negative_tags or "",
            profile_json=source.profile_json,
            thumbnail_url=source.thumbnail_url,
        )

    @staticmethod
    async def update_preset(
        db: AsyncSession,
        preset_id: str,
        **patch: Any,
    ) -> CharacterPreset | None:
        if (
            "default_position" in patch
            and patch["default_position"] is not None
            and patch["default_position"] not in ALLOWED_POSITIONS
        ):
            raise ValueError(f"invalid_position:{patch['default_position']}")
        return await update_character_preset(db, preset_id, **_profile_patch(patch))

    @staticmethod
    async def delete_preset(db: AsyncSession, preset_id: str) -> bool:
        existing = await fetch_character_preset(db, preset_id)
        if existing is None:
            return False
        await delete_character_preset(db, preset_id)
        return True


# ---------------------------------------------------------------------------
# CharacterGroupPresetService
# ---------------------------------------------------------------------------


def _member_from_record(record: SessionCharacter) -> dict[str, Any]:
    """セッション人物 1 人を組み合わせプリセットのメンバー dict にする。"""
    return {
        "name": record.name,
        "appearance_natural": record.appearance_natural or "",
        "appearance_tags": record.appearance_tags or "",
        "negative_tags": record.negative_tags or "",
        "position": record.position,
        "appearance_lock": bool(record.appearance_lock),
        "exclude_from_effects": bool(record.exclude_from_effects),
        "on_stage": bool(record.on_stage),
        "profile": record_profile(record),
        "thumbnail_url": record.thumbnail_url,
    }


def group_members(group: CharacterGroupPreset) -> list[dict[str, Any]]:
    """members_json を dict のリストに戻す。壊れた要素は捨てる。"""
    try:
        data = json.loads(group.members_json or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    members: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        position = item.get("position")
        profile = item.get("profile")
        members.append(
            {
                "name": name,
                "appearance_natural": str(item.get("appearance_natural") or ""),
                "appearance_tags": str(item.get("appearance_tags") or ""),
                "negative_tags": str(item.get("negative_tags") or ""),
                "position": position if position in ALLOWED_POSITIONS else "center",
                "appearance_lock": bool(item.get("appearance_lock", False)),
                "exclude_from_effects": bool(item.get("exclude_from_effects", False)),
                "on_stage": bool(item.get("on_stage", True)),
                "profile": profile if isinstance(profile, dict) else None,
                "thumbnail_url": item.get("thumbnail_url") or None,
            }
        )
    return members


class CharacterGroupPresetService:
    """登場人物の組み合わせ（主人公以外の一式）を名前付きで保存・適用する。"""

    @staticmethod
    async def _snapshot_session(db: AsyncSession, session_id: str) -> str:
        records = await fetch_session_characters(db, session_id)
        members = [_member_from_record(r) for r in records if not r.is_protagonist]
        return json.dumps(members, ensure_ascii=False)

    @staticmethod
    async def list_groups(db: AsyncSession) -> Sequence[CharacterGroupPreset]:
        return await fetch_character_group_presets(db)

    @staticmethod
    async def create_from_session(
        db: AsyncSession, *, name: str, session_id: str
    ) -> CharacterGroupPreset:
        members_json = await CharacterGroupPresetService._snapshot_session(
            db, session_id
        )
        return await insert_character_group_preset(
            db, name=name, members_json=members_json
        )

    @staticmethod
    async def update_group(
        db: AsyncSession,
        group_id: str,
        *,
        name: str | None = None,
        from_session_id: str | None = None,
    ) -> CharacterGroupPreset | None:
        members_json = (
            await CharacterGroupPresetService._snapshot_session(db, from_session_id)
            if from_session_id
            else None
        )
        return await update_character_group_preset(
            db, group_id, name=name, members_json=members_json
        )

    @staticmethod
    async def delete_group(db: AsyncSession, group_id: str) -> bool:
        return (await delete_character_group_preset(db, group_id)) > 0

    @staticmethod
    async def apply_to_session(
        db: AsyncSession, session_id: str, group_id: str
    ) -> Sequence[SessionCharacter]:
        """主人公以外の登場人物を、組み合わせのメンバーで置き換える。

        削除と挿入は同じトランザクションで行う。呼び出し側が 1 回だけ commit する。
        """
        group = await fetch_character_group_preset(db, group_id)
        if group is None:
            raise LookupError("group_preset_not_found")
        members = group_members(group)
        if len(members) > CHARACTER_LIMIT:
            raise CharacterLimitExceededError()
        await delete_non_protagonist_session_characters(db, session_id)
        # 主人公がいれば slot 0、他は 1 以降。reassign_positions で詰め直す
        base_slot = 1
        for offset, member in enumerate(members):
            await insert_session_character(
                db,
                session_id=session_id,
                slot_index=base_slot + offset,
                name=member["name"],
                appearance_natural=member["appearance_natural"],
                appearance_tags=member["appearance_tags"],
                position=member["position"],
                appearance_lock=member["appearance_lock"],
                exclude_from_effects=member["exclude_from_effects"],
                negative_tags=member["negative_tags"],
                profile_json=dump_profile(member["profile"]),
                on_stage=member["on_stage"],
                thumbnail_url=member["thumbnail_url"],
            )
        await SessionCharacterService.reassign_positions(db, session_id)
        return await fetch_session_characters(db, session_id)


# ---------------------------------------------------------------------------
# Stage roster (on-stage characters in prompt order)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CharacterLook:
    """履歴に残した 1 人分の姿（その手番で描いたタグと、そのときの設定の連番）。"""

    tags: str
    spec_rev: int


LOOK_SOURCES = ("spec", "history", "fixed")


def parse_character_states(raw: str | None) -> list[dict[str, Any]]:
    """``history.character_states_json`` を読む。壊れた要素は捨てる。"""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    entries: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        character_id = item.get("character_id")
        tags = item.get("tags")
        if not isinstance(character_id, str) or not character_id:
            continue
        if not isinstance(tags, str):
            continue
        spec_rev = item.get("spec_rev", 0)
        entries.append(
            {
                "character_id": character_id,
                "tags": tags.strip(),
                "spec_rev": spec_rev if isinstance(spec_rev, int) else 0,
            }
        )
    return entries


def looks_by_id(entries: Sequence[dict[str, Any]]) -> dict[str, CharacterLook]:
    """人物 ID ごとの姿。"""
    return {
        entry["character_id"]: CharacterLook(
            tags=entry["tags"], spec_rev=entry["spec_rev"]
        )
        for entry in entries
    }


async def load_character_looks(
    db: AsyncSession, session_id: str
) -> dict[str, CharacterLook]:
    """セッションの最新の姿（人物ごとのタグを持つ最後の履歴）を読む。"""
    raw = await fetch_latest_character_states(db, session_id)
    return looks_by_id(parse_character_states(raw))


def resolve_character_look(
    record: Any, looks: dict[str, CharacterLook] | None
) -> tuple[str, str, str | None]:
    """人物の今の姿を決める。戻り値は (画像に使うタグ, 出どころ, 履歴の姿)。

    - 姿を固定（appearance_lock）: 毎回設定のタグ（"fixed"）
    - 履歴の姿があり、記録時の設定の連番が今と同じ: 履歴の姿（"history"）
    - それ以外（登場したばかり・手番の後に設定を変えた）: 設定のタグ（"spec"）

    設定のタグが空なら 1 つ目は空文字になり、呼び出し側が自然文を使う。
    3 つ目は画面表示用で、設定が優先されている間も直前に描いた姿を返す。
    """
    spec_tags = (getattr(record, "appearance_tags", "") or "").strip()
    entry = (looks or {}).get(getattr(record, "id", None) or "")
    current = entry.tags if entry and entry.tags else None
    if getattr(record, "appearance_lock", False):
        return spec_tags, "fixed", current
    spec_rev = int(getattr(record, "appearance_spec_rev", 0) or 0)
    if entry and entry.tags and entry.spec_rev == spec_rev:
        return entry.tags, "history", current
    return spec_tags, "spec", current


@dataclass(frozen=True)
class StageCharacter:
    """プロンプトに載せる 1 人分。``record_id`` が None なのは未保存の主人公。

    ``appearance_*`` はユーザーが書いた設定、``look_tags`` は今回使う姿のタグ
    （``look_source`` が設定か履歴か固定か）。``ref`` は LLM とのやり取りに使う
    "C1" などの呼び名で、LLM の出力はこれで人物に対応付ける。
    """

    record_id: str | None
    name: str
    position: str
    appearance_natural: str
    appearance_tags: str
    negative_tags: str
    is_protagonist: bool
    appearance_lock: bool
    exclude_from_effects: bool
    profile: dict[str, Any] | None
    look_tags: str = ""
    look_source: str = "spec"
    spec_rev: int = 0
    ref: str = ""


def _stage_from_record(
    record: Any, looks: dict[str, CharacterLook] | None
) -> StageCharacter:
    look_tags, look_source, _current = resolve_character_look(record, looks)
    return StageCharacter(
        record_id=getattr(record, "id", None),
        name=record.name,
        position=record.position,
        appearance_natural=(getattr(record, "appearance_natural", "") or "").strip(),
        appearance_tags=(getattr(record, "appearance_tags", "") or "").strip(),
        negative_tags=(getattr(record, "negative_tags", "") or "").strip(),
        is_protagonist=bool(getattr(record, "is_protagonist", False)),
        appearance_lock=bool(getattr(record, "appearance_lock", False)),
        exclude_from_effects=bool(getattr(record, "exclude_from_effects", False)),
        profile=record_profile(record),
        look_tags=look_tags,
        look_source=look_source,
        spec_rev=int(getattr(record, "appearance_spec_rev", 0) or 0),
    )


def stage_ref(index: int) -> str:
    """登場順の添字から LLM 向けの呼び名（"C1" など）を作る。"""
    return f"C{index + 1}"


_REF_PATTERN = re.compile(r"^\s*(?:c|character)?\s*(\d+)\s*$", re.IGNORECASE)


def ref_to_stage_index(ref: Any) -> int | None:
    """ "C2" / "c2" / "Character 2" / 2 を登場順の添字（1）に戻す。読めなければ None。"""
    if isinstance(ref, int) and not isinstance(ref, bool):
        return ref - 1 if ref >= 1 else None
    if not isinstance(ref, str):
        return None
    match = _REF_PATTERN.match(ref)
    if not match:
        return None
    number = int(match.group(1))
    return number - 1 if number >= 1 else None


def build_stage_roster(
    records: Sequence[Any],
    *,
    limit: int | None = None,
    protagonist_name: str | None = None,
    protagonist_tags: str | None = None,
    looks: dict[str, CharacterLook] | None = None,
) -> list[StageCharacter]:
    """登場中の人物を、プロンプトに載せる順（主人公→slot 順）に並べる。

    画像用・テキスト用の人物一覧、LLM が返す ``characters`` と人物の対応、
    人物別ネガティブの付与、履歴に残す姿は、すべてこの並びと ``ref`` を基準にする。

    - 主人公と ``on_stage`` の人物だけを残す（主人公は常に登場扱い）
    - DB に主人公がまだ無い初回ターンは、kwargs の主人公を先頭へ差し込む
    - ``limit``（画像モデルのキャラクタープロンプト上限）を超える分は切り捨てる
    - ``looks`` は履歴に残した姿。無ければ全員が設定の姿になる
    """
    visible = [
        r
        for r in records
        if getattr(r, "is_protagonist", False) or getattr(r, "on_stage", True)
    ]
    ordered = sorted(
        visible,
        key=lambda r: (0 if getattr(r, "is_protagonist", False) else 1, r.slot_index),
    )
    roster = [_stage_from_record(r, looks) for r in ordered]
    kwarg_tags = (protagonist_tags or "").strip()
    if kwarg_tags and not any(c.is_protagonist for c in roster):
        name = (protagonist_name or "Protagonist").strip() or "Protagonist"
        roster.insert(
            0,
            StageCharacter(
                record_id=None,
                name=name,
                position="center",
                appearance_natural="",
                appearance_tags=kwarg_tags,
                negative_tags="",
                is_protagonist=True,
                appearance_lock=False,
                exclude_from_effects=False,
                profile=None,
                look_tags=kwarg_tags,
            ),
        )
    if limit is not None and limit > 0 and len(roster) > limit:
        logger.info(
            "stage roster truncated to model limit: %d -> %d", len(roster), limit
        )
        roster = roster[:limit]
    return [replace(c, ref=stage_ref(i)) for i, c in enumerate(roster)]


def build_character_states(
    previous: Sequence[dict[str, Any]],
    stage: Sequence[StageCharacter],
    character_prompts: Sequence[dict[str, Any]] | None,
    registered_ids: Iterable[str],
    *,
    protagonist_id: str | None = None,
) -> list[dict[str, Any]] | None:
    """この手番で描いた各人物の姿（履歴に残す値）を作る。

    - 前回の姿を人物 ID ごとに引き継ぐ（登場 OFF の人物も含む）。削除された人物は捨てる
    - 登場中の人物は、今回の出力（``stage_index`` で対応付け済み）のタグで上書きする
    - 姿を固定・指示対象外の人物は上書きしない（前回の姿のまま）
    - 一覧外の人物（``stage_index`` が None）は記録しない
    - ``protagonist_id`` は、初回ターンでまだ行が無かった主人公（record_id None）の ID

    人物ごとの出力が無い手番は None を返し、履歴には何も残さない（前の姿が続く）。
    """
    if not character_prompts:
        return None
    registered = set(registered_ids)
    if protagonist_id:
        registered.add(protagonist_id)
    states: dict[str, dict[str, Any]] = {
        entry["character_id"]: dict(entry)
        for entry in previous
        if entry["character_id"] in registered
    }
    for pos, entry in enumerate(character_prompts):
        if not isinstance(entry, dict):
            continue
        idx = entry.get("stage_index", pos)
        if not isinstance(idx, int) or not 0 <= idx < len(stage):
            continue
        member = stage[idx]
        record_id = member.record_id
        if record_id is None and member.is_protagonist:
            record_id = protagonist_id
        if record_id is None or record_id not in registered:
            continue
        if member.appearance_lock or member.exclude_from_effects:
            continue
        tags = entry.get("prompt")
        if not isinstance(tags, str) or not tags.strip():
            continue
        states[record_id] = {
            "character_id": record_id,
            "tags": tags.strip(),
            "spec_rev": member.spec_rev,
        }
    return list(states.values())


def resolve_stage_limit(user_settings: dict[str, Any], nsfw_mode: bool) -> int:
    """画像生成 1 回に載せられる人物数。NovelAI はモデルごと（V4.5=6 / V5=22）。

    チャットのように手番の TurnContext を持たない経路で、手番と同じ上限を使うため。
    """
    from ..consts.novelai_models import resolve_user_image_model
    from ..consts.prompt_expander import (
        MAX_CHARACTER_PROMPTS_V45,
        max_character_prompts,
    )
    from .providers import resolve_image_provider

    if resolve_image_provider() == "novelai":
        return max_character_prompts(resolve_user_image_model(user_settings, nsfw_mode))
    return MAX_CHARACTER_PROMPTS_V45


def _normalize_tag(tag: str) -> str:
    """タグ比較用の正規化（大小文字・アンダースコア・強調の括弧を無視）。"""
    return " ".join(tag.strip().strip("{}[]()").replace("_", " ").lower().split())


def remove_avoided_tags(prompt: str, negative_tags: str) -> str:
    """ポジティブのタグ列から、ネガティブに指定されたタグと同じものを取り除く。

    同じタグがポジティブとネガティブの両方にあると打ち消し合うため、
    人物ごとのネガティブ設定を LLM の出力（好みメモリ由来のタグなど）より優先する。
    """
    avoided = {_normalize_tag(t) for t in negative_tags.split(",") if t.strip()}
    avoided.discard("")
    if not avoided:
        return prompt
    kept = [
        tag.strip()
        for tag in prompt.split(",")
        if tag.strip() and _normalize_tag(tag) not in avoided
    ]
    return ", ".join(kept)


def attach_stage_negatives(
    characters: Sequence[dict[str, Any]],
    stage: Sequence[StageCharacter],
    limit: int | None,
) -> list[dict[str, Any]]:
    """画像生成用の character prompt に人物別ネガティブを付け、上限で切り詰める。

    ``characters`` は LLM 出力をパースしたもの。各要素の ``stage_index``
    （無ければ配列位置）で ``stage`` の人物に対応させる。一覧に無い人物
    （指示で新たに登場した人など）にはネガティブを付けない。
    ネガティブに指定したタグは、その人物のポジティブからも取り除く。
    """
    result: list[dict[str, Any]] = []
    for pos, entry in enumerate(characters):
        item = dict(entry)
        idx = item.get("stage_index", pos)
        if isinstance(idx, int) and 0 <= idx < len(stage):
            negative = stage[idx].negative_tags
            if negative and not item.get("negative_prompt"):
                item["negative_prompt"] = negative
            prompt = item.get("prompt")
            if negative and isinstance(prompt, str):
                cleaned = remove_avoided_tags(prompt, negative)
                if cleaned != prompt:
                    logger.info(
                        "removed avoided tags from %s: %r -> %r",
                        stage[idx].ref or idx,
                        prompt[:120],
                        cleaned[:120],
                    )
                    item["prompt"] = cleaned
        result.append(item)
    if limit is not None and limit > 0 and len(result) > limit:
        logger.info(
            "character prompts truncated to model limit: %d -> %d", len(result), limit
        )
        result = result[:limit]
    return result


_POSITION_LABEL_JA = {
    "left": "左",
    "center-left": "中央左",
    "center": "中央",
    "center-right": "中央右",
    "right": "右",
}


def build_session_characters_prompt_section(
    records: Sequence[Any],
    *,
    limit: int | None = None,
    protagonist_name: str | None = None,
    protagonist_tags: str | None = None,
    include_profile: bool = True,
    looks: dict[str, CharacterLook] | None = None,
) -> str:
    """Build a Japanese prompt fragment from session-character records.

    Returns an empty string when there are no on-stage records, so callers can
    append the result unconditionally and fall back to existing
    single-character behavior automatically (FR-011 / SC-003).

    Each character is shown with the look used this turn (``looks``). The
    user-written natural description is included only while the setting is in
    effect, so an outdated setting doesn't contradict the carried-over look.
    ``include_profile`` adds each non-protagonist's personality line. The
    protagonist keeps using the self profile / template character personality
    that the narrative prompts already carry.
    """
    roster = build_stage_roster(
        records,
        limit=limit,
        protagonist_name=protagonist_name,
        protagonist_tags=protagonist_tags,
        looks=looks,
    )
    if not roster:
        return ""

    lines: list[str] = ["", "[同シーンの登場キャラクター一覧]"]
    has_profile = False
    for character in roster:
        position_label = _POSITION_LABEL_JA.get(character.position, character.position)
        descriptor_bits: list[str] = [f"位置={position_label}"]
        if character.look_source != "history" and character.appearance_natural:
            descriptor_bits.append(f"外見: {character.appearance_natural}")
        if character.look_tags:
            descriptor_bits.append(f"タグ: {character.look_tags}")
        markers: list[str] = []
        if character.is_protagonist:
            markers.append("[主人公]")
        if character.exclude_from_effects:
            markers.append("[指示対象外・外見を変更しない]")
        if character.appearance_lock:
            markers.append("[姿を固定]")
        marker_str = (" " + " ".join(markers)) if markers else ""
        lines.append(f"- {character.name}（{', '.join(descriptor_bits)}）{marker_str}")
        if include_profile and not character.is_protagonist:
            profile_line = format_profile_line_ja(character.profile)
            if profile_line:
                lines.append(f"  人物設定: {profile_line}")
                has_profile = True
    lines.append("上記の登場人物が同じ場面に共存している前提で描写してください。")
    lines.append(
        "「指示対象外」「姿を固定」とマークされた人物にはユーザー指示の効果（着替え・行動・現実改変等）を"
        "適用せず、現在の外見をそのまま保ってください。その効果を別の人物に移してもいけません。"
    )
    if has_profile:
        lines.append(
            "「人物設定」がある人物は、その一人称・性格・反応スタイルを厳守し、"
            "セリフや反応をそれに合わせてください。"
        )
    return "\n".join(lines)


async def load_session_characters_for_prompt(
    db: AsyncSession,
    session_id: str,
) -> list[SessionCharacter]:
    """Single-query loader for prompt assembly (FR-011)."""
    return await fetch_session_characters(db, session_id)


async def upsert_protagonist_session_character(
    db: AsyncSession,
    session_id: str,
    *,
    name: str,
    appearance_tags: str,
) -> SessionCharacter:
    """Create the protagonist session_character, or sync its name.

    The row's appearance fields are the user's setting. They are filled from
    the resolved identity only when the row is created; later turns never
    overwrite them (the drawn look is kept per history instead).
    The record is always placed at slot_index=0, position=center.
    """
    existing = await fetch_protagonist_session_character(db, session_id)
    if existing is None:
        record = await insert_session_character(
            db,
            session_id=session_id,
            slot_index=0,
            name=name,
            appearance_natural="",
            appearance_tags=appearance_tags,
            position="center",
            is_protagonist=True,
        )
        # Shift non-protagonist records to start at slot 1
        await SessionCharacterService.reassign_positions(db, session_id)
        return record
    if name and existing.name != name:
        await update_session_character(db, existing.id, name=name)
        await db.refresh(existing)
    return existing


_POSITION_LABEL_EN = {
    "left": "left",
    "center-left": "center-left",
    "center": "center",
    "center-right": "center-right",
    "right": "right",
}


_GENDER_TOKEN_PATTERN = re.compile(
    r"\b\d*\+?(?:girl|boy|other)s?\b|\b(?:woman|man|women|men|female|male)\b",
    re.IGNORECASE,
)


def _with_gender_token(tags: str, profile: dict[str, Any] | None) -> str:
    """性別トークンが無いタグに、性格プロフィールの性別から 1girl / 1boy を補う。

    性別トークンが無いと女性寄りに描かれやすいため、画像用の一覧に載せるときだけ補う。
    """
    if not tags or _GENDER_TOKEN_PATTERN.search(tags):
        return tags
    gender = (profile or {}).get("gender")
    if gender == "woman":
        return f"1girl, {tags}"
    if gender == "man":
        return f"1boy, {tags}"
    return tags


def build_novelai_characters_section(
    records: Sequence[Any],
    *,
    protagonist_name: str | None = None,
    protagonist_tags: str | None = None,
    limit: int | None = None,
    looks: dict[str, CharacterLook] | None = None,
) -> str:
    """Build an English NovelAI-image prompt section from session-character records.

    Returns an empty string when there are no on-stage records with useful
    tag/name data so callers can append the result unconditionally
    (FR-010 / FR-012).

    Characters are listed in :func:`build_stage_roster` order with a ``ref``
    ("C1", "C2", ...) and their current look (``looks``). The LLM is told to
    put that ``ref`` on each entry, so its output maps back to characters by
    ref instead of array position. ``protagonist_name`` / ``protagonist_tags``
    act as a fallback for callers that resolve the identity before the DB
    record is created (i.e. the very first upsert turn). When both a DB
    protagonist record and kwargs are supplied, the DB record takes precedence.
    """
    roster = build_stage_roster(
        records,
        limit=limit,
        protagonist_name=protagonist_name,
        protagonist_tags=protagonist_tags,
        looks=looks,
    )
    if not roster:
        return ""

    lines: list[str] = [
        "",
        "## Registered Characters (all MUST appear in the image; tags are each "
        "character's CURRENT look: keep them unless the instruction changes "
        "THAT character)",
    ]
    for character in roster:
        position = _POSITION_LABEL_EN.get(character.position, character.position)
        tags = character.look_tags
        if not character.is_protagonist:
            tags = _with_gender_token(tags, character.profile)
        descriptor: list[str] = [f"position: {position}"]
        if tags:
            descriptor.append(f"tags: {tags}")
        elif character.appearance_natural:
            descriptor.append(f"appearance: {character.appearance_natural}")
        marker_parts: list[str] = []
        if character.is_protagonist:
            marker_parts.append("[protagonist]")
        if character.exclude_from_effects:
            marker_parts.append(
                "[bystander, do NOT apply user instruction effects, keep tags exactly]"
            )
        if character.appearance_lock:
            marker_parts.append("[fixed look, keep these tags exactly]")
        if character.negative_tags:
            marker_parts.append(f"avoid: {character.negative_tags}")
        marker = (" " + " ".join(marker_parts)) if marker_parts else ""
        lines.append(
            f"- {character.ref} ({character.name}, {', '.join(descriptor)}){marker}"
        )

    protagonist = next((c for c in roster if c.is_protagonist), None)
    lines.append("Rules for the registered characters:")
    if protagonist is not None:
        lines.append(
            f"- First-person words in the instruction (I, me, my, 僕, 私, 俺, "
            f"わたし) and sentences without a subject refer to {protagonist.ref} "
            "(the protagonist)."
        )
    lines.append(
        "- A description attached to a listed character inside the instruction "
        '(e.g. "Emma, the woman in a hostess dress") describes THAT character. '
        "It is NOT a new outfit or look for the protagonist or anyone else."
    )
    lines.append(
        "- Apply each change only to the character it happens to. Never move a "
        "change onto a different character. If the instruction changes a "
        "[fixed look] or [bystander] character, keep that character as is and "
        "do not give the change to anyone else."
    )
    lines.append(
        "- Clothing carries over: if the instruction does not give a character "
        "new clothes, KEEP the clothing and accessory tags from that character's "
        "current look. A body, gender or age transformation alone never removes "
        "clothes. Remove or change clothes only when the instruction explicitly "
        "says so for that character."
    )
    lines.append("- Never put a character's \"avoid\" tags into that character's tags.")
    lines.append(
        '- Output one "characters" entry per listed character, in the order '
        'above, each with "ref" set to its code, e.g. '
        '{"ref": "C1", "tags": "...", "position": "center"}. People who are not '
        "listed (only when the instruction introduces them) go AFTER all listed "
        'characters and have no "ref".'
    )
    return "\n".join(lines)


def _parse_history_after_description_json(
    after_description: str | None,
) -> dict | None:
    """Parse the JSON payload from a stored ``after_description`` string.

    Strips optional ``\u0060\u0060\u0060json`` fences and recovers from trailing prose by
    extracting the first ``{...}`` block. Returns ``None`` for legacy plain-text
    descriptions or any malformed payload.
    """
    if not after_description:
        return None
    text = after_description.strip()
    if text.startswith("```"):
        rest = text[3:]
        idx = 0
        while idx < len(rest) and not rest[idx].isspace():
            idx += 1
        text = rest[idx:].lstrip()
        if text.endswith("```"):
            text = text[: -len("```")].rstrip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    return data


def _looks_like_novelai_tag_list(text: str) -> bool:
    """Heuristic: treat comma-separated NovelAI-style prompts as tag lists.

    Used when ``after_description`` stores the character prompt string directly
    (Opus JSON-split success path) rather than a JSON envelope.
    """
    stripped = text.strip()
    if not stripped or len(stripped) < 8:
        return False
    # Japanese free-text history (non-Opus dress-up) is not tags.
    narrative_markers = (
        "に変身した姿",
        "という現実改変",
        "により変化した姿",
        "transformed appearance",
        "after transforming",
    )
    if any(marker in stripped for marker in narrative_markers):
        return False
    # Narrative Japanese sentences without tag separators are not tags.
    if "。" in stripped or "、" in stripped:
        return False
    lower = stripped.lower()
    has_subject = any(
        token in lower
        for token in (
            "1girl",
            "1boy",
            "1other",
            "2girls",
            "2boys",
            "solo",
            "multiple girls",
            "multiple boys",
        )
    )
    comma_count = stripped.count(",")
    if has_subject and comma_count >= 1:
        return True
    # Quality-tag heavy prompts without explicit 1girl/1boy still count.
    return comma_count >= 2 and any(
        token in lower
        for token in (
            "masterpiece",
            "best quality",
            "amazing quality",
            "very aesthetic",
        )
    )


def extract_protagonist_tags_from_history(
    after_description: str | None,
) -> str | None:
    """Extract the protagonist appearance tags from a prior history entry.

    Supported shapes:
    1. Multi-character JSON:
       ``{"characters": [{"tags": "...", ...}, ...], "scene": "..."}``
    2. Single-character JSON:
       ``{"character": "...", "scene": "..."}``
    3. Plain NovelAI tag list (character prompt stored as ``after_description``
       after a successful Opus JSON split).

    Returns ``None`` for Japanese narrative descriptions or malformed payloads.
    """
    if not after_description:
        return None
    data = _parse_history_after_description_json(after_description)
    if data is not None:
        # Multi-character format: {"characters": [{"tags": "...", ...}, ...]}
        characters = data.get("characters")
        if isinstance(characters, list) and characters:
            first = characters[0]
            if isinstance(first, dict):
                tags = first.get("tags")
                if isinstance(tags, str):
                    tags_stripped = tags.strip()
                    if tags_stripped:
                        return tags_stripped
        # Single-character format: {"character": "...", "scene": "..."}
        # 単一キャラ format でも主人公タグとして扱う (FR-010 dress-up bug fix)
        single = data.get("character")
        if isinstance(single, str):
            single_stripped = single.strip()
            if single_stripped:
                return single_stripped
        return None

    # Opus success path stores character prompt as a plain tag string.
    plain = after_description.strip()
    if _looks_like_novelai_tag_list(plain):
        return plain
    return None


def resolve_protagonist_image_identity(
    *,
    last_after_description: str | None,
    character: Any | None,
    self_profile: dict | None,
    custom_metadata: dict | None,
) -> tuple[str | None, str | None]:
    """Resolve the protagonist's display name and appearance tags for the
    NovelAI image prompt's Registered Characters section (FR-010).

    Priority for tags:
        1. JSON-parsed ``characters[0].tags`` from the previous turn's
           ``after_description`` (preserves continuity across turns).
        2. ``custom_metadata.base_tags`` -> ``self_profile.appearance_tags``
           -> ``character.base_tags``. Used both for new sessions and for
           legacy plain-text histories: without protagonist tags the LLM
           tends to merge supporting-character traits into the main subject,
           so a base-tag fallback is safer than skipping the entry entirely.

    The display name is taken from custom metadata, the self-profile, or the
    template character in that order, defaulting to ``"Protagonist"``.
    """
    custom_metadata = custom_metadata or {}

    extracted = extract_protagonist_tags_from_history(last_after_description)
    if extracted:
        tags: str | None = extracted
    else:
        candidates = (
            (custom_metadata.get("base_tags") or "").strip(),
            ((self_profile or {}).get("appearance_tags") or "").strip(),
            ((getattr(character, "base_tags", "") if character else "") or "").strip(),
        )
        tags = next((c for c in candidates if c), None)

    if not tags:
        return (None, None)

    name_candidates = (
        (custom_metadata.get("name") or "").strip(),
        ((self_profile or {}).get("display_name") or "").strip(),
        ((getattr(character, "name", "") if character else "") or "").strip(),
    )
    name = next((c for c in name_candidates if c), "Protagonist")
    return (name, tags)


__all__ = [
    "ALLOWED_POSITIONS",
    "CHARACTER_LIMIT",
    "CharacterGroupPresetService",
    "CharacterLimitExceededError",
    "CharacterLook",
    "CharacterPresetService",
    "LOOK_SOURCES",
    "SessionCharacterService",
    "StageCharacter",
    "attach_stage_negatives",
    "remove_avoided_tags",
    "build_character_states",
    "build_novelai_characters_section",
    "build_session_characters_prompt_section",
    "build_stage_roster",
    "dump_profile",
    "extract_protagonist_tags_from_history",
    "group_members",
    "load_character_looks",
    "load_session_characters_for_prompt",
    "looks_by_id",
    "parse_character_states",
    "record_profile",
    "ref_to_stage_index",
    "resolve_character_look",
    "resolve_protagonist_image_identity",
    "resolve_stage_limit",
    "stage_ref",
    "upsert_protagonist_session_character",
]
