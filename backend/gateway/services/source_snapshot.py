"""開始素材(セッション / 履歴 / Prompt Expander エントリ)のスナップショット。

Adventure の run 作成とキャラチャットのキャラ作成・姿の変更が共用する。
「セッション時点の画像ファイル・外見タグ・服装タグ・経緯・属性・統計」を
1 つにまとめ、呼び出し側はこれをコピーして自分の永続化形式へ写す。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ..databases.base import async_session_factory
from .character_service import extract_protagonist_tags_from_history
from .characters import character_manager
from .custom_sessions import load_custom_session_metadata
from .image_paths import resolve_stored_image_path
from .prompt_expander_service import (
    PromptExpanderError,
    PromptExpanderService,
    entry_nsfw,
    entry_to_dict,
    resolve_entry_image_file,
)
from .session import DEFAULT_USER_ID, session_store


class SourceSnapshotError(RuntimeError):
    """開始素材が見つからない / 画像が無い。code は source_not_found | image_not_found。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


CLOTHING_TAG_PATTERN = re.compile(
    r"\b(?:dress|skirt|shirt|top|pants|shorts|uniform|jacket|coat|suit|"
    r"leotard|lingerie|underwear|bra|panties|swimsuit|kimono|clothes|"
    r"outfit|shoes|boots|socks|stockings|gloves|hat)\b",
    re.IGNORECASE,
)
SCENE_OR_ACTION_TAG_PATTERN = re.compile(
    r"\b(?:looking|applying|standing|sitting|walking|mirror|closet|room|"
    r"background|shelf)\b",
    re.IGNORECASE,
)


def history_visual_description(history: Any) -> tuple[str, str]:
    """履歴の after/before 記述から (外見タグ, 服装タグ) を取り出す。

    タグ列として解釈できないときは記述全文を外見として返し、服装は空。
    """
    description = history.after_description or history.before_description or ""
    extracted = extract_protagonist_tags_from_history(description)
    if not extracted:
        return description.strip(), ""

    tags = [tag.strip() for tag in extracted.split(",") if tag.strip()]
    clothing = [tag for tag in tags if CLOTHING_TAG_PATTERN.search(tag)]
    appearance = [
        tag
        for tag in tags
        if not CLOTHING_TAG_PATTERN.search(tag)
        and not SCENE_OR_ACTION_TAG_PATTERN.search(tag)
    ]
    return ", ".join(appearance) or extracted, ", ".join(clothing)


def identity_tags_only(tags: str) -> str:
    """カンマ区切りタグから服装・情景タグを除き、同一性タグだけを返す。

    partner_appearance の初期値を作る history_visual_description と同じ
    フィルタを使い、書き戻し後も初期値と同じ形式を保つ。npc_tags は服装を
    含むため、素のまま保存すると攻略対象の服装が以後固定されてしまう。
    """
    parts = [tag.strip() for tag in tags.split(",") if tag.strip()]
    identity = [
        tag
        for tag in parts
        if not CLOTHING_TAG_PATTERN.search(tag)
        and not SCENE_OR_ACTION_TAG_PATTERN.search(tag)
    ]
    return ", ".join(identity)


async def resolve_session_identity(session: Any) -> tuple[str, str]:
    """セッションの人物名と一人称を (self_profile → テンプレ → カスタム) の順で解決する。

    conversation_service.build_chat_context と同じ規則。既定は ("キャラクター", "僕")。
    """
    name, pronoun = "キャラクター", "僕"
    if bool(getattr(session, "self_mode", False)):
        profile = await session_store.get_self_profile()
        if profile:
            name = str(profile.get("display_name") or name)
            pronoun = str(profile.get("pronoun") or pronoun)
        return name, pronoun
    character_id = str(getattr(session, "character_id", "") or "")
    if character_id:
        character = character_manager.get_by_id(character_id)
        if character:
            return character.name, character.pronoun
    metadata = load_custom_session_metadata(str(getattr(session, "id", "") or ""))
    if metadata:
        name = str(metadata.get("name") or name)
        pronoun = str(metadata.get("pronoun") or pronoun)
    return name, pronoun


