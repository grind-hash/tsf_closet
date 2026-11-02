"""BGM catalog loader for Adventure mode.

The LLM selects one semantic key per turn; the frontend maps keys to
audio URLs served by the backend and handles playback. Keys are the only
contract between the two layers, so the LLM must never see or emit
filenames.

Keys, descriptions, and audio filenames live in ``data/bgm/catalog.json``
so that adding a track only requires dropping an audio file and adding a
JSON entry. The catalog is reloaded when the file's mtime changes, so no
server restart is needed. A broken catalog never fails a turn: the last
successfully parsed catalog (or a minimal built-in default) is kept.

Each track has a scope. Only ``adventure`` tracks are offered to the
Adventure LLM; ``salon`` tracks are chosen by the salon screens themselves,
and ``salon_se`` entries are the salon's one-shot sound effects.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# モジュール属性にしておくとテストから monkeypatch で差し替えられる
_CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "bgm" / "catalog.json"


class BgmTrack(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]+$", min_length=1, max_length=64)
    file: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=300)
    # 出所の表記。BGMテスト画面にそのまま表示するので、表示したい文をそのまま
    # 書く(例: "SUNO v4.5-all で作成", "○○の音楽素材 より配布")。自作曲など
    # 表記が不要な曲では省略する。
    # 任意フィールドにしておくこと。必須にすると credit の無いカタログが検証
    # エラーでカタログ全体の破損扱いになり、BGM が組み込み既定の1曲へ劣化する。
    credit: str | None = Field(default=None, max_length=120)
    # どのモードの曲か。adventure だけを TSF シナリオの LLM に選曲候補として渡し、
    # salon はサロン経営の画面が幕に合わせて自分で選ぶ。salon_se はサロンの効果音
    # (ループしない短い音)。省略時は adventure
    scope: Literal["adventure", "salon", "salon_se"] = "adventure"

    @field_validator("file")
    @classmethod
    def reject_path_traversal(cls, value: str) -> str:
        if Path(value).name != value:
            raise ValueError(f"file must be a bare filename: {value!r}")
        return value


class BgmCatalog(BaseModel):
    default_key: str = Field(min_length=1, max_length=64)
    tracks: list[BgmTrack] = Field(min_length=1)

    def adventure_tracks(self) -> list[BgmTrack]:
        """TSF シナリオの選曲候補。adventure の曲が1曲も無ければ全曲を使う。"""
        tracks = [track for track in self.tracks if track.scope == "adventure"]
        return tracks or list(self.tracks)

    def resolved_default_key(self) -> str:
        tracks = self.adventure_tracks()
        if self.default_key in {track.key for track in tracks}:
            return self.default_key
        return tracks[0].key


# カタログが一度も読めない場合の最小フォールバック(daily 1曲)
_BUILTIN_CATALOG = BgmCatalog(
    default_key="daily",
    tracks=[
        BgmTrack(
            key="daily",
            file="scene06_daily.ogg",
            description="everyday ordinary scenes; also the fallback",
        )
    ],
)

# (mtime, catalog)。mtime が変わったときだけ再パースする
_cache: tuple[float, BgmCatalog] | None = None


def get_bgm_catalog() -> BgmCatalog:
    """カタログを返す。JSON 破損時は last-good、初回破損時は組み込み既定。"""
    global _cache
    try:
        mtime = _CATALOG_PATH.stat().st_mtime
    except OSError as error:
        if _cache is not None:
            return _cache[1]
        logger.warning("BGM catalog is unreadable at %s: %s", _CATALOG_PATH, error)
        return _BUILTIN_CATALOG
    if _cache is not None and _cache[0] == mtime:
        return _cache[1]
    try:
        catalog = BgmCatalog.model_validate(
            json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        )
    except (OSError, ValueError) as error:
        # ValueError は json.JSONDecodeError と pydantic.ValidationError を包含する
        logger.warning("BGM catalog failed to parse, keeping previous: %s", error)
        return _cache[1] if _cache is not None else _BUILTIN_CATALOG
    _cache = (mtime, catalog)
    return catalog


def get_bgm_keys() -> tuple[str, ...]:
    """TSF シナリオの LLM が選べるキー(adventure の曲だけ)。"""
    return tuple(track.key for track in get_bgm_catalog().adventure_tracks())


def get_bgm_default() -> str:
    return get_bgm_catalog().resolved_default_key()


def get_bgm_prompt_guide() -> str:
    """Shared enumeration for the director and resolution system prompts."""
    return ", ".join(
        f"{track.key} ({track.description})"
        for track in get_bgm_catalog().adventure_tracks()
    )


def resolve_bgm_audio_path(filename: str) -> Path | None:
    """カタログ登録済みファイル名だけを実パスへ解決する(トラバーサル防止)。"""
    name = Path(filename).name
    if name != filename:
        return None
    for track in get_bgm_catalog().tracks:
        if track.file == name:
            path = _CATALOG_PATH.parent / name
            return path if path.is_file() else None
    return None


# Shared selection policy for the director and resolution system prompts.
# Grounds "importance" in relationship/story progression so a minor early
# event (e.g. a small gift right after the start) never gets the climax track.
BGM_SELECTION_RULES: str = (
    "Choose the category from the scene's location and mood, weighed against "
    "how far the story and the relationship have actually progressed. "
    "important_event is reserved for a rare climactic turning point relative "
    "to that progression, such as a confession, its decisive answer, or a "
    "revelation that permanently changes the relationship or the story. When "
    "state.sim.affection (0-100) and state.sim.stage are present, measure the "
    "relationship progression with them: while affection is low or the stage "
    "is early, greetings, small gifts, first outings, and pleasant "
    "conversation are ordinary courtship beats that take daily or the "
    "category matching the location, even when the partner is delighted. "
    "When no category clearly fits, use daily; when in doubt between "
    "important_event and another category, choose the other category."
)

__all__ = [
    "BGM_SELECTION_RULES",
    "BgmCatalog",
    "BgmTrack",
    "get_bgm_catalog",
    "get_bgm_default",
    "get_bgm_keys",
    "get_bgm_prompt_guide",
    "resolve_bgm_audio_path",
]
