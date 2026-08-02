"""お気に入り衣装スナップショットの永続化サービス。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..databases.models import FavoriteOutfit, History, TransformationTag
from .session import DEFAULT_USER_ID

LABEL_MAX_LENGTH = 80


class FavoriteServiceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class FavoriteOutfitView:
    id: str
    history_id: str
    session_id: str
    label: Optional[str]
    image_url: str
    instruction: str
    costume_category: Optional[str]
    history_created_at: Optional[datetime]
    created_at: datetime


def _normalize_label(label: Optional[str]) -> Optional[str]:
    if label is None:
        return None
    text = label.strip()
    if not text:
        return None
    if len(text) > LABEL_MAX_LENGTH:
        raise FavoriteServiceError(
            "label_too_long",
            f"ラベルは{LABEL_MAX_LENGTH}文字以内にしてください",
        )
    return text


def _to_view(
    fav: FavoriteOutfit,
    history: History,
    costume_category: Optional[str] = None,
) -> FavoriteOutfitView:
    return FavoriteOutfitView(
        id=fav.id,
        history_id=fav.history_id,
        session_id=fav.session_id,
        label=fav.label,
        image_url=f"/history/images/{history.id}",
        instruction=history.instruction or "",
        costume_category=costume_category,
        history_created_at=history.created_at,
        created_at=fav.created_at,
    )


class FavoriteOutfitService:
    @staticmethod
    async def list_for_user(
        db: AsyncSession,
        *,
        user_id: str = DEFAULT_USER_ID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[FavoriteOutfitView], int]:
        offset = (page - 1) * page_size

        count_stmt = (
            select(func.count())
            .select_from(FavoriteOutfit)
            .where(FavoriteOutfit.user_id == user_id)
        )
        total = int((await db.execute(count_stmt)).scalar_one() or 0)

        stmt = (
            select(FavoriteOutfit, History, TransformationTag.costume_category)
            .join(History, History.id == FavoriteOutfit.history_id)
            .outerjoin(TransformationTag, TransformationTag.history_id == History.id)
            .where(FavoriteOutfit.user_id == user_id)
            .order_by(desc(FavoriteOutfit.created_at), desc(FavoriteOutfit.id))
            .limit(page_size)
            .offset(offset)
        )
        rows = (await db.execute(stmt)).all()
        items = [
            _to_view(fav, history, costume_category)
            for fav, history, costume_category in rows
        ]
        return items, total

    @staticmethod
    async def add(
        db: AsyncSession,
        *,
        history_id: str,
        label: Optional[str] = None,
        user_id: str = DEFAULT_USER_ID,
    ) -> FavoriteOutfitView:
        history = await db.get(History, history_id)
        if history is None:
            raise FavoriteServiceError("history_not_found", "履歴が見つかりません")

        existing_stmt = select(FavoriteOutfit).where(
            FavoriteOutfit.user_id == user_id,
            FavoriteOutfit.history_id == history_id,
        )
        existing = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            raise FavoriteServiceError(
                "already_favorited",
                "すでにお気に入りに登録されています",
            )

        fav = FavoriteOutfit(
            id=str(uuid.uuid4()),
            user_id=user_id,
            history_id=history_id,
            session_id=history.session_id,
            label=_normalize_label(label),
        )
        db.add(fav)
        await db.flush()

        tag = await db.get(TransformationTag, history_id)
        category = tag.costume_category if tag else None
        return _to_view(fav, history, category)

    @staticmethod
    async def update_label(
        db: AsyncSession,
        *,
        favorite_id: str,
        label: Optional[str],
        user_id: str = DEFAULT_USER_ID,
    ) -> FavoriteOutfitView:
        stmt = select(FavoriteOutfit).where(
            FavoriteOutfit.id == favorite_id,
            FavoriteOutfit.user_id == user_id,
        )
        fav = (await db.execute(stmt)).scalar_one_or_none()
        if fav is None:
            raise FavoriteServiceError(
                "favorite_not_found", "お気に入りが見つかりません"
            )

        history = await db.get(History, fav.history_id)
        if history is None:
            raise FavoriteServiceError("history_not_found", "履歴が見つかりません")

        fav.label = _normalize_label(label)
        await db.flush()

        tag = await db.get(TransformationTag, history.id)
        category = tag.costume_category if tag else None
        return _to_view(fav, history, category)

    @staticmethod
    async def delete(
        db: AsyncSession,
        *,
        favorite_id: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> bool:
        stmt = select(FavoriteOutfit).where(
            FavoriteOutfit.id == favorite_id,
            FavoriteOutfit.user_id == user_id,
        )
        fav = (await db.execute(stmt)).scalar_one_or_none()
        if fav is None:
            return False
        await db.delete(fav)
        await db.flush()
        return True

    @staticmethod
    async def delete_by_history(
        db: AsyncSession,
        *,
        history_id: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> bool:
        stmt = select(FavoriteOutfit).where(
            FavoriteOutfit.user_id == user_id,
            FavoriteOutfit.history_id == history_id,
        )
        fav = (await db.execute(stmt)).scalar_one_or_none()
        if fav is None:
            return False
        await db.delete(fav)
        await db.flush()
        return True

    @staticmethod
    async def favorited_history_ids(
        db: AsyncSession,
        *,
        history_ids: list[str],
        user_id: str = DEFAULT_USER_ID,
    ) -> set[str]:
        if not history_ids:
            return set()
        stmt = select(FavoriteOutfit.history_id).where(
            FavoriteOutfit.user_id == user_id,
            FavoriteOutfit.history_id.in_(history_ids),
        )
        rows = (await db.execute(stmt)).scalars().all()
        return {str(hid) for hid in rows}

    @staticmethod
    async def is_favorited(
        db: AsyncSession,
        *,
        history_id: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> bool:
        stmt = select(FavoriteOutfit.id).where(
            FavoriteOutfit.user_id == user_id,
            FavoriteOutfit.history_id == history_id,
        )
        return (await db.execute(stmt)).scalar_one_or_none() is not None
