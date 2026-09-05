"""Unit tests for FavoriteOutfitService (spec 009)."""

from __future__ import annotations

import pytest

from gateway.databases.models import History, User
from gateway.databases.models import Session as SessionORM
from gateway.services.favorite_service import (
    FavoriteOutfitService,
    FavoriteServiceError,
)


async def _setup(factory):
    async with factory() as db:
        db.add(User(id="default-user"))
        db.add(
            SessionORM(
                id="sess-1",
                user_id="default-user",
                current_image_path="img/start.png",
                character_id="char-1",
            )
        )
        db.add(
            History(
                id="hist-1",
                session_id="sess-1",
                instruction="白いドレスに着替えて",
                image_path="history_images/hist-1.png",
                feeling_text="…これは",
            )
        )
        db.add(
            History(
                id="hist-2",
                session_id="sess-1",
                instruction="メイド服",
                image_path="history_images/hist-2.png",
            )
        )
        await db.commit()
    return factory


@pytest.mark.asyncio
async def test_add_and_list_favorites(isolated_db):
    factory = await _setup(isolated_db.async_factory)
    async with factory() as db:
        view = await FavoriteOutfitService.add(
            db, history_id="hist-1", label="白ドレス"
        )
        await db.commit()
        assert view.history_id == "hist-1"
        assert view.label == "白ドレス"
        assert view.image_url == "/history/images/hist-1"

    async with factory() as db:
        items, total = await FavoriteOutfitService.list_for_user(
            db, page=1, page_size=20
        )
        assert total == 1
        assert items[0].instruction == "白いドレスに着替えて"
        assert items[0].label == "白ドレス"


@pytest.mark.asyncio
async def test_duplicate_favorite_raises(isolated_db):
    factory = await _setup(isolated_db.async_factory)
    async with factory() as db:
        await FavoriteOutfitService.add(db, history_id="hist-1")
        await db.commit()

    async with factory() as db:
        with pytest.raises(FavoriteServiceError) as exc:
            await FavoriteOutfitService.add(db, history_id="hist-1")
        assert exc.value.code == "already_favorited"


@pytest.mark.asyncio
async def test_missing_history_raises(isolated_db):
    factory = await _setup(isolated_db.async_factory)
    async with factory() as db:
        with pytest.raises(FavoriteServiceError) as exc:
            await FavoriteOutfitService.add(db, history_id="missing")
        assert exc.value.code == "history_not_found"


@pytest.mark.asyncio
async def test_label_too_long_raises(isolated_db):
    factory = await _setup(isolated_db.async_factory)
    async with factory() as db:
        with pytest.raises(FavoriteServiceError) as exc:
            await FavoriteOutfitService.add(db, history_id="hist-1", label="あ" * 81)
        assert exc.value.code == "label_too_long"


@pytest.mark.asyncio
async def test_update_label_and_delete_by_history(isolated_db):
    factory = await _setup(isolated_db.async_factory)
    async with factory() as db:
        view = await FavoriteOutfitService.add(db, history_id="hist-2")
        await db.commit()
        fav_id = view.id

    async with factory() as db:
        updated = await FavoriteOutfitService.update_label(
            db, favorite_id=fav_id, label="メイド"
        )
        await db.commit()
        assert updated.label == "メイド"

    async with factory() as db:
        deleted = await FavoriteOutfitService.delete_by_history(db, history_id="hist-2")
        await db.commit()
        assert deleted is True
        items, total = await FavoriteOutfitService.list_for_user(db)
        assert total == 0
        assert items == []


@pytest.mark.asyncio
async def test_favorited_history_ids(isolated_db):
    factory = await _setup(isolated_db.async_factory)
    async with factory() as db:
        await FavoriteOutfitService.add(db, history_id="hist-1")
        await db.commit()

    async with factory() as db:
        ids = await FavoriteOutfitService.favorited_history_ids(
            db, history_ids=["hist-1", "hist-2", "hist-x"]
        )
        assert ids == {"hist-1"}
