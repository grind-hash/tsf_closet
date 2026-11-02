"""キャラクター(CharacterPreset)からプレイ・サロンの接客を始めるための変換。

キャラクターの人物設定を、カスタム画像のセッションと同じ形の人物像
(name / description / pronoun / personality / gender / base_tags / tsf_attitude)にし、
立ち絵を元画像にする。セッションごとのプロフィールはカスタムセッションと同じ
`session_{id}.json` に書くので、依頼・会話などは追加の分岐なしで読める。
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from ..databases.base import async_session_factory
from ..databases.character_repo import fetch_character_preset, fetch_character_presets
from ..databases.models import CharacterPreset
from .character_preset_portrait import preset_portrait_file
from .character_profile import normalize_character_profile
from .character_service import record_profile, with_gender_token
from .custom_sessions import normalize_gender
from .source_snapshot import split_appearance_tags


class PresetSessionError(RuntimeError):
    """キャラクターからセッションを始められない。code は API のエラーコード。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PresetPlaySource:
    preset_id: str
    profile: dict[str, str]
    image_path: Path


def preset_play_profile(preset: CharacterPreset) -> dict[str, str]:
    """キャラクターを、プレイ用の人物像(カスタムセッションのプロフィールの形)にする。

    説明は人物メモ、無ければ外見の説明文。外見タグは情景・動作のタグを落とし、
    性別トークンが無ければ補う(無いと女性寄りに描かれる)。
    """
    profile = normalize_character_profile(record_profile(preset) or {})
    tags = str(preset.appearance_tags or "").strip()
    identity, clothing = split_appearance_tags(tags)
    look = ", ".join(part for part in (identity, clothing) if part) or tags
    return {
        "name": preset.name,
        "description": profile["memo"] or str(preset.appearance_natural or "").strip(),
        "pronoun": profile["pronoun"] or "僕",
        "personality": profile["personality"],
        "gender": normalize_gender(profile["gender"]),
        "base_tags": with_gender_token(look, profile),
        "tsf_attitude": profile["tsf_attitude"],
    }


async def load_preset_play_source(preset_id: str) -> PresetPlaySource:
    """キャラクターの人物像と立ち絵のファイル。

    Raises: PresetSessionError(character_preset_not_found / image_not_found)
    """
    async with async_session_factory() as db:
        preset = await fetch_character_preset(db, preset_id)
        if preset is None:
            raise PresetSessionError(
                "character_preset_not_found", "キャラクターが見つかりません"
            )
        image_path = preset_portrait_file(preset)
        profile = preset_play_profile(preset)
    if image_path is None:
        raise PresetSessionError("image_not_found", "キャラクターの立ち絵がありません")
    return PresetPlaySource(preset_id=preset_id, profile=profile, image_path=image_path)


def portrait_png_bytes(path: Path) -> bytes:
    """立ち絵を PNG のバイト列にする(元画像は .png で保存するため)。"""
    data = path.read_bytes()
    if data.startswith(b"\x89PNG"):
        return data
    with Image.open(BytesIO(data)) as image:
        converted = BytesIO()
        image.save(converted, format="PNG")
        return converted.getvalue()


async def list_salon_preset_customers(db: AsyncSession) -> list[dict[str, Any]]:
    """サロンに来店するキャラクター(来店する設定で、立ち絵があるもの)の id と名前。"""
    presets = await fetch_character_presets(db)
    return [
        {"id": preset.id, "name": preset.name}
        for preset in presets
        if preset.salon_enabled and preset_portrait_file(preset) is not None
    ]