async def build_prompt_expander_snapshot(
    entry_id: str,
) -> tuple[dict[str, Any], Path, str, bool]:
    """Prompt Expander のエントリを開始素材にしたスナップショットを組み立てる。

    ゲームセッション由来の時系列・属性・統計は無く、外見は保存済みの最終プロンプト
    （＋キャラクタープロンプト）を使う。NSFW は画像モデルの family から導出する。
    """
    try:
        async with async_session_factory() as db:
            entry = await PromptExpanderService.get_entry(
                db, entry_id=entry_id, user_id=DEFAULT_USER_ID
            )
            view = entry_to_dict(entry)
            image_path = resolve_entry_image_file(entry)
            nsfw_mode = bool(entry_nsfw(entry))
    except PromptExpanderError as exc:
        raise SourceSnapshotError(
            "source_not_found", "開始元の Prompt Expander エントリが見つかりません"
        ) from exc
    if image_path is None:
        raise SourceSnapshotError("image_not_found", "開始画像が見つかりません")
    appearance_parts = [str(view.get("final_prompt") or "").strip()]
    appearance_parts.extend(
        str(item).strip() for item in view.get("character_prompts") or []
    )
    appearance = ", ".join(part for part in appearance_parts if part)
    snapshot = {
        "source_session_id": None,
        "source_history_id": None,
        "source_prompt_expander_entry_id": entry_id,
        "character_name": None,
        "appearance": appearance,
        "clothing": "",
        "attributes": [],
        "timeline": [],
        "stats": None,
    }
    return snapshot, image_path, appearance, nsfw_mode


async def build_source_snapshot(
    source_session_id: str | None,
    source_history_id: str | None,
    *,
    source_prompt_expander_entry_id: str | None = None,
) -> tuple[dict[str, Any], Path, str, bool]:
    """開始素材から (snapshot, 画像パス, 外見タグ, nsfw_mode) を組み立てる。

    履歴を指定したときはその時点(履歴の created_at まで)の経緯・属性・統計に絞る。

    Raises:
        SourceSnapshotError: 素材が無い(source_not_found) / 画像が無い(image_not_found)
    """
    if source_prompt_expander_entry_id:
        return await build_prompt_expander_snapshot(source_prompt_expander_entry_id)
    if not source_session_id:
        raise SourceSnapshotError(
            "source_not_found", "開始元セッションが見つかりません"
        )
    source_session = await session_store.get_session_by_id(source_session_id)
    if source_session is None or source_session.user_id != DEFAULT_USER_ID:
        raise SourceSnapshotError(
            "source_not_found", "開始元セッションが見つかりません"
        )

    source_history = None
    until_created_at = None
    appearance = ""
    starting_clothing = ""
    if source_history_id:
        source_history = await session_store.get_history_by_id(source_history_id)
        if source_history is None or source_history.session_id != source_session_id:
            raise SourceSnapshotError(
                "source_not_found", "開始元の履歴が見つかりません"
            )
        image_path = session_store.resolve_history_image_file(source_history)
        until_created_at = source_history.created_at
        appearance, starting_clothing = history_visual_description(source_history)
    else:
        image_path = resolve_stored_image_path(source_session.current_image_path)
        current_image_name = Path(source_session.current_image_path or "").name
        histories = await session_store.get_history(source_session_id)
        current_history = next(
            (
                item
                for item in reversed(histories)
                if Path(item.image_path).name == current_image_name
            ),
            None,
        )
        if current_history is not None:
            appearance, starting_clothing = history_visual_description(current_history)

    if image_path is None:
        raise SourceSnapshotError("image_not_found", "開始画像が見つかりません")

    timeline = await session_store.get_session_timeline_until(
        source_session_id, until_created_at=until_created_at, limit=30
    )
    attributes_raw = await session_store.get_session_attributes(source_session_id)
    attributes: list[str] = []
    for attribute in attributes_raw:
        created_raw = attribute.get("created_at")
        if until_created_at is not None and created_raw:
            try:
                if datetime.fromisoformat(str(created_raw)) > until_created_at:
                    continue
            except (TypeError, ValueError):
                pass
        attributes.append(str(attribute.get("attribute_text", "")))

    stats = await session_store.get_session_stats(source_session_id)
    if source_history_id and stats is not None:
        stats = await session_store.reconstruct_stats_at_history(
            source_session_id,
            source_history_id,
            difficulty=stats.difficulty,
            nsfw_mode=stats.nsfw_mode,
        )
    nsfw_mode = bool(stats.nsfw_mode) if stats else False
    # 旧テスト用モック等で character_id が無くても snapshot 構築は続行する
    source_character = character_manager.get_by_id(
        str(getattr(source_session, "character_id", "") or "")
    )
    snapshot = {
        "source_session_id": source_session_id,
        "source_history_id": source_history_id,
        "character_name": source_character.name if source_character else None,
        "appearance": appearance,
        "clothing": starting_clothing,
        "attributes": attributes,
        "timeline": [
            {"type": event_type, "text": text} for event_type, text in timeline
        ],
        "stats": {
            "bloom": stats.bloom,
            "shame": stats.shame,
            "adaptation": stats.adaptation,
        }
        if stats
        else None,
    }
    return snapshot, image_path, appearance, nsfw_mode
