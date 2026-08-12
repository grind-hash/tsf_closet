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
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import and_, delete, desc, func, or_, select
from urllib.parse import quote

from ..services.characters import CharacterManager
from ..settings.config import settings
from ..databases.base import async_session_factory
from ..databases.models import Conversation as ConversationORM
from ..databases.models import History as HistoryORM
from ..databases.models import Session as SessionORM
from ..databases.models import PlaySummary as PlaySummaryORM

router = APIRouter(prefix="/gallery", tags=["gallery"])


def _escape_like(value: str) -> str:
    """LIKE パターン用に % / _ / \\ をエスケープする"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _make_snippet(text: str, query: str, max_len: int = 80) -> str:
    """検索語周辺を切り出したスニペットを返す"""
    if not text:
        return ""

    idx = text.lower().find(query.lower())
    if idx < 0:
        idx = text.find(query)
    if idx < 0:
        snippet = text[:max_len]
        return snippet + ("…" if len(text) > max_len else "")

    start = max(0, idx - 20)
    end = min(len(text), idx + len(query) + 40)
    snippet = text[start:end]
    if start > 0:
        snippet = f"…{snippet}"
    if end < len(text):
        snippet = f"{snippet}…"
    return snippet


def _matching_session_ids_select(pattern: str):
    """指示・会話・要約のいずれかに一致する session_id を返す SELECT"""
    history_match = select(HistoryORM.session_id.label("session_id")).where(
        or_(
            HistoryORM.instruction.like(pattern, escape="\\"),
            HistoryORM.feeling_text.like(pattern, escape="\\"),
            HistoryORM.before_description.like(pattern, escape="\\"),
            HistoryORM.after_description.like(pattern, escape="\\"),
        )
    )
    conversation_match = select(ConversationORM.session_id.label("session_id")).where(
        ConversationORM.content.like(pattern, escape="\\")
    )
    summary_match = select(PlaySummaryORM.session_id.label("session_id")).where(
        or_(
            PlaySummaryORM.title.like(pattern, escape="\\"),
            PlaySummaryORM.summary.like(pattern, escape="\\"),
        )
    )
    return history_match.union(conversation_match, summary_match)


async def _fetch_match_snippets(
    db_session,
    session_ids: list[str],
    query: str,
) -> dict[str, str]:
    """セッションごとの代表的なマッチ箇所を取得する（会話を優先）"""
    if not session_ids or not query:
        return {}

    pattern = f"%{_escape_like(query)}%"
    snippets: dict[str, str] = {}

    conv_rows = (
        await db_session.execute(
            select(ConversationORM.session_id, ConversationORM.content)
            .where(
                ConversationORM.session_id.in_(session_ids),
                ConversationORM.content.like(pattern, escape="\\"),
            )
            .order_by(desc(ConversationORM.created_at))
        )
    ).all()
    for session_id, content in conv_rows:
        sid = str(session_id)
        if sid not in snippets and content:
            snippets[sid] = _make_snippet(content, query)

    remaining = [sid for sid in session_ids if sid not in snippets]
    if remaining:
        history_rows = (
            await db_session.execute(
                select(
                    HistoryORM.session_id,
                    HistoryORM.instruction,
                    HistoryORM.feeling_text,
                    HistoryORM.before_description,
                    HistoryORM.after_description,
                )
                .where(
                    HistoryORM.session_id.in_(remaining),
                    or_(
                        HistoryORM.instruction.like(pattern, escape="\\"),
                        HistoryORM.feeling_text.like(pattern, escape="\\"),
                        HistoryORM.before_description.like(pattern, escape="\\"),
                        HistoryORM.after_description.like(pattern, escape="\\"),
                    ),
                )
                .order_by(desc(HistoryORM.created_at))
            )
        ).all()
        for row in history_rows:
            sid = str(row.session_id)
            if sid in snippets:
                continue
            for field in (
                row.instruction,
                row.feeling_text,
                row.before_description,
                row.after_description,
            ):
                if field and (query.lower() in field.lower() or query in field):
                    snippets[sid] = _make_snippet(field, query)
                    break

    remaining = [sid for sid in session_ids if sid not in snippets]
    if remaining:
        summary_rows = (
            await db_session.execute(
                select(
                    PlaySummaryORM.session_id,
                    PlaySummaryORM.title,
                    PlaySummaryORM.summary,
                ).where(
                    PlaySummaryORM.session_id.in_(remaining),
                    or_(
                        PlaySummaryORM.title.like(pattern, escape="\\"),
                        PlaySummaryORM.summary.like(pattern, escape="\\"),
                    ),
                )
            )
        ).all()
        for row in summary_rows:
            sid = str(row.session_id)
            if sid in snippets:
                continue
            for field in (row.title, row.summary):
                if field and (query.lower() in field.lower() or query in field):
                    snippets[sid] = _make_snippet(field, query)
                    break

    return snippets


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
    is_favorited: bool = False


class GallerySession(BaseModel):
    """セッション単位のギャラリー情報"""

    session_id: str
    character_name: str | None
    thumbnail_url: str
    item_count: int
    first_timestamp: str
    last_timestamp: str
    self_mode: bool = False
    has_summary: bool = False
    match_snippet: str | None = None
    last_instruction: str | None = None


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
    q: str | None = Query(
        None,
        description="フリーワード検索（会話・指示・感想・説明・要約タイトルなど）",
        max_length=200,
    ),
):
    """ギャラリーのセッション一覧を取得（q 指定時はやり取りを横断検索）"""
    offset = (page - 1) * page_size
    query = (q or "").strip()
    match_select = (
        _matching_session_ids_select(f"%{_escape_like(query)}%") if query else None
    )

    async with async_session_factory() as db_session:
        total_stmt = select(func.count(func.distinct(HistoryORM.session_id)))
        if match_select is not None:
            total_stmt = total_stmt.where(HistoryORM.session_id.in_(match_select))
        total = (await db_session.execute(total_stmt)).scalar() or 0

        summary_base = select(
            HistoryORM.session_id.label("session_id"),
            func.count(HistoryORM.id).label("item_count"),
            func.min(HistoryORM.created_at).label("first_timestamp"),
            func.max(HistoryORM.created_at).label("last_timestamp"),
        )
        if match_select is not None:
            summary_base = summary_base.where(HistoryORM.session_id.in_(match_select))
        summary_subquery = summary_base.group_by(HistoryORM.session_id).subquery()

        latest_created_base = select(
            HistoryORM.session_id.label("session_id"),
            func.max(HistoryORM.created_at).label("max_created_at"),
        )
        if match_select is not None:
            latest_created_base = latest_created_base.where(
                HistoryORM.session_id.in_(match_select)
            )
        latest_created_subquery = latest_created_base.group_by(
            HistoryORM.session_id
        ).subquery()

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
                HistoryORM.instruction.label("last_instruction"),
                SessionORM.character_id,
                SessionORM.self_mode,
                PlaySummaryORM.session_id.isnot(None).label("has_summary"),
            )
            .outerjoin(
                latest_id_subquery,
                summary_subquery.c.session_id == latest_id_subquery.c.session_id,
            )
            .outerjoin(
                HistoryORM,
                HistoryORM.id == latest_id_subquery.c.latest_id,
            )
            .outerjoin(SessionORM, SessionORM.id == summary_subquery.c.session_id)
            .outerjoin(
                PlaySummaryORM,
                PlaySummaryORM.session_id == summary_subquery.c.session_id,
            )
            .order_by(desc(summary_subquery.c.last_timestamp))
            .limit(page_size)
            .offset(offset)
        )
        rows = (await db_session.execute(stmt)).all()

        snippets: dict[str, str] = {}
        if query and rows:
            session_ids = [str(row.session_id) for row in rows]
            snippets = await _fetch_match_snippets(db_session, session_ids, query)

    char_manager = CharacterManager()

    # self_mode セッション用: self_profile から display_name を取得
    self_display_name: str | None = None
    from ..services.settings_service import settings_service

    try:
        self_profile = await settings_service.get_self_profile()
        if self_profile:
            self_display_name = self_profile.get("display_name")
    except Exception:
        pass

    sessions = []
    for row in rows:
        session_id = str(row.session_id)
        latest_id = str(row.latest_id) if row.latest_id else None
        is_self_mode = bool(row.self_mode) if row.self_mode is not None else False
        last_instruction = (
            str(row.last_instruction).strip() if row.last_instruction else None
        )
        if last_instruction == "":
            last_instruction = None

        character_name = None
        if is_self_mode and self_display_name:
            character_name = self_display_name
        elif row.character_id:
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
                self_mode=is_self_mode,
                has_summary=bool(row.has_summary),
                match_snippet=snippets.get(session_id),
                last_instruction=last_instruction,
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
        history_ids = [row.id for row in rows]
        from ..services.favorite_service import FavoriteOutfitService
        from ..services.session import DEFAULT_USER_ID

        favorited_ids = await FavoriteOutfitService.favorited_history_ids(
            db_session,
            history_ids=history_ids,
            user_id=DEFAULT_USER_ID,
        )

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
            is_favorited=row.id in favorited_ids,
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

        from ..services.favorite_service import FavoriteOutfitService
        from ..services.session import DEFAULT_USER_ID

        is_favorited = await FavoriteOutfitService.is_favorited(
            db_session,
            history_id=row.id,
            user_id=DEFAULT_USER_ID,
        )

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
            is_favorited=is_favorited,
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


# ------------------------------------------------------------------
# Play Summary endpoints
# ------------------------------------------------------------------


@router.get(
    "/sessions/{session_id}/summary",
    summary="プレイ要約を取得",
    description="既存のプレイ要約を取得する。未生成の場合は404",
)
async def get_session_summary(session_id: str) -> dict:
    """Get existing play summary for a session."""
    from ..services.summary_service import summary_service

    result = await summary_service.get_summary(session_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_SUMMARY", "message": "Summary not found"},
        )
    return result


@router.post(
    "/sessions/{session_id}/summary",
    summary="プレイ要約を生成",
    description="LLMを使用してプレイ要約とタイトルを生成する",
)
async def generate_session_summary(
    session_id: str,
    language: str = Query("ja", description="Output language (ja/en)"),
) -> dict:
    """Generate play summary for a session using LLM."""
    from ..services.summary_service import summary_service

    # Verify session exists
    async with async_session_factory() as db_session:
        stmt = select(SessionORM).where(SessionORM.id == session_id)
        session = (await db_session.execute(stmt)).scalars().first()
        if session is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "SESSION_NOT_FOUND",
                    "message": "Session not found",
                },
            )

    try:
        return await summary_service.generate_summary(session_id, language)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Summary generation failed: {e}",
        )


# ------------------------------------------------------------------
# Export endpoints (chat history with images)
# ------------------------------------------------------------------


def _content_disposition(filename: str) -> str:
    """Build a Content-Disposition header with UTF-8 fallback support."""
    quoted = quote(filename, safe="")
    return f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quoted}"


@router.get(
    "/sessions/{session_id}/export/markdown",
    summary="チャット履歴をMarkdownでエクスポート",
    description="セッションのチャット履歴を画像base64埋め込みのMarkdownでダウンロード",
)
async def export_session_markdown(session_id: str) -> Response:
    """Export chat history as Markdown (.md) with embedded JPEG images."""
    from ..services.export_service import build_markdown_export

    try:
        content, filename = await build_markdown_export(session_id)
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail={"error": "SESSION_NOT_FOUND", "message": "Session not found"},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Markdown export failed: {exc}")

    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.get(
    "/sessions/{session_id}/export/novel-html",
    summary="チャット履歴を小説形式HTMLのzipでエクスポート",
    description="HTML + CSS + 画像 を含むzipアーカイブとしてダウンロード",
)
async def export_session_novel_html(session_id: str) -> Response:
    """Export chat history as a novel-style HTML zip archive."""
    from ..services.export_service import build_novel_html_zip

    try:
        content, filename = await build_novel_html_zip(session_id)
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail={"error": "SESSION_NOT_FOUND", "message": "Session not found"},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Novel HTML export failed: {exc}")

    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition(filename)},
    )
