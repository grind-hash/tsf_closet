"""お気に入りプロンプト（よく使うタグや文章）の永続化サービス。

TSF Closet の DB にだけ保存する。NovelAI のプロンプトチャンクとは同期しない
（チャンクは NovelAI 側でユーザーのキーストアにより暗号化されており、API キー
だけでは読み書きできないため）。
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..databases.models import FavoritePrompt, FavoritePromptCategory
from .session import DEFAULT_USER_ID

LABEL_MAX_LENGTH = 80
CONTENT_MAX_LENGTH = 4000
DEFAULT_COLOR = "#6B7280"
_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


class FavoritePromptServiceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _normalize_label(label: str | None) -> str:
    text = (label or "").strip()
    if not text:
        raise FavoritePromptServiceError("label_required", "名前を入力してください")
    if len(text) > LABEL_MAX_LENGTH:
        raise FavoritePromptServiceError(
            "label_too_long",
            f"名前は{LABEL_MAX_LENGTH}文字以内にしてください",
        )
    return text


def _normalize_content(content: str | None) -> str:
    # 末尾の区切り（", " など）は意図して付けることがあるため、そのまま保存する
    text = content or ""
    if not text.strip():
        raise FavoritePromptServiceError("content_required", "内容を入力してください")
    if len(text) > CONTENT_MAX_LENGTH:
        raise FavoritePromptServiceError(
            "content_too_long",
            f"内容は{CONTENT_MAX_LENGTH}文字以内にしてください",
        )
    return text


def _normalize_color(color: str | None) -> str:
    if color is None or not color.strip():
        return DEFAULT_COLOR
    text = color.strip()
    if not _COLOR_PATTERN.match(text):
        raise FavoritePromptServiceError(
            "invalid_color", "色は #RRGGBB 形式で指定してください"
        )
    return text.upper()


async def _next_sort_order(
    db: AsyncSession,
    model: type[FavoritePrompt] | type[FavoritePromptCategory],
    user_id: str,
) -> int:
    stmt = select(func.max(model.sort_order)).where(model.user_id == user_id)
    current = (await db.execute(stmt)).scalar_one_or_none()
    return 0 if current is None else int(current) + 1


async def _get_category(
    db: AsyncSession, category_id: str, user_id: str
) -> FavoritePromptCategory:
    stmt = select(FavoritePromptCategory).where(
        FavoritePromptCategory.id == category_id,
        FavoritePromptCategory.user_id == user_id,
    )
    category = (await db.execute(stmt)).scalar_one_or_none()
    if category is None:
        raise FavoritePromptServiceError(
            "category_not_found", "カテゴリーが見つかりません"
        )
    return category


async def _get_prompt(db: AsyncSession, prompt_id: str, user_id: str) -> FavoritePrompt:
    stmt = select(FavoritePrompt).where(
        FavoritePrompt.id == prompt_id,
        FavoritePrompt.user_id == user_id,
    )
    prompt = (await db.execute(stmt)).scalar_one_or_none()
    if prompt is None:
        raise FavoritePromptServiceError(
            "prompt_not_found", "お気に入りプロンプトが見つかりません"
        )
    return prompt


async def _resolve_category_id(
    db: AsyncSession, category_id: str | None, user_id: str
) -> str | None:
    if not category_id:
        return None
    category = await _get_category(db, category_id, user_id)
    return category.id


class FavoritePromptService:
    @staticmethod
    async def list_all(
        db: AsyncSession,
        *,
        user_id: str = DEFAULT_USER_ID,
    ) -> tuple[list[FavoritePromptCategory], list[FavoritePrompt]]:
        categories_stmt = (
            select(FavoritePromptCategory)
            .where(FavoritePromptCategory.user_id == user_id)
            .order_by(FavoritePromptCategory.sort_order, FavoritePromptCategory.id)
        )
        prompts_stmt = (
            select(FavoritePrompt)
            .where(FavoritePrompt.user_id == user_id)
            .order_by(FavoritePrompt.sort_order, FavoritePrompt.id)
        )
        categories = list((await db.execute(categories_stmt)).scalars().all())
        prompts = list((await db.execute(prompts_stmt)).scalars().all())
        return categories, prompts

    @staticmethod
    async def create_prompt(
        db: AsyncSession,
        *,
        label: str,
        content: str,
        color: str | None = None,
        category_id: str | None = None,
        user_id: str = DEFAULT_USER_ID,
    ) -> FavoritePrompt:
        prompt = FavoritePrompt(
            id=str(uuid.uuid4()),
            user_id=user_id,
            category_id=await _resolve_category_id(db, category_id, user_id),
            label=_normalize_label(label),
            content=_normalize_content(content),
            color=_normalize_color(color),
            sort_order=await _next_sort_order(db, FavoritePrompt, user_id),
        )
        db.add(prompt)
        await db.flush()
        await db.refresh(prompt)
        return prompt

    @staticmethod
    async def update_prompt(
        db: AsyncSession,
        *,
        prompt_id: str,
        changes: dict[str, Any],
        user_id: str = DEFAULT_USER_ID,
    ) -> FavoritePrompt:
        """``changes`` に含まれる項目だけを更新する（category_id=None は未分類へ移動）。"""
        prompt = await _get_prompt(db, prompt_id, user_id)
        if "label" in changes:
            prompt.label = _normalize_label(changes["label"])
        if "content" in changes:
            prompt.content = _normalize_content(changes["content"])
        if "color" in changes:
            prompt.color = _normalize_color(changes["color"])
        if "category_id" in changes:
            prompt.category_id = await _resolve_category_id(
                db, changes["category_id"], user_id
            )
        await db.flush()
        await db.refresh(prompt)
        return prompt

    @staticmethod
    async def delete_prompt(
        db: AsyncSession,
        *,
        prompt_id: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> bool:
        try:
            prompt = await _get_prompt(db, prompt_id, user_id)
        except FavoritePromptServiceError:
            return False
        await db.delete(prompt)
        await db.flush()
        return True

    @staticmethod
    async def create_category(
        db: AsyncSession,
        *,
        label: str,
        color: str | None = None,
        user_id: str = DEFAULT_USER_ID,
    ) -> FavoritePromptCategory:
        category = FavoritePromptCategory(
            id=str(uuid.uuid4()),
            user_id=user_id,
            label=_normalize_label(label),
            color=_normalize_color(color),
            sort_order=await _next_sort_order(db, FavoritePromptCategory, user_id),
        )
        db.add(category)
        await db.flush()
        await db.refresh(category)
        return category

    @staticmethod
    async def update_category(
        db: AsyncSession,
        *,
        category_id: str,
        changes: dict[str, Any],
        user_id: str = DEFAULT_USER_ID,
    ) -> FavoritePromptCategory:
        category = await _get_category(db, category_id, user_id)
        if "label" in changes:
            category.label = _normalize_label(changes["label"])
        if "color" in changes:
            category.color = _normalize_color(changes["color"])
        await db.flush()
        await db.refresh(category)
        return category

    @staticmethod
    async def delete_category(
        db: AsyncSession,
        *,
        category_id: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> bool:
        """カテゴリーを削除する。中のプロンプトは消さずに未分類へ移す。"""
        try:
            category = await _get_category(db, category_id, user_id)
        except FavoritePromptServiceError:
            return False
        await db.execute(
            update(FavoritePrompt)
            .where(
                FavoritePrompt.user_id == user_id,
                FavoritePrompt.category_id == category.id,
            )
            .values(category_id=None)
        )
        await db.delete(category)
        await db.flush()
        return True
