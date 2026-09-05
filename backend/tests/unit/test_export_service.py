"""Tests for export_service (Markdown + Novel HTML zip)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

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


@pytest.mark.parametrize(
    ("profile_json", "expected"),
    [
        (None, "主人公"),
        ("{invalid", "主人公"),
        (json.dumps({"display_name": "  テスト名  "}), "テスト名"),
    ],
)
def test_resolve_self_display_name(profile_json: str | None, expected: str) -> None:
    from gateway.services import export_service as export_mod

    assert export_mod._resolve_self_display_name(profile_json) == expected


@pytest.mark.asyncio
async def test_export_service_emits_markdown_and_zip(
    isolated_db, tmp_path: Path, monkeypatch
):
    # Arrange: isolated SQLite (session.py and export_service.py are patched by
    # the isolated_db fixture) + temp data dir.
    test_session_factory = isolated_db.async_factory

    from gateway.services import export_service as export_mod

    # Setup data dir: data/history_images/ stores PNGs, image_path stored as
    # "history_images/<id>.png" (relative to data/).
    data_dir = tmp_path / "data"
    history_dir = data_dir / "history_images"
    monkeypatch.setattr(export_mod.settings, "history_images_dir", history_dir)

    img_rel = "history_images/hist1.png"
    no_feeling_img_rel = "history_images/hist2.png"
    sur_rel = "history_images/hist1_sur.png"
    _make_png(data_dir / img_rel, (200, 100, 100))
    _make_png(data_dir / no_feeling_img_rel, (100, 100, 200))
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
            History(
                id="hist2",
                session_id=sess.id,
                instruction="画質を改善",
                image_path=no_feeling_img_rel,
                feeling_text="(画質改善)",
            )
        )
        db.add(
            History(
                id="hist3",
                session_id=sess.id,
                instruction="画像なしの履歴",
                image_path="history_images/missing.png",
                feeling_text="画像がない心境",
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
    assert "# Character" in text
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
        assert "assets/view.js" in names
        assert "assets/images/hist_hist1.jpg" in names
        assert "assets/images/hist_hist2.jpg" in names
        assert "assets/images/hist_hist3.jpg" not in names
        assert "assets/images/sur_hist1.jpg" in names

        html = zf.read("index.html").decode("utf-8")
        assert "<title>Character -" in html
        assert "バニーガールに変身" in html
        assert "ドキドキする" in html
        assert "ええっ、こんな格好" in html
        assert "message--right" in html  # user bubble
        assert "message--left" in html  # character bubble
        assert 'src="assets/images/hist_hist1.jpg"' in html
        assert 'data-view-target="chat-view"' in html
        assert 'data-view-target="paired-view"' in html
        assert 'id="paired-view"' in html

        paired_html = html.split('id="paired-view"', maxsplit=1)[1].split(
            "</main>", maxsplit=1
        )[0]
        assert paired_html.count('class="paired-card"') == 2
        assert 'src="assets/images/hist_hist1.jpg"' in paired_html
        assert 'src="assets/images/hist_hist2.jpg"' in paired_html
        assert "ドキドキする" in paired_html
        assert "バニーガールに変身" in paired_html
        assert 'class="paired-entry__instruction"' in paired_html
        assert "心境テキストはありません" in paired_html
        assert "ええっ、こんな格好" not in paired_html
        assert "sur_hist1.jpg" not in paired_html
        assert "画像がない心境" not in paired_html

        css = zf.read("assets/style.css").decode("utf-8")
        assert "grid-template-columns: minmax(260px, 42%)" in css
        assert "@media (max-width: 640px)" in css
        script = zf.read("assets/view.js").decode("utf-8")
        assert 'tab.setAttribute("aria-selected", String(isActive))' in script


@pytest.mark.asyncio
async def test_self_mode_export_uses_profile_display_name(
    isolated_db, tmp_path: Path, monkeypatch
):
    test_session_factory = isolated_db.async_factory

    from gateway.services import export_service as export_mod

    data_dir = tmp_path / "data"
    history_dir = data_dir / "history_images"
    monkeypatch.setattr(export_mod.settings, "history_images_dir", history_dir)

    img_rel = "history_images/self.png"
    _make_png(data_dir / img_rel, (120, 160, 200))

    async with test_session_factory() as db:
        db.add(
            User(
                id="self-user",
                self_profile_json=json.dumps({"display_name": "ありす"}),
            )
        )
        await db.commit()
        db.add(
            Session(
                id="self-mode-session",
                user_id="self-user",
                character_id="nonexistent-preset",
                current_image_path=img_rel,
                transformation_count=1,
                is_active=True,
                self_mode=True,
            )
        )
        db.add(
            History(
                id="self-history",
                session_id="self-mode-session",
                instruction="衣装を変更",
                image_path=img_rel,
                feeling_text="少し恥ずかしい",
            )
        )
        await db.commit()

    md_bytes, _ = await export_mod.build_markdown_export("self-mode-session")
    markdown = md_bytes.decode("utf-8")
    assert "# ありす" in markdown
    assert "### ありす" in markdown

    zip_bytes, _ = await export_mod.build_novel_html_zip("self-mode-session")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        html = zf.read("index.html").decode("utf-8")
        assert "<title>ありす -" in html
        assert "<figcaption>ありす</figcaption>" in html
        assert "ありす ·" in html
        assert ">Character ·" not in html


@pytest.mark.asyncio
async def test_export_history_only_session_includes_all_messages(
    isolated_db, tmp_path: Path, monkeypatch
):
    """Sessions with History but no Conversation must still emit messages."""
    test_session_factory = isolated_db.async_factory

    from gateway.services import export_service as export_mod

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
async def test_export_service_raises_lookup_error_when_missing(isolated_db):
    from gateway.services import export_service as export_mod

    with pytest.raises(LookupError):
        await export_mod.build_markdown_export("no-such-session")
    with pytest.raises(LookupError):
        await export_mod.build_novel_html_zip("no-such-session")
