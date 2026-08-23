"""Prompt Expander サービス。

自然言語指示を NovelAI テキストモデルで画像プロンプトへ拡張し、
NovelAI で画像を生成して専用の履歴（1セッション複数エントリ）へ保存する。
通常ゲームの Session/History には影響を与えない独立機能。
"""

from __future__ import annotations

import base64
import json
import logging
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Literal, Optional, Sequence

import httpx
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..consts.novelai_models import get_image_model_info
from ..consts.novelai_text_models import (
    DEFAULT_NOVELAI_TEXT_MODEL,
    NOVELAI_TEXT_MODEL_LABELS,
    NOVELAI_TEXT_MODEL_OPTIONS,
    is_novelai_text_model,
)
from ..consts.prompt_expander import (
    DEFAULT_PROMPT_EXPANDER_I2I_NOISE,
    DEFAULT_PROMPT_EXPANDER_I2I_STRENGTH,
    DEFAULT_PROMPT_EXPANDER_IMAGE_MODEL,
    DEFAULT_PROMPT_EXPANDER_IMAGE_SIZE,
    DEFAULT_PROMPT_EXPANDER_MANGA_LAYOUT,
    DEFAULT_PROMPT_EXPANDER_MANGA_READING_DIRECTION,
    DEFAULT_PROMPT_EXPANDER_MANGA_TEXT_LANGUAGE,
    PROMPT_EXPANDER_IMAGE_SIZES,
    PROMPT_EXPANDER_MANGA_LAYOUTS,
    PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO,
    PROMPT_EXPANDER_MANGA_READING_DIRECTIONS,
    PROMPT_EXPANDER_MANGA_TEXT_LANGUAGES,
    PROMPT_EXPANDER_MEMORY_MAX_LEN,
    PROMPT_EXPANDER_TITLE_MAX_LEN,
    is_prompt_expander_image_model,
    max_character_prompts,
    normalize_manga_panel_count,
    supports_manga_mode,
)
from ..databases.base import async_session_factory
from ..databases.models import PromptExpanderEntry, PromptExpanderSession, User
from ..settings.config import settings
from .anlas_service import AnlasBalance, get_anlas_balance
from .image_generation import ImageGenerationResult, image_service
from .llm_service import llm_service
from .prompt_expander_prompts import (
    ExpandMode,
    MangaOptions,
    PromptExpanderOutputError,
    build_negative_system_prompt,
    build_negative_user_prompt,
    build_positive_system_prompt,
    build_positive_user_prompt,
    build_suggest_characters_prompts,
    parse_character_json,
    parse_manga_json,
    parse_suggestions_json,
    sanitize_by_mode,
)
from .session import DEFAULT_USER_ID, session_store
from .settings_service import settings_service

logger = logging.getLogger(__name__)

SourceKind = Literal["none", "history", "entry", "upload"]


class PromptExpanderError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# 設定（users.prompt_expander_settings_json）
# ---------------------------------------------------------------------------


