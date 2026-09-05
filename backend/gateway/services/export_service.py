"""Export service for chat history with embedded images.

Provides two export formats:
- Markdown (.md) with base64-embedded JPEG images
- Novel-style HTML packaged as a ZIP archive with images under assets/
"""

from __future__ import annotations

import base64
import html
import io
import json
import logging
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image
from sqlalchemy import select

from ..databases.base import async_session_factory
from ..databases.models import Conversation as ConversationORM
from ..databases.models import History as HistoryORM
from ..databases.models import Session as SessionORM
from ..databases.models import User as UserORM
from ..services.characters import CharacterManager
from ..settings.config import BASE_DIR, settings

logger = logging.getLogger(__name__)


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_NOVEL_HTML_TEMPLATE = _TEMPLATES_DIR / "novel.html.tmpl"
_NOVEL_CSS = _TEMPLATES_DIR / "novel.css"
_NOVEL_JS = _TEMPLATES_DIR / "novel.js"

_MAX_IMAGE_SIDE = 1024
_JPEG_QUALITY = 85


@dataclass
class _ImageRef:
    """Reference to an image file with a stable identifier for asset naming."""

    asset_id: str
    abs_path: Path


@dataclass
class _MessageEntry:
    """Single message entry assembled from a Conversation row."""

    role: str  # "user" | "character" | "system"
    content: str
    created_at: datetime
    instruction_type: str | None
    images: list[_ImageRef]


@dataclass
class _TransformationEntry:
    """画像と心境を対応付けた変身履歴。"""

    history_id: str
    created_at: datetime
    instruction: str
    feeling_text: str
    main_image: _ImageRef | None


@dataclass
class _SessionBundle:
    """Aggregated data required to render an export."""

    session_id: str
    session_created_at: datetime
    character_name: str
    initial_image: _ImageRef | None
    messages: list[_MessageEntry]
    transformations: list[_TransformationEntry]


# ---------------------------------------------------------------------------
# Path resolution helpers
# ---------------------------------------------------------------------------


_HISTORY_IMAGE_URL_RE = re.compile(r"^/(?:api/)?history/images/([^/?#]+)")
_HISTORY_SURROUNDINGS_URL_RE = re.compile(r"^/(?:api/)?history/surroundings/([^/?#]+)")


def _resolve_history_image_path(history: HistoryORM) -> Path | None:
    """Resolve absolute path to a history image file."""
    if not history.image_path:
        return None
    candidate = settings.history_images_dir.parent / history.image_path
    if candidate.exists():
        return candidate
    return None


def _resolve_history_surroundings_path(history: HistoryORM) -> Path | None:
    """Resolve absolute path to a history surroundings image file."""
    if not history.surroundings_image_path:
        return None
    candidate = settings.history_images_dir.parent / history.surroundings_image_path
    if candidate.exists():
        return candidate
    return None


def _extract_history_id_from_url(url: str) -> tuple[str, str] | None:
    """Return (kind, history_id) where kind is 'image' or 'surroundings'."""
    if not url:
        return None
    match = _HISTORY_IMAGE_URL_RE.match(url)
    if match:
        return ("image", match.group(1))
    match = _HISTORY_SURROUNDINGS_URL_RE.match(url)
    if match:
        return ("surroundings", match.group(1))
    return None


# ---------------------------------------------------------------------------
# Image processing helpers
# ---------------------------------------------------------------------------


def _load_resized_jpeg(path: Path) -> bytes:
    """Load an image, resize so the longest side <= _MAX_IMAGE_SIDE, return JPEG bytes."""
    with Image.open(path) as img:
        img = img.convert("RGB")
        width, height = img.size
        longest = max(width, height)
        if longest > _MAX_IMAGE_SIDE:
            scale = _MAX_IMAGE_SIDE / float(longest)
            new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            img = img.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
        return buf.getvalue()


