"""お気に入りプロンプトの永続化サービス。"""

from __future__ import annotations

import pytest

from gateway.databases.models import User
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
