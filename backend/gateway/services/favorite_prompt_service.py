"""お気に入りプロンプト（よく使うタグや文章）の永続化サービス。

TSF Closet の DB にだけ保存する。NovelAI のプロンプトチャンクとは同期しない
（チャンクは NovelAI 側でユーザーのキーストアにより暗号化されており、API キー
だけでは読み書きできないため）。
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..databases.models import FavoritePrompt, FavoritePromptCategory
from ..schemas.favorite_prompts import (
    FavoritePromptFile,
    FavoritePromptFileCategory,
    FavoritePromptFilePrompt,
)
from .favorite_prompt_file import (
    EXPORT_FORMAT,
    EXPORT_VERSION,
    FavoritePromptFileEntries,
)
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


@dataclass(frozen=True)
class FavoritePromptImportItem:
    category: str | None
    label: str
    content: str
    # 未指定なら上書き時は既存の色を残し、新規追加時は既定色にする
    color: str | None


@dataclass
class FavoritePromptImportPlan:
    """インポートで行う変更。プレビューと実行で同じ計画を使う。"""

    # 既存カテゴリー名 → ID（同名が複数あるときは並び順で先のもの）
    category_ids: dict[str, str] = field(default_factory=dict)
    # 新しく作るカテゴリー（名前, 色）
    new_categories: list[tuple[str, str]] = field(default_factory=list)
    creates: list[FavoritePromptImportItem] = field(default_factory=list)
    overwrites: list[tuple[FavoritePrompt, FavoritePromptImportItem]] = field(
        default_factory=list
    )


def _with_position(
    position: str, exc: FavoritePromptServiceError
) -> FavoritePromptServiceError:
    return FavoritePromptServiceError(exc.code, f"{position}: {exc.message}")


def _normalize_optional_color(color: str | None) -> str | None:
    if color is None or not color.strip():
        return None
    return _normalize_color(color)


def _normalize_file_category(label: str | None) -> str | None:
    if label is None or not label.strip():
        return None
    return _normalize_label(label)


async def _build_import_plan(
    db: AsyncSession, entries: FavoritePromptFileEntries, user_id: str
) -> FavoritePromptImportPlan:
    """ファイルの内容を検証し、既存データと照合する。

    カテゴリーは名前で照合し、無ければ新しく作る（既存カテゴリーの色は変えない）。
    プロンプトは「カテゴリー + 名前」で照合し、一致したものは内容と色を上書きする
    （色が空なら既存の色を残す）。
    """
    # ファイルに書かれた順。色の指定が無ければ None（新規作成時は既定色）
    category_colors: dict[str, str | None] = {}
    for entry in entries.categories:
        try:
            label = _normalize_label(entry.label)
            color = _normalize_optional_color(entry.color)
        except FavoritePromptServiceError as exc:
            raise _with_position(entry.position, exc) from exc
        if category_colors.get(label) is None:
            category_colors[label] = color

    items: dict[tuple[str | None, str], FavoritePromptImportItem] = {}
    for entry in entries.prompts:
        try:
            category = _normalize_file_category(entry.category)
        except FavoritePromptServiceError as exc:
            raise _with_position(f"{entry.position}のカテゴリー", exc) from exc
        try:
            item = FavoritePromptImportItem(
                category=category,
                label=_normalize_label(entry.label),
                content=_normalize_content(entry.content),
                color=_normalize_optional_color(entry.color),
            )
        except FavoritePromptServiceError as exc:
            raise _with_position(entry.position, exc) from exc
        # ファイル内の重複は後の項目の内容を使う（並び順は最初の位置のまま）
        items[(item.category, item.label)] = item

    categories, prompts = await FavoritePromptService.list_all(db, user_id=user_id)
    plan = FavoritePromptImportPlan()
    for existing_category in categories:
        plan.category_ids.setdefault(existing_category.label, existing_category.id)
    existing: dict[tuple[str | None, str], FavoritePrompt] = {}
    for prompt in prompts:
        existing.setdefault((prompt.category_id, prompt.label), prompt)

    required = [*category_colors, *(i.category for i in items.values())]
    for label in dict.fromkeys(required):
        if label is not None and label not in plan.category_ids:
            plan.new_categories.append(
                (label, category_colors.get(label) or DEFAULT_COLOR)
            )

    for item in items.values():
        if item.category is not None and item.category not in plan.category_ids:
            plan.creates.append(item)
            continue
        category_id = plan.category_ids[item.category] if item.category else None
        target = existing.get((category_id, item.label))
        if target is None:
            plan.creates.append(item)
        else:
            plan.overwrites.append((target, item))
    return plan


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

    @staticmethod
    async def export_file(
        db: AsyncSession,
        *,
        user_id: str = DEFAULT_USER_ID,
    ) -> FavoritePromptFile:
        categories, prompts = await FavoritePromptService.list_all(db, user_id=user_id)
        labels = {c.id: c.label for c in categories}
        return FavoritePromptFile(
            format=EXPORT_FORMAT,
            version=EXPORT_VERSION,
            exported_at=datetime.now(UTC),
            categories=[
                FavoritePromptFileCategory(label=c.label, color=c.color)
                for c in categories
            ],
            prompts=[
                FavoritePromptFilePrompt(
                    category=labels.get(p.category_id) if p.category_id else None,
                    label=p.label,
                    content=p.content,
                    color=p.color,
                )
                for p in prompts
            ],
        )

    @staticmethod
    async def preview_import(
        db: AsyncSession,
        *,
        entries: FavoritePromptFileEntries,
        user_id: str = DEFAULT_USER_ID,
    ) -> FavoritePromptImportPlan:
        """書き込まずに、インポートで追加・上書きされる内容を返す。"""
        return await _build_import_plan(db, entries, user_id)

    @staticmethod
    async def import_file(
        db: AsyncSession,
        *,
        entries: FavoritePromptFileEntries,
        user_id: str = DEFAULT_USER_ID,
    ) -> FavoritePromptImportPlan:
        """ファイルの内容を取り込む。新しいカテゴリーとプロンプトは末尾に追加する。"""
        plan = await _build_import_plan(db, entries, user_id)
        category_ids = dict(plan.category_ids)
        category_order = await _next_sort_order(db, FavoritePromptCategory, user_id)
        for offset, (label, color) in enumerate(plan.new_categories):
            category = FavoritePromptCategory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                label=label,
                color=color,
                sort_order=category_order + offset,
            )
            db.add(category)
            category_ids[label] = category.id
        for prompt, item in plan.overwrites:
            prompt.content = item.content
            if item.color is not None:
                prompt.color = item.color
        prompt_order = await _next_sort_order(db, FavoritePrompt, user_id)
        for offset, item in enumerate(plan.creates):
            db.add(
                FavoritePrompt(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    category_id=category_ids[item.category] if item.category else None,
                    label=item.label,
                    content=item.content,
                    color=item.color or DEFAULT_COLOR,
                    sort_order=prompt_order + offset,
                )
            )
        await db.flush()
        return plan

    @staticmethod
    async def reorder_prompts(
        db: AsyncSession,
        *,
        placements: list[tuple[str, str | None]],
        user_id: str = DEFAULT_USER_ID,
    ) -> None:
        """並び順とカテゴリーをまとめて保存する（ドラッグ＆ドロップの並べ替え用）。

        ``placements`` は表示順に並べた (プロンプトID, カテゴリーID)。含まれないプロンプト
        （別の画面で追加された直後など）は、元の並びのまま後ろに置く。
        """
        categories, prompts = await FavoritePromptService.list_all(db, user_id=user_id)
        by_id = {p.id: p for p in prompts}
        category_ids = {c.id for c in categories}
        ordered: list[tuple[FavoritePrompt, str | None]] = []
        for prompt_id, category_id in placements:
            prompt = by_id.pop(prompt_id, None)
            if prompt is None:
                raise FavoritePromptServiceError(
                    "prompt_not_found", "お気に入りプロンプトが見つかりません"
                )
            if category_id is not None and category_id not in category_ids:
                raise FavoritePromptServiceError(
                    "category_not_found", "カテゴリーが見つかりません"
                )
            ordered.append((prompt, category_id))
        ordered.extend((p, p.category_id) for p in by_id.values())
        for index, (prompt, category_id) in enumerate(ordered):
            prompt.sort_order = index
            prompt.category_id = category_id
        await db.flush()
