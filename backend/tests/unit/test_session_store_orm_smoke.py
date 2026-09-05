import ast
import sys
from pathlib import Path

import pytest

from gateway.databases.models import User
from gateway.services.session import DatabaseSessionStore


@pytest.mark.asyncio
async def test_session_store_smoke_works_with_orm(
    isolated_db, tmp_path: Path, monkeypatch
):
    test_session_factory = isolated_db.async_factory
    module = sys.modules["gateway.services.session"]

    history_images_dir = tmp_path / "history_images"
    history_images_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(module.settings, "history_images_dir", history_images_dir)

    async with test_session_factory() as db_session:
        db_session.add(User(id="smoke-user"))
        await db_session.commit()

    store = DatabaseSessionStore(history_images_dir=history_images_dir)

    created = await store.create_session(
        image_path="session/start.png",
        character_id="char-1",
        user_id="smoke-user",
    )
    assert created.user_id == "smoke-user"

    active = await store.get_active_session("smoke-user")
    assert active is not None
    assert active.id == created.id

    await store.update_session(created.id, transformation_count=2)
    updated = await store.get_session_by_id(created.id)
    assert updated is not None
    assert updated.transformation_count == 2

    incremented = await store.increment_transformation_count(created.id)
    assert incremented == 3

    history = await store.add_history(
        session_id=created.id,
        instruction="smoke instruction",
        image_data=b"PNG",
        feeling_text="ok",
        before_description="before",
        after_description="after",
    )
    assert history.session_id == created.id

    history_list = await store.get_history(created.id)
    assert len(history_list) == 1
    assert history_list[0].id == history.id

    stats = await store.get_or_create_session_stats(
        created.id, difficulty="hard", nsfw_mode=True
    )
    assert stats.difficulty == "hard"
    assert stats.nsfw_mode is True

    stats.bloom = 15
    await store.update_session_stats(stats)
    persisted_stats = await store.get_session_stats(created.id)
    assert persisted_stats is not None
    assert persisted_stats.bloom == 15


def test_runtime_session_gallery_have_no_raw_sql_literals():
    backend_root = Path(__file__).resolve().parents[2]
    session_text = (backend_root / "gateway" / "services" / "session.py").read_text(
        encoding="utf-8"
    )
    gallery_text = (
        backend_root / "gateway" / "routes" / "gallery_router.py"
    ).read_text(encoding="utf-8")

    def _has_forbidden_runtime_usage(source: str, forbidden_import: str) -> bool:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == forbidden_import:
                return True
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr != "execute":
                    continue
                if isinstance(node.func.value, ast.Name) and node.func.value.id in {
                    "conn",
                    "cursor",
                }:
                    return True
        return False

    assert _has_forbidden_runtime_usage(session_text, "gateway.database") is False
    assert _has_forbidden_runtime_usage(session_text, ".database") is False
    assert _has_forbidden_runtime_usage(gallery_text, "gateway.database") is False
    assert _has_forbidden_runtime_usage(gallery_text, ".database") is False
