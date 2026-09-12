"""キャラチャット(TSF シナリオを経由しないキャラクターとの会話)。

スレッド(案内役キャラ「セレナ」/ 過去セッション由来のキャラ)の永続化、
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
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, desc, func, select

from ..consts.character_chat import (
    ADVENTURE_RECENT_CHAT_MAX,
    ADVENTURE_SCENE_CONTEXT_MAX,
    AVATAR_MODES,
    BASE_APPEARANCE_DESCRIPTION,
    BASE_AVATAR_FILENAME,
    BASE_AVATAR_URL,
    BASE_CHARACTER_KEY,
    BASE_CHARACTER_NAME,
    BASE_CHARACTER_PRONOUN,
    BASE_CLOTHING_TAGS,
    BASE_IDENTITY_TAGS,
    BASE_LIVE2D_URL,
    BASE_PORTRAIT_FILENAME,
    CHARACTER_CHAT_KIND_ADVENTURE,
    CHARACTER_CHAT_KIND_BASE,
    CHARACTER_CHAT_KIND_SESSION,
    HISTORY_MESSAGES,
    LIVE2D_EXPRESSIONS,
    LIVE2D_GESTURES,
    LIVE2D_TALK_HEADER_INSTRUCTION,
    MESSAGE_MAX,
    PAST_PLAY_LOOKUP_KINDS,
    PERSONA_MONOLOGUE_CHARS,
    PERSONA_MONOLOGUES_MAX,
    PERSONA_TIMELINE_MAX,
    PLANNER_RECENT_MESSAGES,
    REPLY_MAX,
    SUMMARY_EVERY,
    SUMMARY_MAX_CHARS,
    THREAD_MESSAGE_LIMIT,
    base_portrait_dir,
    load_origin_lore,
)
from ..consts.companion_avatar import (
    AVATAR_EXPRESSION_DEFAULT,
    AVATAR_GESTURE_DEFAULT,
    avatar_expression_keys,
    avatar_gesture_keys,
    avatar_talk_header_instruction,
    may_start_talk_header,
    normalize_avatar_expression,
    normalize_avatar_gesture,
    parse_talk_header,
    strip_talk_header_line,
    strip_talk_header_lines,
)
from ..consts.language import normalize_language
from ..consts.novelai_models import resolve_user_image_model
from ..databases.base import async_session_factory
from ..databases.models import (
    AvatarModel,
    CharacterChatMessage,
    CharacterChatThread,
    User,
)
from ..settings.config import settings
from .adventure_inventory import inventory_enabled, lean_inventory_for_llm
from .adventure_romance import (
    recent_scene_context,
    romance_script_names,
    talk_relationship_context,
)
from .avatar_service import (
    avatar_display_name,
    avatar_exists,
    avatar_file_url,
    avatar_variant_label,
    list_avatar_variants,
    list_avatars,
)
from .character_chat_lookups import (
    LookupRun,
    available_real_world_kinds,
    is_policy_refused,
    run_lookups,
    session_candidates,
)
from .character_chat_models import (
    CharacterChatAppearanceOutput,
    CharacterChatPlan,
    CharacterChatPlayProposal,
    empty_plan,
    non_english_tag_parts,
)
from .character_chat_play_proposal import (
    PlayProposalOutcome,
    build_play_catalog,
    catalog_names,
    catalog_prompt_items,
    grounding_plan,
    play_proposal_meta,
    self_profile_hint,
)
from .character_chat_prompts import (
    adventure_persona_prompt,
    appearance_change_system_prompt,
    appearance_change_user_prompt,
    base_persona_block,
    current_time_block,
    lookup_block,
    memory_block,
    origin_lore_block,
    planner_system_prompt,
    planner_user_prompt,
    play_proposal_block,
    play_proposal_system_prompt,
    play_proposal_unavailable_block,
    play_proposal_user_prompt,
    real_world_block,
    reply_system_prompt,
    session_persona_block,
    summary_system_prompt,
    summary_user_prompt,
    web_search_refusal_block,
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
    CLOTHING_TAG_PATTERN,
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


def _recent_monologues(
    histories: list[Any], *, until_history_id: str | None
) -> list[dict[str, str]]:
    """自分自身モード用: 履歴の feeling_text(心の声)を古い順に、指定履歴まで・直近 N 件に絞って短く写す。

    自分自身モードは stats を追跡しないため、キャラチャットの人物設定では
    これを心境の根拠にする。
    """
    rows = list(histories)
    if until_history_id:
        for index, row in enumerate(rows):
            if getattr(row, "id", None) == until_history_id:
                rows = rows[: index + 1]
                break
    picked: list[dict[str, str]] = []
    for row in rows:
        text = " ".join(str(getattr(row, "feeling_text", "") or "").split())
        if not text:
            continue
        instruction = " ".join(str(getattr(row, "instruction", "") or "").split())
        picked.append(
            {"instruction": instruction[:40], "text": text[:PERSONA_MONOLOGUE_CHARS]}
        )
    return picked[-PERSONA_MONOLOGUES_MAX:]


def normalize_chat_input(text: str) -> str:
    """発言を空白畳み込みと上限で正規化する。"""
    return " ".join(str(text or "").split()).strip()[:MESSAGE_MAX]


def normalize_chat_reply(text: str, name: str) -> str:
    """LLM の返答から名前プレフィックス・全体を囲む括弧・ヘッダ行を剥がして上限で切る。

    adventure_romance.normalize_talk_reply と同じ規則だが、セレナがアプリの
    説明をする場面もあるため上限は REPLY_MAX にする。ヘッダ行は先頭だけでなく、
    モデルが段落ごとに繰り返したものも剥がす。
    """
    reply = strip_code_fence(str(text or ""))
    _, _, reply = strip_talk_header_lines(reply)
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


def _spoken_text(message: Any) -> str:
    """表示・要約・文脈に渡す発言の本文。

    キャラの発言からは本文に残ったヘッダの行を除く(以前の保存分には、段落ごとに
    繰り返されたヘッダが残っていることがある)。ユーザーの発言には手を入れない。
    """
    if message.role == "user":
        return message.content
    return strip_talk_header_lines(message.content)[2].strip()


def _planner_recent_messages(
    recent: list[CharacterChatMessage],
) -> list[dict[str, str]]:
    """判定 LLM・提案 LLM に渡す直近の会話(話し言葉だけ、1 件 300 文字まで)。"""
    return [
        {
            "role": "user" if item.role == "user" else "character",
            "content": _spoken_text(item)[:300],
        }
        for item in recent[-PLANNER_RECENT_MESSAGES:]
    ]


def _reply_history(
    messages: list[CharacterChatMessage],
    *,
    expressions: tuple[str, ...] = (),
    gestures: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    """返答 LLM へ渡す会話履歴。

    expressions を渡した手番(表情ヘッダを求める手番)では、保存時に剥がした
    ヘッダを過去の返答へ付け直す。履歴の返答がヘッダ無しのままだと、モデルが
    その形を真似てヘッダを書かなくなるため。記録の無い返答と、いまの表示で
    表せないキーは、画面に実際に出た表示と同じ neutral / idle で埋める。
    解析できずに本文へ残ったヘッダ(角括弧の欠けた形など)は、表示の有無に
    かかわらず剥がし、記録が無ければその値を使う。
    """
    history: list[dict[str, str]] = []
    for item in messages:
        if item.role == "user":
            history.append({"role": "user", "content": item.content})
            continue
        left_expression, left_gesture, content = strip_talk_header_lines(item.content)
        content = content.strip()
        if expressions:
            meta = _json_load(item.meta_json, {})
            expression = (
                normalize_avatar_expression(meta.get("expression")) or left_expression
            )
            gesture = normalize_avatar_gesture(meta.get("gesture")) or left_gesture
            if expression not in expressions:
                expression = AVATAR_EXPRESSION_DEFAULT
            if gesture not in gestures:
                gesture = AVATAR_GESTURE_DEFAULT
            content = f"[expression={expression} gesture={gesture}]\n{content}"
        history.append({"role": "assistant", "content": content})
    return history


def _local_now() -> datetime:
    """サーバーのローカル時刻(タイムゾーン付き)。テストで差し替える。"""
    return datetime.now().astimezone()


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


# 場面合成用の構図タグ(adventure_service の _NPC_PROMPT_SUFFIX など)。立ち絵には不要
_COMPOSITION_TAG_PATTERN = re.compile(
    r"\b(?:protagonist|focus|foreground|supporting character)\b", re.IGNORECASE
)


def _split_portrait_tags(tags: str) -> tuple[str, str]:
    """攻略対象の立ち絵タグを (同一性タグ, 服装タグ) に分ける。

    服装は CLOTHING_TAG_PATTERN に一致するもの。残りから場面・動作タグと
    構図タグを落としたものが同一性タグ。
    """
    parts = [part.strip() for part in tags.split(",") if part.strip()]
    clothing = [part for part in parts if CLOTHING_TAG_PATTERN.search(part)]
    identity = [
        part
        for part in identity_tags_only(tags).split(", ")
        if part and not _COMPOSITION_TAG_PATTERN.search(part)
    ]
    return ", ".join(identity), ", ".join(clothing)


def _base_avatar_file() -> Path | None:
    """案内役キャラの同梱 3D モデル(base_portrait_dir()/serena.vrm)。無ければ None。

    同梱しない配布では None になり、_resolve_avatar はこの候補を飛ばして
    名前一致の登録済みモデル、それも無ければ 2D 立ち絵へ倒れる。
    """
    path = base_portrait_dir() / BASE_AVATAR_FILENAME
    return path if path.is_file() else None


def _avatar_choice(appearance: dict[str, Any]) -> tuple[str, str | None]:
    """appearance["avatar"] に保存した 3D モデルの指定を (mode, avatar_id) で返す。"""
    raw = appearance.get("avatar")
    if not isinstance(raw, dict):
        return "auto", None
    mode = str(raw.get("mode") or "auto")
    if mode not in AVATAR_MODES:
        mode = "auto"
    avatar_id = str(raw.get("avatar_id") or "").strip() or None
    if mode == "model" and not avatar_id:
        mode = "auto"
    return mode, avatar_id


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


class _HeaderBuffer:
    """返答のヘッダ行 ``[expression=.. gesture=..]`` を配信前に取り除くバッファ。

    表情ヘッダを求める手番(3D モデル・Live2D 表示中)でだけ有効。先頭のヘッダに
    加え、モデルが段落ごとに繰り返したヘッダの行も取り除く。行頭がヘッダの書き出し
    (``[`` か expression= / gesture= のラベル)でありうる間だけ改行か一定長まで溜め、
    そうでないと分かった行は即時に流す。本文より前の空行は流さない。
    """

    _LIMIT = 64

    def __init__(self, *, enabled: bool) -> None:
        self._enabled = enabled
        self._buffer = ""
        # 行頭にいるか(ヘッダの判定は行頭の文字列だけに行う)
        self._at_line_start = True
        # 本文をまだ流していないか(先頭ヘッダは語彙のキーだけの形も剥がす)
        self._before_text = True

    def feed(self, chunk: str) -> list[str]:
        if not self._enabled:
            return [chunk]
        self._buffer += chunk
        return self._drain(final=False)

    def flush(self) -> list[str]:
        if not self._enabled:
            return []
        return self._drain(final=True)

    def _drain(self, *, final: bool) -> list[str]:
        out: list[str] = []
        while self._buffer:
            newline = self._buffer.find("\n")
            end = len(self._buffer) if newline < 0 else newline + 1
            if not self._at_line_start:
                # 行の途中は行末の改行までそのまま流す
                out.append(self._buffer[:end])
                self._buffer = self._buffer[end:]
                self._at_line_start = newline >= 0
                continue
            line = self._buffer if newline < 0 else self._buffer[:newline]
            if (
                newline < 0
                and not final
                and (
                    not line.strip()
                    or (len(line) < self._LIMIT and may_start_talk_header(line))
                )
            ):
                # ヘッダの書き出しでありうる行頭は、改行まで溜める
                break
            self._buffer = self._buffer[end:]
            kept = self._strip(line)
            if kept is not None:
                out.append(kept + ("\n" if newline >= 0 else ""))
                self._before_text = False
            self._at_line_start = newline >= 0
        return out

    def _strip(self, line: str) -> str | None:
        """行頭から確定した 1 行のヘッダを剥がす。流すものが無ければ None。"""
        if self._before_text:
            if not line.strip():
                return None
            _, _, line = parse_talk_header(line)
            if not line.strip():
                return None
        return strip_talk_header_line(line)


@dataclass
class _AdventureView:
    """adventure 種が 1 回の処理で参照する run の読み取りビュー。"""

    run: Any
    state: dict[str, Any]
    sim: dict[str, Any]
    partner_name: str
    player_name: str
    epilogue: bool
    turns: list[Any]
    companion: bool
    avatar_id: str | None
    composite: bool

    @property
    def avatar_url(self) -> str | None:
        return avatar_file_url(self.avatar_id) if self.avatar_id else None


async def _load_adventure_view(run_id: str) -> _AdventureView | None:
    """run を読んでビューにする。無ければ None、romance 以外は talk_unavailable。

    adventure_service は character_chat_service を遅延 import するため、こちらも
    遅延 import で循環を避ける。
    """
    from .adventure_service import AdventureError, adventure_service

    try:
        run = await adventure_service.get_run_orm(run_id, with_turns=True)
    except AdventureError:
        return None
    state = _json_load(run.state_json, {})
    sim = state.get("sim") if run.preset == "romance" else None
    if not isinstance(sim, dict):
        raise CharacterChatError(
            "talk_unavailable", "キャラチャットは恋愛シミュレーションでのみ使えます"
        )
    partner_name, player_name = romance_script_names(sim, run.language)
    companion = bool(state.get("companion_mode"))
    avatar_id = str(state.get("companion_avatar_id") or "").strip() or None
    return _AdventureView(
        run=run,
        state=state,
        sim=sim,
        partner_name=partner_name,
        player_name=player_name,
        epilogue=bool(state.get("epilogue")),
        turns=sorted(
            list(run.turns or []), key=lambda item: int(item.turn_number or 0)
        ),
        companion=companion,
        avatar_id=avatar_id if companion else None,
        composite=bool(state.get("enable_composite_scene")) and not companion,
    )


def _adventure_file(raw: Any) -> Path | None:
    """Adventure が保存した画像パス(絶対パス文字列)を実ファイルに解決する。"""
    text = str(raw or "").strip()
    if not text:
        return None
    path = Path(text)
    if path.is_file():
        return path
    resolved = resolve_stored_image_path(text)
    return resolved if resolved is not None and resolved.is_file() else None


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
            "content": _spoken_text(message),
            "meta": _json_load(message.meta_json, {}),
            "created_at": _to_iso(message.created_at),
        }

    @staticmethod
    def _public_persona(thread: CharacterChatThread) -> dict[str, Any]:
        """右パネルに出す人物設定(セッション由来のみ。LLM 向けの生データは出さない)。"""
        if thread.kind == CHARACTER_CHAT_KIND_ADVENTURE:
            return CharacterChatService._adventure_public_persona(thread)
        if thread.kind != CHARACTER_CHAT_KIND_SESSION:
            return {}
        persona = _json_load(thread.persona_json, {})
        stats = persona.get("stats") or {}
        transformation_count = int(persona.get("transformation_count") or 0)
        bloom = int(stats.get("bloom") or 0)
        english = thread.language == "en"
        self_mode = bool(persona.get("self_mode"))
        stage: str | None
        if self_mode:
            # 自分自身モードは stats を追跡しないので心理段階・数値を出さない
            stage = None
            stage_label = ""
        elif transformation_count == 0:
            stage = "pre_transform"
            stage_label = "Not yet transformed" if english else "未変身"
        else:
            stage = get_stage_name(bloom)
            stage_label = stage if english else get_stage_display_name(stage)
        payload: dict[str, Any] = {
            "character_name": str(persona.get("character_name") or thread.name),
            "session_updated_at": persona.get("session_updated_at"),
            "summary_title": str(persona.get("summary_title") or ""),
            "summary_text": str(persona.get("summary_text") or ""),
            "stage": stage,
            "stage_label": stage_label,
            "transformation_count": transformation_count,
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
            "self_mode": self_mode,
        }
        if not self_mode:
            payload["stats"] = {
                "bloom": int(stats.get("bloom") or 0),
                "shame": int(stats.get("shame") or 0),
                "adaptation": int(stats.get("adaptation") or 0),
            }
        return payload

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

    @staticmethod
    def _adventure_mode(appearance: dict[str, Any]) -> str:
        """adventure 種の姿の追従モード。run 以外の素材やチャット側の変更は custom。"""
        source = appearance.get("source") or {}
        source_type = str(source.get("type") or "")
        if not source_type:
            # 作成直後(姿が未設定)は既定に従う
            return "default"
        if source_type != "adventure":
            return "custom"
        return str(source.get("adventure_mode") or "default")

    def _can_reset_appearance(
        self, thread: CharacterChatThread, appearance: dict[str, Any]
    ) -> bool:
        if thread.kind == CHARACTER_CHAT_KIND_ADVENTURE:
            return self._adventure_mode(appearance) != "default"
        initial = self._initial_appearance(thread, appearance)
        if initial is None:
            return False
        current = {key: appearance.get(key) for key in _APPEARANCE_KEYS}
        wanted = {key: initial.get(key) for key in _APPEARANCE_KEYS}
        current_portrait = Path(str(thread.portrait_path or "")).name or None
        wanted_portrait = Path(str(initial.get("portrait_path") or "")).name or None
        return current != wanted or current_portrait != wanted_portrait

    async def reset_appearance(self, thread_id: str) -> dict[str, Any]:
        """姿を作成時点(同梱 PNG / コピーした元画像とそのタグ)へ戻す。画像生成はしない。

        adventure 種は「シナリオの姿に合わせる」(表示モードで決める既定)に戻す。
        """
        async with async_session_factory() as db:
            kind = (await self._get_thread_orm(db, thread_id)).kind
        if kind == CHARACTER_CHAT_KIND_ADVENTURE:
            return await self.set_adventure_appearance(thread_id, mode="default")
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
        adventure: dict[str, Any] | None = None,
        avatar: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        appearance = _json_load(thread.appearance_json, {})
        portrait = self._portrait_file(thread)
        payload: dict[str, Any] = {
            "id": thread.id,
            "kind": thread.kind,
            "source_run_id": thread.source_run_id,
            "adventure": adventure,
            # 3D モデル(VRM)の解決結果。一覧では省略(None)
            "avatar": avatar,
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
                    "content": _spoken_text(last_message)[:120],
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
        adventure = None
        if thread.kind == CHARACTER_CHAT_KIND_ADVENTURE:
            adventure = await self._adventure_summary(thread)
        avatar = await self._resolve_avatar(db, thread, adventure=adventure)
        return self._thread_to_dict(
            thread,
            message_count=count,
            last_message=last_message,
            messages=messages if with_messages else None,
            adventure=adventure,
            avatar=avatar,
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
                adventure = None
                if thread.kind == CHARACTER_CHAT_KIND_ADVENTURE:
                    adventure = await self._adventure_summary(thread)
                payloads.append(
                    self._thread_to_dict(
                        thread,
                        message_count=count,
                        last_message=last[-1] if last else None,
                        adventure=adventure,
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
        """案内役キャラ(セレナ)のスレッドを返す。無ければ作る(ユーザーごとに 1 件)。"""
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
        recent_monologues: list[dict[str, str]] = []
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
                if bool(getattr(session, "self_mode", False)):
                    # 自分自身モードは stats が動かないので、そのときの心の声を心境の根拠にする
                    recent_monologues = _recent_monologues(
                        await session_store.get_history(source_session_id),
                        until_history_id=source_history_id,
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
            "recent_monologues": recent_monologues,
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
        reference_override: Path | None = None,
        use_character_reference: bool = False,
    ) -> str:
        """外見タグから立ち絵を 1 枚描き、スレッドディレクトリへ保存してファイル名を返す。

        reference_override があればそれを参照画像にする(無ければいまの姿)。
        use_character_reference は NovelAI の精密参照(Anlas 消費。FE が確認済み)。
        """
        provider = resolve_image_provider()
        image_model = (
            resolve_user_image_model(user_settings, nsfw_mode)
            if provider == Provider.NOVELAI
            else None
        )
        reference = reference_override or self._portrait_file(thread)
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
                use_character_reference=use_character_reference,
            )
        except PortraitGenerationError as exc:
            raise CharacterChatError(exc.code, str(exc)) from exc
        except Exception as exc:
            # プロバイダー由来の例外(API エラー・タイムアウト等)は利用者向けエラーに写し、
            # SSE を無言で閉じない。タイムアウト系は str() が空になるため型名を添える
            logger.warning(
                "character chat portrait generation failed: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            detail = str(exc) or type(exc).__name__
            raise CharacterChatError(
                "image_generation_failed", f"立ち絵の生成に失敗しました({detail})"
            ) from exc
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
        reference_override: Path | None = None,
        use_character_reference: bool = False,
    ) -> dict[str, Any]:
        """立ち絵を描いて thread に反映し、portrait_image イベントの data を返す。"""
        async with async_session_factory() as db:
            thread = await self._get_thread_orm(db, thread_id)
            filename = await self._generate_portrait(
                thread,
                appearance,
                nsfw_mode=nsfw_mode,
                user_settings=user_settings,
                reference_override=reference_override,
                use_character_reference=use_character_reference,
            )
            self._remove_generated_portrait(thread)
            appearance = {**appearance, "portrait_kind": "standing"}
            if thread.kind == CHARACTER_CHAT_KIND_ADVENTURE:
                # チャット側で描いた姿は run に追従させない(シナリオの姿に合わせるで戻す)
                source = dict(appearance.get("source") or {})
                source["type"] = "adventure"
                source["run_id"] = thread.source_run_id
                source["adventure_mode"] = "custom"
                appearance["source"] = source
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
        self,
        thread_id: str,
        *,
        reference: str = "current",
        use_precise_reference: bool = False,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """現在の外見タグから立ち絵を描き直す(同梱 PNG が無いセレナの初回生成も兼ねる)。

        reference が scene / partner のときは adventure 種の run が持つ画像を参照にする。
        use_precise_reference は NovelAI の精密参照(Anlas 消費)で、FE が確認済みの前提。
        """
        tracker = begin_cost_tracking()
        async with self._thread_locks[thread_id]:
            async with async_session_factory() as db:
                thread = await self._get_thread_orm(db, thread_id)
                appearance = _json_load(thread.appearance_json, {})
                kind = thread.kind
                thread_nsfw = bool(thread.nsfw_mode)
                source_run_id = thread.source_run_id
            user_settings = await session_store.get_user_settings()
            nsfw_mode = (
                bool(user_settings.get("nsfw_mode"))
                if kind == CHARACTER_CHAT_KIND_BASE
                else thread_nsfw
            )
            reference_override: Path | None = None
            if kind == CHARACTER_CHAT_KIND_ADVENTURE and source_run_id:
                view = await _load_adventure_view(source_run_id)
                if view is not None:
                    nsfw_mode = bool(view.run.nsfw_mode)
                    # 参照画像に合わせて外見タグも run の最新値にしておく
                    identity, clothing = self._adventure_identity(view)
                    if identity:
                        appearance = {
                            **appearance,
                            "identity_tags": identity,
                            "clothing_tags": clothing
                            or str(appearance.get("clothing_tags") or ""),
                        }
                    if reference in ("scene", "partner"):
                        candidates = self._adventure_images(view)
                        reference_override = candidates.get(
                            "partner_portrait" if reference == "partner" else "scene"
                        )
                        if reference_override is None:
                            raise CharacterChatError(
                                "reference_not_found", "参照にする画像がありません"
                            )
            yield {"event": "status", "data": {"phase": "portrait"}}
            data = await self._apply_portrait(
                thread_id,
                appearance,
                nsfw_mode=nsfw_mode,
                user_settings=user_settings,
                reference_override=reference_override,
                use_character_reference=bool(use_precise_reference),
            )
            yield {"event": "portrait_image", "data": data}
            if tracker.total_usd > 0:
                yield {"event": "cost", "data": {"cost_usd": tracker.total_usd}}
            yield {"event": "complete", "data": {}}

    # ------------------------------------------------------------------
    # 会話
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 3D モデル(VRM)
    # ------------------------------------------------------------------

    def base_avatar_path(self) -> Path:
        """案内役キャラの同梱 3D モデルの実ファイル。無ければ avatar_not_found。"""
        path = _base_avatar_file()
        if path is None:
            raise CharacterChatError("avatar_not_found", "同梱の 3D モデルがありません")
        return path

    def _avatar_name_candidates(
        self, thread: CharacterChatThread, adventure: dict[str, Any] | None
    ) -> set[str]:
        """登録済みモデルの character_name と照合する名前(casefold 済み)。"""
        names: list[str] = [str(thread.name or "")]
        if thread.kind == CHARACTER_CHAT_KIND_BASE:
            names.extend(BASE_CHARACTER_NAME.values())
        elif thread.kind == CHARACTER_CHAT_KIND_SESSION:
            persona = _json_load(thread.persona_json, {})
            names.append(str(persona.get("character_name") or ""))
        elif adventure:
            names.append(str(adventure.get("partner_name") or ""))
        return {name.strip().casefold() for name in names if name.strip()}

    @staticmethod
    def _avatar_payload(
        *,
        mode: str,
        source: str | None,
        url: str | None,
        name: str | None,
        model: AvatarModel | None = None,
        variants: list[AvatarModel] | None = None,
        missing: bool = False,
    ) -> dict[str, Any]:
        rows = variants or []
        return {
            "mode": mode,
            "id": model.id if model is not None else None,
            "url": url,
            "source": source,
            "name": name,
            "character_name": (
                str(model.character_name or "").strip() or None
                if model is not None
                else None
            ),
            "variant_label": (
                str(model.variant_label or "").strip() or None
                if model is not None
                else None
            ),
            # 同じキャラクターの衣装差分(2 件以上あるときだけ)
            "variants": [
                {
                    "id": row.id,
                    "label": avatar_variant_label(row),
                    "current": bool(model is not None and row.id == model.id),
                }
                for row in rows
            ]
            if len(rows) > 1
            else [],
            # 明示的に選んだモデルが削除されていて自動に倒したとき True
            "missing": missing,
        }

    async def _resolve_avatar(
        self,
        db,
        thread: CharacterChatThread,
        *,
        adventure: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """表示する 3D モデルを決める。

        優先順は 明示選択 → (案内役) 同梱 serena.vrm → (adventure 種) run の対面会話
        モデル → character_name が一致する登録済みモデル → なし(2D 立ち絵)。
        adventure は _adventure_summary の dict(companion_avatar_id / partner_name)。
        """
        appearance = _json_load(thread.appearance_json, {})
        mode, chosen_id = _avatar_choice(appearance)
        if mode == "none":
            return self._avatar_payload(mode="none", source=None, url=None, name=None)
        if mode == "live2d":
            if thread.kind != CHARACTER_CHAT_KIND_BASE:
                return self._avatar_payload(
                    mode="none", source=None, url=None, name=None
                )
            return self._avatar_payload(
                mode="live2d", source="bundled", url=BASE_LIVE2D_URL, name=thread.name
            )
        missing = False
        if mode == "model" and chosen_id:
            model = await db.get(AvatarModel, chosen_id)
            if model is not None:
                return self._avatar_payload(
                    mode="model",
                    source="registered",
                    url=avatar_file_url(model.id),
                    name=avatar_display_name(model),
                    model=model,
                    variants=await list_avatar_variants(db, model.id),
                )
            missing = True
        if thread.kind == CHARACTER_CHAT_KIND_BASE and _base_avatar_file() is not None:
            return self._avatar_payload(
                mode="auto",
                source="bundled",
                url=BASE_AVATAR_URL,
                name=thread.name,
                missing=missing,
            )
        run_avatar_id = (
            str(adventure.get("companion_avatar_id") or "").strip()
            if thread.kind == CHARACTER_CHAT_KIND_ADVENTURE and adventure
            else ""
        )
        if run_avatar_id:
            model = await db.get(AvatarModel, run_avatar_id)
            if model is not None:
                return self._avatar_payload(
                    mode="auto",
                    source="run",
                    url=avatar_file_url(model.id),
                    name=avatar_display_name(model),
                    model=model,
                    variants=await list_avatar_variants(db, model.id),
                    missing=missing,
                )
        candidates = self._avatar_name_candidates(thread, adventure)
        matched = [
            model
            for model in await list_avatars(db)
            if str(model.character_name or "").strip().casefold() in candidates
        ]
        if matched:
            # list_avatar_variants と同じ並び(差分ラベル → 名前 → 登録順)の先頭
            matched.sort(
                key=lambda row: (
                    str(row.variant_label or ""),
                    str(row.name or ""),
                    row.created_at or datetime.min,
                )
            )
            model = matched[0]
            return self._avatar_payload(
                mode="auto",
                source="registered",
                url=avatar_file_url(model.id),
                name=avatar_display_name(model),
                model=model,
                variants=await list_avatar_variants(db, model.id),
                missing=missing,
            )
        return self._avatar_payload(
            mode="auto", source=None, url=None, name=None, missing=missing
        )

    async def set_avatar(
        self, thread_id: str, *, mode: str = "auto", avatar_id: str | None = None
    ) -> dict[str, Any]:
        """アバターの表示指定を既存の外見設定へ保存する。"""
        if mode not in AVATAR_MODES:
            raise CharacterChatError("invalid_input", "3D モデルの指定が不正です")
        async with self._thread_locks[thread_id], async_session_factory() as db:
            thread = await self._get_thread_orm(db, thread_id)
            if mode == "live2d" and thread.kind != CHARACTER_CHAT_KIND_BASE:
                raise CharacterChatError("invalid_input", "Live2D は案内役専用です")
            chosen = str(avatar_id or "").strip() or None
            if mode == "model" and (
                chosen is None or not await avatar_exists(db, chosen)
            ):
                raise CharacterChatError("avatar_not_found", "3Dモデルが見つかりません")
            appearance = _json_load(thread.appearance_json, {})
            appearance["avatar"] = {
                "mode": mode,
                "avatar_id": chosen if mode == "model" else None,
            }
            thread.appearance_json = json.dumps(appearance, ensure_ascii=False)
            thread.updated_at = datetime.now()
            await db.commit()
            await db.refresh(thread)
            return await self._thread_payload(db, thread, with_messages=False, limit=1)

    async def _apply_appearance_tags(
        self, thread_id: str, appearance: dict[str, Any]
    ) -> dict[str, Any]:
        """立ち絵を描かずに外見タグだけ thread へ反映し、appearance_updated の data を返す。

        3D モデル表示中の着替えに使う。見えない立ち絵の画像生成を省き、
        「立ち絵を描き直す」で後から描ける状態にしておく。
        """
        async with async_session_factory() as db:
            thread = await self._get_thread_orm(db, thread_id)
            merged = _json_load(thread.appearance_json, {})
            for key in ("identity_tags", "clothing_tags", "description"):
                merged[key] = str(appearance.get(key) or "")
            if thread.kind == CHARACTER_CHAT_KIND_ADVENTURE:
                # チャット側で変えた姿は run に追従させない(シナリオの姿に合わせるで戻す)
                source = dict(merged.get("source") or {})
                source["type"] = "adventure"
                source["run_id"] = thread.source_run_id
                source["adventure_mode"] = "custom"
                merged["source"] = source
            thread.appearance_json = json.dumps(merged, ensure_ascii=False)
            thread.updated_at = datetime.now()
            await db.commit()
            await db.refresh(thread)
            payload = self._thread_to_dict(thread, message_count=0, last_message=None)
        return {
            "appearance": payload["appearance"],
            "portrait_url": payload["portrait_url"],
        }

    # ------------------------------------------------------------------
    # adventure 種(TSF シナリオの攻略対象)
    # ------------------------------------------------------------------

    @staticmethod
    def _partner_present(main_characters: Any, partner_name: str) -> bool:
        from .adventure_service import romance_partner_visual_entry

        if not isinstance(main_characters, list):
            return False
        entry, _ = romance_partner_visual_entry(main_characters, [], partner_name)
        return entry is not None

    def _adventure_identity(self, view: _AdventureView) -> tuple[str, str]:
        """run の現在値から (同一性タグ, 服装タグ) を読む。

        Adventure の攻略対象立ち絵と同じく、その手番の visual LLM が出した
        npc_tags(state["last_image_prompt"])を優先し、服装と同一性に分ける。
        sim["partner_appearance"] は開始素材の記述から作った初期値で、素材が濃い
        場面だと行為・体位タグが残るため、npc_tags を取れない run の保険にだけ
        使い、その場合も同一性タグへ絞る。
        """
        from .adventure_service import romance_partner_visual_entry

        visual_state = view.state.get("visual_state") or {}
        main_characters = (
            visual_state.get("main_characters")
            if isinstance(visual_state, dict)
            else None
        )
        last_prompt = view.state.get("last_image_prompt")
        npc_tags = (
            [str(tag) for tag in (last_prompt.get("npc_tags") or [])]
            if isinstance(last_prompt, dict)
            else []
        )
        entry, partner_tags = (
            romance_partner_visual_entry(main_characters, npc_tags, view.partner_name)
            if isinstance(main_characters, list)
            else (None, "")
        )
        entry_clothing = str(entry.get("clothing") or "").strip() if entry else ""
        if partner_tags.strip():
            identity, clothing = _split_portrait_tags(partner_tags)
            if identity:
                return identity, clothing or entry_clothing
        initial = str(view.sim.get("partner_appearance") or "").strip()
        return identity_tags_only(initial) or initial, entry_clothing

    def _adventure_images(self, view: _AdventureView) -> dict[str, Path | None]:
        """run が持つ攻略対象の画像。partner_portrait = 最新の立ち絵、scene = 相手が写る最新の場面。"""
        state = view.state
        partner_portrait = _adventure_file(
            state.get("partner_portrait_path")
        ) or _adventure_file(state.get("opening_partner_portrait_path"))
        partner_source = _adventure_file(state.get("partner_image_path"))
        scene: Path | None = None
        for turn in reversed(view.turns):
            delta = _json_load(getattr(turn, "state_delta_json", None), {})
            visual_state = (
                delta.get("visual_state") if isinstance(delta, dict) else None
            )
            present = isinstance(visual_state, dict) and self._partner_present(
                visual_state.get("main_characters"), view.partner_name
            )
            image = _adventure_file(getattr(turn, "image_path", None))
            if present and image is not None:
                scene = image
                break
        if scene is None:
            visual_state = state.get("visual_state") or {}
            if isinstance(visual_state, dict) and self._partner_present(
                visual_state.get("main_characters"), view.partner_name
            ):
                scene = _adventure_file(view.run.current_image_path)
        return {
            "partner_portrait": partner_portrait,
            "partner_source": partner_source,
            "scene": scene,
        }

    def _adventure_appearance_choice(
        self, view: _AdventureView, mode: str
    ) -> tuple[Path, str, str]:
        """モードに応じた (画像, portrait_kind, 実際に採用したモード)。

        default はプレイヤーが見てきた画像: 合成モードなら相手が写る最新の場面画像、
        非合成/対面会話モードなら最新の攻略対象立ち絵。無ければ順に倒す。
        """
        images = self._adventure_images(view)
        order: list[str]
        if mode == "partner_portrait":
            order = ["partner_portrait", "scene", "partner_source"]
        elif mode == "scene" or view.composite:
            order = ["scene", "partner_portrait", "partner_source"]
        else:
            order = ["partner_portrait", "scene", "partner_source"]
        for key in order:
            path = images.get(key)
            if path is not None:
                kind = "standing" if key == "partner_portrait" else "scene"
                return path, kind, mode
        raise CharacterChatError("image_not_found", "攻略対象の画像がありません")

    def _apply_adventure_appearance(
        self, thread: CharacterChatThread, view: _AdventureView, mode: str
    ) -> bool:
        """run の画像とタグを姿に写す(必要なときだけコピー)。変更があれば True。"""
        path, kind, effective = self._adventure_appearance_choice(view, mode)
        identity, clothing = self._adventure_identity(view)
        appearance = _json_load(thread.appearance_json, {})
        source = dict(appearance.get("source") or {})
        unchanged = (
            str(source.get("type") or "") == "adventure"
            and str(source.get("adventure_image") or "") == str(path)
            and str(source.get("adventure_mode") or "") == effective
            and str(appearance.get("identity_tags") or "") == identity
            and str(appearance.get("clothing_tags") or "") == clothing
            and bool(thread.portrait_path)
        )
        if unchanged:
            return False
        if (
            str(source.get("adventure_image") or "") != str(path)
            or not thread.portrait_path
        ):
            self._remove_generated_portrait(thread)
            filename = self._copy_source_image(thread.id, path)
            thread.portrait_path = self._stored_path(thread.id, filename)
        appearance.update(
            {
                "identity_tags": identity or str(appearance.get("identity_tags") or ""),
                "clothing_tags": clothing,
                "description": "",
                "portrait_kind": kind,
                "source": {
                    "type": "adventure",
                    "run_id": thread.source_run_id,
                    "adventure_mode": effective,
                    "adventure_image": str(path),
                },
            }
        )
        thread.appearance_json = json.dumps(appearance, ensure_ascii=False)
        return True

    def _adventure_persona_cache(self, view: _AdventureView) -> dict[str, Any]:
        """run 削除後も会話を続けられるよう、最後に読んだ文脈を persona_json に控える。"""
        from .adventure_service import sanitize_visual_state, speech_rule_from_state

        run = view.run
        context: dict[str, Any] = {
            "run_id": run.id,
            "title": str(run.title or ""),
            "status": str(run.status or ""),
            "turn_count": int(run.turn_count or 0),
            "max_turns": int(run.max_turns or 0),
            "partner_name": view.partner_name,
            "player_name": view.player_name,
            "speech_rule": speech_rule_from_state(view.state),
            "partner": {
                "name": view.partner_name,
                "profile": str(view.sim.get("partner_profile") or ""),
                "speech_style": str(view.sim.get("partner_speech_style") or ""),
                "appearance": str(view.sim.get("partner_appearance") or ""),
            },
            "relationship": talk_relationship_context(
                view.sim, view.state, int(run.turn_count or 0), epilogue=view.epilogue
            ),
            "hidden_preferences": view.sim.get("hidden_preferences"),
            "current_scene": sanitize_visual_state(view.state.get("visual_state", {})),
            "reality_rules": list(view.state.get("reality_rules", [])),
            "recent_scenes": recent_scene_context(
                view.turns, ADVENTURE_SCENE_CONTEXT_MAX
            ),
            "companion": view.companion,
            "avatar_id": view.avatar_id,
            "composite": view.composite,
            "use_precise_reference": bool(view.state.get("use_precise_reference")),
        }
        if inventory_enabled(view.state):
            context["inventory"] = lean_inventory_for_llm(view.state)
        return context

    def _adventure_context(
        self, thread: CharacterChatThread, view: _AdventureView | None
    ) -> dict[str, Any]:
        """返答の system prompt に渡す文脈。run が無ければ控えを使う。"""
        cache = _json_load(thread.persona_json, {})
        base = self._adventure_persona_cache(view) if view is not None else cache
        context = {
            "task": (
                "Reply as the partner in a free chat outside the story scenes. "
                "Nothing in the story advances."
            ),
            "partner_name": base.get("partner_name") or thread.name,
            "player_name": base.get("player_name") or "",
            "speech_rule": base.get("speech_rule") or "",
            "partner": base.get("partner") or {},
            "relationship": base.get("relationship") or {},
            "hidden_preferences": base.get("hidden_preferences"),
            "current_scene": base.get("current_scene"),
            "reality_rules": base.get("reality_rules") or [],
            "recent_scenes": base.get("recent_scenes") or [],
        }
        if base.get("inventory"):
            context["inventory"] = base["inventory"]
        if view is None:
            context["run_missing"] = True
        return context

    async def _sync_adventure_thread(
        self, thread: CharacterChatThread, view: _AdventureView
    ) -> None:
        """run の現在値を名前・姿(追従モードのとき)・控えに写す。呼び出し側がコミットする。"""
        if view.partner_name and thread.name != view.partner_name:
            thread.name = view.partner_name
        appearance = _json_load(thread.appearance_json, {})
        mode = self._adventure_mode(appearance)
        if mode != "custom":
            try:
                self._apply_adventure_appearance(thread, view, mode)
            except CharacterChatError as exc:
                logger.warning("adventure appearance sync skipped: %s", exc)
        thread.persona_json = json.dumps(
            self._adventure_persona_cache(view), ensure_ascii=False
        )
        thread.nsfw_mode = bool(view.run.nsfw_mode)

    async def _adventure_summary(self, thread: CharacterChatThread) -> dict[str, Any]:
        """配信用の run 情報(ライブ。run が無ければ控えから最小限)。"""
        from .adventure_service import adventure_service

        cache = _json_load(thread.persona_json, {})
        view = None
        if thread.source_run_id:
            try:
                view = await _load_adventure_view(thread.source_run_id)
            except CharacterChatError:
                view = None
        appearance_mode = self._adventure_mode(_json_load(thread.appearance_json, {}))
        if view is None:
            relationship = cache.get("relationship") or {}
            return {
                "run_id": thread.source_run_id,
                "available": False,
                "title": str(cache.get("title") or ""),
                "status": str(cache.get("status") or ""),
                "turn_count": int(cache.get("turn_count") or 0),
                "max_turns": int(cache.get("max_turns") or 0),
                "partner_name": str(cache.get("partner_name") or thread.name),
                "player_name": str(cache.get("player_name") or ""),
                "companion_mode": bool(cache.get("companion")),
                "companion_avatar_id": None,
                "companion_avatar_url": None,
                "composite": bool(cache.get("composite")),
                "affection": relationship.get("affection"),
                "stage": relationship.get("stage"),
                "day": relationship.get("day"),
                "slot": relationship.get("slot"),
                "dating": bool(relationship.get("dating")),
                "partner_portrait_url": None,
                "scene_image_url": None,
                "use_precise_reference": False,
                "appearance_mode": appearance_mode,
            }
        images = self._adventure_images(view)
        relationship = talk_relationship_context(
            view.sim, view.state, int(view.run.turn_count or 0), epilogue=view.epilogue
        )
        partner_portrait = images.get("partner_portrait")
        scene = images.get("scene")
        return {
            "run_id": view.run.id,
            "available": True,
            "title": str(view.run.title or ""),
            "status": str(view.run.status or ""),
            "turn_count": int(view.run.turn_count or 0),
            "max_turns": int(view.run.max_turns or 0),
            "partner_name": view.partner_name,
            "player_name": view.player_name,
            "companion_mode": view.companion,
            "companion_avatar_id": view.avatar_id,
            "companion_avatar_url": view.avatar_url,
            "composite": view.composite,
            "affection": relationship.get("affection"),
            "stage": relationship.get("stage"),
            "day": relationship.get("day"),
            "slot": relationship.get("slot"),
            "dating": bool(relationship.get("dating")),
            "partner_portrait_url": (
                adventure_service.image_url(view.run.id, partner_portrait)
                if partner_portrait is not None
                else None
            ),
            "scene_image_url": (
                adventure_service.image_url(view.run.id, scene)
                if scene is not None
                else None
            ),
            "use_precise_reference": bool(view.state.get("use_precise_reference")),
            "appearance_mode": appearance_mode,
        }

    @staticmethod
    def _adventure_public_persona(thread: CharacterChatThread) -> dict[str, Any]:
        """右パネル用(控えから。ライブ値は adventure ブロックが持つ)。"""
        cache = _json_load(thread.persona_json, {})
        relationship = cache.get("relationship") or {}
        partner = cache.get("partner") or {}
        scenes = cache.get("recent_scenes") or []
        return {
            "character_name": str(cache.get("partner_name") or thread.name),
            "summary_title": str(cache.get("title") or ""),
            "summary_text": str(partner.get("profile") or ""),
            "stage": str(relationship.get("stage") or ""),
            "stage_label": str(relationship.get("stage") or ""),
            "affection": relationship.get("affection"),
            "day": relationship.get("day"),
            "slot": relationship.get("slot"),
            "total_days": relationship.get("total_days"),
            "dating": bool(relationship.get("dating")),
            "given_gifts": list(relationship.get("given_gifts") or []),
            "completed_milestones": list(
                relationship.get("completed_milestones") or []
            ),
            "attributes": [str(item) for item in cache.get("reality_rules") or []],
            "timeline": [
                {
                    "type": "scene",
                    "text": (
                        f"Day {item.get('day')} {item.get('slot')}: "
                        f"{str(item.get('narrative') or '')[:160]}"
                    ),
                }
                for item in scenes
                if isinstance(item, dict)
            ],
            "outfit_description": str(partner.get("appearance") or ""),
            "play_memory_context": "",
            "speech_style": str(partner.get("speech_style") or ""),
        }

    async def get_or_create_adventure_thread(self, run_id: str) -> dict[str, Any]:
        """run の攻略対象と話すスレッドを返す。無ければ作る(run ごとに 1 件)。

        作成時に旧トークモードのログ(talk_log)があればメッセージとして取り込み、
        run の state からは消す。
        """
        view = await _load_adventure_view(run_id)
        if view is None:
            raise CharacterChatError("run_not_found", "アドベンチャーが見つかりません")
        user_settings = await session_store.get_user_settings()
        lang = _lang(view.run.language or user_settings.get("language"))
        async with self._thread_locks[f"run:{run_id}"]:
            async with async_session_factory() as db:
                existing = (
                    (
                        await db.execute(
                            select(CharacterChatThread)
                            .where(
                                CharacterChatThread.user_id == DEFAULT_USER_ID,
                                CharacterChatThread.kind
                                == CHARACTER_CHAT_KIND_ADVENTURE,
                                CharacterChatThread.source_run_id == run_id,
                            )
                            .order_by(CharacterChatThread.created_at)
                        )
                    )
                    .scalars()
                    .first()
                )
                if existing is not None:
                    await self._sync_adventure_thread(existing, view)
                    await db.commit()
                    await db.refresh(existing)
                    return await self._thread_payload(
                        db, existing, with_messages=False, limit=1
                    )
                await self._ensure_user(db)
                now = datetime.now()
                thread = CharacterChatThread(
                    id=uuid.uuid4().hex,
                    user_id=DEFAULT_USER_ID,
                    kind=CHARACTER_CHAT_KIND_ADVENTURE,
                    name=view.partner_name,
                    pronoun=_FALLBACK_PRONOUN[lang],
                    persona_json="{}",
                    appearance_json="{}",
                    portrait_path=None,
                    source_run_id=run_id,
                    language=lang,
                    nsfw_mode=bool(view.run.nsfw_mode),
                    created_at=now,
                    updated_at=now,
                )
                db.add(thread)
                await db.flush()
                await self._sync_adventure_thread(thread, view)
                await db.commit()
                await db.refresh(thread)
                thread_id = thread.id
            await self._import_talk_log(thread_id, run_id)
            async with async_session_factory() as db:
                thread = await self._get_thread_orm(db, thread_id)
                return await self._thread_payload(
                    db, thread, with_messages=False, limit=1
                )

    async def _import_talk_log(self, thread_id: str, run_id: str) -> int:
        """旧トークモードのログをメッセージとして取り込む。取り込んだ件数を返す。"""
        from .adventure_service import adventure_service

        entries = await adventure_service.consume_talk_log(run_id)
        if not entries:
            return 0
        base = datetime.now() - timedelta(seconds=len(entries))
        async with async_session_factory() as db:
            thread = await self._get_thread_orm(db, thread_id)
            for index, entry in enumerate(entries):
                text = str(entry.get("text") or "").strip()
                if not text:
                    continue
                role = "user" if entry.get("role") == "user" else "character"
                meta: dict[str, Any] = {
                    "imported": True,
                    "after_turn": entry.get("after_turn"),
                }
                if role == "character":
                    meta["expression"] = normalize_avatar_expression(
                        entry.get("expression")
                    )
                    meta["gesture"] = normalize_avatar_gesture(entry.get("gesture"))
                db.add(
                    CharacterChatMessage(
                        id=uuid.uuid4().hex,
                        thread_id=thread_id,
                        role=role,
                        content=text,
                        meta_json=json.dumps(meta, ensure_ascii=False),
                        created_at=base + timedelta(milliseconds=index),
                    )
                )
            thread.updated_at = datetime.now()
            await db.commit()
        return len(entries)

    async def set_adventure_appearance(
        self, thread_id: str, *, mode: str = "default"
    ) -> dict[str, Any]:
        """adventure 種の姿を run の画像に切り替える(default / partner_portrait / scene)。"""
        async with self._thread_locks[thread_id], async_session_factory() as db:
            thread = await self._get_thread_orm(db, thread_id)
            if thread.kind != CHARACTER_CHAT_KIND_ADVENTURE or not thread.source_run_id:
                raise CharacterChatError(
                    "talk_unavailable", "シナリオに紐づいたキャラクターではありません"
                )
            view = await _load_adventure_view(thread.source_run_id)
            if view is None:
                raise CharacterChatError(
                    "run_not_found", "アドベンチャーが見つかりません"
                )
            self._apply_adventure_appearance(thread, view, mode)
            thread.updated_at = datetime.now()
            await db.commit()
            await db.refresh(thread)
            return await self._thread_payload(db, thread, with_messages=False, limit=1)

    async def recent_adventure_messages(
        self, run_id: str, *, after_turn: int
    ) -> list[dict[str, Any]]:
        """run に紐づくチャットのうち、after_turn 以降(=前の手番以降)の発言を古い順に返す。"""
        async with async_session_factory() as db:
            thread = (
                (
                    await db.execute(
                        select(CharacterChatThread).where(
                            CharacterChatThread.user_id == DEFAULT_USER_ID,
                            CharacterChatThread.kind == CHARACTER_CHAT_KIND_ADVENTURE,
                            CharacterChatThread.source_run_id == run_id,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if thread is None:
                return []
            rows = await self._load_messages(
                db, thread.id, limit=ADVENTURE_RECENT_CHAT_MAX * 4
            )
        entries: list[dict[str, Any]] = []
        for row in rows:
            meta = _json_load(row.meta_json, {})
            try:
                turn = int(meta.get("after_turn"))
            except (TypeError, ValueError):
                continue
            if turn < after_turn:
                continue
            entries.append(
                {
                    "role": "user" if row.role == "user" else "partner",
                    "text": _spoken_text(row),
                    "after_turn": turn,
                }
            )
        return entries[-ADVENTURE_RECENT_CHAT_MAX:]

    async def _plan(
        self,
        *,
        kind: str,
        name: str,
        recent: list[CharacterChatMessage],
        message: str,
        text_model: str | None,
        language: str,
        real_world_kinds: frozenset[str] = frozenset(),
    ) -> CharacterChatPlan:
        """判定 LLM。失敗しても返答は止めず、空の計画に倒す。

        real_world_kinds は今回使ってよい現実世界の調べ物。判定 LLM の選択肢に載せ、
        計画の検証でもそれ以外の種類を落とす。
        """
        try:
            candidates = await session_candidates(language)
        except Exception as exc:
            logger.warning(
                "character chat session candidates failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            candidates = []
        recent_messages = _planner_recent_messages(recent)
        try:
            return await generate_validated(
                CharacterChatPlan,
                generate=lambda system, user: _generate_text(
                    system, user, text_model=text_model
                ),
                system_prompt=planner_system_prompt(
                    language, real_world_kinds=real_world_kinds
                ),
                user_prompt=planner_user_prompt(
                    kind=kind,
                    character_name=name,
                    recent_messages=recent_messages,
                    session_candidates=candidates,
                    message=message,
                    today=(
                        _local_now().date().isoformat()
                        if "web_search" in real_world_kinds
                        else None
                    ),
                ),
                context={"allowed_kinds": (*PAST_PLAY_LOOKUP_KINDS, *real_world_kinds)},
            )
        except (StructuredOutputError, Exception) as exc:
            logger.warning(
                "character chat planner failed; replying without lookups: %s: %s",
                type(exc).__name__,
                exc,
            )
            return empty_plan()

    async def _propose_play(
        self,
        *,
        language: str,
        text_model: str | None,
        nsfw_mode: bool,
        memory_text: str | None,
        recent: list[CharacterChatMessage],
        message: str,
        lookups: LookupRun,
    ) -> PlayProposalOutcome:
        """おすすめのプレイを 1 件作る。失敗しても返答は止めず、カードの無い結果に倒す。

        根拠には判定 LLM がすでに調べた本文に加えて、傾向と最近のセッションを読む。
        生成は返答と同じ設定プロバイダー(_generate_text)で行い、料金も同じ集計に載せる。
        """
        try:
            catalog = build_play_catalog()
        except Exception as exc:
            logger.warning(
                "character chat play catalog failed: %s: %s", type(exc).__name__, exc
            )
            catalog = {}
        if not catalog:
            logger.warning("character chat play proposal skipped: no characters")
            return PlayProposalOutcome(
                meta=None, reply_block=play_proposal_unavailable_block(language)
            )
        try:
            profile_hint = self_profile_hint(await settings_service.get_self_profile())
        except Exception as exc:
            logger.warning(
                "character chat self profile for play proposal failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            profile_hint = None
        self_mode_available = profile_hint is not None
        already_run = {str(item.get("kind")) for item in lookups.details}
        try:
            grounding = await run_lookups(
                grounding_plan(already_run), language=language
            )
        except Exception as exc:
            logger.warning(
                "character chat play proposal lookups failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            grounding = LookupRun()
        try:
            proposal = await generate_validated(
                CharacterChatPlayProposal,
                generate=lambda system, user: _generate_text(
                    system, user, text_model=text_model
                ),
                system_prompt=play_proposal_system_prompt(
                    language,
                    nsfw_mode=nsfw_mode,
                    self_mode_available=self_mode_available,
                ),
                user_prompt=play_proposal_user_prompt(
                    characters=catalog_prompt_items(catalog),
                    self_profile=profile_hint,
                    play_records="\n\n".join(
                        text for text in (lookups.text, grounding.text) if text
                    ),
                    memory_text=memory_text,
                    recent_messages=_planner_recent_messages(recent),
                    message=message,
                ),
                context={
                    "catalog": catalog_names(catalog),
                    "self_mode_available": self_mode_available,
                },
            )
        except (StructuredOutputError, Exception) as exc:
            logger.warning(
                "character chat play proposal failed: %s: %s", type(exc).__name__, exc
            )
            return PlayProposalOutcome(
                meta=None,
                reply_block=play_proposal_unavailable_block(language),
                grounding_text=grounding.text,
                grounding_details=grounding.details,
            )
        entry = catalog[proposal.character_ref]
        meta = play_proposal_meta(proposal, entry)
        logger.info(
            "character chat play proposal: %s (%s, self_mode=%s)",
            entry.ref,
            proposal.instruction_type,
            proposal.self_mode,
        )
        return PlayProposalOutcome(
            meta=meta,
            reply_block=play_proposal_block(meta, language),
            grounding_text=grounding.text,
            grounding_details=grounding.details,
        )

    async def _resolve_appearance_change(
        self,
        appearance: dict[str, Any],
        request: str,
        *,
        text_model: str | None,
        language: str,
    ) -> dict[str, Any]:
        """着替え要求を外見タグへ写す。identity は明示されない限り据え置く。

        タグに日本語が混じったら(依頼文の丸写し)、混じった要素を示して 1 回だけ
        再生成する。それでも直らなければ、通じないタグで立ち絵を描かないよう拒否する。
        """
        identity = str(appearance.get("identity_tags") or "")
        clothing = str(appearance.get("clothing_tags") or "")

        async def _generate(rejected_tags: str | None) -> CharacterChatAppearanceOutput:
            return await generate_validated(
                CharacterChatAppearanceOutput,
                generate=lambda system, user: _generate_text(
                    system, user, text_model=text_model
                ),
                system_prompt=appearance_change_system_prompt(language),
                user_prompt=appearance_change_user_prompt(
                    identity_tags=identity,
                    clothing_tags=clothing,
                    request=request,
                    rejected_tags=rejected_tags,
                ),
            )

        output = await _generate(None)
        rejected = non_english_tag_parts(output.identity_tags) + non_english_tag_parts(
            output.clothing_tags
        )
        if rejected:
            logger.info(
                "character chat appearance tags contained non-English parts; "
                "retrying once: %s",
                rejected,
            )
            output = await _generate(", ".join(rejected))
            rejected = non_english_tag_parts(
                output.identity_tags
            ) + non_english_tag_parts(output.clothing_tags)
            if rejected:
                raise CharacterChatError(
                    "appearance_tags_not_english",
                    "着替えを英語の外見タグに変換できませんでした"
                    f"（{', '.join(rejected)}）。別の言い方でもう一度お試しください",
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
        adventure_context: dict[str, Any] | None = None,
        header_instruction: str = "",
        origin_lore_text: str = "",
        self_profile: dict[str, Any] | None = None,
        real_world_text: str = "",
        search_refused: bool = False,
        play_proposal_text: str = "",
    ) -> str:
        persona = _json_load(thread.persona_json, {})
        appearance = _json_load(thread.appearance_json, {})
        if thread.kind == CHARACTER_CHAT_KIND_ADVENTURE:
            context = adventure_context or {}
            chat_look = ""
            if self._adventure_mode(appearance) == "custom":
                chat_look = str(
                    appearance.get("description") or ""
                ).strip() or ", ".join(
                    part
                    for part in (
                        str(appearance.get("identity_tags") or "").strip(),
                        str(appearance.get("clothing_tags") or "").strip(),
                    )
                    if part
                )
            return adventure_persona_prompt(
                language,
                partner_name=str(context.get("partner_name") or thread.name),
                player_name=str(context.get("player_name") or ""),
                speech_rule=str(context.get("speech_rule") or ""),
                header_instruction=header_instruction,
                context={
                    key: value
                    for key, value in context.items()
                    if key not in ("partner_name", "player_name", "speech_rule")
                },
                memory_block_text=memory_block(memory_text, language),
                summary_text=thread.summary_text,
                lookup_block_text=lookup_block(lookup_text, language),
                chat_appearance_description=chat_look,
                appearance_change_request=appearance_change_request,
            )
        is_base = thread.kind == CHARACTER_CHAT_KIND_BASE
        if is_base:
            persona_text = base_persona_block(language)
        else:
            persona_text = session_persona_block(
                persona, language, self_profile=self_profile
            )
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
            origin_lore_block_text=origin_lore_block(origin_lore_text, language),
            header_instruction=header_instruction,
            relaxed_length=thread.kind == CHARACTER_CHAT_KIND_SESSION,
            # いまの日時と現実世界の調べ物は案内役キャラだけ(セッション由来は作中の人物)
            current_time_text=(
                current_time_block(_local_now(), language) if is_base else ""
            ),
            real_world_block_text=(
                real_world_block(real_world_text, language) if is_base else ""
            ),
            search_refusal_text=(
                web_search_refusal_block(language) if is_base and search_refused else ""
            ),
            # おすすめのプレイは案内役キャラだけ
            play_proposal_text=play_proposal_text if is_base else "",
        )

    async def _persist_messages(
        self,
        thread_id: str,
        *,
        user_text: str,
        reply_text: str,
        meta: dict[str, Any],
        user_meta: dict[str, Any] | None = None,
    ) -> tuple[CharacterChatMessage, CharacterChatMessage]:
        now = datetime.now()
        user_message = CharacterChatMessage(
            id=uuid.uuid4().hex,
            thread_id=thread_id,
            role="user",
            content=user_text,
            meta_json=json.dumps(user_meta, ensure_ascii=False) if user_meta else None,
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
                    messages=[
                        {"role": m.role, "content": _spoken_text(m)} for m in fresh
                    ],
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
        self,
        *,
        thread_id: str,
        content: str,
        use_web_search: bool = False,
        use_weather: bool = False,
        request_play_proposal: bool = False,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """1 発言の処理。

        use_web_search / use_weather は設定画面のトグル。案内役キャラのスレッドで、
        サーバーにキー・地点が設定されているときだけ効く。request_play_proposal は
        「おすすめのプレイを聞く」ボタンからの送信で、案内役キャラのスレッドでは判定 LLM を
        省いて必ず提案する(判定 LLM が依頼を拾った手番も提案する)。提案は
        character_message の meta.play_proposal に載る。

        Yields:
            status{phase: plan|search|propose|reply|portrait|memory} /
            chat_chunk{chunk} /
            chat_done{user_message, character_message, thread} /
            portrait_image{image_url, appearance} / appearance_updated{appearance,
            portrait_url}(3D モデル表示中の着替え) / portrait_error{code, message} /
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
            # 自分自身モード由来は、通常プレイと同じく自プロフィールを毎手番ライブで読む
            self_profile: dict[str, Any] | None = None
            if thread.kind == CHARACTER_CHAT_KIND_SESSION and bool(
                _json_load(thread.persona_json, {}).get("self_mode")
            ):
                try:
                    self_profile = await settings_service.get_self_profile()
                except Exception as exc:  # pragma: no cover - 補助情報
                    logger.warning(
                        "character chat self profile failed: %s: %s",
                        type(exc).__name__,
                        exc,
                    )
            nsfw_mode = (
                bool(user_settings.get("nsfw_mode"))
                if thread.kind == CHARACTER_CHAT_KIND_BASE
                else bool(thread.nsfw_mode)
            )
            adventure_context: dict[str, Any] | None = None
            header_instruction = ""
            # 表情ヘッダで選べるキー。履歴の返答へヘッダを付け直すときの範囲にもなる
            header_expressions: tuple[str, ...] = ()
            header_gestures: tuple[str, ...] = ()
            after_turn: int | None = None
            view: _AdventureView | None = None
            if thread.kind == CHARACTER_CHAT_KIND_ADVENTURE:
                view = (
                    await _load_adventure_view(thread.source_run_id)
                    if thread.source_run_id
                    else None
                )
                async with async_session_factory() as db:
                    persisted = await self._get_thread_orm(db, thread_id)
                    if view is not None:
                        await self._sync_adventure_thread(persisted, view)
                        await db.commit()
                        await db.refresh(persisted)
                    db.expunge(persisted)
                thread = persisted
                adventure_context = self._adventure_context(thread, view)
                if view is not None:
                    nsfw_mode = bool(view.run.nsfw_mode)
                    after_turn = int(view.run.turn_count or 0)
            appearance = _json_load(thread.appearance_json, {})
            # 選択したアバターで表現できる表情・身振りのヘッダを求める
            async with async_session_factory() as db:
                avatar = await self._resolve_avatar(
                    db,
                    thread,
                    adventure=(
                        {
                            "companion_avatar_id": view.avatar_id,
                            "partner_name": view.partner_name,
                        }
                        if view is not None
                        else None
                    ),
                )
            avatar_shown = bool(avatar.get("url"))
            if avatar_shown:
                if avatar.get("mode") == "live2d":
                    header_instruction = LIVE2D_TALK_HEADER_INSTRUCTION
                    header_expressions = LIVE2D_EXPRESSIONS
                    header_gestures = LIVE2D_GESTURES
                else:
                    header_instruction = avatar_talk_header_instruction()
                    header_expressions = avatar_expression_keys()
                    header_gestures = avatar_gesture_keys()

            # 現実世界の調べ物(Web 検索・天気)は案内役キャラだけが使う
            real_world_kinds = (
                available_real_world_kinds(
                    use_web_search=use_web_search, use_weather=use_weather
                )
                if thread.kind == CHARACTER_CHAT_KIND_BASE
                else frozenset()
            )
            is_base = thread.kind == CHARACTER_CHAT_KIND_BASE
            # 「おすすめのプレイを聞く」ボタンからの送信は、判定 LLM を待たずに必ず提案する
            # (案内役キャラだけ)。判定 LLM を省くため、この手番は判定由来の調べ物をしない
            forced_proposal = request_play_proposal and is_base
            if request_play_proposal and not is_base:
                logger.info(
                    "character chat play proposal requested outside the guide thread; "
                    "ignored"
                )
            if forced_proposal:
                plan = empty_plan()
            else:
                yield {"event": "status", "data": {"phase": "plan"}}
                plan = await self._plan(
                    kind=thread.kind,
                    name=thread.name,
                    recent=recent,
                    message=message,
                    text_model=text_model,
                    language=language,
                    real_world_kinds=real_world_kinds,
                )
            lookups = LookupRun()
            if plan.lookups:
                if any(
                    lookup.kind in real_world_kinds
                    and not is_policy_refused(lookup, message=message)
                    for lookup in plan.lookups
                ):
                    # 外部 API は待ち時間が長くなりうるため、進捗を分けて示す
                    yield {"event": "status", "data": {"phase": "search"}}
                lookups = await run_lookups(
                    plan,
                    language=language,
                    allowed_kinds=(*PAST_PLAY_LOOKUP_KINDS, *real_world_kinds),
                    message=message,
                )
            # おすすめのプレイは返答がその内容に触れるため、返答ストリームの前に作る
            proposal: PlayProposalOutcome | None = None
            if is_base and (forced_proposal or plan.play_proposal):
                yield {"event": "status", "data": {"phase": "propose"}}
                proposal = await self._propose_play(
                    language=language,
                    text_model=text_model,
                    nsfw_mode=nsfw_mode,
                    memory_text=memory_text,
                    recent=recent,
                    message=message,
                    lookups=lookups,
                )
                # 提案のために読んだ記録も、返答の根拠と引用表示に載せる
                lookups = LookupRun(
                    text="\n\n".join(
                        text for text in (lookups.text, proposal.grounding_text) if text
                    ),
                    real_world_text=lookups.real_world_text,
                    details=[*lookups.details, *proposal.grounding_details],
                    web_search_refused=lookups.web_search_refused,
                )
            # 「別の層の記憶」は案内役キャラだけ。判定 LLM が呼んだ手番にだけ載せる
            origin_lore_text = ""
            if plan.origin_lore and thread.kind == CHARACTER_CHAT_KIND_BASE:
                origin_lore_text = load_origin_lore(language)
                if origin_lore_text:
                    logger.info("character chat: origin lore attached to this reply")
                else:
                    logger.warning(
                        "character chat planner requested origin lore but no lore "
                        "file was found"
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
                lookup_text=lookups.text,
                real_world_text=lookups.real_world_text,
                search_refused=lookups.web_search_refused,
                appearance_change_request=plan.appearance_request,
                adventure_context=adventure_context,
                header_instruction=header_instruction,
                origin_lore_text=origin_lore_text,
                self_profile=self_profile,
                play_proposal_text=proposal.reply_block if proposal else "",
            )
            history = _reply_history(
                recent, expressions=header_expressions, gestures=header_gestures
            )
            reply = ""
            # 3D モデル表示中は先頭ヘッダ行(表情・身振り)を配信前に剥がす
            header = _HeaderBuffer(enabled=bool(header_instruction))
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
                    for visible in header.feed(chunk):
                        yield {"event": "chat_chunk", "data": {"chunk": visible}}
                for visible in header.flush():
                    yield {"event": "chat_chunk", "data": {"chunk": visible}}
            except Exception:
                if appearance_task is not None:
                    appearance_task.cancel()
                raise
            expression = gesture = None
            if header_instruction:
                raw_expression, raw_gesture, _ = strip_talk_header_lines(
                    strip_code_fence(reply)
                )
                expression = normalize_avatar_expression(raw_expression)
                gesture = normalize_avatar_gesture(raw_gesture)
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
                    # 引用表示用の明細(種類・検索語・本文・関係するセッション・出典)
                    "lookups": lookups.details,
                    "appearance_request": plan.appearance_request,
                    # おすすめのプレイの提案カード(用意できた手番だけ)
                    **(
                        {"play_proposal": proposal.meta}
                        if proposal is not None and proposal.meta
                        else {}
                    ),
                    **(
                        {"after_turn": after_turn}
                        if thread.kind == CHARACTER_CHAT_KIND_ADVENTURE
                        else {}
                    ),
                    # 3D モデル表示中の返答だけ表情・身振りを残す(種類を問わない)
                    **(
                        {"expression": expression, "gesture": gesture}
                        if header_instruction
                        else {}
                    ),
                },
                user_meta=(
                    {"after_turn": after_turn}
                    if thread.kind == CHARACTER_CHAT_KIND_ADVENTURE
                    else None
                ),
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
                    if avatar_shown:
                        # 3D モデル表示中は見えない立ち絵を描かず、外見タグだけ更新する
                        data = await self._apply_appearance_tags(
                            thread_id, new_appearance
                        )
                        yield {"event": "appearance_updated", "data": data}
                    else:
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
