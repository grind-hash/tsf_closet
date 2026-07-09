"""Tests for export_service (Markdown + Novel HTML zip)."""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gateway.databases.base import Base
from gateway.databases.models import (
    Conversation,
    History,
    Session,
    User,
)


def _make_png(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (64, 64), color)
    img.save(path, format="PNG")


@pytest.mark.asyncio
async def test_export_service_emits_markdown_and_zip(tmp_path: Path, monkeypatch):
    # Arrange: in-memory SQLite + temp data dir.
    db_path = tmp_path / "export.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    test_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Patch async_session_factory in BOTH session.py and export_service.py.
    from gateway.services import export_service as export_mod

    monkeypatch.setattr(export_mod, "async_session_factory", test_session_factory)
    if "gateway.services.session" in sys.modules:
        monkeypatch.setattr(
            sys.modules["gateway.services.session"],
            "async_session_factory",
            test_session_factory,
        )

    # Setup data dir: data/history_images/ stores PNGs, image_path stored as
    # "history_images/<id>.png" (relative to data/).
    data_dir = tmp_path / "data"
    history_dir = data_dir / "history_images"
    monkeypatch.setattr(export_mod.settings, "history_images_dir", history_dir)

    img_rel = "history_images/hist1.png"
    sur_rel = "history_images/hist1_sur.png"
    _make_png(data_dir / img_rel, (200, 100, 100))
    _make_png(data_dir / sur_rel, (100, 200, 100))

    # Seed DB.
    async with test_session_factory() as db:
        db.add(User(id="u1"))
        await db.commit()

        sess = Session(
            id="sess-abcdef1234",
            user_id="u1",
            character_id="nonexistent-preset",
            current_image_path="images/characters/missing.png",
            transformation_count=1,
            is_active=True,
        )
        db.add(sess)
        await db.commit()

        db.add(
            History(
                id="hist1",
                session_id=sess.id,
                instruction="バニーガールに変身",
                image_path=img_rel,
                feeling_text="ドキドキする",
                surroundings_image_path=sur_rel,
            )
        )
        db.add(
            Conversation(
                id="c1",
                session_id=sess.id,
                role="user",
                content="バニーガールに変身して",
                instruction_type="dress_up",
            )
        )
        db.add(
            Conversation(
                id="c2",
                session_id=sess.id,
                role="character",
                content="ええっ、こんな格好...！",
                instruction_type="dress_up",
                related_history_id="hist1",
            )
        )
        await db.commit()

    # Act + Assert: Markdown.
    md_bytes, md_name = await export_mod.build_markdown_export("sess-abcdef1234")
    assert md_name.endswith(".md")
    assert "sess-abc" in md_name
    text = md_bytes.decode("utf-8")
    # History-derived: user instruction and character feeling text must appear.
    assert "バニーガールに変身" in text
    assert "ドキドキする" in text
    # Conversation-derived: chat conversation content must appear.
    assert "ええっ、こんな格好" in text
    # JPEG data URI must be embedded (history image + surroundings image).
    assert text.count("data:image/jpeg;base64,") >= 2

    # Act + Assert: Novel HTML zip.
    zip_bytes, zip_name = await export_mod.build_novel_html_zip("sess-abcdef1234")
    assert zip_name.endswith(".zip")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "index.html" in names
        assert "assets/style.css" in names
        assert "assets/images/hist_hist1.jpg" in names
        assert "assets/images/sur_hist1.jpg" in names

        html = zf.read("index.html").decode("utf-8")
        assert "バニーガールに変身" in html
        assert "ドキドキする" in html
        assert "ええっ、こんな格好" in html
        assert "message--right" in html  # user bubble
        assert "message--left" in html  # character bubble
        assert 'src="assets/images/hist_hist1.jpg"' in html


@pytest.mark.asyncio
async def test_export_history_only_session_includes_all_messages(
    tmp_path: Path, monkeypatch
):
    """Sessions with History but no Conversation must still emit messages."""
    db_path = tmp_path / "history_only.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    test_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    from gateway.services import export_service as export_mod

    monkeypatch.setattr(export_mod, "async_session_factory", test_session_factory)

    data_dir = tmp_path / "data"
    history_dir = data_dir / "history_images"
    monkeypatch.setattr(export_mod.settings, "history_images_dir", history_dir)

    # 5 history rows, each with an image. No Conversation rows.
    async with test_session_factory() as db:
        db.add(User(id="u1"))
        await db.commit()
        db.add(
            Session(
                id="hist-only-session",
                user_id="u1",
                character_id=None,
                current_image_path="",
                transformation_count=5,
                is_active=True,
            )
        )
        await db.commit()
        for i in range(5):
            rel = f"history_images/h{i}.png"
            _make_png(data_dir / rel, (50 * i % 255, 100, 200))
            db.add(
                History(
                    id=f"h{i}",
                    session_id="hist-only-session",
                    instruction=f"指示{i}",
                    image_path=rel,
                    feeling_text=f"感想{i}",
                )
            )
        await db.commit()

    md_bytes, _ = await export_mod.build_markdown_export("hist-only-session")
    text = md_bytes.decode("utf-8")
    # Every instruction and feeling must appear.
    for i in range(5):
        assert f"指示{i}" in text, f"missing instruction {i}"
        assert f"感想{i}" in text, f"missing feeling {i}"
    # 5 embedded images.
    assert text.count("data:image/jpeg;base64,") == 5


@pytest.mark.asyncio
async def test_export_service_raises_lookup_error_when_missing(
    tmp_path: Path, monkeypatch
):
    db_path = tmp_path / "empty.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    test_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    from gateway.services import export_service as export_mod

    monkeypatch.setattr(export_mod, "async_session_factory", test_session_factory)

    with pytest.raises(LookupError):
        await export_mod.build_markdown_export("no-such-session")
    with pytest.raises(LookupError):
        await export_mod.build_novel_html_zip("no-such-session")
