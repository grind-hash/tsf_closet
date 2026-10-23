"""お気に入りプロンプトの永続化サービス。"""

from __future__ import annotations

import pytest

from gateway.databases.models import User
from gateway.services.favorite_prompt_file import (
    EXPORT_FORMAT,
    FavoritePromptFileEntries,
    FileCategoryEntry,
    FilePromptEntry,
)
from gateway.services.favorite_prompt_service import (
    DEFAULT_COLOR,
    FavoritePromptService,
    FavoritePromptServiceError,
)

USER_ID = "default-user"


@pytest.fixture
async def db(isolated_db):
    async with isolated_db.async_factory() as session:
        session.add(User(id=USER_ID))
        await session.commit()
        yield session


async def test_create_and_list_in_sort_order(db):
    category = await FavoritePromptService.create_category(
        db, label="衣装", color="#ff0000"
    )
    first = await FavoritePromptService.create_prompt(
        db, label="白ワンピース", content="white dress, ", category_id=category.id
    )
    second = await FavoritePromptService.create_prompt(
        db, label="背景", content="classroom"
    )
    await db.commit()

    categories, prompts = await FavoritePromptService.list_all(db)

    assert [c.label for c in categories] == ["衣装"]
    assert categories[0].color == "#FF0000"
    assert [p.id for p in prompts] == [first.id, second.id]
    assert prompts[0].category_id == category.id
    assert prompts[0].content == "white dress, "
    assert prompts[1].category_id is None
    assert prompts[1].color == DEFAULT_COLOR
    assert first.sort_order < second.sort_order


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"label": "  ", "content": "x"}, "label_required"),
        ({"label": "a" * 81, "content": "x"}, "label_too_long"),
        ({"label": "a", "content": " \n"}, "content_required"),
        ({"label": "a", "content": "x" * 4001}, "content_too_long"),
        ({"label": "a", "content": "x", "color": "red"}, "invalid_color"),
        (
            {"label": "a", "content": "x", "category_id": "missing"},
            "category_not_found",
        ),
    ],
)
async def test_create_prompt_validation(db, kwargs, code):
    with pytest.raises(FavoritePromptServiceError) as excinfo:
        await FavoritePromptService.create_prompt(db, **kwargs)
    assert excinfo.value.code == code


async def test_update_prompt_only_changes_given_fields(db):
    category = await FavoritePromptService.create_category(db, label="衣装")
    prompt = await FavoritePromptService.create_prompt(
        db, label="旧名", content="tag", color="#123456", category_id=category.id
    )

    updated = await FavoritePromptService.update_prompt(
        db, prompt_id=prompt.id, changes={"label": "新名"}
    )
    assert updated.label == "新名"
    assert updated.content == "tag"
    assert updated.color == "#123456"
    assert updated.category_id == category.id

    moved = await FavoritePromptService.update_prompt(
        db, prompt_id=prompt.id, changes={"category_id": None}
    )
    assert moved.category_id is None


async def test_update_unknown_prompt_raises(db):
    with pytest.raises(FavoritePromptServiceError) as excinfo:
        await FavoritePromptService.update_prompt(
            db, prompt_id="missing", changes={"label": "x"}
        )
    assert excinfo.value.code == "prompt_not_found"


async def test_delete_category_moves_prompts_to_uncategorized(db):
    category = await FavoritePromptService.create_category(db, label="衣装")
    prompt = await FavoritePromptService.create_prompt(
        db, label="白ワンピース", content="white dress", category_id=category.id
    )
    await db.commit()

    assert await FavoritePromptService.delete_category(db, category_id=category.id)
    await db.commit()

    categories, prompts = await FavoritePromptService.list_all(db)
    assert categories == []
    assert [p.id for p in prompts] == [prompt.id]
    assert prompts[0].category_id is None


async def test_delete_prompt(db):
    prompt = await FavoritePromptService.create_prompt(db, label="a", content="b")
    assert await FavoritePromptService.delete_prompt(db, prompt_id=prompt.id)
    assert not await FavoritePromptService.delete_prompt(db, prompt_id=prompt.id)


async def test_other_users_items_are_not_visible(db):
    db.add(User(id="other-user"))
    await db.flush()
    other = await FavoritePromptService.create_prompt(
        db, label="a", content="b", user_id="other-user"
    )

    _, prompts = await FavoritePromptService.list_all(db)
    assert prompts == []
    assert not await FavoritePromptService.delete_prompt(db, prompt_id=other.id)


def _entries(
    *prompts: tuple[str | None, str, str], categories: tuple[str, ...] = ()
) -> FavoritePromptFileEntries:
    return FavoritePromptFileEntries(
        categories=[
            FileCategoryEntry(f"カテゴリーの{i}件目", label, "#123456")
            for i, label in enumerate(categories, start=1)
        ],
        prompts=[
            FilePromptEntry(f"{i}行目", category, label, content, None)
            for i, (category, label, content) in enumerate(prompts, start=2)
        ],
    )