def _to_data_uri(jpeg_bytes: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")


def _resolve_self_display_name(self_profile_json: str | None) -> str:
    """自分自身プロフィールから表示名を取得する。"""
    if not self_profile_json:
        return "主人公"
    try:
        profile = json.loads(self_profile_json)
    except (json.JSONDecodeError, TypeError):
        return "主人公"
    if not isinstance(profile, dict):
        return "主人公"
    display_name = profile.get("display_name")
    if not isinstance(display_name, str) or not display_name.strip():
        return "主人公"
    return display_name.strip()


# ---------------------------------------------------------------------------
# Bundle assembly
# ---------------------------------------------------------------------------


async def _load_session_bundle(session_id: str) -> _SessionBundle | None:
    """Load session, history, and conversation data needed for export."""
    async with async_session_factory() as db:
        session_row = (
            (await db.execute(select(SessionORM).where(SessionORM.id == session_id)))
            .scalars()
            .first()
        )
        if session_row is None:
            return None

        history_rows = (
            (
                await db.execute(
                    select(HistoryORM)
                    .where(HistoryORM.session_id == session_id)
                    .order_by(HistoryORM.created_at.asc(), HistoryORM.id.asc())
                )
            )
            .scalars()
            .all()
        )
        history_by_id: dict[str, HistoryORM] = {h.id: h for h in history_rows}

        conv_rows = (
            (
                await db.execute(
                    select(ConversationORM)
                    .where(ConversationORM.session_id == session_id)
                    .order_by(
                        ConversationORM.created_at.asc(), ConversationORM.id.asc()
                    )
                )
            )
            .scalars()
            .all()
        )

        character_id = session_row.character_id
        session_created_at = session_row.created_at
        current_image_path = session_row.current_image_path
        is_self_mode = bool(session_row.self_mode)
        self_profile_json: str | None = None
        if is_self_mode:
            self_profile_json = (
                await db.execute(
                    select(UserORM.self_profile_json).where(
                        UserORM.id == session_row.user_id
                    )
                )
            ).scalar_one_or_none()

    # Resolve initial character image (preset only; custom uploads skipped here
    # but a fallback to the session's stored image is attempted below).
    character_name = "Character"
    initial_image: _ImageRef | None = None
    if character_id:
        try:
            manager = CharacterManager()
            char = manager.get_by_id(character_id)
            if char is not None:
                character_name = char.name
                image_path = BASE_DIR / char.image_path
                if image_path.exists():
                    initial_image = _ImageRef(asset_id="initial", abs_path=image_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to resolve preset character image: %s", exc)

    if is_self_mode:
        character_name = _resolve_self_display_name(self_profile_json)

    if initial_image is None and current_image_path:
        # Custom upload fallback: try data/ relative, then BASE_DIR relative.
        for candidate in (
            settings.history_images_dir.parent / current_image_path,
            BASE_DIR / current_image_path,
        ):
            if candidate.exists():
                initial_image = _ImageRef(asset_id="initial", abs_path=candidate)
                break

    # Assemble messages from BOTH History (transformation events) and Conversation
    # (chat/action/etc.). FE constructs ChatMessage[] from these two sources
    # combined and sorted chronologically, so we mirror that behavior here.
    used_history_ids: set[str] = set()
    messages: list[_MessageEntry] = []
    transformations: list[_TransformationEntry] = []

    # History-derived messages: per History row, emit a user instruction and a
    # character feeling message with the resulting image(s).
    for hist in history_rows:
        instruction_type = hist.instruction_type or "dress_up"
        messages.append(
            _MessageEntry(
                role="user",
                content=hist.instruction or "",
                created_at=hist.created_at,
                instruction_type=instruction_type,
                images=[],
            )
        )

        feeling_text = (hist.feeling_text or "").strip()
        skip_feeling = not feeling_text or feeling_text == "(画質改善)"
        display_feeling_text = "" if skip_feeling else feeling_text
        feeling_content = "" if skip_feeling else f"💭 {display_feeling_text}"

        hist_images: list[_ImageRef] = []
        main = _resolve_history_image_path(hist)
        main_ref: _ImageRef | None = None
        if main is not None and hist.id not in used_history_ids:
            main_ref = _ImageRef(asset_id=f"hist_{hist.id}", abs_path=main)
            hist_images.append(main_ref)
            used_history_ids.add(hist.id)
        sur = _resolve_history_surroundings_path(hist)
        if sur is not None:
            hist_images.append(_ImageRef(asset_id=f"sur_{hist.id}", abs_path=sur))

        transformations.append(
            _TransformationEntry(
                history_id=hist.id,
                created_at=hist.created_at,
                instruction=(hist.instruction or "").strip(),
                feeling_text=display_feeling_text,
                main_image=main_ref,
            )
        )

        # Always emit a character message (even if feeling text is missing) so
        # that the image still appears in the export.
        if feeling_content or hist_images:
            messages.append(
                _MessageEntry(
                    role="character",
                    content=feeling_content,
                    created_at=hist.created_at,
                    instruction_type=None,
                    images=hist_images,
                )
            )

    # Conversation-derived messages (chat/action/reality_alter not in History).
    for conv in conv_rows:
        images: list[_ImageRef] = []
        if conv.related_history_id and conv.related_history_id in history_by_id:
            hist = history_by_id[conv.related_history_id]
            main = _resolve_history_image_path(hist)
            if main is not None and hist.id not in used_history_ids:
                images.append(_ImageRef(asset_id=f"hist_{hist.id}", abs_path=main))
                used_history_ids.add(hist.id)
            sur = _resolve_history_surroundings_path(hist)
            if sur is not None:
                asset = f"sur_{hist.id}"
                if all(i.asset_id != asset for i in images):
                    images.append(_ImageRef(asset_id=asset, abs_path=sur))

        if conv.attached_image_url:
            parsed = _extract_history_id_from_url(conv.attached_image_url)
            if parsed is not None:
                kind, hid = parsed
                hist = history_by_id.get(hid)
                if hist is not None:
                    if kind == "image":
                        main = _resolve_history_image_path(hist)
                        if main is not None and hid not in used_history_ids:
                            images.append(
                                _ImageRef(asset_id=f"hist_{hid}", abs_path=main)
                            )
                            used_history_ids.add(hid)
                    else:
                        sur = _resolve_history_surroundings_path(hist)
                        if sur is not None:
                            asset = f"sur_{hid}"
                            if all(i.asset_id != asset for i in images):
                                images.append(_ImageRef(asset_id=asset, abs_path=sur))

        messages.append(
            _MessageEntry(
                role=conv.role,
                content=conv.content or "",
                created_at=conv.created_at,
                instruction_type=conv.instruction_type,
                images=images,
            )
        )

    # Stable chronological sort. For same-timestamp ties, prefer user before
    # character before system so a transformation instruction comes before its
    # resulting feeling text.
    role_order = {"user": 0, "character": 1, "system": 2}
    messages.sort(key=lambda m: (m.created_at, role_order.get(m.role, 9)))

    return _SessionBundle(
        session_id=session_id,
        session_created_at=session_created_at,
        character_name=character_name,
        initial_image=initial_image,
        messages=messages,
        transformations=transformations,
    )


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------


def _format_role_label(role: str, character_name: str) -> str:
    if role == "user":
        return "You"
    if role == "character":
        return character_name
    return "System"


async def build_markdown_export(session_id: str) -> tuple[bytes, str]:
    """Build Markdown export (.md) with base64-embedded JPEG images.

    Returns:
        (file bytes, suggested filename)
    Raises:
        LookupError: if the session is not found.
    """
    bundle = await _load_session_bundle(session_id)
    if bundle is None:
        raise LookupError(f"Session not found: {session_id}")

    lines: list[str] = []
    date_str = bundle.session_created_at.strftime("%Y-%m-%d")
    lines.append(f"# {bundle.character_name} — {date_str}")
    lines.append("")
    lines.append(f"- Session: `{bundle.session_id}`")
    lines.append(f"- Messages: {len(bundle.messages)}")
    lines.append("- Exported at: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("")

    if bundle.initial_image is not None:
        try:
            jpeg = _load_resized_jpeg(bundle.initial_image.abs_path)
            lines.append(f"![{bundle.character_name}]({_to_data_uri(jpeg)})")
            lines.append("")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to embed initial image: %s", exc)

    lines.append("---")
    lines.append("")

    for msg in bundle.messages:
        role_label = _format_role_label(msg.role, bundle.character_name)
        ts = msg.created_at.strftime("%H:%M:%S")
        type_suffix = f" [{msg.instruction_type}]" if msg.instruction_type else ""
        lines.append(f"### {role_label}{type_suffix} — {ts}")
        lines.append("")
        lines.append(msg.content)
        lines.append("")
        for img_ref in msg.images:
            try:
                jpeg = _load_resized_jpeg(img_ref.abs_path)
                lines.append(f"![]({_to_data_uri(jpeg)})")
                lines.append("")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to embed image %s: %s", img_ref.asset_id, exc)

    content = "\n".join(lines).encode("utf-8")
    filename = f"chat_{date_str}_{bundle.session_id[:8]}.md"
    return content, filename


# ---------------------------------------------------------------------------
# Novel HTML zip export
# ---------------------------------------------------------------------------


def _render_message_html(
    msg: _MessageEntry,
    character_name: str,
    asset_dir_rel: str,
) -> str:
    """Render a single message as HTML markup."""
    if msg.role == "user":
        side = "right"
        speaker = "You"
    elif msg.role == "character":
        side = "left"
        speaker = character_name
    else:
        side = "system"
        speaker = "System"

    safe_speaker = html.escape(speaker)
    safe_content = html.escape(msg.content).replace("\n", "<br>")
    ts = html.escape(msg.created_at.strftime("%Y-%m-%d %H:%M"))
    type_badge = ""
    if msg.instruction_type:
        type_badge = (
            f'<span class="bubble__type">{html.escape(msg.instruction_type)}</span>'
        )

    parts: list[str] = []
    parts.append(f'<div class="message message--{side}">')
    parts.append(
        f'  <div class="message__meta">{safe_speaker} · {ts}{type_badge}</div>'
    )
    parts.append(f'  <div class="bubble">{safe_content}</div>')
    parts.append("</div>")

    for img_ref in msg.images:
        rel = f"{asset_dir_rel}/{img_ref.asset_id}.jpg"
        parts.append(
            f'<figure class="char-image char-image--{side}">'
            f'<img src="{html.escape(rel)}" alt="" loading="lazy">'
            "</figure>"
        )

    return "\n".join(parts)


def _render_transformation_html(
    entry: _TransformationEntry,
    character_name: str,
    asset_dir_rel: str,
) -> str:
    """画像と心境を左右に並べる履歴カードを描画する。"""
    if entry.main_image is None:
        return ""

    safe_name = html.escape(character_name)
    safe_instruction = html.escape(entry.instruction or "指示内容はありません").replace(
        "\n", "<br>"
    )
    safe_feeling = html.escape(
        entry.feeling_text or "心境テキストはありません"
    ).replace("\n", "<br>")
    timestamp = html.escape(entry.created_at.strftime("%Y-%m-%d %H:%M"))
    image_rel = f"{asset_dir_rel}/{entry.main_image.asset_id}.jpg"

    return "\n".join(
        [
            f'<section class="paired-entry" data-history-id="{html.escape(entry.history_id)}">',
            '  <div class="paired-entry__instruction">',
            '    <span class="paired-entry__instruction-label">指示</span>',
            f"    <p>{safe_instruction}</p>",
            "  </div>",
            f'<article class="paired-card" data-history-id="{html.escape(entry.history_id)}">',
            '  <figure class="paired-card__image">',
            f'    <img src="{html.escape(image_rel)}" alt="{safe_name}" loading="lazy">',
            "  </figure>",
            '  <div class="paired-card__content">',
            f'    <div class="paired-card__meta">{safe_name} · {timestamp}</div>',
            f'    <div class="paired-card__feeling">{safe_feeling}</div>',
            "  </div>",
            "</article>",
            "</section>",
        ]
    )


async def build_novel_html_zip(session_id: str) -> tuple[bytes, str]:
    """Build novel-style HTML packaged as a zip archive.

    Returns:
        (zip bytes, suggested filename)
    Raises:
        LookupError: if the session is not found.
    """
    bundle = await _load_session_bundle(session_id)
    if bundle is None:
        raise LookupError(f"Session not found: {session_id}")

    if (
        not _NOVEL_HTML_TEMPLATE.exists()
        or not _NOVEL_CSS.exists()
        or not _NOVEL_JS.exists()
    ):
        raise RuntimeError("Novel HTML template files are missing")

    template = _NOVEL_HTML_TEMPLATE.read_text(encoding="utf-8")
    css_content = _NOVEL_CSS.read_text(encoding="utf-8")
    js_content = _NOVEL_JS.read_text(encoding="utf-8")

    date_str = bundle.session_created_at.strftime("%Y-%m-%d")
    title = f"{bundle.character_name} - {date_str}"
    asset_dir_rel = "assets/images"

    # チャットビューを組み立てる。
    chat_body_parts: list[str] = []
    if bundle.initial_image is not None:
        chat_body_parts.append(
            '<figure class="char-image char-image--cover">'
            f'<img src="{asset_dir_rel}/initial.jpg" alt="" loading="lazy">'
            f"<figcaption>{html.escape(bundle.character_name)}</figcaption>"
            "</figure>"
        )
    for msg in bundle.messages:
        chat_body_parts.append(
            _render_message_html(msg, bundle.character_name, asset_dir_rel)
        )

    # 画像と心境の対応ビューを組み立てる。
    paired_body_parts = [
        rendered_entry
        for entry in bundle.transformations
        if (
            rendered_entry := _render_transformation_html(
                entry, bundle.character_name, asset_dir_rel
            )
        )
    ]
    if not paired_body_parts:
        paired_body_parts.append(
            '<p class="paired-log__empty">画像付きの変身履歴はありません</p>'
        )

    rendered = (
        template.replace("{{TITLE}}", html.escape(title))
        .replace("{{HEADER}}", html.escape(title))
        .replace("{{MESSAGE_COUNT}}", str(len(bundle.messages)))
        .replace("{{CHAT_BODY}}", "\n".join(chat_body_parts))
        .replace("{{PAIRED_BODY}}", "\n".join(paired_body_parts))
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.html", rendered)
        zf.writestr("assets/style.css", css_content)
        zf.writestr("assets/view.js", js_content)

        seen_assets: set[str] = set()

        def _write_image(ref: _ImageRef) -> None:
            if ref.asset_id in seen_assets:
                return
            seen_assets.add(ref.asset_id)
            try:
                jpeg = _load_resized_jpeg(ref.abs_path)
                zf.writestr(f"assets/images/{ref.asset_id}.jpg", jpeg)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to write image %s: %s", ref.asset_id, exc)

        if bundle.initial_image is not None:
            _write_image(bundle.initial_image)
        for msg in bundle.messages:
            for img_ref in msg.images:
                _write_image(img_ref)

    filename = f"chat_{date_str}_{bundle.session_id[:8]}_novel.zip"
    return buf.getvalue(), filename
