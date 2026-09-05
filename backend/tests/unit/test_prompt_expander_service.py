"""PromptExpanderService と拡張/生成オーケストレーションのテスト。"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from gateway.databases.models import History, User
from gateway.databases.models import Session as SessionORM
from gateway.services import prompt_expander_service as pe
from gateway.services.image_generation import ImageGenerationResult


def _png(color: str = "red") -> bytes:
    buf = BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="PNG")
    return buf.getvalue()


def _png_base64(color: str = "red") -> str:
    import base64

    return "data:image/png;base64," + base64.b64encode(_png(color)).decode()


@pytest.fixture
async def factory(isolated_db, tmp_path: Path, monkeypatch):
    session_factory = isolated_db.async_factory
    async with session_factory() as db:
        db.add(User(id="default-user"))
        db.add(
            SessionORM(
                id="game-sess",
                user_id="default-user",
                current_image_path="img/start.png",
                character_id="char1",
            )
        )
        db.add(
            History(
                id="hist-1",
                session_id="game-sess",
                instruction="赤いドレス",
                image_path="history_images/hist-1.png",
                after_description="A girl in a red dress.",
            )
        )
        await db.commit()
    monkeypatch.setattr(
        pe.settings, "prompt_expander_images_dir", tmp_path / "pe_images"
    )
    monkeypatch.setattr(pe.settings, "novelai_api_key", "test-key")

    async def _no_global_memory(user_id: str = "default-user"):
        return None

    # グローバルメモリ参照は実 DB へ行くためテストでは常に空にする
    monkeypatch.setattr(pe.settings_service, "get_memory_text", _no_global_memory)
    return session_factory


@pytest.mark.asyncio
async def test_session_crud_and_order(factory):
    async with factory() as db:
        first = await pe.PromptExpanderService.create_session(db, title="  ")
        second = await pe.PromptExpanderService.create_session(db, title="着せ替え案")
        await db.commit()
        assert first.title == "Session 1"
        assert second.title == "着せ替え案"

    async with factory() as db:
        views = await pe.PromptExpanderService.list_sessions(db)
        assert [v.title for v in views] == ["着せ替え案", "Session 1"]
        assert views[0].entry_count == 0 and views[0].thumbnail_entry_id is None

    async with factory() as db:
        renamed = await pe.PromptExpanderService.rename_session(
            db, session_id=first.id, title="新タイトル"
        )
        await db.commit()
        assert renamed.title == "新タイトル"
        with pytest.raises(pe.PromptExpanderError) as exc:
            await pe.PromptExpanderService.rename_session(
                db, session_id=first.id, title=" "
            )
        assert exc.value.code == "invalid_title"

    async with factory() as db:
        assert await pe.PromptExpanderService.delete_session(db, session_id=second.id)
        assert not await pe.PromptExpanderService.delete_session(
            db, session_id="missing"
        )
        await db.commit()
        with pytest.raises(pe.PromptExpanderError) as exc:
            await pe.PromptExpanderService.get_session(db, session_id=second.id)
        assert exc.value.code == "session_not_found"


@pytest.mark.asyncio
async def test_upload_entry_writes_png_and_bumps_session(factory, tmp_path: Path):
    async with factory() as db:
        session = await pe.PromptExpanderService.create_session(db, title="s")
        await db.commit()
        before = session.updated_at

    async with factory() as db:
        entry = await pe.PromptExpanderService.add_uploaded_entry(
            db, session_id=session.id, image_base64=_png_base64(), instruction="参考"
        )
        await db.commit()
        assert entry.kind == "uploaded"
        assert entry.instruction == "参考"
        path = pe.resolve_entry_image_file(entry)
        assert path is not None and path.is_file()
        assert path.parent == tmp_path / "pe_images" / session.id
        assert entry.image_path.endswith(f"{session.id}/{entry.id}.png")

    async with factory() as db:
        views = await pe.PromptExpanderService.list_sessions(db)
        assert views[0].entry_count == 1
        assert views[0].thumbnail_entry_id == entry.id
        assert views[0].updated_at >= before
        view = pe.entry_to_dict(
            await pe.PromptExpanderService.get_entry(db, entry_id=entry.id)
        )
        assert view["image_url"] == f"/prompt-expander/images/{entry.id}"
        assert view["character_prompts"] == []
        assert view["nsfw"] is None

    async with factory() as db:
        with pytest.raises(pe.PromptExpanderError) as exc:
            await pe.PromptExpanderService.add_uploaded_entry(
                db, session_id=session.id, image_base64="bm90IGFuIGltYWdl"
            )
        assert exc.value.code == "invalid_image"


@pytest.mark.asyncio
async def test_delete_entry_and_session_images(factory, tmp_path: Path):
    async with factory() as db:
        session = await pe.PromptExpanderService.create_session(db, title="s")
        e1 = await pe.PromptExpanderService.add_uploaded_entry(
            db, session_id=session.id, image_base64=_png_base64()
        )
        e2 = await pe.PromptExpanderService.add_uploaded_entry(
            db, session_id=session.id, image_base64=_png_base64("blue")
        )
        await db.commit()

    async with factory() as db:
        paths = await pe.PromptExpanderService.delete_entry(db, entry_id=e1.id)
        await db.commit()
    for path in paths:
        pe.remove_entry_image(path)
    assert not (tmp_path / "pe_images" / session.id / f"{e1.id}.png").exists()
    assert (tmp_path / "pe_images" / session.id / f"{e2.id}.png").exists()

    async with factory() as db:
        await pe.PromptExpanderService.delete_session(db, session_id=session.id)
        await db.commit()
    pe.remove_session_images(session.id)
    assert not (tmp_path / "pe_images" / session.id).exists()
    async with factory() as db:
        items, total = await pe.PromptExpanderService.list_entries(db)
        assert total == 0 and items == []


@pytest.mark.asyncio
async def test_settings_roundtrip_and_leniency(factory):
    async with factory() as db:
        current = await pe.PromptExpanderService.get_settings(db)
        assert current.text_model == "glm-4-6"
        assert current.confirm_before_generate is True
        saved = await pe.PromptExpanderService.save_settings(
            db,
            patch={
                "text_model": "xialong-v1",
                "image_model": "nai-diffusion-5-full",
                "i2i_strength": 0.55,
                "seed": 42,
                "memory_text": "  金髪が好き  ",
                "use_memory": True,
                "unknown_key": "ignored",
            },
        )
        await db.commit()
        assert saved.text_model == "xialong-v1"
        assert saved.image_model == "nai-diffusion-5-full"
        assert saved.i2i_strength == 0.55
        assert saved.seed == 42
        assert saved.memory_text == "金髪が好き"

    async with factory() as db:
        reloaded = await pe.PromptExpanderService.get_settings(db)
        assert reloaded.seed == 42 and reloaded.use_memory is True
        cleared = await pe.PromptExpanderService.save_settings(db, patch={"seed": None})
        await db.commit()
        assert cleared.seed is None
        assert cleared.text_model == "xialong-v1"

    # 壊れた保存値は既定へ倒す（他のキーは残す）
    async with factory() as db:
        user = await db.get(User, "default-user")
        user.prompt_expander_settings_json = json.dumps(
            {
                "text_model": "gpt",
                "image_model": "x",
                "i2i_strength": 5,
                "use_memory": True,
            }
        )
        await db.commit()
    async with factory() as db:
        lenient = await pe.PromptExpanderService.get_settings(db)
        assert lenient.text_model == "glm-4-6"
        assert lenient.image_model == "nai-diffusion-4-5-full"
        assert lenient.i2i_strength == pe.DEFAULT_PROMPT_EXPANDER_I2I_STRENGTH
        assert lenient.use_memory is True


@pytest.mark.asyncio
async def test_resolve_source_variants(factory, monkeypatch, tmp_path: Path):
    hist_img = tmp_path / "hist-1.png"
    hist_img.write_bytes(_png("green"))
    fake_history = SimpleNamespace(
        id="hist-1",
        session_id="game-sess",
        image_path=str(hist_img),
        after_description="A girl in a red dress.",
        before_description="before",
    )

    async def _get_history(history_id: str):
        return fake_history if history_id == "hist-1" else None

    monkeypatch.setattr(pe.session_store, "get_history_by_id", _get_history)
    monkeypatch.setattr(
        pe.session_store, "resolve_history_image_file", lambda h: Path(h.image_path)
    )

    async with factory() as db:
        session = await pe.PromptExpanderService.create_session(db, title="s")
        uploaded = await pe.PromptExpanderService.add_uploaded_entry(
            db, session_id=session.id, image_base64=_png_base64()
        )
        await db.commit()

    async with factory() as db:
        none = await pe.resolve_source(db, source_kind="none")
        assert none.image_bytes is None

        history = await pe.resolve_source(
            db, source_kind="history", source_history_id="hist-1"
        )
        assert history.image_bytes == _png("green")
        assert history.context_description == "A girl in a red dress."
        meta_only = await pe.resolve_source(
            db, source_kind="history", source_history_id="hist-1", load_image=False
        )
        assert meta_only.image_bytes is None

        with pytest.raises(pe.PromptExpanderError) as exc:
            await pe.resolve_source(db, source_kind="history", source_history_id="nope")
        assert exc.value.code == "history_not_found"

        entry = await pe.resolve_source(
            db, source_kind="entry", source_entry_id=uploaded.id
        )
        assert entry.image_bytes is not None
        assert entry.current_prompt is None

        upload = await pe.resolve_source(
            db, source_kind="upload", source_image=_png_base64("blue")
        )
        assert upload.image_bytes is not None

        with pytest.raises(pe.PromptExpanderError) as exc:
            await pe.resolve_source(db, source_kind="entry")
        assert exc.value.code == "invalid_source"


@pytest.mark.asyncio
async def test_generate_entry_calls_novelai_raw_and_persists(
    factory, tmp_path: Path, monkeypatch
):
    generate_mock = AsyncMock(
        return_value=ImageGenerationResult(
            images=[_png("purple")],
            provider="novelai",
            model="nai-diffusion-5-full",
            seed=123,
        )
    )
    monkeypatch.setattr(pe.image_service, "generate_image", generate_mock)

    async with factory() as db:
        session = await pe.PromptExpanderService.create_session(db, title="s")
        await db.commit()

    outcome = await pe.generate_entry(
        session.id,
        pe.GenerateParams(
            prompt="銀髪の少女が、赤いドレスを着ている。",
            negative_prompt="眼鏡",
            character_prompts=["1girl, silver hair", "", "1boy"],
            character_mode=True,
            instruction="赤いドレスにして",
            positive_expand_mode="japanese",
            image_model="nai-diffusion-5-full",
            text_model="glm-4-6",
            image_size="square",
            seed=None,
        ),
    )
    kwargs = generate_mock.await_args.kwargs
    assert generate_mock.await_args.args == ("銀髪の少女が、赤いドレスを着ている。",)
    assert kwargs["raw_prompt"] is True
    assert kwargs["provider_override"] == "novelai"
    assert kwargs["novelai_model_override"] == "nai-diffusion-5-full"
    assert kwargs["size_override"] == "square"
    assert kwargs["nsfw_mode"] is True
    assert kwargs["negative_prompt"] == "眼鏡"
    assert kwargs["image_bytes"] is None
    assert [c["prompt"] for c in kwargs["characters"]] == ["1girl, silver hair", "1boy"]

    entry = outcome.entry
    assert entry["kind"] == "generated"
    assert entry["seed"] == 123
    assert entry["character_prompts"] == ["1girl, silver hair", "1boy"]
    assert entry["positive_expand_mode"] == "japanese"
    assert entry["instruction"] == "赤いドレスにして"
    assert entry["source_kind"] == "none"
    assert entry["i2i_strength"] is None
    assert entry["nsfw"] is True
    assert (
        tmp_path / "pe_images" / session.id / f"{entry['id']}.png"
    ).read_bytes() == _png("purple")

    async with factory() as db:
        items, total = await pe.PromptExpanderService.list_entries(db)
        assert total == 1 and items[0].id == entry["id"]
        views = await pe.PromptExpanderService.list_sessions(db)
        assert views[0].entry_count == 1


@pytest.mark.asyncio
async def test_generate_entry_i2i_from_entry_and_limits(factory, monkeypatch):
    generate_mock = AsyncMock(
        return_value=ImageGenerationResult(
            images=[_png("purple")],
            provider="novelai",
            model="nai-diffusion-4-5-curated",
            seed=7,
        )
    )
    monkeypatch.setattr(pe.image_service, "generate_image", generate_mock)
    async with factory() as db:
        session = await pe.PromptExpanderService.create_session(db, title="s")
        source = await pe.PromptExpanderService.add_uploaded_entry(
            db, session_id=session.id, image_base64=_png_base64("blue")
        )
        await db.commit()

    outcome = await pe.generate_entry(
        session.id,
        pe.GenerateParams(
            prompt="1girl",
            image_model="nai-diffusion-4-5-curated",
            source_kind="entry",
            source_entry_id=source.id,
            i2i_strength=0.6,
            i2i_noise=0.0,
            seed=5,
        ),
    )
    kwargs = generate_mock.await_args.kwargs
    assert kwargs["image_bytes"] == _png("blue")
    assert kwargs["i2i_strength_override"] == 0.6
    assert kwargs["i2i_noise_override"] == 0.0
    assert kwargs["nsfw_mode"] is False
    assert kwargs["seed"] == 5
    assert outcome.entry["source_kind"] == "entry"
    assert outcome.entry["source_entry_id"] == source.id
    assert outcome.entry["i2i_strength"] == 0.6
    assert outcome.entry["nsfw"] is False

    with pytest.raises(pe.PromptExpanderError) as exc:
        await pe.generate_entry(
            session.id,
            pe.GenerateParams(
                prompt="x",
                image_model="nai-diffusion-4-5-full",
                character_prompts=[f"c{i}" for i in range(7)],
            ),
        )
    assert exc.value.code == "too_many_characters"

    with pytest.raises(pe.PromptExpanderError) as exc:
        await pe.generate_entry("missing", pe.GenerateParams(prompt="x"))
    assert exc.value.code == "session_not_found"

    generate_mock.side_effect = RuntimeError("boom")
    with pytest.raises(pe.PromptExpanderError) as exc:
        await pe.generate_entry(session.id, pe.GenerateParams(prompt="x"))
    assert exc.value.code == "image_failed"


@pytest.mark.asyncio
async def test_expand_prompts_modes_and_memory(factory, monkeypatch):
    calls: list[tuple[str, str, dict]] = []

    async def _fake_generate_text(system_prompt, user_prompt, **kwargs):
        calls.append((system_prompt, user_prompt, kwargs))
        if '"base_prompt"' in system_prompt:
            return SimpleNamespace(
                content='```json\n{"base_prompt":"2girls, cafe","character_prompts":["1girl, a","1girl, b"]}\n```',
                cost_usd=None,
            )
        if "negative prompt" in system_prompt.lower()[:200]:
            return SimpleNamespace(content="glasses, hat", cost_usd=None)
        return SimpleNamespace(content="1girl, red dress\n", cost_usd=None)

    monkeypatch.setattr(pe.llm_service, "generate_text", _fake_generate_text)

    async with factory() as db:
        await pe.PromptExpanderService.save_settings(
            db, patch={"memory_text": "金髪が好き", "use_memory": True}
        )
        session = await pe.PromptExpanderService.create_session(db, title="s")
        await db.commit()

    result = await pe.expand_prompts(
        pe.ExpandParams(
            instruction="赤いドレスにする",
            image_model="nai-diffusion-4-5-full",
            text_model="glm-4-6",
        )
    )
    assert (
        result.positive_prompt
        == "1girl, red dress, moe, anime, very aesthetic, best quality"
    )
    assert result.character_prompts is None
    assert result.negative_prompt is None
    system, user, kwargs = calls[-1]
    assert kwargs == {
        "provider_override": "novelai",
        "novelai_model_override": "glm-4-6",
    }
    assert "金髪が好き" in system and "最優先指示" in system
    assert "Adult content tags are allowed only" in system
    assert "None (new prompt)" in user

    # メモリ OFF なら system に載らない / curated は SAFE ルール
    async with factory() as db:
        await pe.PromptExpanderService.save_settings(db, patch={"use_memory": False})
        await db.commit()
    await pe.expand_prompts(
        pe.ExpandParams(
            instruction="x",
            image_model="nai-diffusion-5-curated",
            text_model="xialong-v1",
        )
    )
    system, _, kwargs = calls[-1]
    assert "金髪が好き" not in system
    assert "Adult or explicit tags are disabled" in system
    assert kwargs["novelai_model_override"] == "xialong-v1"

    # キャラモード + ネガティブ + 作業欄の現在値
    result = await pe.expand_prompts(
        pe.ExpandParams(
            instruction="カフェで二人",
            character_mode=True,
            expand_negative=True,
            negative_instruction="眼鏡と帽子を出さない",
            image_model="nai-diffusion-5-full",
            text_model="glm-4-6",
            current_prompt="1girl, park",
            current_character_prompts=["1girl, black hair"],
            current_negative="lowres",
        )
    )
    assert (
        result.positive_prompt
        == "2girls, cafe, moe, anime, very aesthetic, best quality"
    )
    assert result.character_prompts == ["1girl, a", "1girl, b"]
    assert result.negative_prompt == "glasses, hat"
    positive_system, positive_user, _ = calls[-2]
    assert "between 1 and 22" in positive_system
    assert "Current positive prompt:\n1girl, park" in positive_user
    assert "Current character prompts:\n1. 1girl, black hair" in positive_user
    _, negative_user, _ = calls[-1]
    assert "Current negative prompt:\nlowres" in negative_user

    # 参照元エントリのプロンプトを引き継ぐ / 引き継がない
    async with factory() as db:
        from gateway.databases.models import PromptExpanderEntry

        db.add(
            PromptExpanderEntry(
                id="src-entry",
                session_id=session.id,
                kind="generated",
                final_prompt="1girl, blue kimono",
                final_negative_prompt="hat",
                character_prompts_json='["1girl, blue kimono"]',
                image_model="nai-diffusion-5-full",
                image_path="x.png",
            )
        )
        await db.commit()
    await pe.expand_prompts(
        pe.ExpandParams(
            instruction="笑顔に",
            image_model="nai-diffusion-5-full",
            text_model="glm-4-6",
            source_kind="entry",
            source_entry_id="src-entry",
        )
    )
    assert "Current positive prompt:\n1girl, blue kimono" in calls[-1][1]
    await pe.expand_prompts(
        pe.ExpandParams(
            instruction="笑顔に",
            image_model="nai-diffusion-5-full",
            text_model="glm-4-6",
            source_kind="entry",
            source_entry_id="src-entry",
            inherit_source_prompts=False,
        )
    )
    assert "None (new prompt)" in calls[-1][1]

    with pytest.raises(pe.PromptExpanderError) as exc:
        await pe.expand_prompts(
            pe.ExpandParams(
                instruction="x", text_model="gpt-4", image_model="nai-diffusion-5-full"
            )
        )
    assert exc.value.code == "invalid_text_model"


@pytest.mark.asyncio
async def test_expand_invalid_llm_output_and_suggest(factory, monkeypatch):
    monkeypatch.setattr(
        pe.llm_service,
        "generate_text",
        AsyncMock(return_value=SimpleNamespace(content="not json", cost_usd=None)),
    )
    with pytest.raises(pe.PromptExpanderError) as exc:
        await pe.expand_prompts(
            pe.ExpandParams(
                instruction="x",
                character_mode=True,
                image_model="nai-diffusion-5-full",
                text_model="glm-4-6",
            )
        )
    assert exc.value.code == "invalid_llm_output"

    # メモリが無ければ提案できない
    with pytest.raises(pe.PromptExpanderError) as exc:
        await pe.suggest_character_prompts(
            text_model="glm-4-6",
            image_model="nai-diffusion-5-full",
            mode="tags",
            count=2,
        )
    assert exc.value.code == "memory_empty"

    # use_memory ON のときだけグローバルメモリへフォールバックする
    async def _global_memory(user_id="default-user"):
        return "銀髪が好き"

    monkeypatch.setattr(pe.settings_service, "get_memory_text", _global_memory)
    async with factory() as db:
        await pe.PromptExpanderService.save_settings(db, patch={"use_memory": True})
        await db.commit()
    monkeypatch.setattr(
        pe.llm_service,
        "generate_text",
        AsyncMock(
            return_value=SimpleNamespace(
                content='{"suggestions":[{"title":"銀髪","prompt":"1girl, silver hair"},{"title":"金髪","prompt":"1girl, blonde"}]}',
                cost_usd=None,
            )
        ),
    )
    result = await pe.suggest_character_prompts(
        text_model="glm-4-6", image_model="nai-diffusion-5-full", mode="tags", count=2
    )
    assert [s["prompt"] for s in result.suggestions] == [
        "1girl, silver hair",
        "1girl, blonde",
    ]
    system = pe.llm_service.generate_text.await_args.args[0]
    assert "銀髪が好き" in system and "propose 2 favorite" in system


async def test_expand_prompts_manga_mode(factory, monkeypatch):
    """漫画モードは V5 専用で、JSON をタグ見出し + コマ説明に結合する。"""
    calls: list[tuple[str, str]] = []

    async def _fake_generate_text(system_prompt, user_prompt, **kwargs):
        calls.append((system_prompt, user_prompt))
        return SimpleNamespace(
            content=(
                '{"base_tags":"1boy, 1girl, japanese text, text, speech bubble, border",'
                '"panel_description":"There are two comic panels. The first panel shows a boy. The second panel shows a girl.",'
                '"character_prompts":["boy, short hair, There\'s a speech bubble next to the boy that says \\"えっ\\""]}'
            ),
            cost_usd=None,
        )

    monkeypatch.setattr(pe.llm_service, "generate_text", _fake_generate_text)

    manga = pe.MangaOptions(panel_count=2, layout="vertical", text_language="ja")
    result = await pe.expand_prompts(
        pe.ExpandParams(
            instruction="男が女になる2コマ漫画",
            character_mode=True,
            image_model="nai-diffusion-5-full",
            text_model="glm-4-6",
            manga=manga,
        )
    )
    assert result.positive_prompt == (
        "1boy, 1girl, japanese text, text, speech bubble, border, "
        "moe, anime, very aesthetic, best quality, "
        "There are two comic panels. The first panel shows a boy. "
        "The second panel shows a girl."
    )
    assert result.character_prompts == [
        'boy, short hair, There\'s a speech bubble next to the boy that says "えっ"'
    ]
    system, user = calls[-1]
    assert "Describe exactly 2 comic panels." in system
    assert "stacked vertically" in system
    assert "Never create before/after panels" not in system
    assert user.endswith("does not explicitly change.")

    # キャラクターモード OFF なら character_prompts は返さない。
    # 日本語モードでも漫画モードは英語構成（品質タグ補完あり）で、system も英語指定
    result = await pe.expand_prompts(
        pe.ExpandParams(
            instruction="男が女になる2コマ漫画",
            positive_mode="japanese",
            character_mode=False,
            image_model="nai-diffusion-5-curated",
            text_model="glm-4-6",
            manga=pe.MangaOptions(),
        )
    )
    assert result.character_prompts is None
    assert result.positive_prompt.startswith(
        "1boy, 1girl, japanese text, text, speech bubble, border, moe, anime"
    )
    system, _ = calls[-1]
    assert "natural English prose" in system
    assert "natural Japanese prose" not in system

    # V4.5 では拒否（LLM は呼ばれない）
    before = len(calls)
    with pytest.raises(pe.PromptExpanderError) as exc_info:
        await pe.expand_prompts(
            pe.ExpandParams(
                instruction="2コマ漫画",
                image_model="nai-diffusion-4-5-full",
                text_model="glm-4-6",
                manga=pe.MangaOptions(),
            )
        )
    assert exc_info.value.code == "manga_requires_v5"
    assert len(calls) == before


async def test_settings_manga_fields_roundtrip(factory):
    async with factory() as db:
        current = await pe.PromptExpanderService.get_settings(db)
        assert current.manga_mode is False
        assert current.manga_panel_count == 0
        assert current.manga_layout == "auto"
        assert current.manga_dialogue is True
        assert current.manga_text_language == "auto"
        assert current.manga_sound_effects is True
        assert current.manga_reading_direction == "rtl"
        saved = await pe.PromptExpanderService.save_settings(
            db,
            patch={
                "manga_mode": True,
                "manga_panel_count": 4,
                "manga_layout": "horizontal",
                "manga_dialogue": False,
                "manga_text_language": "ja",
                "manga_sound_effects": False,
                "manga_reading_direction": "ltr",
            },
        )
        await db.commit()
        assert saved.manga_mode is True
        assert saved.manga_panel_count == 4
        assert saved.manga_layout == "horizontal"
        assert saved.manga_dialogue is False
        assert saved.manga_text_language == "ja"
        assert saved.manga_sound_effects is False
        assert saved.manga_reading_direction == "ltr"
        # 不正値は既定へ倒す
        saved = await pe.PromptExpanderService.save_settings(
            db,
            patch={
                "manga_panel_count": 99,
                "manga_layout": "diagonal",
                "manga_text_language": "fr",
                "manga_reading_direction": "ttb",
            },
        )
        await db.commit()
        assert saved.manga_panel_count == 6
        assert saved.manga_layout == "auto"
        assert saved.manga_text_language == "auto"
        assert saved.manga_reading_direction == "rtl"


async def test_generate_entry_persists_manga_flags_only_for_v5(
    factory, tmp_path: Path, monkeypatch
):
    generate_mock = AsyncMock(
        return_value=ImageGenerationResult(
            images=[_png("purple")],
            provider="novelai",
            model="nai-diffusion-5-full",
            seed=1,
        )
    )
    monkeypatch.setattr(pe.image_service, "generate_image", generate_mock)
    async with factory() as db:
        session = await pe.PromptExpanderService.create_session(db, title="s")
        await db.commit()

    outcome = await pe.generate_entry(
        session.id,
        pe.GenerateParams(
            prompt="1girl, border, There are three comic panels.",
            image_model="nai-diffusion-5-full",
            manga_mode=True,
            manga_panel_count=3,
        ),
    )
    assert outcome.entry["manga_mode"] is True
    assert outcome.entry["manga_panel_count"] == 3

    # おまかせ（0）は None として保存
    outcome = await pe.generate_entry(
        session.id,
        pe.GenerateParams(
            prompt="1girl, border, There are two comic panels.",
            image_model="nai-diffusion-5-full",
            manga_mode=True,
            manga_panel_count=0,
        ),
    )
    assert outcome.entry["manga_mode"] is True
    assert outcome.entry["manga_panel_count"] is None

    # V4.5 では印を残さない
    outcome = await pe.generate_entry(
        session.id,
        pe.GenerateParams(
            prompt="1girl",
            image_model="nai-diffusion-4-5-full",
            manga_mode=True,
            manga_panel_count=3,
        ),
    )
    assert outcome.entry["manga_mode"] is False
    assert outcome.entry["manga_panel_count"] is None


@pytest.mark.asyncio
async def test_suggest_respects_use_memory_toggle(factory, monkeypatch):
    """メモリ OFF のときは PE メモリもグローバルメモリも提案に混ぜない。"""
    mock = AsyncMock(
        return_value=SimpleNamespace(
            content='{"suggestions":[{"title":"店員","prompt":"1girl, waitress"}]}',
            cost_usd=None,
        )
    )
    monkeypatch.setattr(pe.llm_service, "generate_text", mock)

    global_calls: list[str] = []

    async def _global_memory(user_id="default-user"):
        global_calls.append(user_id)
        return "グローバルの好み"

    monkeypatch.setattr(pe.settings_service, "get_memory_text", _global_memory)
    async with factory() as db:
        await pe.PromptExpanderService.save_settings(
            db, patch={"memory_text": "PE の好み", "use_memory": False}
        )
        await db.commit()

    # OFF のまま下書きだけで提案する（メモリはどちらも載らない）
    await pe.suggest_character_prompts(
        text_model="glm-4-6",
        image_model="nai-diffusion-5-full",
        mode="tags",
        count=1,
        input_text="カフェで働く少女",
    )
    system = mock.await_args.args[0]
    assert "PE の好み" not in system
    assert "グローバルの好み" not in system
    assert "No preference memory is available" in system
    # グローバルメモリの取得自体を行わない
    assert global_calls == []

    # OFF かつ下書きも無ければ従来どおり memory_empty
    with pytest.raises(pe.PromptExpanderError) as exc:
        await pe.suggest_character_prompts(
            text_model="glm-4-6",
            image_model="nai-diffusion-5-full",
            mode="tags",
            count=1,
        )
    assert exc.value.code == "memory_empty"

    # ON にすれば PE メモリが載る
    async with factory() as db:
        await pe.PromptExpanderService.save_settings(db, patch={"use_memory": True})
        await db.commit()
    await pe.suggest_character_prompts(
        text_model="glm-4-6",
        image_model="nai-diffusion-5-full",
        mode="tags",
        count=1,
    )
    assert "PE の好み" in mock.await_args.args[0]


@pytest.mark.asyncio
async def test_suggest_uses_input_text_and_relaxes_memory_guard(factory, monkeypatch):
    mock = AsyncMock(
        return_value=SimpleNamespace(
            content='{"suggestions":[{"title":"店員","prompt":"1girl, waitress"}]}',
            cost_usd=None,
        )
    )
    monkeypatch.setattr(pe.llm_service, "generate_text", mock)

    # メモリが無くても下書きがあれば提案できる
    result = await pe.suggest_character_prompts(
        text_model="glm-4-6",
        image_model="nai-diffusion-5-full",
        mode="tags",
        count=1,
        input_text="  カフェで働く少女  ",
    )
    assert [s["prompt"] for s in result.suggestions] == ["1girl, waitress"]
    system, user = mock.await_args.args[0], mock.await_args.args[1]
    assert "Current prompt draft:\nカフェで働く少女" in user
    assert "No preference memory is available" in system
    assert "current prompt draft" in system

    # 空白だけの下書きはメモリ無しと同じ扱い
    with pytest.raises(pe.PromptExpanderError) as exc:
        await pe.suggest_character_prompts(
            text_model="glm-4-6",
            image_model="nai-diffusion-5-full",
            mode="tags",
            count=1,
            input_text="   ",
        )
    assert exc.value.code == "memory_empty"

    # メモリがあるときは下書きの偏りルールだけ付き、メモリ無しルールは付かない
    async with factory() as db:
        await pe.PromptExpanderService.save_settings(
            db, patch={"memory_text": "銀髪が好き", "use_memory": True}
        )
        await db.commit()
    await pe.suggest_character_prompts(
        text_model="glm-4-6",
        image_model="nai-diffusion-5-full",
        mode="tags",
        count=1,
        input_text="カフェ",
    )
    system, user = mock.await_args.args[0], mock.await_args.args[1]
    assert "銀髪が好き" in system
    assert "No preference memory is available" not in system
    assert "current prompt draft" in system
    assert user.startswith("Current prompt draft:\nカフェ")


@pytest.mark.asyncio
async def test_expand_replaces_false_friend_shorts_only_in_tag_modes(
    factory, monkeypatch
):
    def _set_llm(content: str):
        monkeypatch.setattr(
            pe.llm_service,
            "generate_text",
            AsyncMock(return_value=SimpleNamespace(content=content, cost_usd=None)),
        )

    _set_llm("1girl, shorts, smile")
    result = await pe.expand_prompts(
        pe.ExpandParams(
            instruction="白いショーツを穿いた少女",
            image_model="nai-diffusion-4-5-full",
            text_model="glm-4-6",
        )
    )
    assert result.positive_prompt == (
        "1girl, panties, smile, moe, anime, very aesthetic, best quality"
    )
    # 語彙注意はシステムプロンプトにも入る
    system = pe.llm_service.generate_text.await_args.args[0]
    assert "ショーツ" in system and "panties" in system

    # 指示に「ショーツ」が無ければ shorts はそのまま
    _set_llm("1girl, shorts, smile")
    result = await pe.expand_prompts(
        pe.ExpandParams(
            instruction="短パンの少女",
            image_model="nai-diffusion-4-5-full",
            text_model="glm-4-6",
        )
    )
    assert result.positive_prompt.startswith("1girl, shorts, smile")

    # 日本語文モードは対象外
    _set_llm("白いショーツ姿の少女が微笑む。")
    result = await pe.expand_prompts(
        pe.ExpandParams(
            instruction="白いショーツ",
            positive_mode="japanese",
            image_model="nai-diffusion-4-5-full",
            text_model="glm-4-6",
        )
    )
    assert result.positive_prompt == "白いショーツ姿の少女が微笑む。"
    system = pe.llm_service.generate_text.await_args.args[0]
    assert "Japanese vocabulary note" not in system

    # キャラクターモードでは base と各キャラクターの両方に掛かる（複数語タグは不変）
    _set_llm(
        '{"base_prompt":"2girls, shorts","character_prompts":["1girl, shorts","1girl, denim shorts"]}'
    )
    result = await pe.expand_prompts(
        pe.ExpandParams(
            instruction="ショーツの二人",
            character_mode=True,
            image_model="nai-diffusion-4-5-full",
            text_model="glm-4-6",
        )
    )
    assert result.positive_prompt.startswith("2girls, panties")
    assert result.character_prompts is not None
    assert result.character_prompts[0].startswith("1girl, panties")
    assert result.character_prompts[1].startswith("1girl, denim shorts")

    # ネガティブ（タグ）にも掛かる
    _set_llm("shorts, hat")
    result = await pe.expand_prompts(
        pe.ExpandParams(
            expand_positive=False,
            expand_negative=True,
            negative_instruction="ショーツは描かない",
            image_model="nai-diffusion-4-5-full",
            text_model="glm-4-6",
        )
    )
    assert result.negative_prompt == "panties, hat"


@pytest.mark.asyncio
async def test_expand_manga_notation_is_passed_and_enforced(factory, monkeypatch):
    calls: list[tuple[str, str]] = []

    async def _fake_generate_text(system_prompt, user_prompt, **kwargs):
        calls.append((system_prompt, user_prompt))
        # LLM がナレーション【三日後】を落とし、セリフだけ描いた想定
        return SimpleNamespace(
            content=(
                '{"base_tags":"1girl, japanese text, text, speech bubble, border",'
                '"panel_description":"There are two comic panels. The first panel, at the top right, shows a girl. '
                'There\'s a speech bubble next to the girl that says \\"え、これ私…？\\". The second panel shows her walking.",'
                '"character_prompts":[]}'
            ),
            cost_usd=None,
        )

    monkeypatch.setattr(pe.llm_service, "generate_text", _fake_generate_text)
    result = await pe.expand_prompts(
        pe.ExpandParams(
            instruction="①鏡を見る「え、これ私…？」\n②【三日後】街を歩く",
            image_model="nai-diffusion-5-full",
            text_model="glm-4-6",
            manga=pe.MangaOptions(text_language="ja"),
        )
    )
    system, user = calls[-1]
    assert "Describe exactly 2 comic panels, following the panel numbers" in system
    assert "Do not invent additional narration boxes" in system
    assert '1. panel 1, speech bubble: "え、これ私…？"' in user
    assert '2. panel 2, narration box: "三日後"' in user
    assert result.positive_prompt is not None
    assert result.positive_prompt.endswith(
        'In panel 2, there\'s a narration box at the top of the panel that reads "三日後".'
    )
    assert result.positive_prompt.count("え、これ私…？") == 1


@pytest.mark.asyncio
async def test_settings_manga_narration_roundtrip(factory):
    async with factory() as db:
        current = await pe.PromptExpanderService.get_settings(db)
        assert current.manga_narration is False
        saved = await pe.PromptExpanderService.save_settings(
            db, patch={"manga_narration": True}
        )
        await db.commit()
        assert saved.manga_narration is True
    async with factory() as db:
        assert (await pe.PromptExpanderService.get_settings(db)).manga_narration is True


@pytest.mark.asyncio
async def test_draft_manga_script(factory, monkeypatch):
    mock = AsyncMock(
        return_value=SimpleNamespace(
            content="①放課後の教室。彼女が鏡を見る「え…？」\n②体が変わっていく《ドクン》",
            cost_usd=None,
        )
    )
    monkeypatch.setattr(pe.llm_service, "generate_text", mock)
    async with factory() as db:
        await pe.PromptExpanderService.save_settings(
            db, patch={"memory_text": "銀髪が好き", "use_memory": True}
        )
        await db.commit()

    result = await pe.draft_manga_script(
        pe.MangaScriptParams(
            instruction="放課後、彼女が制服姿に変わってしまい戸惑う",
            image_model="nai-diffusion-5-full",
            text_model="glm-4-6",
            manga=pe.MangaOptions(panel_count=2, narration=True),
        )
    )
    assert (
        result.script
        == "①放課後の教室。彼女が鏡を見る「え…？」\n②体が変わっていく《ドクン》"
    )
    assert result.text_model == "glm-4-6"
    system, user = mock.await_args.args[:2]
    assert "Write exactly 2 panels." in system
    assert "Add a 【...】 narration box where" in system
    assert "銀髪が好き" in system
    assert user.startswith("Synopsis:\n放課後、彼女が制服姿に変わってしまい戸惑う")

    # V4.5 では使えない / 空のあらすじは不可 / 形式不正は invalid_llm_output
    with pytest.raises(pe.PromptExpanderError) as exc:
        await pe.draft_manga_script(
            pe.MangaScriptParams(
                instruction="x",
                image_model="nai-diffusion-4-5-full",
                text_model="glm-4-6",
            )
        )
    assert exc.value.code == "manga_requires_v5"
    with pytest.raises(pe.PromptExpanderError) as exc:
        await pe.draft_manga_script(
            pe.MangaScriptParams(
                instruction="  ",
                image_model="nai-diffusion-5-full",
                text_model="glm-4-6",
            )
        )
    assert exc.value.code == "invalid_request"
    mock.return_value = SimpleNamespace(content="コマ番号のない文章", cost_usd=None)
    with pytest.raises(pe.PromptExpanderError) as exc:
        await pe.draft_manga_script(
            pe.MangaScriptParams(
                instruction="x",
                image_model="nai-diffusion-5-full",
                text_model="glm-4-6",
            )
        )
    assert exc.value.code == "invalid_llm_output"


def test_merge_tags_is_idempotent():
    assert (
        pe.merge_tags("1girl, smile", ("white background", "no shadow"))
        == "1girl, smile, white background, no shadow"
    )
    # 既にあるタグは大文字小文字を問わず足さず、末尾のカンマも整える
    assert (
        pe.merge_tags("1girl, White Background,", ("white background", "no shadow"))
        == "1girl, White Background, no shadow"
    )
    assert pe.merge_tags("", ("multiple views",)) == "multiple views"
    once = pe.merge_tags("1girl", ("no shadow",))
    assert pe.merge_tags(once, ("no shadow",)) == once
    # 日本語自然文（V5）にもカンマ区切りで足す
    assert (
        pe.merge_tags("銀髪の少女が微笑んでいる。", ("transparent background",))
        == "銀髪の少女が微笑んでいる。, transparent background"
    )


def test_merge_tags_ignores_emphasis_syntax():
    """強調記法の有無で重複判定がぶれない（{{white background}} を二重に足さない）。"""
    assert (
        pe.merge_tags("1girl, white background", ("{{white background}}",))
        == "1girl, white background"
    )
    assert (
        pe.merge_tags("1girl, {{White Background}}", ("white background",))
        == "1girl, {{White Background}}"
    )
    # 数値強調も同じタグとして扱う
    assert (
        pe.merge_tags("1girl, 1.3::white background::", ("{{white background}}",))
        == "1girl, 1.3::white background::"
    )


def test_apply_transparent_background_by_model():
    prompt, negative = pe.apply_transparent_background(
        "1girl", "", "nai-diffusion-5-full"
    )
    assert prompt == "1girl, transparent background, no shadow"
    assert negative == "multiple views, reference sheet, character sheet, turnaround"
    prompt, negative = pe.apply_transparent_background(
        "1girl", "lowres", "nai-diffusion-4-5-curated"
    )
    assert prompt == "1girl, simple background, white background, no shadow"
    assert negative.startswith("lowres, multiple views")


def test_apply_transparent_background_emphasis():
    """V4.5 は背景タグだけを強調し、V5 はネイティブ透過なので強調しない。"""
    prompt, _ = pe.apply_transparent_background(
        "1girl", "", "nai-diffusion-4-5-full", 2
    )
    assert prompt == ("1girl, {{simple background}}, {{white background}}, no shadow")
    prompt, _ = pe.apply_transparent_background(
        "1girl", "", "nai-diffusion-4-5-full", 1
    )
    assert prompt == "1girl, {simple background}, {white background}, no shadow"
    # V5 は段数を渡しても素のまま
    prompt, _ = pe.apply_transparent_background("1girl", "", "nai-diffusion-5-full", 3)
    assert prompt == "1girl, transparent background, no shadow"


@pytest.mark.asyncio
async def test_generate_entry_inpaint_passes_mask_and_persists_it(factory, monkeypatch):
    """インペイントはマスクを生成へ渡し、同じ領域で作り直せるよう保存する。"""
    generate_mock = AsyncMock(
        return_value=ImageGenerationResult(
            images=[_png("purple")],
            provider="novelai",
            model="nai-diffusion-4-5-full-inpainting",
            seed=3,
        )
    )
    monkeypatch.setattr(pe.image_service, "generate_image", generate_mock)
    async with factory() as db:
        session = await pe.PromptExpanderService.create_session(db, title="s")
        base = await pe.PromptExpanderService.add_uploaded_entry(
            db, session_id=session.id, image_base64=_png_base64("green")
        )
        await db.commit()

    mask = _png_base64("white")
    outcome = await pe.generate_entry(
        session.id,
        pe.GenerateParams(
            prompt="1girl, smiling",
            image_model="nai-diffusion-4-5-full",
            source_kind="entry",
            source_entry_id=base.id,
            i2i_strength=0.8,
            inpaint_mask=mask,
        ),
    )
    kwargs = generate_mock.await_args.kwargs
    assert kwargs["mask_bytes"] == pe.decode_image_base64(mask)
    assert kwargs["image_bytes"] is not None
    entry = outcome.entry
    assert entry["inpaint"] is True
    assert entry["mask_url"] == f"/prompt-expander/entries/{entry['id']}/mask"
    saved = pe.entry_mask_file(session.id, entry["id"])
    assert saved.is_file()

    # 保存済みマスクは entry ID 指定で再利用できる（表情差分を作り続けるため）
    outcome2 = await pe.generate_entry(
        session.id,
        pe.GenerateParams(
            prompt="1girl, angry",
            image_model="nai-diffusion-4-5-full",
            source_kind="entry",
            source_entry_id=base.id,
            inpaint_mask_entry_id=entry["id"],
        ),
    )
    assert generate_mock.await_args.kwargs["mask_bytes"] == saved.read_bytes()
    assert outcome2.entry["inpaint"] is True

    # マスクなしの通常生成では mask_bytes を渡さず、印も付かない
    outcome3 = await pe.generate_entry(
        session.id,
        pe.GenerateParams(prompt="1girl", image_model="nai-diffusion-4-5-full"),
    )
    assert generate_mock.await_args.kwargs["mask_bytes"] is None
    assert outcome3.entry["inpaint"] is False
    assert outcome3.entry["mask_url"] is None


@pytest.mark.asyncio
async def test_generate_entry_inpaint_requires_source(factory, monkeypatch):
    """元画像が無ければインペイントは成立しないので、黙って i2i に落とさず拒否する。"""
    generate_mock = AsyncMock(
        return_value=ImageGenerationResult(images=[_png()], provider="novelai")
    )
    monkeypatch.setattr(pe.image_service, "generate_image", generate_mock)
    async with factory() as db:
        session = await pe.PromptExpanderService.create_session(db, title="s")
        await db.commit()

    with pytest.raises(pe.PromptExpanderError) as exc:
        await pe.generate_entry(
            session.id,
            pe.GenerateParams(
                prompt="1girl",
                image_model="nai-diffusion-4-5-full",
                inpaint_mask=_png_base64("white"),
            ),
        )
    assert exc.value.code == "inpaint_requires_source"
    generate_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_entry_removes_inpaint_mask(factory, monkeypatch, tmp_path: Path):
    generate_mock = AsyncMock(
        return_value=ImageGenerationResult(images=[_png()], provider="novelai", seed=1)
    )
    monkeypatch.setattr(pe.image_service, "generate_image", generate_mock)
    async with factory() as db:
        session = await pe.PromptExpanderService.create_session(db, title="s")
        base = await pe.PromptExpanderService.add_uploaded_entry(
            db, session_id=session.id, image_base64=_png_base64("green")
        )
        await db.commit()

    outcome = await pe.generate_entry(
        session.id,
        pe.GenerateParams(
            prompt="1girl",
            image_model="nai-diffusion-4-5-full",
            source_kind="entry",
            source_entry_id=base.id,
            inpaint_mask=_png_base64("white"),
        ),
    )
    entry_id = outcome.entry["id"]
    mask_path = pe.entry_mask_file(session.id, entry_id)
    assert mask_path.is_file()

    async with factory() as db:
        paths = await pe.PromptExpanderService.delete_entry(db, entry_id=entry_id)
        await db.commit()
    for path in paths:
        pe.remove_entry_image(path)
    assert not mask_path.exists()
    assert not pe.entry_image_file(session.id, entry_id).exists()


@pytest.mark.asyncio
async def test_generate_entry_passes_character_reference_on_v45(factory, monkeypatch):
    generate_mock = AsyncMock(
        return_value=ImageGenerationResult(
            images=[_png("purple")],
            provider="novelai",
            model="nai-diffusion-4-5-full",
            seed=7,
        )
    )
    monkeypatch.setattr(pe.image_service, "generate_image", generate_mock)
    async with factory() as db:
        session = await pe.PromptExpanderService.create_session(db, title="s")
        uploaded = await pe.PromptExpanderService.add_uploaded_entry(
            db, session_id=session.id, image_base64=_png_base64("green")
        )
        await db.commit()

    # upload 参照: bytes がそのまま渡り、エントリには種別と強度だけ残る（ID は無い）
    outcome = await pe.generate_entry(
        session.id,
        pe.GenerateParams(
            prompt="1girl, standing",
            image_model="nai-diffusion-4-5-full",
            reference_kind="upload",
            reference_image=_png_base64("blue"),
            reference_type="character&style",
            reference_strength=0.6,
            reference_fidelity=0.9,
        ),
    )
    refs = generate_mock.await_args.kwargs["character_references"]
    assert len(refs) == 1
    assert refs[0]["type"] == "character&style"
    assert refs[0]["strength"] == 0.6 and refs[0]["fidelity"] == 0.9
    assert isinstance(refs[0]["image"], bytes)
    assert refs[0]["image"] == pe.decode_image_base64(_png_base64("blue"))
    entry = outcome.entry
    assert entry["reference_kind"] == "upload"
    assert entry["reference_entry_id"] is None
    assert entry["reference_history_id"] is None
    assert entry["reference_type"] == "character&style"
    assert entry["reference_strength"] == 0.6
    assert entry["reference_fidelity"] == 0.9
    assert entry["transparent_background"] is False

    # entry 参照: 参照元 ID を記録し、i2i 元（image_bytes）とは独立
    outcome = await pe.generate_entry(
        session.id,
        pe.GenerateParams(
            prompt="1girl, sitting",
            image_model="nai-diffusion-4-5-curated",
            reference_kind="entry",
            reference_entry_id=uploaded.id,
        ),
    )
    kwargs = generate_mock.await_args.kwargs
    assert kwargs["image_bytes"] is None
    ref = kwargs["character_references"][0]
    assert ref["image"] == pe.entry_image_file(session.id, uploaded.id).read_bytes()
    assert ref["type"] == "character"
    assert ref["strength"] == 0.85 and ref["fidelity"] == 1.0
    assert outcome.entry["reference_kind"] == "entry"
    assert outcome.entry["reference_entry_id"] == uploaded.id
    assert outcome.entry["reference_type"] == "character"

    # 参照なしなら渡さない
    outcome = await pe.generate_entry(
        session.id,
        pe.GenerateParams(prompt="1girl", image_model="nai-diffusion-4-5-full"),
    )
    assert generate_mock.await_args.kwargs["character_references"] is None
    assert outcome.entry["reference_kind"] == "none"
    assert outcome.entry["reference_type"] is None


@pytest.mark.asyncio
async def test_generate_entry_rejects_reference_on_v5(factory, monkeypatch):
    generate_mock = AsyncMock()
    monkeypatch.setattr(pe.image_service, "generate_image", generate_mock)
    async with factory() as db:
        session = await pe.PromptExpanderService.create_session(db, title="s")
        await db.commit()
    with pytest.raises(pe.PromptExpanderError) as exc:
        await pe.generate_entry(
            session.id,
            pe.GenerateParams(
                prompt="1girl",
                image_model="nai-diffusion-5-full",
                reference_kind="upload",
                reference_image=_png_base64(),
            ),
        )
    assert exc.value.code == "precise_reference_requires_v45"
    generate_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_entry_transparent_background_suffix_by_model(
    factory, monkeypatch
):
    generate_mock = AsyncMock(
        return_value=ImageGenerationResult(
            images=[_png("purple")],
            provider="novelai",
            model="nai-diffusion-5-full",
            seed=1,
        )
    )
    monkeypatch.setattr(pe.image_service, "generate_image", generate_mock)
    async with factory() as db:
        session = await pe.PromptExpanderService.create_session(db, title="s")
        await db.commit()

    # V5: transparent background をネイティブ指示。保存値には足さない
    outcome = await pe.generate_entry(
        session.id,
        pe.GenerateParams(
            prompt="1girl, standing",
            negative_prompt="lowres",
            image_model="nai-diffusion-5-full",
            transparent_background=True,
        ),
    )
    assert generate_mock.await_args.args == (
        "1girl, standing, transparent background, no shadow",
    )
    assert (
        generate_mock.await_args.kwargs["negative_prompt"]
        == "lowres, multiple views, reference sheet, character sheet, turnaround"
    )
    assert outcome.entry["final_prompt"] == "1girl, standing"
    assert outcome.entry["final_negative_prompt"] == "lowres"
    assert outcome.entry["transparent_background"] is True

    # V4.5: 白背景で生成させ、切り抜きはフロント側
    outcome = await pe.generate_entry(
        session.id,
        pe.GenerateParams(
            prompt="1girl, standing",
            image_model="nai-diffusion-4-5-full",
            transparent_background=True,
        ),
    )
    assert generate_mock.await_args.args == (
        "1girl, standing, simple background, white background, no shadow",
    )
    assert (
        generate_mock.await_args.kwargs["negative_prompt"]
        == "multiple views, reference sheet, character sheet, turnaround"
    )
    assert outcome.entry["transparent_background"] is True

    # 漫画モード（V5）ではコマ枠を切り抜けないので無効
    outcome = await pe.generate_entry(
        session.id,
        pe.GenerateParams(
            prompt="1girl, border",
            image_model="nai-diffusion-5-full",
            manga_mode=True,
            transparent_background=True,
        ),
    )
    assert generate_mock.await_args.args == ("1girl, border",)
    assert generate_mock.await_args.kwargs["negative_prompt"] == ""
    assert outcome.entry["transparent_background"] is False
    assert outcome.entry["manga_mode"] is True

    # OFF なら従来どおり
    outcome = await pe.generate_entry(
        session.id,
        pe.GenerateParams(prompt="1girl", image_model="nai-diffusion-4-5-full"),
    )
    assert generate_mock.await_args.args == ("1girl",)
    assert outcome.entry["transparent_background"] is False


@pytest.mark.asyncio
async def test_settings_reference_and_transparent_roundtrip(factory):
    async with factory() as db:
        current = await pe.PromptExpanderService.get_settings(db)
        assert current.use_precise_reference is False
        assert current.reference_type == "character"
        assert current.reference_strength == 0.85
        assert current.reference_fidelity == 1.0
        assert current.transparent_background is False
        saved = await pe.PromptExpanderService.save_settings(
            db,
            patch={
                "use_precise_reference": True,
                "reference_type": "style",
                "reference_strength": 0.5,
                "reference_fidelity": 0.25,
                "transparent_background": True,
            },
        )
        await db.commit()
        assert saved.use_precise_reference is True
        assert saved.reference_type == "style"
        assert saved.reference_strength == 0.5
        assert saved.reference_fidelity == 0.25
        assert saved.transparent_background is True
        # 不正な種別は既定へ倒し、範囲外の強度は invalid_settings
        saved = await pe.PromptExpanderService.save_settings(
            db, patch={"reference_type": "vibe"}
        )
        assert saved.reference_type == "character"
        with pytest.raises(pe.PromptExpanderError) as exc:
            await pe.PromptExpanderService.save_settings(
                db, patch={"reference_strength": 1.5}
            )
        assert exc.value.code == "invalid_settings"
    # 壊れた保存値は該当キーだけ捨てる
    loaded = pe._settings_from_json(
        json.dumps({"reference_strength": "x", "transparent_background": True})
    )
    assert loaded.reference_strength == 0.85
    assert loaded.transparent_background is True


@pytest.mark.asyncio
async def test_expand_passes_transparent_rule_only_outside_manga(factory, monkeypatch):
    mock = AsyncMock(
        return_value=SimpleNamespace(
            content="1girl, red dress, moe, anime, very aesthetic, best quality",
            cost_usd=None,
        )
    )
    monkeypatch.setattr(pe.llm_service, "generate_text", mock)
    await pe.expand_prompts(
        pe.ExpandParams(
            instruction="赤いドレス",
            expand_positive=True,
            positive_mode="tags",
            image_model="nai-diffusion-4-5-full",
            text_model="glm-4-6",
            transparent_background=True,
        )
    )
    assert "Transparent background mode is ON" in mock.await_args.args[0]
    await pe.expand_prompts(
        pe.ExpandParams(
            instruction="赤いドレス",
            expand_positive=True,
            positive_mode="tags",
            image_model="nai-diffusion-4-5-full",
            text_model="glm-4-6",
        )
    )
    assert "Transparent background mode is ON" not in mock.await_args.args[0]
