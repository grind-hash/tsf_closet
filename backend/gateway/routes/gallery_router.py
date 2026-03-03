"""
Gallery API endpoints
007-chat-interactive-ux
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, delete, desc, func, or_, select

from ..services.characters import CharacterManager
from ..settings.config import settings
from ..databases.base import async_session_factory
from ..databases.models import History as HistoryORM
from ..databases.models import Session as SessionORM

router = APIRouter(prefix="/gallery", tags=["gallery"])


def _load_custom_session_name(session_id: str) -> str | None:
    metadata_path = (
        settings.history_images_dir / "custom" / f"session_{session_id}.json"
    )
    if not metadata_path.exists():
        return None
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        name = data.get("name")
        return name if isinstance(name, str) and name else None
    except Exception:
        return None


def _to_iso(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return datetime.now().isoformat()


class GalleryItem(BaseModel):
    """ギャラリーアイテム"""

    id: str
    session_id: str
    image_url: str
    instruction: str
    feeling_text: str | None
    before_description: str | None
    after_description: str | None
    timestamp: str
    costume_category: str | None
    exposure_level: str | None


class GallerySession(BaseModel):
    """セッション単位のギャラリー情報"""

    session_id: str
    character_name: str | None
    thumbnail_url: str
    item_count: int
    first_timestamp: str
    last_timestamp: str


class GallerySessionsResponse(BaseModel):
    """セッション一覧レスポンス"""

    sessions: list[GallerySession]
    total: int
    page: int
    page_size: int
    has_more: bool


class GalleryListResponse(BaseModel):
    """ギャラリー一覧レスポンス"""

    items: list[GalleryItem]
    total: int
    page: int
    page_size: int
    has_more: bool


class GalleryDetailResponse(BaseModel):
    """ギャラリー詳細レスポンス"""

    item: GalleryItem
    prev_id: str | None
    next_id: str | None


@router.get("/sessions", response_model=GallerySessionsResponse)
async def get_gallery_sessions(
    page: int = Query(1, ge=1, description="ページ番号"),
    page_size: int = Query(20, ge=1, le=100, description="1ページあたりのセッション数"),
):
    """ギャラリーのセッション一覧を取得"""
    offset = (page - 1) * page_size

    async with async_session_factory() as db_session:
        total_stmt = select(func.count(func.distinct(HistoryORM.session_id)))
        total = (await db_session.execute(total_stmt)).scalar() or 0

        summary_subquery = (
            select(
                HistoryORM.session_id.label("session_id"),
                func.count(HistoryORM.id).label("item_count"),
                func.min(HistoryORM.created_at).label("first_timestamp"),
                func.max(HistoryORM.created_at).label("last_timestamp"),
            )
            .group_by(HistoryORM.session_id)
            .subquery()
        )

        latest_created_subquery = (
            select(
                HistoryORM.session_id.label("session_id"),
                func.max(HistoryORM.created_at).label("max_created_at"),
            )
            .group_by(HistoryORM.session_id)
            .subquery()
        )

        latest_id_subquery = (
            select(
                HistoryORM.session_id.label("session_id"),
                func.max(HistoryORM.id).label("latest_id"),
            )
            .join(
                latest_created_subquery,
                and_(
                    HistoryORM.session_id == latest_created_subquery.c.session_id,
                    HistoryORM.created_at == latest_created_subquery.c.max_created_at,
                ),
            )
            .group_by(HistoryORM.session_id)
            .subquery()
        )

        stmt = (
            select(
                summary_subquery.c.session_id,
                latest_id_subquery.c.latest_id,
                summary_subquery.c.item_count,
                summary_subquery.c.first_timestamp,
                summary_subquery.c.last_timestamp,
                SessionORM.character_id,
            )
            .outerjoin(
                latest_id_subquery,
                summary_subquery.c.session_id == latest_id_subquery.c.session_id,
            )
            .outerjoin(SessionORM, SessionORM.id == summary_subquery.c.session_id)
            .order_by(desc(summary_subquery.c.last_timestamp))
            .limit(page_size)
            .offset(offset)
        )
        rows = (await db_session.execute(stmt)).all()

    char_manager = CharacterManager()
    sessions = []
    for row in rows:
        session_id = str(row.session_id)
        latest_id = str(row.latest_id) if row.latest_id else None

        character_name = None
        if row.character_id:
            char = char_manager.get_by_id(row.character_id)
            character_name = char.name if char else row.character_id
        else:
            character_name = _load_custom_session_name(session_id)

        thumbnail_url = f"/history/images/{latest_id}" if latest_id else ""

        sessions.append(
            GallerySession(
                session_id=session_id,
                character_name=character_name,
                thumbnail_url=thumbnail_url,
                item_count=int(row.item_count),
                first_timestamp=_to_iso(row.first_timestamp),
                last_timestamp=_to_iso(row.last_timestamp),
            )
        )

    has_more = (offset + len(sessions)) < total

    return GallerySessionsResponse(
        sessions=sessions,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


@router.get("", response_model=GalleryListResponse)
async def get_gallery(
    page: int = Query(1, ge=1, description="ページ番号"),
    page_size: int = Query(20, ge=1, le=100, description="1ページあたりのアイテム数"),
    session_id: str | None = Query(None, description="セッションIDでフィルタ"),
):
    """ギャラリー一覧を取得"""
    offset = (page - 1) * page_size

    async with async_session_factory() as db_session:
        count_stmt = select(func.count()).select_from(HistoryORM)
        if session_id:
            count_stmt = count_stmt.where(HistoryORM.session_id == session_id)
        total = (await db_session.execute(count_stmt)).scalar_one() or 0

        stmt = select(HistoryORM)
        if session_id:
            stmt = stmt.where(HistoryORM.session_id == session_id)
        stmt = (
            stmt.order_by(HistoryORM.created_at.desc(), HistoryORM.id.desc())
            .limit(page_size)
            .offset(offset)
        )
        rows = (await db_session.execute(stmt)).scalars().all()

    items = [
        GalleryItem(
            id=row.id,
            session_id=row.session_id,
            image_url=f"/history/images/{row.id}",
            instruction=row.instruction or "",
            feeling_text=row.feeling_text,
            before_description=row.before_description,
            after_description=row.after_description,
            timestamp=_to_iso(row.created_at),
            costume_category=None,
            exposure_level=None,
        )
        for row in rows
    ]

    has_more = (offset + len(items)) < total

    return GalleryListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


@router.get("/{item_id}", response_model=GalleryDetailResponse)
async def get_gallery_item(item_id: str):
    """ギャラリーアイテムの詳細を取得"""
    async with async_session_factory() as db_session:
        row = (
            (
                await db_session.execute(
                    select(HistoryORM).where(HistoryORM.id == item_id).limit(1)
                )
            )
            .scalars()
            .first()
        )

        if not row:
            raise HTTPException(status_code=404, detail="Item not found")

        item = GalleryItem(
            id=row.id,
            session_id=row.session_id,
            image_url=f"/history/images/{row.id}",
            instruction=row.instruction or "",
            feeling_text=row.feeling_text,
            before_description=row.before_description,
            after_description=row.after_description,
            timestamp=_to_iso(row.created_at),
            costume_category=None,
            exposure_level=None,
        )

        prev_stmt = (
            select(HistoryORM.id)
            .where(
                or_(
                    HistoryORM.created_at < row.created_at,
                    and_(
                        HistoryORM.created_at == row.created_at, HistoryORM.id < item_id
                    ),
                )
            )
            .order_by(HistoryORM.created_at.desc(), HistoryORM.id.desc())
            .limit(1)
        )
        prev_id = (await db_session.execute(prev_stmt)).scalar()

        next_stmt = (
            select(HistoryORM.id)
            .where(
                or_(
                    HistoryORM.created_at > row.created_at,
                    and_(
                        HistoryORM.created_at == row.created_at, HistoryORM.id > item_id
                    ),
                )
            )
            .order_by(HistoryORM.created_at.asc(), HistoryORM.id.asc())
            .limit(1)
        )
        next_id = (await db_session.execute(next_stmt)).scalar()

    return GalleryDetailResponse(
        item=item,
        prev_id=str(prev_id) if prev_id else None,
        next_id=str(next_id) if next_id else None,
    )


class DeleteResponse(BaseModel):
    """削除結果レスポンス"""

    success: bool
    deleted_count: int
    message: str


@router.delete("/sessions/{session_id}", response_model=DeleteResponse)
async def delete_gallery_session(session_id: str):
    """セッションとその全履歴アイテムを削除"""
    async with async_session_factory() as db_session:
        try:
            rows = (
                await db_session.execute(
                    select(HistoryORM.id, HistoryORM.image_path).where(
                        HistoryORM.session_id == session_id
                    )
                )
            ).all()

            if not rows:
                raise HTTPException(
                    status_code=404,
                    detail=f"Session {session_id} not found or has no history",
                )

            deleted_count = len(rows)

            for row in rows:
                image_path_value = row.image_path
                if image_path_value:
                    image_path = Path(image_path_value)
                    if image_path.exists():
                        try:
                            os.remove(image_path)
                        except OSError:
                            pass

            await db_session.execute(
                delete(HistoryORM).where(HistoryORM.session_id == session_id)
            )
            await db_session.execute(
                delete(SessionORM).where(SessionORM.id == session_id)
            )
            await db_session.commit()

            return DeleteResponse(
                success=True,
                deleted_count=deleted_count,
                message=f"Session {session_id} and {deleted_count} history items deleted",
            )
        except HTTPException:
            raise
        except Exception as exc:
            await db_session.rollback()
            raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/{item_id}", response_model=DeleteResponse)
async def delete_gallery_item(item_id: str):
    """単一のギャラリーアイテムを削除"""
    async with async_session_factory() as db_session:
        try:
            row = (
                await db_session.execute(
                    select(
                        HistoryORM.id,
                        HistoryORM.image_path,
                        HistoryORM.surroundings_image_path,
                    )
                    .where(HistoryORM.id == item_id)
                    .limit(1)
                )
            ).first()

            if not row:
                raise HTTPException(status_code=404, detail=f"Item {item_id} not found")

            # メイン画像を削除
            if row.image_path:
                image_path = Path(row.image_path)
                if image_path.exists():
                    try:
                        os.remove(image_path)
                    except OSError:
                        pass

            # 周囲状況画像を削除
            if row.surroundings_image_path:
                surroundings_path = (
                    settings.history_images_dir.parent / row.surroundings_image_path
                )
                if surroundings_path.exists():
                    try:
                        os.remove(surroundings_path)
                    except OSError:
                        pass

            await db_session.execute(delete(HistoryORM).where(HistoryORM.id == item_id))
            await db_session.commit()

            return DeleteResponse(
                success=True,
                deleted_count=1,
                message=f"Item {item_id} deleted",
            )
        except HTTPException:
            raise
        except Exception as exc:
            await db_session.rollback()
            raise HTTPException(status_code=500, detail=str(exc))