async def test_import_creates_missing_categories_and_overwrites_matches(db):
    outfit = await FavoritePromptService.create_category(
        db, label="衣装", color="#ff0000"
    )
    dress = await FavoritePromptService.create_prompt(
        db, label="白ワンピース", content="old", category_id=outfit.id
    )
    loose = await FavoritePromptService.create_prompt(db, label="笑顔", content="old")
    await db.commit()

    entries = _entries(
        ("衣装", "白ワンピース", "white sundress"),
        (None, "笑顔", "smile"),
        # 同じ名前でもカテゴリーが違えば別物として追加する
        ("衣装", "笑顔", "grin"),
        ("髪型", "ポニーテール", "ponytail"),
        categories=("衣装", "小物"),
    )
    preview = await FavoritePromptService.preview_import(db, entries=entries)
    assert [(item.category, item.label) for _, item in preview.overwrites] == [
        ("衣装", "白ワンピース"),
        (None, "笑顔"),
    ]
    assert [item.label for item in preview.creates] == ["笑顔", "ポニーテール"]
    assert preview.new_categories == [("小物", "#123456"), ("髪型", "#6B7280")]
    # プレビューでは書き込まない
    await db.rollback()
    categories, prompts = await FavoritePromptService.list_all(db)
    assert len(categories) == 1
    assert len(prompts) == 2

    await FavoritePromptService.import_file(db, entries=entries)
    await db.commit()

    categories, prompts = await FavoritePromptService.list_all(db)
    assert [(c.label, c.color) for c in categories] == [
        ("衣装", "#FF0000"),
        ("小物", "#123456"),
        ("髪型", "#6B7280"),
    ]
    by_id = {p.id: p for p in prompts}
    assert by_id[dress.id].content == "white sundress"
    assert by_id[loose.id].content == "smile"
    hair = next(c for c in categories if c.label == "髪型")
    assert [(p.label, p.category_id) for p in prompts[2:]] == [
        ("笑顔", outfit.id),
        ("ポニーテール", hair.id),
    ]


async def test_import_keeps_existing_color_when_file_leaves_it_blank(db):
    kept = await FavoritePromptService.create_prompt(
        db, label="笑顔", content="old", color="#ff0000"
    )
    await db.commit()
    entries = FavoritePromptFileEntries(
        prompts=[
            FilePromptEntry("2行目", None, "笑顔", "smile", None),
            FilePromptEntry("3行目", None, "新規", "new", None),
        ]
    )

    await FavoritePromptService.import_file(db, entries=entries)
    await db.commit()

    _, prompts = await FavoritePromptService.list_all(db)
    by_label = {p.label: p for p in prompts}
    assert by_label["笑顔"].id == kept.id
    assert by_label["笑顔"].content == "smile"
    assert by_label["笑顔"].color == "#FF0000"
    assert by_label["新規"].color == DEFAULT_COLOR


async def test_import_reports_row_of_invalid_item(db):
    entries = _entries((None, "ok", "a"), (None, " ", "b"))
    with pytest.raises(FavoritePromptServiceError) as exc:
        await FavoritePromptService.import_file(db, entries=entries)
    assert exc.value.code == "label_required"
    assert exc.value.message == "3行目: 名前を入力してください"


async def test_import_uses_last_duplicate_in_file(db):
    entries = _entries((None, "a", "first"), (None, "a", "second"))
    plan = await FavoritePromptService.import_file(db, entries=entries)
    await db.commit()

    assert len(plan.creates) == 1
    _, prompts = await FavoritePromptService.list_all(db)
    assert [(p.label, p.content) for p in prompts] == [("a", "second")]


async def test_export_refers_categories_by_name(db):
    category = await FavoritePromptService.create_category(db, label="衣装")
    await FavoritePromptService.create_prompt(
        db, label="白ワンピース", content="white dress", category_id=category.id
    )
    await db.commit()

    data = await FavoritePromptService.export_file(db)

    assert data.format == EXPORT_FORMAT
    assert [c.label for c in data.categories] == ["衣装"]
    assert [(p.category, p.label) for p in data.prompts] == [("衣装", "白ワンピース")]


async def test_reorder_moves_between_categories_and_keeps_unlisted(db):
    outfit = await FavoritePromptService.create_category(db, label="衣装")
    a = await FavoritePromptService.create_prompt(db, label="a", content="a")
    b = await FavoritePromptService.create_prompt(
        db, label="b", content="b", category_id=outfit.id
    )
    c = await FavoritePromptService.create_prompt(db, label="c", content="c")
    await db.commit()

    # c を衣装の先頭へ移し、a を未分類に残す。b は送らない（後ろへ残る）
    await FavoritePromptService.reorder_prompts(
        db, placements=[(a.id, None), (c.id, outfit.id)]
    )
    await db.commit()

    _, prompts = await FavoritePromptService.list_all(db)
    assert [(p.id, p.category_id) for p in prompts] == [
        (a.id, None),
        (c.id, outfit.id),
        (b.id, outfit.id),
    ]


@pytest.mark.parametrize("target", ["prompt", "category"])
async def test_reorder_rejects_unknown_ids(db, target):
    prompt = await FavoritePromptService.create_prompt(db, label="a", content="a")
    await db.commit()
    placements = [("missing", None)] if target == "prompt" else [(prompt.id, "missing")]

    with pytest.raises(FavoritePromptServiceError) as exc:
        await FavoritePromptService.reorder_prompts(db, placements=placements)
    assert exc.value.code == f"{target}_not_found"