class PromptExpanderSettings(BaseModel):
    """Prompt Expander 専用設定。プレイ側の設定とは独立。

    保存済み JSON の読込では未知キーを無視し、不正値は既定値へ倒す。
    """

    model_config = ConfigDict(extra="ignore")

    text_model: str = DEFAULT_NOVELAI_TEXT_MODEL
    image_model: str = DEFAULT_PROMPT_EXPANDER_IMAGE_MODEL
    image_size: str = DEFAULT_PROMPT_EXPANDER_IMAGE_SIZE
    i2i_strength: float = Field(DEFAULT_PROMPT_EXPANDER_I2I_STRENGTH, ge=0.01, le=0.99)
    i2i_noise: float = Field(DEFAULT_PROMPT_EXPANDER_I2I_NOISE, ge=0.0, le=0.99)
    seed: Optional[int] = Field(None, ge=0, le=999999999)
    memory_text: str = Field("", max_length=PROMPT_EXPANDER_MEMORY_MAX_LEN)
    use_memory: bool = False
    confirm_before_generate: bool = True
    inherit_source_prompts: bool = True
    # 漫画モード（V5 のコマ割り・吹き出し生成。拡張時の LLM 指示にだけ効く）
    manga_mode: bool = False
    manga_panel_count: int = PROMPT_EXPANDER_MANGA_PANEL_COUNT_AUTO
    manga_layout: str = DEFAULT_PROMPT_EXPANDER_MANGA_LAYOUT
    manga_dialogue: bool = True
    manga_text_language: str = DEFAULT_PROMPT_EXPANDER_MANGA_TEXT_LANGUAGE
    manga_sound_effects: bool = True
    manga_reading_direction: str = DEFAULT_PROMPT_EXPANDER_MANGA_READING_DIRECTION

    @field_validator("manga_reading_direction", mode="before")
    @classmethod
    def _coerce_manga_reading_direction(cls, value: object) -> str:
        return (
            value  # type: ignore[return-value]
            if isinstance(value, str)
            and value in PROMPT_EXPANDER_MANGA_READING_DIRECTIONS
            else DEFAULT_PROMPT_EXPANDER_MANGA_READING_DIRECTION
        )

    @field_validator("manga_panel_count", mode="before")
    @classmethod
    def _coerce_manga_panel_count(cls, value: object) -> int:
        return normalize_manga_panel_count(value)

    @field_validator("manga_layout", mode="before")
    @classmethod
    def _coerce_manga_layout(cls, value: object) -> str:
        return (
            value  # type: ignore[return-value]
            if isinstance(value, str) and value in PROMPT_EXPANDER_MANGA_LAYOUTS
            else DEFAULT_PROMPT_EXPANDER_MANGA_LAYOUT
        )

    @field_validator("manga_text_language", mode="before")
    @classmethod
    def _coerce_manga_text_language(cls, value: object) -> str:
        return (
            value  # type: ignore[return-value]
            if isinstance(value, str) and value in PROMPT_EXPANDER_MANGA_TEXT_LANGUAGES
            else DEFAULT_PROMPT_EXPANDER_MANGA_TEXT_LANGUAGE
        )

    @field_validator("text_model", mode="before")
    @classmethod
    def _coerce_text_model(cls, value: object) -> str:
        return value if is_novelai_text_model(value) else DEFAULT_NOVELAI_TEXT_MODEL  # type: ignore[return-value]

    @field_validator("image_model", mode="before")
    @classmethod
    def _coerce_image_model(cls, value: object) -> str:
        return (
            value  # type: ignore[return-value]
            if is_prompt_expander_image_model(value)  # type: ignore[arg-type]
            else DEFAULT_PROMPT_EXPANDER_IMAGE_MODEL
        )

    @field_validator("image_size", mode="before")
    @classmethod
    def _coerce_image_size(cls, value: object) -> str:
        return (
            value  # type: ignore[return-value]
            if isinstance(value, str) and value in PROMPT_EXPANDER_IMAGE_SIZES
            else DEFAULT_PROMPT_EXPANDER_IMAGE_SIZE
        )

    @field_validator("memory_text", mode="before")
    @classmethod
    def _coerce_memory_text(cls, value: object) -> str:
        if not isinstance(value, str):
            return ""
        return value.strip()[:PROMPT_EXPANDER_MEMORY_MAX_LEN]


def _settings_from_json(raw: str | None) -> PromptExpanderSettings:
    """保存済み JSON を寛容に読む。壊れたキーは捨てて残りを活かす。"""
    if not raw:
        return PromptExpanderSettings()
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return PromptExpanderSettings()
    if not isinstance(data, dict):
        return PromptExpanderSettings()
    payload = dict(data)
    for _ in range(len(PromptExpanderSettings.model_fields) + 1):
        try:
            return PromptExpanderSettings.model_validate(payload)
        except ValidationError as exc:
            removed = False
            for error in exc.errors():
                loc = error.get("loc") or ()
                if loc and loc[0] in payload:
                    payload.pop(loc[0], None)
                    removed = True
            if not removed:
                break
    return PromptExpanderSettings()


def text_model_options() -> list[dict[str, str]]:
    return [
        {"id": model, "label": NOVELAI_TEXT_MODEL_LABELS.get(model, model)}
        for model in NOVELAI_TEXT_MODEL_OPTIONS
    ]


def novelai_configured() -> bool:
    return bool(settings.novelai_api_key)


# ---------------------------------------------------------------------------
# 画像ファイル
# ---------------------------------------------------------------------------


def _images_root() -> Path:
    return settings.prompt_expander_images_dir


def entry_image_dir(session_id: str) -> Path:
    return _images_root() / session_id


def entry_image_file(session_id: str, entry_id: str) -> Path:
    return entry_image_dir(session_id) / f"{entry_id}.png"


def entry_image_relpath(session_id: str, entry_id: str) -> str:
    """DB に保存する相対パス（data/ の親からの相対）。"""
    path = entry_image_file(session_id, entry_id)
    try:
        return str(path.relative_to(_images_root().parent.parent))
    except ValueError:
        return str(path)


def resolve_entry_image_file(entry: PromptExpanderEntry) -> Path | None:
    candidates = [entry_image_file(entry.session_id, entry.id)]
    if entry.image_path:
        raw = Path(entry.image_path)
        candidates.append(raw)
        candidates.append(_images_root().parent.parent / entry.image_path)
    for path in candidates:
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def remove_session_images(session_id: str) -> None:
    shutil.rmtree(entry_image_dir(session_id), ignore_errors=True)


