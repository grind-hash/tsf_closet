"""キャラクターメイク: プリセットの新しい項目・立ち絵・キャラチャットとの連携。"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from sqlalchemy import select

# isolated_db は fixture 実行時に import 済みのモジュールだけ session factory を差し替える
import gateway.services.adventure_service  # noqa: F401
from gateway.databases.models import AvatarModel as AvatarModelORM
from gateway.databases.models import (
    CharacterChatMessage,
    CharacterChatThread,
    CharacterPreset,
    User,
)
from gateway.databases.models import History as HistoryORM
from gateway.databases.models import Session as SessionORM
from gateway.databases.models import SessionStats as SessionStatsORM
from gateway.routes.character_router import _serialize_preset
from gateway.services import character_chat_service as chat_module
from gateway.services import character_preset_portrait as portrait_module
from gateway.services.character_chat_prompts import character_persona_block
from gateway.services.character_chat_service import (
    CharacterChatError,
    CharacterChatService,
)
from gateway.services.character_preset_portrait import (
    attach_preset_portrait,
    stream_preset_portrait,
)
from gateway.services.character_service import CharacterPresetService
from gateway.services.session import DEFAULT_USER_ID

PLAN_EMPTY = '{"lookups": [], "appearance_request": null}'


def _png(color: str = "red") -> bytes:
    buf = BytesIO()
    Image.new("RGB", (32, 48), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def data_dir(isolated_db, tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "data"
    monkeypatch.setattr(
        portrait_module.settings, "history_images_dir", root / "history_images"
    )
    return root


@pytest.fixture
def service(data_dir: Path, monkeypatch) -> CharacterChatService:
    svc = CharacterChatService()
    svc._images_dir = data_dir / "character_chat_images"
    monkeypatch.setattr(
        chat_module.settings_service, "get_memory_text", AsyncMock(return_value=None)
    )
    return svc


async def _create_preset(factory, **fields):
    async with factory() as db:
        if await db.get(User, DEFAULT_USER_ID) is None:
            db.add(User(id=DEFAULT_USER_ID))
        record = await CharacterPresetService.create_preset_raw(db, **fields)
        await db.commit()
        await db.refresh(record)
        return record


def _fake_llm(monkeypatch, captured: list[str], reply: str = "こんにちは") -> None:
    async def fake_generate_text(system_prompt, user_prompt, **kwargs):
        content = PLAN_EMPTY if "retrieval planner" in system_prompt else "要約"
        return SimpleNamespace(content=content, cost_usd=0.0)

    async def fake_stream(system_prompt, user_prompt, **kwargs):
        captured.append(system_prompt)
        yield reply

    monkeypatch.setattr(chat_module.llm_service, "generate_text", fake_generate_text)
    monkeypatch.setattr(chat_module.llm_service, "generate_feeling_stream", fake_stream)


async def _collect(generator) -> list[dict]:
    return [event async for event in generator]


PROFILE = {
    "pronoun": "あたし",
    "gender": "woman",
    "personality": "面倒見がよく、少し皮肉屋",
    "speech_style": "砕けたタメ口",
    "sample_lines": "「しょうがないなあ」\n「ほら、行くよ」",
    "knowledge": "港町の喫茶店で働いている。\n猫を 2 匹飼っている。",
    "greeting": "いらっしゃい。今日は何にする？",
}


async def test_preset_round_trips_maker_fields(isolated_db, data_dir) -> None:
    record = await _create_preset(
        isolated_db.async_factory,
        name="サクラ",
        appearance_tags="1girl, pink hair, apron",
        profile=PROFILE,
        avatar_model_id=" model-1 ",
        voice={"speaker_id": "spk-1", "style_id": "42"},
    )
    read = _serialize_preset(record)
    assert read.avatar_model_id == "model-1"
    assert read.voice is not None and read.voice.style_id == "42"
    assert read.profile is not None
    assert read.profile.knowledge.endswith("猫を 2 匹飼っている。")
    assert read.profile.sample_lines.count("\n") == 1
    assert read.portrait_url is None

    async with isolated_db.async_factory() as db:
        updated = await CharacterPresetService.update_preset(
            db,
            record.id,
            avatar_model_id="",
            voice={"speaker_id": "", "style_id": ""},
        )
        await db.commit()
        assert updated is not None
        await db.refresh(updated)
        read = _serialize_preset(updated)
    assert read.avatar_model_id is None
    assert read.voice is None


async def test_portrait_generation_stores_image_and_thumbnail(
    isolated_db, data_dir, monkeypatch
) -> None:
    record = await _create_preset(
        isolated_db.async_factory,
        name="サクラ",
        appearance_tags="pink hair, apron",
        profile={"gender": "woman"},
    )
    portrait = AsyncMock(return_value=_png("blue"))
    monkeypatch.setattr(portrait_module, "generate_portrait_bytes", portrait)
    monkeypatch.setattr(portrait_module, "resolve_image_provider", lambda: "openrouter")

    events = await _collect(stream_preset_portrait(record.id))
    kinds = [event["event"] for event in events]
    assert kinds == ["status", "portrait_image", "complete"]
    # 性別トークンが無いタグには、プロフィールの性別から 1girl を補う
    assert portrait.await_args.kwargs["tags"].startswith("1girl, ")
    preset = events[1]["data"]["preset"]
    read = _serialize_preset(preset)
    assert read.portrait_url is not None
    assert read.thumbnail_url == read.portrait_url
    stored = data_dir / "character_images" / record.id
    assert [path.name for path in stored.iterdir()] == [Path(read.portrait_url).name]


async def test_create_character_thread_copies_portrait_and_greeting(
    service: CharacterChatService, isolated_db, data_dir, tmp_path: Path
) -> None:
    record = await _create_preset(
        isolated_db.async_factory,
        name="サクラ",
        appearance_tags="1girl, pink hair, school uniform, smile",
        profile=PROFILE,
    )
    image = tmp_path / "portrait.png"
    image.write_bytes(_png())
    async with isolated_db.async_factory() as db:
        preset = await db.get(CharacterPreset, record.id)
        attach_preset_portrait(preset, image, generated=True)
        await db.commit()

    thread = await service.create_character_thread(record.id)
    assert thread["kind"] == "character"
    assert thread["name"] == "サクラ"
    assert thread["pronoun"] == "あたし"
    assert thread["appearance"]["portrait_kind"] == "standing"
    assert "school uniform" in thread["appearance"]["clothing_tags"]
    assert "school uniform" not in thread["appearance"]["identity_tags"]
    assert thread["portrait_url"] is not None
    assert thread["character"] == {
        "id": record.id,
        "name": "サクラ",
        "voice": None,
        "missing": False,
    }
    assert list((service._images_dir / thread["id"]).glob("source-*.png"))

    detail = await service.get_thread(thread["id"])
    assert [(m["role"], m["content"]) for m in detail["messages"]] == [
        ("character", "いらっしゃい。今日は何にする？")
    ]


async def test_character_settings_are_read_live(
    service: CharacterChatService, isolated_db, data_dir, monkeypatch
) -> None:
    record = await _create_preset(
        isolated_db.async_factory, name="サクラ", profile=PROFILE
    )
    thread = await service.create_character_thread(record.id)
    systems: list[str] = []
    _fake_llm(monkeypatch, systems)

    await _collect(service.stream_message(thread_id=thread["id"], content="やあ"))
    assert "面倒見がよく、少し皮肉屋" in systems[-1]
    assert "港町の喫茶店で働いている。" in systems[-1]
    assert "「しょうがないなあ」" in systems[-1]
    assert "一人称は「あたし」" in systems[-1]

    async with isolated_db.async_factory() as db:
        await CharacterPresetService.update_preset(
            db,
            record.id,
            name="サクラコ",
            profile={**PROFILE, "pronoun": "わたくし", "personality": "おっとり"},
        )
        await db.commit()
        row = await db.get(CharacterChatThread, thread["id"])
        assert row is not None
        await db.refresh(row)
        # 名前と一人称はスレッドの列にも書き写す(一覧・要約で使う)
        assert (row.name, row.pronoun) == ("サクラコ", "わたくし")

    await _collect(service.stream_message(thread_id=thread["id"], content="元気？"))
    assert "おっとり" in systems[-1]
    assert "面倒見がよく" not in systems[-1]
    assert "「サクラコ」" in systems[-1]


async def test_character_avatar_is_used_before_name_match(
    service: CharacterChatService, isolated_db, data_dir
) -> None:
    async with isolated_db.async_factory() as db:
        db.add(
            AvatarModelORM(
                id="vrm-1",
                name="サクラ制服",
                file_path="vrm-1.vrm",
                created_at=datetime(2026, 10, 1),
            )
        )
        await db.commit()
    record = await _create_preset(
        isolated_db.async_factory, name="サクラ", avatar_model_id="vrm-1"
    )
    thread = await service.create_character_thread(record.id)
    detail = await service.get_thread(thread["id"])
    assert detail["avatar"]["source"] == "character"
    assert detail["avatar"]["id"] == "vrm-1"


async def test_deleting_preset_keeps_conversation(
    service: CharacterChatService, isolated_db, data_dir, monkeypatch
) -> None:
    record = await _create_preset(
        isolated_db.async_factory, name="サクラ", profile=PROFILE
    )
    thread = await service.create_character_thread(record.id)
    async with isolated_db.async_factory() as db:
        assert await CharacterPresetService.delete_preset(db, record.id)
        await db.commit()

    detail = await service.get_thread(thread["id"])
    assert detail["character"] is None
    systems: list[str] = []
    _fake_llm(monkeypatch, systems)
    events = await _collect(
        service.stream_message(thread_id=thread["id"], content="やあ")
    )
    assert events[-1]["event"] == "complete"
    # キャラクターが消えても、スレッドの名前と一人称で話し続ける
    assert "「サクラ」" in systems[-1]


async def _seed_session(factory, image: Path) -> None:
    image.write_bytes(_png())
    async with factory() as db:
        if await db.get(User, DEFAULT_USER_ID) is None:
            db.add(User(id=DEFAULT_USER_ID))
        db.add(
            SessionORM(
                id="sess-1",
                user_id=DEFAULT_USER_ID,
                current_image_path=str(image),
                character_id="char1",
                transformation_count=1,
            )
        )
        db.add(
            HistoryORM(
                id="sess-1-h1",
                session_id="sess-1",
                instruction="メイド服に着替える",
                image_path=str(image),
                feeling_text="恥ずかしい",
                after_description="1girl, brown hair, maid dress, standing",
                instruction_type="dress_up",
                created_at=datetime(2026, 9, 1, 10, 0, 0),
            )
        )
        db.add(
            SessionStatsORM(
                session_id="sess-1", bloom=30, shame=60, adaptation=10, nsfw_mode=0
            )
        )
        await db.commit()


async def test_session_thread_can_carry_a_character(
    service: CharacterChatService, isolated_db, data_dir, tmp_path: Path, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory, tmp_path / "start.png")
    record = await _create_preset(
        isolated_db.async_factory, name="サクラ", profile=PROFILE
    )
    thread = await service.create_session_thread(
        source_session_id="sess-1",
        source_history_id="sess-1-h1",
        character_preset_id=record.id,
    )
    assert thread["kind"] == "session"
    assert (thread["name"], thread["pronoun"]) == ("サクラ", "あたし")

    systems: list[str] = []
    _fake_llm(monkeypatch, systems)
    await _collect(service.stream_message(thread_id=thread["id"], content="やあ"))
    # セッションの経緯(変身回数)に、キャラクター設定を重ねる
    assert "これまでの変身回数" in systems[-1]
    assert "ユーザーが決めたキャラクター設定" in systems[-1]
    assert "港町の喫茶店で働いている。" in systems[-1]

    # 紐づけを外すと、名前と一人称はセッションの人物に戻る
    unlinked = await service.unlink_character(thread["id"])
    assert unlinked["character"] is None
    assert unlinked["name"] != "サクラ"


async def test_link_character_creates_preset_from_thread(
    service: CharacterChatService, isolated_db, data_dir, tmp_path: Path
) -> None:
    await _seed_session(isolated_db.async_factory, tmp_path / "start.png")
    thread = await service.create_session_thread(
        source_session_id="sess-1", source_history_id="sess-1-h1"
    )
    linked = await service.link_character(thread["id"], preset_id=None)
    assert linked["character"] is not None
    preset_id = linked["character"]["id"]
    async with isolated_db.async_factory() as db:
        created = await db.get(CharacterPreset, preset_id)
    assert created is not None
    assert created.name == thread["name"]
    assert "maid dress" in created.appearance_tags
    assert created.portrait_path is not None

    base = await service.get_or_create_base_thread()
    with pytest.raises(CharacterChatError) as caught:
        await service.link_character(base["id"], preset_id=preset_id)
    assert caught.value.code == "character_link_unsupported"


async def test_create_character_thread_rejects_unknown_preset(
    service: CharacterChatService,
) -> None:
    with pytest.raises(CharacterChatError) as caught:
        await service.create_character_thread("missing")
    assert caught.value.code == "character_not_found"


def test_character_persona_block_skips_empty_fields() -> None:
    text = character_persona_block(
        name="サクラ",
        pronoun="私",
        profile={"personality": "明るい"},
        language="ja",
    )
    assert "性格: 明るい" in text
    assert "口調" not in text
    assert "知識" not in text
    supplement = character_persona_block(
        name="サクラ", pronoun="私", profile={}, language="ja", supplement=True
    )
    assert supplement == ""


async def test_greeting_rows_are_character_messages(
    service: CharacterChatService, isolated_db, data_dir
) -> None:
    record = await _create_preset(
        isolated_db.async_factory, name="サクラ", profile=PROFILE
    )
    thread = await service.create_character_thread(record.id)
    async with isolated_db.async_factory() as db:
        rows = (
            (
                await db.execute(
                    select(CharacterChatMessage).where(
                        CharacterChatMessage.thread_id == thread["id"]
                    )
                )
            )
            .scalars()
            .all()
        )
    assert [(row.role, row.meta_json) for row in rows] == [
        ("character", '{"greeting": true}')
    ]


async def _character_thread_with_portrait(
    service: CharacterChatService, isolated_db, tmp_path: Path
) -> dict:
    record = await _create_preset(
        isolated_db.async_factory,
        name="サクラ",
        appearance_tags="1girl, pink hair, apron",
        profile=PROFILE,
    )
    image = tmp_path / "portrait.png"
    image.write_bytes(_png())
    async with isolated_db.async_factory() as db:
        preset = await db.get(CharacterPreset, record.id)
        attach_preset_portrait(preset, image, generated=True)
        await db.commit()
    return await service.create_character_thread(record.id)


async def test_expression_portraits_are_stored_and_go_stale(
    service: CharacterChatService, isolated_db, data_dir, tmp_path: Path, monkeypatch
) -> None:
    thread = await _character_thread_with_portrait(service, isolated_db, tmp_path)
    expression = AsyncMock(return_value=_png("green"))
    monkeypatch.setattr(chat_module, "generate_expression_bytes", expression)
    monkeypatch.setattr(chat_module, "resolve_image_provider", lambda: "openrouter")

    events = await _collect(
        service.stream_expression_portraits(
            thread["id"], expressions=["happy", "sad", "happy", "unknown"]
        )
    )
    assert [event["event"] for event in events] == [
        "status",
        "expression_image",
        "status",
        "expression_image",
        "complete",
    ]
    assert expression.await_args_list[0].kwargs["expression_tags"].startswith("smile")
    detail = await service.get_thread(thread["id"])
    assert set(detail["expression_portraits"]) == {"happy", "sad"}

    # 立ち絵が変わると、前の立ち絵から作った差分は使わない
    async with isolated_db.async_factory() as db:
        row = await db.get(CharacterChatThread, thread["id"])
        assert row is not None
        replacement = service._thread_dir(thread["id"]) / "source-other.png"
        replacement.write_bytes(_png("yellow"))
        row.portrait_path = service._stored_path(thread["id"], replacement.name)
        await db.commit()
    detail = await service.get_thread(thread["id"])
    assert detail["expression_portraits"] == {}


async def test_expression_portraits_require_a_portrait(
    service: CharacterChatService, isolated_db, data_dir
) -> None:
    record = await _create_preset(
        isolated_db.async_factory, name="サクラ", profile=PROFILE
    )
    thread = await service.create_character_thread(record.id)
    with pytest.raises(CharacterChatError) as caught:
        await _collect(
            service.stream_expression_portraits(thread["id"], expressions=["happy"])
        )
    assert caught.value.code == "portrait_unavailable"


async def test_reply_carries_expression_when_2d_variants_exist(
    service: CharacterChatService, isolated_db, data_dir, tmp_path: Path, monkeypatch
) -> None:
    thread = await _character_thread_with_portrait(service, isolated_db, tmp_path)
    monkeypatch.setattr(
        chat_module, "generate_expression_bytes", AsyncMock(return_value=_png())
    )
    monkeypatch.setattr(chat_module, "resolve_image_provider", lambda: "openrouter")
    await _collect(
        service.stream_expression_portraits(thread["id"], expressions=["happy"])
    )
    systems: list[str] = []
    _fake_llm(monkeypatch, systems, reply="[expression=happy gesture=nod]\nうれしい")
    events = await _collect(
        service.stream_message(thread_id=thread["id"], content="やあ")
    )
    assert "[expression=<key> gesture=<key>]" in systems[-1]
    done = next(event for event in events if event["event"] == "chat_done")
    message = done["data"]["character_message"]
    assert message["content"] == "うれしい"
    assert message["meta"]["expression"] == "happy"


def test_fit_portrait_canvas_pads_to_portrait_size() -> None:
    from gateway.services.portrait_generation import (
        PORTRAIT_CANVAS_SIZE,
        fit_portrait_canvas,
    )

    buf = BytesIO()
    Image.new("RGBA", (100, 100), (255, 0, 0, 0)).save(buf, format="PNG")
    fitted = Image.open(BytesIO(fit_portrait_canvas(buf.getvalue())))
    assert fitted.size == PORTRAIT_CANVAS_SIZE
    assert fitted.mode == "RGB"
    # 透過の部分は白背景になる
    assert fitted.getpixel((416, 608)) == (255, 255, 255)
