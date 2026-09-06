"""キャラチャット(TSF シナリオを経由しないキャラクターとの会話)。

スレッド(拠点キャラ「セレナ」/ 過去セッション由来のキャラ)の永続化、
1 発言ごとの 判定 LLM → 調べ物 → 返答ストリーム → 保存 → (着替え) → (要約) の
編成、姿の差し替えと立ち絵の描き直しを担う。ルーターは SSE 化だけを行う。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, desc, func, select

from ..consts.character_chat import (
    BASE_APPEARANCE_DESCRIPTION,
    BASE_CHARACTER_KEY,
    BASE_CHARACTER_NAME,
    BASE_CHARACTER_PRONOUN,
    BASE_CLOTHING_TAGS,
    BASE_IDENTITY_TAGS,
    BASE_PORTRAIT_FILENAME,
    CHARACTER_CHAT_KIND_BASE,
    CHARACTER_CHAT_KIND_SESSION,
    HISTORY_MESSAGES,
    MESSAGE_MAX,
    PERSONA_TIMELINE_MAX,
    PLANNER_RECENT_MESSAGES,
    REPLY_MAX,
    SUMMARY_EVERY,
    SUMMARY_MAX_CHARS,
    THREAD_MESSAGE_LIMIT,
    base_portrait_dir,
)
from ..consts.companion_avatar import parse_talk_header
from ..consts.language import normalize_language
from ..consts.novelai_models import resolve_user_image_model
from ..databases.base import async_session_factory
from ..databases.models import CharacterChatMessage, CharacterChatThread, User
from ..settings.config import settings
from .character_chat_lookups import run_lookups, session_candidates
from .character_chat_models import (
    CharacterChatAppearanceOutput,
    CharacterChatPlan,
    empty_plan,
)
from .character_chat_prompts import (
    appearance_change_system_prompt,
    appearance_change_user_prompt,
    base_persona_block,
    lookup_block,
    memory_block,
    planner_system_prompt,
    planner_user_prompt,
    reply_system_prompt,
    session_persona_block,
    summary_system_prompt,
    summary_user_prompt,
)
from .conversation import get_stage_display_name, get_stage_name
from .cost_tracker import begin_cost_tracking, record_cost
from .image_paths import resolve_stored_image_path
from .llm_json import StructuredOutputError, generate_validated, strip_code_fence
from .llm_service import llm_service
from .portrait_generation import PortraitGenerationError, generate_portrait_bytes
from .providers import Provider, resolve_image_provider, resolve_text_provider
from .session import DEFAULT_USER_ID, session_store
from .settings_service import settings_service
from .source_snapshot import (
    SourceSnapshotError,
    build_source_snapshot,
    identity_tags_only,
    resolve_session_identity,
)
from .summary_service import summary_service

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_GENERATED_PORTRAIT_PREFIX = "portrait-"
_FALLBACK_NAME = {"ja": "キャラクター", "en": "Character"}
_FALLBACK_PRONOUN = {"ja": "僕", "en": "I"}


class CharacterChatError(RuntimeError):
    """キャラチャット処理の利用者向けエラー。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _json_load(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def _to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _lang(language: str | None) -> str:
    return "en" if normalize_language(language) == "en" else "ja"


def normalize_chat_input(text: str) -> str:
    """発言を空白畳み込みと上限で正規化する。"""
    return " ".join(str(text or "").split()).strip()[:MESSAGE_MAX]


def normalize_chat_reply(text: str, name: str) -> str:
    """LLM の返答から名前プレフィックス・全体を囲む括弧・ヘッダ行を剥がして上限で切る。

    adventure_romance.normalize_talk_reply と同じ規則だが、セレナがアプリの
    説明をする場面もあるため上限は REPLY_MAX にする。
    """
    reply = strip_code_fence(str(text or ""))
    _, _, reply = parse_talk_header(reply)
    reply = reply.strip()
    clean_name = str(name or "").strip()
    if clean_name:
        prefix = re.compile(rf"^\s*{re.escape(clean_name)}\s*[「『:：]\s*")
        reply = prefix.sub("", reply, count=1)
    reply = reply.strip()
    if reply[:1] in "「『" and reply[-1:] in "」』":
        reply = reply[1:-1].strip()
    elif reply[-1:] in "」』" and reply.count("「") + reply.count("『") < reply.count(
        "」"
    ) + reply.count("』"):
        reply = reply[:-1].strip()
    # 段落は保つ(改行 2 つ以上は 1 つに畳む)
    reply = re.sub(r"[ \t]+", " ", reply)
    reply = re.sub(r"\n{3,}", "\n\n", reply).strip()
    return reply[:REPLY_MAX].strip()


async def _generate_text(
    system_prompt: str, user_prompt: str, *, text_model: str | None
) -> str:
    """設定プロバイダーでテキストを生成し、API 料金を集計へ加算する。"""
    result = await llm_service.generate_text(
        system_prompt,
        user_prompt,
        provider_override=resolve_text_provider(),
        novelai_model_override=text_model,
    )
    record_cost(getattr(result, "cost_usd", None))
    return str(getattr(result, "content", "") or "")


_APPEARANCE_KEYS = (
    "identity_tags",
    "clothing_tags",
    "description",
    "portrait_kind",
    "source",
)


def _with_initial(
    appearance: dict[str, Any], *, portrait_path: str | None
) -> dict[str, Any]:
    """作成時点の姿を appearance["initial"] に控える(「最初の姿に戻す」用)。"""
    initial = {key: appearance.get(key) for key in _APPEARANCE_KEYS}
    initial["portrait_path"] = portrait_path
    return {**appearance, "initial": initial}


class CharacterChatService:
    def __init__(self) -> None:
        self._thread_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._images_dir = settings.history_images_dir.parent / "character_chat_images"

    # ------------------------------------------------------------------
    # 画像パス
    # ------------------------------------------------------------------

    def _thread_dir(self, thread_id: str) -> Path:
        return self._images_dir / thread_id

    def _stored_path(self, thread_id: str, filename: str) -> str:
        """DB に保存する data 相対パス(resolve_stored_image_path で解決できる形)。"""
        return f"character_chat_images/{thread_id}/{filename}"

    @staticmethod
    def image_url(thread_id: str, filename: str) -> str:
        return f"/character-chat/images/{thread_id}/{filename}"

    def _portrait_file(self, thread: CharacterChatThread) -> Path | None:
        if thread.portrait_path:
            # 通常はスレッドディレクトリ直下。旧データや移設時は data 相対で解決する
            local = self._thread_dir(thread.id) / Path(thread.portrait_path).name
            if local.is_file():
                return local
            path = resolve_stored_image_path(thread.portrait_path)
            if path is not None and path.is_file():
                return path
            return None
        if thread.kind == CHARACTER_CHAT_KIND_BASE:
            bundled = base_portrait_dir() / BASE_PORTRAIT_FILENAME
            if bundled.is_file():
                return bundled
        return None

    def image_file(self, thread_id: str, filename: str) -> Path:
        """配信する画像の実ファイル。パス区切りは name だけに落として無害化する。"""
        name = Path(filename).name
        if not name or Path(thread_id).name != thread_id:
            raise CharacterChatError("image_not_found", "画像が見つかりません")
        if name == BASE_PORTRAIT_FILENAME:
            bundled = base_portrait_dir() / name
            if bundled.is_file():
                return bundled
        candidate = self._thread_dir(thread_id) / name
        if candidate.is_file():
            return candidate
        raise CharacterChatError("image_not_found", "画像が見つかりません")

    def _copy_source_image(self, thread_id: str, source: Path) -> str:
        suffix = source.suffix.lower()
        if suffix not in _IMAGE_SUFFIXES:
            suffix = ".png"
        directory = self._thread_dir(thread_id)
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"source-{uuid.uuid4().hex[:8]}{suffix}"
        shutil.copyfile(source, directory / filename)
        return filename

    def _remove_generated_portrait(self, thread: CharacterChatThread) -> None:
        """描き直し前の生成立ち絵を消す(コピーした元画像 source-*.png は残す)。"""
        if not thread.portrait_path:
            return
        name = Path(thread.portrait_path).name
        if not name.startswith(_GENERATED_PORTRAIT_PREFIX):
            return
        path = self._thread_dir(thread.id) / name
        if path.is_file():
            path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # 直列化
    # ------------------------------------------------------------------

    @staticmethod
    async def _ensure_user(db) -> None:
        """FK 先のユーザー行を確保する(設定を一度も保存していない環境向け)。"""
        if await db.get(User, DEFAULT_USER_ID) is None:
            db.add(User(id=DEFAULT_USER_ID))
            await db.flush()

    async def _get_thread_orm(self, db, thread_id: str) -> CharacterChatThread:
        thread = (
            await db.execute(
                select(CharacterChatThread).where(
                    CharacterChatThread.id == thread_id,
                    CharacterChatThread.user_id == DEFAULT_USER_ID,
                )
            )
        ).scalar_one_or_none()
        if thread is None:
            raise CharacterChatError(
                "thread_not_found", "キャラチャットが見つかりません"
            )
        return thread

    async def _load_messages(
        self, db, thread_id: str, *, limit: int
    ) -> list[CharacterChatMessage]:
        rows = (
            (
                await db.execute(
                    select(CharacterChatMessage)
                    .where(CharacterChatMessage.thread_id == thread_id)
                    .order_by(
                        desc(CharacterChatMessage.created_at),
                        desc(CharacterChatMessage.id),
                    )
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return list(reversed(rows))

    async def _message_count(self, db, thread_id: str) -> int:
        return (
            await db.execute(
                select(func.count())
                .select_from(CharacterChatMessage)
                .where(CharacterChatMessage.thread_id == thread_id)
            )
        ).scalar_one() or 0

    def _message_to_dict(self, message: CharacterChatMessage) -> dict[str, Any]:
        return {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "meta": _json_load(message.meta_json, {}),
            "created_at": _to_iso(message.created_at),
        }

    @staticmethod
    def _public_persona(thread: CharacterChatThread) -> dict[str, Any]:
        """右パネルに出す人物設定(セッション由来のみ。LLM 向けの生データは出さない)。"""
        if thread.kind != CHARACTER_CHAT_KIND_SESSION:
            return {}
        persona = _json_load(thread.persona_json, {})
        stats = persona.get("stats") or {}
        transformation_count = int(persona.get("transformation_count") or 0)
        bloom = int(stats.get("bloom") or 0)
        english = thread.language == "en"
        if transformation_count == 0:
            stage = "pre_transform"
            stage_label = "Not yet transformed" if english else "未変身"
        else:
            stage = get_stage_name(bloom)
            stage_label = stage if english else get_stage_display_name(stage)
        return {
            "character_name": str(persona.get("character_name") or thread.name),
            "session_updated_at": persona.get("session_updated_at"),
            "summary_title": str(persona.get("summary_title") or ""),
            "summary_text": str(persona.get("summary_text") or ""),
            "stage": stage,
            "stage_label": stage_label,
            "transformation_count": transformation_count,
            "stats": {
                "bloom": int(stats.get("bloom") or 0),
                "shame": int(stats.get("shame") or 0),
                "adaptation": int(stats.get("adaptation") or 0),
            },
            "attributes": [str(item) for item in persona.get("attributes") or []],
            "timeline": [
                {
                    "type": str(item.get("type") or ""),
                    "text": str(item.get("text") or ""),
                }
                for item in persona.get("timeline") or []
                if isinstance(item, dict)
            ],
            "outfit_description": str(persona.get("outfit_description") or ""),
            "play_memory_context": str(persona.get("play_memory_context") or ""),
            "self_mode": bool(persona.get("self_mode")),
        }

    def _initial_appearance(
        self, thread: CharacterChatThread, appearance: dict[str, Any]
    ) -> dict[str, Any] | None:
        """「最初の姿」。控えが無い旧スレッドは base なら既定値、session なら最古のコピー画像。"""
        initial = appearance.get("initial")
        if isinstance(initial, dict) and initial.get("identity_tags") is not None:
            return initial
        lang = _lang(thread.language)
        if thread.kind == CHARACTER_CHAT_KIND_BASE:
            return {
                "identity_tags": BASE_IDENTITY_TAGS,
                "clothing_tags": BASE_CLOTHING_TAGS,
                "description": BASE_APPEARANCE_DESCRIPTION[lang],
                "portrait_kind": "standing",
                "source": {"type": "base"},
                "portrait_path": None,
            }
        sources = sorted(
            self._thread_dir(thread.id).glob("source-*"),
            key=lambda item: item.stat().st_mtime,
        )
        if not sources:
            return None
        return {
            "identity_tags": str(appearance.get("identity_tags") or ""),
            "clothing_tags": str(appearance.get("clothing_tags") or ""),
            "description": "",
            "portrait_kind": "scene",
            "source": appearance.get("source") or {},
            "portrait_path": self._stored_path(thread.id, sources[0].name),
        }

    def _can_reset_appearance(
        self, thread: CharacterChatThread, appearance: dict[str, Any]
    ) -> bool:
        initial = self._initial_appearance(thread, appearance)
        if initial is None:
            return False
        current = {key: appearance.get(key) for key in _APPEARANCE_KEYS}
        wanted = {key: initial.get(key) for key in _APPEARANCE_KEYS}
        current_portrait = Path(str(thread.portrait_path or "")).name or None
        wanted_portrait = Path(str(initial.get("portrait_path") or "")).name or None
        return current != wanted or current_portrait != wanted_portrait

    async def reset_appearance(self, thread_id: str) -> dict[str, Any]:
        """姿を作成時点(同梱 PNG / コピーした元画像とそのタグ)へ戻す。画像生成はしない。"""
        async with self._thread_locks[thread_id], async_session_factory() as db:
            thread = await self._get_thread_orm(db, thread_id)
            appearance = _json_load(thread.appearance_json, {})
            initial = self._initial_appearance(thread, appearance)
            if initial is None:
                raise CharacterChatError(
                    "initial_appearance_missing", "最初の姿の記録がありません"
                )
            self._remove_generated_portrait(thread)
            for key in _APPEARANCE_KEYS:
                appearance[key] = initial.get(key)
            appearance["initial"] = initial
            thread.appearance_json = json.dumps(appearance, ensure_ascii=False)
            thread.portrait_path = initial.get("portrait_path") or None
            thread.updated_at = datetime.now()
            await db.commit()
            await db.refresh(thread)
            return await self._thread_payload(db, thread, with_messages=False, limit=1)

    def _thread_to_dict(
        self,
        thread: CharacterChatThread,
        *,
        message_count: int,
        last_message: CharacterChatMessage | None,
        messages: list[CharacterChatMessage] | None = None,
    ) -> dict[str, Any]:
        appearance = _json_load(thread.appearance_json, {})
        portrait = self._portrait_file(thread)
        payload: dict[str, Any] = {
            "id": thread.id,
            "kind": thread.kind,
            "name": thread.name,
            "pronoun": thread.pronoun,
            "portrait_url": self.image_url(thread.id, portrait.name)
            if portrait
            else None,
            "portrait_missing": portrait is None,
            "appearance": {
                "identity_tags": str(appearance.get("identity_tags") or ""),
                "clothing_tags": str(appearance.get("clothing_tags") or ""),
                "description": str(appearance.get("description") or ""),
                "portrait_kind": str(appearance.get("portrait_kind") or "scene"),
                "source": appearance.get("source") or {},
            },
            "persona": self._public_persona(thread),
            "can_reset_appearance": self._can_reset_appearance(thread, appearance),
            "summary_text": thread.summary_text,
            "message_count": int(message_count),
            "last_message": (
                {
                    "role": last_message.role,
                    "content": last_message.content[:120],
                    "created_at": _to_iso(last_message.created_at),
                }
                if last_message is not None
                else None
            ),
            "language": thread.language,
            "nsfw_mode": bool(thread.nsfw_mode),
            "created_at": _to_iso(thread.created_at),
            "updated_at": _to_iso(thread.updated_at),
        }
        if messages is not None:
            payload["messages"] = [self._message_to_dict(m) for m in messages]
        return payload

    async def _thread_payload(
        self, db, thread: CharacterChatThread, *, with_messages: bool, limit: int
    ) -> dict[str, Any]:
        count = await self._message_count(db, thread.id)
        messages = (
            await self._load_messages(db, thread.id, limit=limit)
            if with_messages or count
            else []
        )
        last_message = messages[-1] if messages else None
        return self._thread_to_dict(
            thread,
            message_count=count,
            last_message=last_message,
            messages=messages if with_messages else None,
        )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def list_threads(self) -> list[dict[str, Any]]:
        async with async_session_factory() as db:
            threads = (
                (
                    await db.execute(
                        select(CharacterChatThread)
                        .where(CharacterChatThread.user_id == DEFAULT_USER_ID)
                        .order_by(desc(CharacterChatThread.updated_at))
                    )
                )
                .scalars()
                .all()
            )
            payloads = []
            for thread in threads:
                count = await self._message_count(db, thread.id)
                last = await self._load_messages(db, thread.id, limit=1)
                payloads.append(
                    self._thread_to_dict(
                        thread,
                        message_count=count,
                        last_message=last[-1] if last else None,
                    )
                )
            return payloads

    async def get_thread(
        self,
        thread_id: str,
        *,
        with_messages: bool = True,
        limit: int = THREAD_MESSAGE_LIMIT,
    ) -> dict[str, Any]:
        async with async_session_factory() as db:
            thread = await self._get_thread_orm(db, thread_id)
            return await self._thread_payload(
                db, thread, with_messages=with_messages, limit=limit
            )

    async def get_or_create_base_thread(self) -> dict[str, Any]:
        """拠点キャラ(セレナ)のスレッドを返す。無ければ作る(ユーザーごとに 1 件)。"""
        user_settings = await session_store.get_user_settings()
        lang = _lang(user_settings.get("language"))
        async with async_session_factory() as db:
            existing = (
                (
                    await db.execute(
                        select(CharacterChatThread)
                        .where(
                            CharacterChatThread.user_id == DEFAULT_USER_ID,
                            CharacterChatThread.kind == CHARACTER_CHAT_KIND_BASE,
                        )
                        .order_by(CharacterChatThread.created_at)
                    )
                )
                .scalars()
                .first()
            )
            if existing is not None:
                return await self._thread_payload(
                    db, existing, with_messages=False, limit=1
                )
            now = datetime.now()
            await self._ensure_user(db)
            thread = CharacterChatThread(
                id=uuid.uuid4().hex,
                user_id=DEFAULT_USER_ID,
                kind=CHARACTER_CHAT_KIND_BASE,
                name=BASE_CHARACTER_NAME[lang],
                pronoun=BASE_CHARACTER_PRONOUN[lang],
                persona_json=json.dumps(
                    {"key": BASE_CHARACTER_KEY}, ensure_ascii=False
                ),
                appearance_json=json.dumps(
                    _with_initial(
                        {
                            "identity_tags": BASE_IDENTITY_TAGS,
                            "clothing_tags": BASE_CLOTHING_TAGS,
                            "description": BASE_APPEARANCE_DESCRIPTION[lang],
                            "portrait_kind": "standing",
                            "source": {"type": "base"},
                        },
                        portrait_path=None,
                    ),
                    ensure_ascii=False,
                ),
                portrait_path=None,
                language=lang,
                nsfw_mode=bool(user_settings.get("nsfw_mode")),
                created_at=now,
                updated_at=now,
            )
            db.add(thread)
            await db.commit()
            await db.refresh(thread)
            return await self._thread_payload(db, thread, with_messages=False, limit=1)

    async def create_session_thread(
        self,
        *,
        source_session_id: str | None,
        source_history_id: str | None,
        source_prompt_expander_entry_id: str | None = None,
    ) -> dict[str, Any]:
        """過去セッション(または Prompt Expander エントリ)の人物からスレッドを作る。

        人物設定は作成時点のスナップショット。ユーザーメモリだけは会話のたびに最新を読む。
        """
        try:
            (
                snapshot,
                image_path,
                appearance_tags,
                nsfw_mode,
            ) = await build_source_snapshot(
                source_session_id,
                source_history_id,
                source_prompt_expander_entry_id=source_prompt_expander_entry_id,
            )
        except SourceSnapshotError as exc:
            raise CharacterChatError(exc.code, str(exc)) from exc

        user_settings = await session_store.get_user_settings()
        lang = _lang(user_settings.get("language"))
        name, pronoun = _FALLBACK_NAME[lang], _FALLBACK_PRONOUN[lang]
        session = None
        transformation_count = 0
        play_memory_context = ""
        if source_session_id and not source_prompt_expander_entry_id:
            session = await session_store.get_session_by_id(source_session_id)
            if session is not None:
                name, pronoun = await resolve_session_identity(session)
                transformation_count = int(
                    getattr(session, "transformation_count", 0) or 0
                )
                if source_history_id:
                    # 履歴時点の変身回数は、その時点までの着替え・改変の件数で近似する
                    transformation_count = sum(
                        1
                        for item in snapshot.get("timeline") or []
                        if isinstance(item, dict)
                        and item.get("type") in ("dress_up", "reality_alter")
                    )
                try:
                    from .play_memory_service import play_memory_service

                    play_memory_context = (
                        await play_memory_service.build_context(
                            source_session_id, enabled=True, language=lang
                        )
                    ).strip()
                except Exception as exc:  # pragma: no cover - 補助情報
                    logger.warning(
                        "character chat play memory context failed: %s: %s",
                        type(exc).__name__,
                        exc,
                    )

        timeline = [
            item for item in (snapshot.get("timeline") or []) if isinstance(item, dict)
        ][-PERSONA_TIMELINE_MAX:]
        summary = (
            await summary_service.get_summary(source_session_id)
            if session is not None
            else None
        )
        persona = {
            "character_name": name,
            "pronoun": pronoun,
            "stats": snapshot.get("stats"),
            "transformation_count": transformation_count,
            "attributes": list(snapshot.get("attributes") or []),
            "timeline": timeline,
            "play_memory_context": play_memory_context,
            "outfit_description": str(snapshot.get("clothing") or ""),
            "nsfw_mode": bool(nsfw_mode),
            "self_mode": bool(getattr(session, "self_mode", False))
            if session
            else False,
            # セッションの概要(右パネルの表示用。作成時点の PlaySummary があればそれ)
            "session_updated_at": (
                _to_iso(getattr(session, "updated_at", None)) if session else None
            ),
            "summary_title": str((summary or {}).get("title") or ""),
            "summary_text": str((summary or {}).get("summary") or ""),
        }
        source = {
            "type": "prompt_expander" if source_prompt_expander_entry_id else "session",
            "session_id": source_session_id,
            "history_id": source_history_id,
            "entry_id": source_prompt_expander_entry_id,
        }
        thread_id = uuid.uuid4().hex
        filename = self._copy_source_image(thread_id, Path(image_path))
        appearance = _with_initial(
            {
                "identity_tags": identity_tags_only(appearance_tags) or appearance_tags,
                "clothing_tags": str(snapshot.get("clothing") or ""),
                "description": "",
                "portrait_kind": "scene",
                "source": source,
            },
            portrait_path=self._stored_path(thread_id, filename),
        )
        now = datetime.now()
        async with async_session_factory() as db:
            await self._ensure_user(db)
            thread = CharacterChatThread(
                id=thread_id,
                user_id=DEFAULT_USER_ID,
                kind=CHARACTER_CHAT_KIND_SESSION,
                name=name,
                pronoun=pronoun,
                persona_json=json.dumps(persona, ensure_ascii=False),
                appearance_json=json.dumps(appearance, ensure_ascii=False),
                portrait_path=self._stored_path(thread_id, filename),
                source_session_id=source_session_id if session else None,
                source_history_id=source_history_id if session else None,
                source_prompt_expander_entry_id=source_prompt_expander_entry_id,
                language=lang,
                nsfw_mode=bool(nsfw_mode),
                created_at=now,
                updated_at=now,
            )
            db.add(thread)
            await db.commit()
            await db.refresh(thread)
            return await self._thread_payload(db, thread, with_messages=False, limit=1)

    async def delete_thread(self, thread_id: str) -> None:
        async with self._thread_locks[thread_id]:
            async with async_session_factory() as db:
                await self._get_thread_orm(db, thread_id)
                await db.execute(
                    delete(CharacterChatMessage).where(
                        CharacterChatMessage.thread_id == thread_id
                    )
                )
                await db.execute(
                    delete(CharacterChatThread).where(
                        CharacterChatThread.id == thread_id
                    )
                )
                await db.commit()
            shutil.rmtree(self._thread_dir(thread_id), ignore_errors=True)

    # ------------------------------------------------------------------
    # 姿
    # ------------------------------------------------------------------

    async def set_appearance_from_source(
        self,
        thread_id: str,
        *,
        source_session_id: str | None,
        source_history_id: str | None,
        source_prompt_expander_entry_id: str | None = None,
    ) -> dict[str, Any]:
        """姿(画像と外見タグ)を別の素材に差し替える。名前・人物設定は変えない。"""
        try:
            snapshot, image_path, appearance_tags, _ = await build_source_snapshot(
                source_session_id,
                source_history_id,
                source_prompt_expander_entry_id=source_prompt_expander_entry_id,
            )
        except SourceSnapshotError as exc:
            raise CharacterChatError(exc.code, str(exc)) from exc
        async with self._thread_locks[thread_id], async_session_factory() as db:
            thread = await self._get_thread_orm(db, thread_id)
            self._remove_generated_portrait(thread)
            filename = self._copy_source_image(thread.id, Path(image_path))
            appearance = _json_load(thread.appearance_json, {})
            appearance.update(
                {
                    "identity_tags": identity_tags_only(appearance_tags)
                    or appearance_tags,
                    "clothing_tags": str(snapshot.get("clothing") or ""),
                    "description": "",
                    "portrait_kind": "scene",
                    "source": {
                        "type": "prompt_expander"
                        if source_prompt_expander_entry_id
                        else "session",
                        "session_id": source_session_id,
                        "history_id": source_history_id,
                        "entry_id": source_prompt_expander_entry_id,
                    },
                }
            )
            thread.appearance_json = json.dumps(appearance, ensure_ascii=False)
            thread.portrait_path = self._stored_path(thread.id, filename)
            thread.updated_at = datetime.now()
            await db.commit()
            await db.refresh(thread)
            return await self._thread_payload(db, thread, with_messages=False, limit=1)

    async def _generate_portrait(
        self,
        thread: CharacterChatThread,
        appearance: dict[str, Any],
        *,
        nsfw_mode: bool,
        user_settings: dict[str, Any],
    ) -> str:
        """外見タグから立ち絵を 1 枚描き、スレッドディレクトリへ保存してファイル名を返す。"""
        provider = resolve_image_provider()
        image_model = (
            resolve_user_image_model(user_settings, nsfw_mode)
            if provider == Provider.NOVELAI
            else None
        )
        reference = self._portrait_file(thread)
        reference_bytes = reference.read_bytes() if reference is not None else None
        tags = ", ".join(
            part
            for part in (
                str(appearance.get("identity_tags") or "").strip(),
                str(appearance.get("clothing_tags") or "").strip(),
            )
            if part
        )
        if not tags:
            raise CharacterChatError("portrait_unavailable", "外見タグがありません")
        try:
            data = await generate_portrait_bytes(
                tags=tags,
                nsfw_mode=nsfw_mode,
                provider=provider,
                image_model=image_model,
                reference_bytes=reference_bytes,
            )
        except PortraitGenerationError as exc:
            raise CharacterChatError(exc.code, str(exc)) from exc
        directory = self._thread_dir(thread.id)
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{_GENERATED_PORTRAIT_PREFIX}{uuid.uuid4().hex[:8]}.png"
        (directory / filename).write_bytes(data)
        return filename

    async def _apply_portrait(
        self,
        thread_id: str,
        appearance: dict[str, Any],
        *,
        nsfw_mode: bool,
        user_settings: dict[str, Any],
        message_id: str | None = None,
    ) -> dict[str, Any]:
        """立ち絵を描いて thread に反映し、portrait_image イベントの data を返す。"""
        async with async_session_factory() as db:
            thread = await self._get_thread_orm(db, thread_id)
            filename = await self._generate_portrait(
                thread, appearance, nsfw_mode=nsfw_mode, user_settings=user_settings
            )
            self._remove_generated_portrait(thread)
            appearance = {**appearance, "portrait_kind": "standing"}
            thread.appearance_json = json.dumps(appearance, ensure_ascii=False)
            thread.portrait_path = self._stored_path(thread.id, filename)
            thread.updated_at = datetime.now()
            if message_id:
                message = await db.get(CharacterChatMessage, message_id)
                if message is not None:
                    meta = _json_load(message.meta_json, {})
                    meta["portrait_filename"] = filename
                    message.meta_json = json.dumps(meta, ensure_ascii=False)
            await db.commit()
            await db.refresh(thread)
            payload = self._thread_to_dict(thread, message_count=0, last_message=None)
        return {
            "image_url": payload["portrait_url"],
            "appearance": payload["appearance"],
        }

    async def stream_portrait_regeneration(
        self, thread_id: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """現在の外見タグから立ち絵を描き直す(同梱 PNG が無いセレナの初回生成も兼ねる)。"""
        tracker = begin_cost_tracking()
        async with self._thread_locks[thread_id]:
            async with async_session_factory() as db:
                thread = await self._get_thread_orm(db, thread_id)
                appearance = _json_load(thread.appearance_json, {})
                kind = thread.kind
                thread_nsfw = bool(thread.nsfw_mode)
            user_settings = await session_store.get_user_settings()
            nsfw_mode = (
                thread_nsfw
                if kind == CHARACTER_CHAT_KIND_SESSION
                else bool(user_settings.get("nsfw_mode"))
            )
            yield {"event": "status", "data": {"phase": "portrait"}}
            data = await self._apply_portrait(
                thread_id, appearance, nsfw_mode=nsfw_mode, user_settings=user_settings
            )
            yield {"event": "portrait_image", "data": data}
            if tracker.total_usd > 0:
                yield {"event": "cost", "data": {"cost_usd": tracker.total_usd}}
            yield {"event": "complete", "data": {}}

    # ------------------------------------------------------------------
    # 会話
    # ------------------------------------------------------------------

    async def _plan(
        self,
        *,
        kind: str,
        name: str,
        recent: list[CharacterChatMessage],
        message: str,
        text_model: str | None,
        language: str,
    ) -> CharacterChatPlan:
        """判定 LLM。失敗しても返答は止めず、空の計画に倒す。"""
        try:
            candidates = await session_candidates(language)
        except Exception as exc:
            logger.warning(
                "character chat session candidates failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            candidates = []
        recent_messages = [
            {
                "role": "user" if item.role == "user" else "character",
                "content": item.content[:300],
            }
            for item in recent[-PLANNER_RECENT_MESSAGES:]
        ]
        try:
            return await generate_validated(
                CharacterChatPlan,
                generate=lambda system, user: _generate_text(
                    system, user, text_model=text_model
                ),
                system_prompt=planner_system_prompt(language),
                user_prompt=planner_user_prompt(
                    kind=kind,
                    character_name=name,
                    recent_messages=recent_messages,
                    session_candidates=candidates,
                    message=message,
                ),
            )
        except (StructuredOutputError, Exception) as exc:
            logger.warning(
                "character chat planner failed; replying without lookups: %s: %s",
                type(exc).__name__,
                exc,
            )
            return empty_plan()

    async def _resolve_appearance_change(
        self,
        appearance: dict[str, Any],
        request: str,
        *,
        text_model: str | None,
        language: str,
    ) -> dict[str, Any]:
        """着替え要求を外見タグへ写す。identity は明示されない限り据え置く。"""
        identity = str(appearance.get("identity_tags") or "")
        clothing = str(appearance.get("clothing_tags") or "")
        output = await generate_validated(
            CharacterChatAppearanceOutput,
            generate=lambda system, user: _generate_text(
                system, user, text_model=text_model
            ),
            system_prompt=appearance_change_system_prompt(language),
            user_prompt=appearance_change_user_prompt(
                identity_tags=identity, clothing_tags=clothing, request=request
            ),
        )
        return {
            **appearance,
            "identity_tags": output.identity_tags or identity,
            "clothing_tags": output.clothing_tags or clothing,
            "description": output.description
            or str(appearance.get("description") or ""),
        }

    def _build_system_prompt(
        self,
        thread: CharacterChatThread,
        *,
        language: str,
        memory_text: str | None,
        lookup_text: str,
        appearance_change_request: str | None,
    ) -> str:
        persona = _json_load(thread.persona_json, {})
        appearance = _json_load(thread.appearance_json, {})
        if thread.kind == CHARACTER_CHAT_KIND_BASE:
            persona_text = base_persona_block(language)
        else:
            persona_text = session_persona_block(persona, language)
        description = str(appearance.get("description") or "").strip()
        if not description:
            tags = ", ".join(
                part
                for part in (
                    str(appearance.get("identity_tags") or "").strip(),
                    str(appearance.get("clothing_tags") or "").strip(),
                )
                if part
            )
            description = tags
        return reply_system_prompt(
            language,
            name=thread.name,
            pronoun=thread.pronoun,
            persona_block=persona_text,
            memory_block_text=memory_block(memory_text, language),
            summary_text=thread.summary_text,
            lookup_block_text=lookup_block(lookup_text, language),
            appearance_description=description,
            appearance_change_request=appearance_change_request,
        )

    async def _persist_messages(
        self,
        thread_id: str,
        *,
        user_text: str,
        reply_text: str,
        meta: dict[str, Any],
    ) -> tuple[CharacterChatMessage, CharacterChatMessage]:
        now = datetime.now()
        user_message = CharacterChatMessage(
            id=uuid.uuid4().hex,
            thread_id=thread_id,
            role="user",
            content=user_text,
            meta_json=None,
            created_at=now,
        )
        character_message = CharacterChatMessage(
            id=uuid.uuid4().hex,
            thread_id=thread_id,
            role="character",
            content=reply_text,
            meta_json=json.dumps(meta, ensure_ascii=False),
            created_at=now + timedelta(milliseconds=1),
        )
        async with async_session_factory() as db:
            thread = await self._get_thread_orm(db, thread_id)
            db.add(user_message)
            db.add(character_message)
            thread.updated_at = now + timedelta(milliseconds=1)
            await db.commit()
            await db.refresh(user_message)
            await db.refresh(character_message)
        return user_message, character_message

    async def _update_summary(
        self, thread_id: str, *, language: str, text_model: str | None
    ) -> None:
        async with async_session_factory() as db:
            thread = await self._get_thread_orm(db, thread_id)
            messages = await self._load_messages(
                db, thread_id, limit=THREAD_MESSAGE_LIMIT
            )
            summarized = int(thread.summary_message_count or 0)
            fresh = messages[summarized:] if summarized < len(messages) else []
            if not fresh:
                return
            text = await _generate_text(
                summary_system_prompt(language),
                summary_user_prompt(
                    previous=thread.summary_text,
                    messages=[{"role": m.role, "content": m.content} for m in fresh],
                    character_name=thread.name,
                ),
                text_model=text_model,
            )
            text = text.strip()
            if not text:
                return
            thread.summary_text = text[:SUMMARY_MAX_CHARS]
            thread.summary_message_count = len(messages)
            await db.commit()

    async def stream_message(
        self, *, thread_id: str, content: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """1 発言の処理。

        Yields:
            status{phase: plan|reply|portrait|memory} / chat_chunk{chunk} /
            chat_done{user_message, character_message, thread} /
            portrait_image{image_url, appearance} / portrait_error{code, message} /
            cost{cost_usd} / complete{}
        """
        tracker = begin_cost_tracking()
        async with self._thread_locks[thread_id]:
            message = normalize_chat_input(content)
            if not message:
                raise CharacterChatError("invalid_input", "メッセージが空です")
            async with async_session_factory() as db:
                thread = await self._get_thread_orm(db, thread_id)
                recent = await self._load_messages(
                    db, thread_id, limit=HISTORY_MESSAGES
                )
                message_count = await self._message_count(db, thread_id)
                db.expunge(thread)
            user_settings = await session_store.get_user_settings()
            text_model = user_settings.get("novelai_text_model")
            language = _lang(user_settings.get("language"))
            memory_text = await settings_service.get_memory_text()
            appearance = _json_load(thread.appearance_json, {})
            nsfw_mode = (
                bool(thread.nsfw_mode)
                if thread.kind == CHARACTER_CHAT_KIND_SESSION
                else bool(user_settings.get("nsfw_mode"))
            )

            yield {"event": "status", "data": {"phase": "plan"}}
            plan = await self._plan(
                kind=thread.kind,
                name=thread.name,
                recent=recent,
                message=message,
                text_model=text_model,
                language=language,
            )
            lookup_text, lookup_kinds = (
                await run_lookups(plan, language=language) if plan.lookups else ("", [])
            )
            appearance_task: asyncio.Task[dict[str, Any]] | None = None
            if plan.appearance_request:
                # 外見タグの決定は返答ストリームと並列に走らせる(直列にしない)
                appearance_task = asyncio.create_task(
                    self._resolve_appearance_change(
                        appearance,
                        plan.appearance_request,
                        text_model=text_model,
                        language=language,
                    )
                )

            yield {"event": "status", "data": {"phase": "reply"}}
            system_prompt = self._build_system_prompt(
                thread,
                language=language,
                memory_text=memory_text,
                lookup_text=lookup_text,
                appearance_change_request=plan.appearance_request,
            )
            history = [
                {
                    "role": "user" if item.role == "user" else "assistant",
                    "content": item.content,
                }
                for item in recent
            ]
            reply = ""
            try:
                async for chunk in llm_service.generate_feeling_stream(
                    system_prompt,
                    message,
                    provider_override=resolve_text_provider(),
                    novelai_model_override=text_model,
                    usage_callback=record_cost,
                    history=history,
                ):
                    if not chunk:
                        continue
                    reply += chunk
                    yield {"event": "chat_chunk", "data": {"chunk": chunk}}
            except Exception:
                if appearance_task is not None:
                    appearance_task.cancel()
                raise
            reply = normalize_chat_reply(reply, thread.name)
            if not reply:
                if appearance_task is not None:
                    appearance_task.cancel()
                raise CharacterChatError(
                    "invalid_model_output",
                    "返答を解析できませんでした。もう一度お試しください",
                )
            user_message, character_message = await self._persist_messages(
                thread_id,
                user_text=message,
                reply_text=reply,
                meta={
                    "lookups": lookup_kinds,
                    "appearance_request": plan.appearance_request,
                },
            )
            total_messages = message_count + 2
            yield {
                "event": "chat_done",
                "data": {
                    "user_message": self._message_to_dict(user_message),
                    "character_message": self._message_to_dict(character_message),
                    "thread": {
                        "id": thread_id,
                        "message_count": total_messages,
                        "updated_at": _to_iso(character_message.created_at),
                    },
                },
            }

            if appearance_task is not None:
                yield {"event": "status", "data": {"phase": "portrait"}}
                try:
                    new_appearance = await appearance_task
                    data = await self._apply_portrait(
                        thread_id,
                        new_appearance,
                        nsfw_mode=nsfw_mode,
                        user_settings=user_settings,
                        message_id=character_message.id,
                    )
                    yield {"event": "portrait_image", "data": data}
                except Exception as exc:
                    code = getattr(exc, "code", "portrait_failed")
                    logger.warning(
                        "character chat portrait update failed: %s: %s",
                        type(exc).__name__,
                        exc,
                    )
                    yield {
                        "event": "portrait_error",
                        "data": {
                            "code": str(code),
                            "message": str(exc) or type(exc).__name__,
                        },
                    }

            if total_messages - int(thread.summary_message_count or 0) >= SUMMARY_EVERY:
                yield {"event": "status", "data": {"phase": "memory"}}
                try:
                    await self._update_summary(
                        thread_id, language=language, text_model=text_model
                    )
                except Exception as exc:
                    logger.warning(
                        "character chat summary update failed: %s: %s",
                        type(exc).__name__,
                        exc,
                    )

            if tracker.total_usd > 0:
                yield {"event": "cost", "data": {"cost_usd": tracker.total_usd}}
            yield {"event": "complete", "data": {}}


character_chat_service = CharacterChatService()