def remove_entry_image(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Failed to remove prompt expander image: %s", path)


def decode_image_base64(data: str) -> bytes:
    """data URL / 素の base64 を PNG バイト列へ正規化する。"""
    if not isinstance(data, str) or not data.strip():
        raise PromptExpanderError("invalid_image", "画像データが空です")
    payload = data.strip()
    if "," in payload and payload.lower().startswith("data:"):
        payload = payload.split(",", 1)[1]
    try:
        raw = base64.b64decode(payload, validate=False)
    except (ValueError, TypeError) as exc:
        raise PromptExpanderError(
            "invalid_image", "画像データを復号できません"
        ) from exc
    try:
        with Image.open(BytesIO(raw)) as img:
            img.load()
            converted = img.convert("RGBA") if img.mode not in ("RGB", "RGBA") else img
            buffer = BytesIO()
            converted.save(buffer, format="PNG")
            return buffer.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise PromptExpanderError("invalid_image", "画像として読み込めません") from exc


def _write_png(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


# ---------------------------------------------------------------------------
# ビュー変換
# ---------------------------------------------------------------------------


def _to_iso(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return datetime.now().isoformat()


def _load_character_prompts(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if isinstance(item, str) and item.strip()]


def entry_nsfw(entry: PromptExpanderEntry) -> bool | None:
    if not entry.image_model:
        return None
    return get_image_model_info(entry.image_model, nsfw_mode=True).family == "full"


def entry_to_dict(entry: PromptExpanderEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "session_id": entry.session_id,
        "kind": entry.kind,
        "instruction": entry.instruction,
        "positive_expand_mode": entry.positive_expand_mode or "off",
        "negative_expand_mode": entry.negative_expand_mode or "off",
        "character_mode": bool(entry.character_mode),
        "final_prompt": entry.final_prompt or "",
        "final_negative_prompt": entry.final_negative_prompt or "",
        "character_prompts": _load_character_prompts(entry.character_prompts_json),
        "image_model": entry.image_model,
        "text_model": entry.text_model,
        "seed": entry.seed,
        "i2i_strength": entry.i2i_strength,
        "i2i_noise": entry.i2i_noise,
        "image_size": entry.image_size,
        "manga_mode": bool(entry.manga_mode),
        "manga_panel_count": entry.manga_panel_count,
        "source_kind": entry.source_kind or "none",
        "source_history_id": entry.source_history_id,
        "source_entry_id": entry.source_entry_id,
        "image_url": f"/prompt-expander/images/{entry.id}",
        "nsfw": entry_nsfw(entry),
        "created_at": _to_iso(entry.created_at),
    }


@dataclass
class SessionView:
    id: str
    title: str
    entry_count: int
    thumbnail_entry_id: Optional[str]
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "entry_count": self.entry_count,
            "thumbnail_url": (
                f"/prompt-expander/images/{self.thumbnail_entry_id}"
                if self.thumbnail_entry_id
                else None
            ),
            "created_at": _to_iso(self.created_at),
            "updated_at": _to_iso(self.updated_at),
        }


def _normalize_title(title: str | None) -> str:
    text = " ".join((title or "").split())
    return text[:PROMPT_EXPANDER_TITLE_MAX_LEN]


# ---------------------------------------------------------------------------
# DB 操作（flush のみ。commit は呼び出し側）
# ---------------------------------------------------------------------------


class PromptExpanderService:
    @staticmethod
    async def list_sessions(
        db: AsyncSession, *, user_id: str = DEFAULT_USER_ID
    ) -> list[SessionView]:
        stmt = (
            select(PromptExpanderSession)
            .where(PromptExpanderSession.user_id == user_id)
            .order_by(
                desc(PromptExpanderSession.updated_at), desc(PromptExpanderSession.id)
            )
        )
        sessions = (await db.execute(stmt)).scalars().all()
        if not sessions:
            return []
        session_ids = [s.id for s in sessions]
        count_stmt = (
            select(PromptExpanderEntry.session_id, func.count())
            .where(PromptExpanderEntry.session_id.in_(session_ids))
            .group_by(PromptExpanderEntry.session_id)
        )
        counts = {
            sid: int(count or 0) for sid, count in (await db.execute(count_stmt)).all()
        }
        views: list[SessionView] = []
        for session in sessions:
            latest_stmt = (
                select(PromptExpanderEntry.id)
                .where(PromptExpanderEntry.session_id == session.id)
                .order_by(
                    desc(PromptExpanderEntry.created_at), desc(PromptExpanderEntry.id)
                )
                .limit(1)
            )
            latest_id = (await db.execute(latest_stmt)).scalar_one_or_none()
            views.append(
                SessionView(
                    id=session.id,
                    title=session.title or "",
                    entry_count=counts.get(session.id, 0),
                    thumbnail_entry_id=latest_id,
                    created_at=session.created_at,
                    updated_at=session.updated_at,
                )
            )
        return views

    @staticmethod
    async def get_session(
        db: AsyncSession, *, session_id: str, user_id: str = DEFAULT_USER_ID
    ) -> PromptExpanderSession:
        stmt = select(PromptExpanderSession).where(
            PromptExpanderSession.id == session_id,
            PromptExpanderSession.user_id == user_id,
        )
        session = (await db.execute(stmt)).scalar_one_or_none()
        if session is None:
            raise PromptExpanderError(
                "session_not_found", "Prompt Expander セッションが見つかりません"
            )
        return session

    @staticmethod
    async def create_session(
        db: AsyncSession, *, title: str | None = None, user_id: str = DEFAULT_USER_ID
    ) -> PromptExpanderSession:
        await _ensure_user(db, user_id)
        normalized = _normalize_title(title)
        if not normalized:
            count_stmt = (
                select(func.count())
                .select_from(PromptExpanderSession)
                .where(PromptExpanderSession.user_id == user_id)
            )
            total = int((await db.execute(count_stmt)).scalar_one() or 0)
            normalized = f"Session {total + 1}"
        # SQLite の current_timestamp は秒精度で同時刻になり並び順が不定になるため、
        # この機能の時刻は Python 側で付与する
        now = datetime.now()
        session = PromptExpanderSession(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=normalized,
            created_at=now,
            updated_at=now,
        )
        db.add(session)
        await db.flush()
        return session

    @staticmethod
    async def rename_session(
        db: AsyncSession,
        *,
        session_id: str,
        title: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> PromptExpanderSession:
        session = await PromptExpanderService.get_session(
            db, session_id=session_id, user_id=user_id
        )
        normalized = _normalize_title(title)
        if not normalized:
            raise PromptExpanderError("invalid_title", "タイトルを入力してください")
        session.title = normalized
        session.updated_at = datetime.now()
        await db.flush()
        return session

    @staticmethod
    async def delete_session(
        db: AsyncSession, *, session_id: str, user_id: str = DEFAULT_USER_ID
    ) -> bool:
        stmt = select(PromptExpanderSession).where(
            PromptExpanderSession.id == session_id,
            PromptExpanderSession.user_id == user_id,
        )
        session = (await db.execute(stmt)).scalar_one_or_none()
        if session is None:
            return False
        await db.delete(session)
        await db.flush()
        return True

    @staticmethod
    async def list_session_entries(
        db: AsyncSession, *, session_id: str, user_id: str = DEFAULT_USER_ID
    ) -> list[PromptExpanderEntry]:
        await PromptExpanderService.get_session(
            db, session_id=session_id, user_id=user_id
        )
        stmt = (
            select(PromptExpanderEntry)
            .where(PromptExpanderEntry.session_id == session_id)
            .order_by(
                desc(PromptExpanderEntry.created_at), desc(PromptExpanderEntry.id)
            )
        )
        return list((await db.execute(stmt)).scalars().all())

    @staticmethod
    async def list_entries(
        db: AsyncSession,
        *,
        user_id: str = DEFAULT_USER_ID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PromptExpanderEntry], int]:
        offset = (page - 1) * page_size
        base = (
            select(PromptExpanderEntry)
            .join(
                PromptExpanderSession,
                PromptExpanderSession.id == PromptExpanderEntry.session_id,
            )
            .where(PromptExpanderSession.user_id == user_id)
        )
        count_stmt = select(func.count()).select_from(base.subquery())
        total = int((await db.execute(count_stmt)).scalar_one() or 0)
        stmt = (
            base.order_by(
                desc(PromptExpanderEntry.created_at), desc(PromptExpanderEntry.id)
            )
            .limit(page_size)
            .offset(offset)
        )
        items = list((await db.execute(stmt)).scalars().all())
        return items, total

    @staticmethod
    async def get_entry(
        db: AsyncSession, *, entry_id: str, user_id: str = DEFAULT_USER_ID
    ) -> PromptExpanderEntry:
        stmt = (
            select(PromptExpanderEntry)
            .join(
                PromptExpanderSession,
                PromptExpanderSession.id == PromptExpanderEntry.session_id,
            )
            .where(
                PromptExpanderEntry.id == entry_id,
                PromptExpanderSession.user_id == user_id,
            )
        )
        entry = (await db.execute(stmt)).scalar_one_or_none()
        if entry is None:
            raise PromptExpanderError("entry_not_found", "エントリが見つかりません")
        return entry

    @staticmethod
    async def delete_entry(
        db: AsyncSession, *, entry_id: str, user_id: str = DEFAULT_USER_ID
    ) -> Path | None:
        """エントリ行を削除し、後で消すべき画像ファイルのパスを返す。"""
        entry = await PromptExpanderService.get_entry(
            db, entry_id=entry_id, user_id=user_id
        )
        path = resolve_entry_image_file(entry)
        await db.delete(entry)
        await db.flush()
        return path

    @staticmethod
    async def add_uploaded_entry(
        db: AsyncSession,
        *,
        session_id: str,
        image_base64: str,
        instruction: str | None = None,
        user_id: str = DEFAULT_USER_ID,
    ) -> PromptExpanderEntry:
        session = await PromptExpanderService.get_session(
            db, session_id=session_id, user_id=user_id
        )
        png = decode_image_base64(image_base64)
        entry_id = str(uuid.uuid4())
        entry = PromptExpanderEntry(
            id=entry_id,
            session_id=session_id,
            kind="uploaded",
            instruction=(instruction or "").strip() or None,
            positive_expand_mode="off",
            negative_expand_mode="off",
            character_mode=False,
            manga_mode=False,
            manga_panel_count=None,
            final_prompt="",
            final_negative_prompt="",
            character_prompts_json="[]",
            source_kind="none",
            image_path=entry_image_relpath(session_id, entry_id),
            created_at=datetime.now(),
        )
        db.add(entry)
        session.updated_at = entry.created_at
        await db.flush()
        _write_png(entry_image_file(session_id, entry_id), png)
        return entry

    @staticmethod
    async def get_settings(
        db: AsyncSession, *, user_id: str = DEFAULT_USER_ID
    ) -> PromptExpanderSettings:
        user = await db.get(User, user_id)
        raw = getattr(user, "prompt_expander_settings_json", None) if user else None
        return _settings_from_json(raw)

    @staticmethod
    async def save_settings(
        db: AsyncSession,
        *,
        patch: dict[str, Any],
        user_id: str = DEFAULT_USER_ID,
    ) -> PromptExpanderSettings:
        user = await _ensure_user(db, user_id)
        current = _settings_from_json(user.prompt_expander_settings_json)
        merged = current.model_dump()
        for key, value in patch.items():
            if key not in PromptExpanderSettings.model_fields:
                continue
            # seed は None で「ランダム」に戻せる。他の項目は None を据え置き扱いにする
            if value is None and key != "seed":
                continue
            merged[key] = value
        try:
            validated = PromptExpanderSettings.model_validate(merged)
        except ValidationError as exc:
            raise PromptExpanderError("invalid_settings", str(exc)) from exc
        user.prompt_expander_settings_json = validated.model_dump_json()
        await db.flush()
        return validated


async def _ensure_user(db: AsyncSession, user_id: str) -> User:
    user = await db.get(User, user_id)
    if user is None:
        user = User(id=user_id, nsfw_mode=0, difficulty="normal", language="ja")
        db.add(user)
        await db.flush()
    return user


# ---------------------------------------------------------------------------
# 参照元（i2i 元 / 現在のプロンプト）
# ---------------------------------------------------------------------------


@dataclass
class SourceResolution:
    image_bytes: Optional[bytes] = None
    current_prompt: Optional[str] = None
    current_character_prompts: list[str] = field(default_factory=list)
    current_negative: Optional[str] = None
    context_description: Optional[str] = None


async def resolve_source(
    db: AsyncSession,
    *,
    source_kind: str,
    source_history_id: str | None = None,
    source_entry_id: str | None = None,
    source_image: str | None = None,
    user_id: str = DEFAULT_USER_ID,
    load_image: bool = True,
) -> SourceResolution:
    if source_kind == "none":
        return SourceResolution()
    if source_kind == "history":
        if not source_history_id:
            raise PromptExpanderError("invalid_source", "履歴IDが指定されていません")
        history = await session_store.get_history_by_id(source_history_id)
        if history is None:
            raise PromptExpanderError("history_not_found", "履歴が見つかりません")
        image_bytes: bytes | None = None
        if load_image:
            path = session_store.resolve_history_image_file(history)
            if path is None:
                raise PromptExpanderError("image_not_found", "履歴画像が見つかりません")
            image_bytes = path.read_bytes()
        return SourceResolution(
            image_bytes=image_bytes,
            context_description=(
                history.after_description or history.before_description or None
            ),
        )
    if source_kind == "entry":
        if not source_entry_id:
            raise PromptExpanderError(
                "invalid_source", "エントリIDが指定されていません"
            )
        entry = await PromptExpanderService.get_entry(
            db, entry_id=source_entry_id, user_id=user_id
        )
        image_bytes = None
        if load_image:
            path = resolve_entry_image_file(entry)
            if path is None:
                raise PromptExpanderError(
                    "image_not_found", "エントリ画像が見つかりません"
                )
            image_bytes = path.read_bytes()
        return SourceResolution(
            image_bytes=image_bytes,
            current_prompt=entry.final_prompt or None,
            current_character_prompts=_load_character_prompts(
                entry.character_prompts_json
            ),
            current_negative=entry.final_negative_prompt or None,
        )
    if source_kind == "upload":
        if not load_image:
            return SourceResolution()
        if not source_image:
            raise PromptExpanderError("invalid_source", "アップロード画像がありません")
        return SourceResolution(image_bytes=decode_image_base64(source_image))
    raise PromptExpanderError("invalid_source", "参照元の種別が不正です")


# ---------------------------------------------------------------------------
# LLM: プロンプト拡張 / キャラクター提案
# ---------------------------------------------------------------------------


@dataclass
class ExpandParams:
    instruction: str = ""
    expand_positive: bool = True
    positive_mode: ExpandMode = "tags"
    character_mode: bool = False
    expand_negative: bool = False
    negative_mode: ExpandMode = "tags"
    negative_instruction: str = ""
    image_model: str = DEFAULT_PROMPT_EXPANDER_IMAGE_MODEL
    text_model: str = DEFAULT_NOVELAI_TEXT_MODEL
    language: str = "ja"
    source_kind: str = "none"
    source_history_id: Optional[str] = None
    source_entry_id: Optional[str] = None
    inherit_source_prompts: bool = True
    current_prompt: Optional[str] = None
    current_character_prompts: Sequence[str] = ()
    current_negative: Optional[str] = None
    # 漫画モード（None なら通常拡張）
    manga: Optional[MangaOptions] = None


@dataclass
class ExpandResult:
    positive_prompt: Optional[str] = None
    character_prompts: Optional[list[str]] = None
    negative_prompt: Optional[str] = None
    text_model: str = DEFAULT_NOVELAI_TEXT_MODEL


def _image_model_nsfw(image_model: str) -> bool:
    return get_image_model_info(image_model, nsfw_mode=True).family == "full"


async def _call_llm(system_prompt: str, user_prompt: str, text_model: str) -> str:
    if not is_novelai_text_model(text_model):
        raise PromptExpanderError("invalid_text_model", "テキストモデルが不正です")
    if not novelai_configured():
        raise PromptExpanderError(
            "novelai_not_configured", "NovelAI API キーが設定されていません"
        )
    try:
        result = await llm_service.generate_text(
            system_prompt,
            user_prompt,
            provider_override="novelai",
            novelai_model_override=text_model,
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (401, 403):
            raise PromptExpanderError(
                "llm_failed",
                "NovelAI テキスト API の認証に失敗しました（Opus 契約と API キーを確認してください）",
            ) from exc
        if status == 429:
            raise PromptExpanderError(
                "llm_failed", "NovelAI テキスト API の利用上限に達しました"
            ) from exc
        raise PromptExpanderError(
            "llm_failed",
            f"NovelAI テキスト API でエラーが発生しました（HTTP {status}）",
        ) from exc
    except PromptExpanderError:
        raise
    except Exception as exc:  # noqa: BLE001 - 呼び出し側へ一律で伝える
        logger.exception("Prompt Expander LLM call failed")
        raise PromptExpanderError(
            "llm_failed", f"テキスト生成に失敗しました: {exc}"
        ) from exc
    content = (result.content or "").strip()
    if not content:
        raise PromptExpanderError(
            "invalid_llm_output", "LLM から空の応答が返されました"
        )
    return content


async def expand_prompts(
    params: ExpandParams, *, user_id: str = DEFAULT_USER_ID
) -> ExpandResult:
    """正プロンプト／ネガティブプロンプトを LLM で拡張する（画像は生成しない）。"""
    if not params.expand_positive and not params.expand_negative:
        raise PromptExpanderError("invalid_request", "拡張対象が指定されていません")
    if not is_prompt_expander_image_model(params.image_model):
        raise PromptExpanderError("unsupported_image_model", "画像モデルが不正です")
    if params.manga is not None and not supports_manga_mode(params.image_model):
        raise PromptExpanderError(
            "manga_requires_v5",
            "漫画モードは NovelAI Diffusion V5 系モデルでのみ使用できます",
        )

    async with async_session_factory() as db:
        pe_settings = await PromptExpanderService.get_settings(db, user_id=user_id)
        source = await resolve_source(
            db,
            source_kind=params.source_kind,
            source_history_id=params.source_history_id,
            source_entry_id=params.source_entry_id,
            user_id=user_id,
            load_image=False,
        )

    memory_text = pe_settings.memory_text if pe_settings.use_memory else ""
    nsfw = _image_model_nsfw(params.image_model)
    max_characters = max_character_prompts(params.image_model)
    inherit = params.inherit_source_prompts

    # 作業欄に入力済みの「現在の」内容を優先し、無ければ参照元から引き継ぐ
    current_prompt = (params.current_prompt or "").strip() or (
        source.current_prompt if inherit else None
    )
    current_characters = [c for c in params.current_character_prompts if c.strip()] or (
        source.current_character_prompts if inherit else []
    )
    current_negative = (params.current_negative or "").strip() or (
        source.current_negative if inherit else None
    )
    context_description = source.context_description if inherit else None

    result = ExpandResult(text_model=params.text_model)

    if params.expand_positive:
        instruction = params.instruction.strip()
        if not instruction:
            raise PromptExpanderError("invalid_request", "指示を入力してください")
        system_prompt = build_positive_system_prompt(
            mode=params.positive_mode,
            character_mode=params.character_mode,
            max_characters=max_characters,
            nsfw=nsfw,
            memory_text=memory_text,
            language=params.language,
            manga=params.manga,
        )
        user_prompt = build_positive_user_prompt(
            instruction=instruction,
            current_prompt=current_prompt,
            current_character_prompts=current_characters,
            character_mode=params.character_mode,
            context_description=context_description,
            manga=params.manga is not None,
        )
        raw = await _call_llm(system_prompt, user_prompt, params.text_model)
        try:
            if params.manga is not None:
                base, characters = parse_manga_json(
                    raw,
                    max_characters=max_characters,
                    character_mode=params.character_mode,
                )
                result.positive_prompt = base
                result.character_prompts = characters
            elif params.character_mode:
                base, characters = parse_character_json(
                    raw, max_characters=max_characters, mode=params.positive_mode
                )
                result.positive_prompt = base
                result.character_prompts = characters
            else:
                sanitized = sanitize_by_mode(
                    raw, params.positive_mode, ensure_quality=True
                )
                if not sanitized:
                    raise PromptExpanderOutputError("空のプロンプトが返されました")
                result.positive_prompt = sanitized
                result.character_prompts = None
        except PromptExpanderOutputError as exc:
            raise PromptExpanderError("invalid_llm_output", str(exc)) from exc

    if params.expand_negative:
        negative_instruction = params.negative_instruction.strip()
        if not negative_instruction:
            raise PromptExpanderError(
                "invalid_request", "ネガティブプロンプトの指示を入力してください"
            )
        system_prompt = build_negative_system_prompt(
            mode=params.negative_mode,
            memory_text=memory_text,
            language=params.language,
        )
        user_prompt = build_negative_user_prompt(
            instruction=negative_instruction, current_negative=current_negative
        )
        raw = await _call_llm(system_prompt, user_prompt, params.text_model)
        sanitized = sanitize_by_mode(raw, params.negative_mode, ensure_quality=False)
        if not sanitized:
            raise PromptExpanderError(
                "invalid_llm_output", "空のネガティブプロンプトが返されました"
            )
        result.negative_prompt = sanitized

    return result


@dataclass
class SuggestResult:
    suggestions: list[dict[str, str]]
    text_model: str


async def suggest_character_prompts(
    *,
    text_model: str,
    image_model: str,
    mode: ExpandMode,
    count: int,
    language: str = "ja",
    user_id: str = DEFAULT_USER_ID,
) -> SuggestResult:
    """PE メモリ（無ければグローバルメモリ）から好みのキャラクタープロンプトを提案する。"""
    async with async_session_factory() as db:
        pe_settings = await PromptExpanderService.get_settings(db, user_id=user_id)
    memory_text = (pe_settings.memory_text or "").strip()
    if not memory_text:
        memory_text = (await settings_service.get_memory_text(user_id) or "").strip()
    if not memory_text:
        raise PromptExpanderError(
            "memory_empty",
            "メモリ情報がありません。設定でメモリを入力するか「メモリ情報を持ってくる」を実行してください",
        )
    system_prompt, user_prompt = build_suggest_characters_prompts(
        memory_text=memory_text,
        count=count,
        mode=mode,
        nsfw=_image_model_nsfw(image_model),
        language=language,
    )
    raw = await _call_llm(system_prompt, user_prompt, text_model)
    try:
        suggestions = parse_suggestions_json(raw, count=count, mode=mode)
    except PromptExpanderOutputError as exc:
        raise PromptExpanderError("invalid_llm_output", str(exc)) from exc
    return SuggestResult(suggestions=suggestions, text_model=text_model)


# ---------------------------------------------------------------------------
# 画像生成
# ---------------------------------------------------------------------------


@dataclass
class GenerateParams:
    prompt: str
    negative_prompt: str = ""
    character_prompts: Sequence[str] = ()
    character_mode: bool = False
    instruction: str = ""
    positive_expand_mode: str = "off"
    negative_expand_mode: str = "off"
    image_model: str = DEFAULT_PROMPT_EXPANDER_IMAGE_MODEL
    text_model: Optional[str] = None
    image_size: str = DEFAULT_PROMPT_EXPANDER_IMAGE_SIZE
    seed: Optional[int] = None
    i2i_strength: Optional[float] = None
    i2i_noise: Optional[float] = None
    source_kind: str = "none"
    source_history_id: Optional[str] = None
    source_entry_id: Optional[str] = None
    source_image: Optional[str] = None
    # 漫画モードで拡張したプロンプトかどうか（エントリのバッジ・復元用。生成には影響しない）
    manga_mode: bool = False
    manga_panel_count: Optional[int] = None


@dataclass
class GenerateOutcome:
    entry: dict[str, Any]
    result: ImageGenerationResult


async def generate_entry(
    session_id: str,
    params: GenerateParams,
    *,
    user_id: str = DEFAULT_USER_ID,
) -> GenerateOutcome:
    """NovelAI で画像を生成し、エントリとして保存する。"""
    if not is_prompt_expander_image_model(params.image_model):
        raise PromptExpanderError("unsupported_image_model", "画像モデルが不正です")
    if params.image_size not in PROMPT_EXPANDER_IMAGE_SIZES:
        raise PromptExpanderError("invalid_request", "画像サイズが不正です")
    prompt = " ".join(params.prompt.split()).strip()
    if not prompt:
        raise PromptExpanderError("invalid_request", "プロンプトを入力してください")
    if not novelai_configured():
        raise PromptExpanderError(
            "novelai_not_configured", "NovelAI API キーが設定されていません"
        )

    character_prompts = [
        " ".join(item.split()).strip() for item in params.character_prompts
    ]
    character_prompts = [item for item in character_prompts if item]
    limit = max_character_prompts(params.image_model)
    if len(character_prompts) > limit:
        raise PromptExpanderError(
            "too_many_characters",
            f"このモデルで指定できるキャラクタープロンプトは最大{limit}件です",
        )

    async with async_session_factory() as db:
        await PromptExpanderService.get_session(
            db, session_id=session_id, user_id=user_id
        )
        source = await resolve_source(
            db,
            source_kind=params.source_kind,
            source_history_id=params.source_history_id,
            source_entry_id=params.source_entry_id,
            source_image=params.source_image,
            user_id=user_id,
            load_image=True,
        )

    characters_payload: list[dict[str, Any]] | None = None
    if character_prompts:
        characters_payload = [
            {
                "prompt": item,
                "negative_prompt": "",
                "position": (0.5, 0.5),
                "enabled": True,
            }
            for item in character_prompts
        ]

    nsfw = _image_model_nsfw(params.image_model)
    negative = " ".join(params.negative_prompt.split()).strip()
    try:
        result = await image_service.generate_image(
            prompt,
            image_bytes=source.image_bytes,
            provider_override="novelai",
            negative_prompt=negative,
            i2i_strength_override=params.i2i_strength,
            i2i_noise_override=params.i2i_noise,
            nsfw_mode=nsfw,
            seed=params.seed,
            characters=characters_payload,
            size_override=params.image_size,
            novelai_model_override=params.image_model,
            raw_prompt=True,
        )
    except PromptExpanderError:
        raise
    except Exception as exc:  # noqa: BLE001 - 画像生成の失敗は一律でエラー応答にする
        logger.exception("Prompt Expander image generation failed")
        raise PromptExpanderError(
            "image_failed", f"画像生成に失敗しました: {exc}"
        ) from exc
    if not result.images:
        raise PromptExpanderError("image_failed", "画像が返されませんでした")

    # 漫画モードは V5 系モデル専用なので、それ以外では印を残さない
    manga_mode = bool(params.manga_mode) and supports_manga_mode(params.image_model)
    entry_id = str(uuid.uuid4())
    async with async_session_factory() as db:
        session = await PromptExpanderService.get_session(
            db, session_id=session_id, user_id=user_id
        )
        entry = PromptExpanderEntry(
            id=entry_id,
            session_id=session_id,
            kind="generated",
            instruction=(params.instruction or "").strip() or prompt,
            positive_expand_mode=params.positive_expand_mode or "off",
            negative_expand_mode=params.negative_expand_mode or "off",
            character_mode=bool(params.character_mode or character_prompts),
            final_prompt=prompt,
            final_negative_prompt=negative,
            character_prompts_json=json.dumps(character_prompts, ensure_ascii=False),
            image_model=params.image_model,
            text_model=params.text_model,
            seed=result.seed if result.seed is not None else params.seed,
            i2i_strength=(
                params.i2i_strength if source.image_bytes is not None else None
            ),
            i2i_noise=params.i2i_noise if source.image_bytes is not None else None,
            image_size=params.image_size,
            manga_mode=manga_mode,
            manga_panel_count=(
                normalize_manga_panel_count(params.manga_panel_count) or None
                if manga_mode
                else None
            ),
            source_kind=params.source_kind
            if source.image_bytes is not None
            else "none",
            source_history_id=(
                params.source_history_id if params.source_kind == "history" else None
            ),
            source_entry_id=(
                params.source_entry_id if params.source_kind == "entry" else None
            ),
            image_path=entry_image_relpath(session_id, entry_id),
            created_at=datetime.now(),
        )
        db.add(entry)
        session.updated_at = entry.created_at
        await db.flush()
        _write_png(entry_image_file(session_id, entry_id), result.images[0])
        await db.commit()
        view = entry_to_dict(entry)
    return GenerateOutcome(entry=view, result=result)


async def fetch_anlas_safely() -> AnlasBalance | None:
    """Anlas 残高を取得する。失敗しても生成結果の応答は返したいので None に倒す。"""
    if not novelai_configured():
        return None
    try:
        return await get_anlas_balance()
    except Exception:  # noqa: BLE001
        logger.warning("Failed to fetch Anlas balance after prompt expander generation")
        return None
