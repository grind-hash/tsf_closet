"""play_with_stream の特性テスト（分解前後で SSE の並びと保存内容が変わらないことを固定する）。

LLM / 画像生成 / DB はすべて偽物に差し替え、指示タイプごとに
- 送出される StreamEvent の type の並び
- complete イベントの内容
- add_history / update_session / 属性・パラメータの保存内容
を検証する。数値の乱数は最小値に固定する。
"""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from gateway.models import SessionStats
from gateway.services import game_service as gs_module
from gateway.services.achievements import AchievementStats
from gateway.services.game_service import GameService
from gateway.services.llm_service import LLMServiceError
from gateway.settings.config import settings

SESSION_ID = "session-char"


class FakeSessionStore:
    """play_with_stream が触る session_store のメソッドだけを持つ記録付きの偽物。"""

    def __init__(
        self,
        *,
        user_settings: dict[str, Any] | None = None,
        self_profile: dict[str, Any] | None = None,
        latest_history: Any | None = None,
        attributes: list[str] | None = None,
        transformation_count: int = 2,
    ) -> None:
        self.user_settings = user_settings or {
            "nsfw_mode": False,
            "difficulty": "normal",
            "language": "ja",
            "novelai_text_model": None,
            "bloom_calc_method": "legacy",
        }
        self.self_profile = self_profile
        self.latest_history = latest_history
        self.attributes = list(attributes or [])
        self.stats = SessionStats.create_with_difficulty(SESSION_ID, "normal", False)
        self.transformation_count = transformation_count
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _record(self, name: str, **kwargs: Any) -> None:
        self.calls.append((name, kwargs))

    def calls_of(self, name: str) -> list[dict[str, Any]]:
        return [kwargs for called, kwargs in self.calls if called == name]

    async def get_user_settings(self):
        return dict(self.user_settings)

    async def get_self_profile(self):
        return self.self_profile

    async def select_history_as_base(self, history_id):
        return None

    async def get_latest_history(self, session_id):
        return self.latest_history

    async def get_session_attribute_texts(self, session_id):
        return list(self.attributes)

    async def get_or_create_session_stats(self, session_id):
        return copy.deepcopy(self.stats)

    async def get_recent_instructions(self, session_id, limit=20):
        return []

    async def get_session_timeline(self, session_id, limit=30):
        return []

    async def get_history(self, session_id):
        return []

    async def add_history(self, **kwargs):
        self._record("add_history", **kwargs)
        return SimpleNamespace(
            id="hist-1", image_path="history_images/hist-1.png", **kwargs
        )

    async def update_session(self, **kwargs):
        self._record("update_session", **kwargs)

    async def save_transformation_tag(self, **kwargs):
        self._record("save_transformation_tag", **kwargs)

    async def add_session_attribute(self, session_id, text):
        self._record("add_session_attribute", session_id=session_id, text=text)
        self.attributes.append(text)
        return {"id": "attr-1", "attribute_text": text}

    async def update_session_stats(self, stats):
        self._record("update_session_stats", stats=stats)
        self.stats = stats

    async def record_parameter_change_log(self, **kwargs):
        self._record("record_parameter_change_log", **kwargs)

    async def increment_transformation_count(self, session_id):
        self.transformation_count += 1
        self._record("increment_transformation_count", session_id=session_id)
        return self.transformation_count

    async def has_achieved_ending_for_session(self, session_id):
        return False

    async def get_session_tag_counts(self, session_id):
        return {}

    async def get_achieved_ending_ids(self):
        return []

    async def save_achieved_ending(self, ending_id, session_id):
        self._record("save_achieved_ending", ending_id=ending_id, session_id=session_id)

    async def update_history_surroundings(self, **kwargs):
        self._record("update_history_surroundings", **kwargs)


class Harness:
    def __init__(self, service: GameService, store: FakeSessionStore) -> None:
        self.service = service
        self.store = store
        self.image_calls: list[dict[str, Any]] = []
        self.text_calls: list[dict[str, Any]] = []
        self.feeling_calls: list[dict[str, Any]] = []


def _character() -> SimpleNamespace:
    return SimpleNamespace(
        id="char1",
        pronoun="僕",
        gender="man",
        personality="穏やか",
        description="黒髪の青年",
        base_tags="1boy, black hair",
    )


def _session(*, self_mode: bool = False, count: int = 2) -> SimpleNamespace:
    return SimpleNamespace(
        id=SESSION_ID, self_mode=self_mode, transformation_count=count
    )


def _build(
    monkeypatch: pytest.MonkeyPatch,
    *,
    provider: str = "selfhost",
    store: FakeSessionStore | None = None,
    session: SimpleNamespace | None = None,
    character: SimpleNamespace | None = None,
    feeling_chunks: list[str] | tuple[str, ...] = ("心境", "テキスト"),
    feeling_error: Exception | None = None,
    image_result: tuple[bytes, float | None, int | None] = (b"after-image", 0.5, 4242),
    image_error: Exception | None = None,
    novelai_prompt_json: dict[str, Any] | None = None,
) -> Harness:
    service = GameService()
    store = store or FakeSessionStore()
    harness = Harness(service, store)
    session = session or _session()
    character = character if character is not None else _character()

    monkeypatch.setattr(settings, "image_provider", provider)
    monkeypatch.setattr(settings, "image_description_provider", provider)
    monkeypatch.setattr(settings, "feeling_provider", provider)
    monkeypatch.setattr(settings, "enable_prompt_preview", False)
    monkeypatch.setattr(gs_module, "session_store", store)
    monkeypatch.setattr(
        gs_module.settings_service, "get_history_lookback_count", lambda _id: 10
    )
    monkeypatch.setattr(gs_module.random, "randint", lambda low, high: low)

    # 実績まわりは DB を触るので差し替える
    monkeypatch.setattr(
        gs_module,
        "classify_for_achievement",
        AsyncMock(return_value=SimpleNamespace(categories=["CROSS_DRESS"])),
    )
    monkeypatch.setattr(gs_module, "update_achievement_counts", lambda cats: None)
    monkeypatch.setattr(gs_module, "get_user_achievements", lambda: [])
    monkeypatch.setattr(gs_module, "get_global_stats", lambda: AchievementStats())
    monkeypatch.setattr(gs_module, "check_achievements", lambda *a, **k: [])
    monkeypatch.setattr(gs_module, "check_achievement", lambda *a, **k: False)
    monkeypatch.setattr(gs_module, "save_user_achievement", lambda *a, **k: None)

    monkeypatch.setattr(
        service,
        "_get_or_create_session_for_stream",
        AsyncMock(return_value=(session, character, b"before-image")),
    )
    monkeypatch.setattr(service, "_load_custom_session_metadata", lambda _id: {})
    monkeypatch.setattr(service, "_get_anlas_event", AsyncMock(return_value=None))
    monkeypatch.setattr(
        service, "_get_memory_priority_suffix", AsyncMock(return_value="")
    )

    async def fake_generate_image(*args: Any, **kwargs: Any):
        harness.image_calls.append({"args": args, **kwargs})
        if image_error is not None:
            raise image_error
        return image_result

    monkeypatch.setattr(service, "_generate_image", fake_generate_image)

    async def fake_feeling_stream(**kwargs: Any):
        harness.feeling_calls.append(kwargs)
        if feeling_error is not None:
            raise feeling_error
        for chunk in feeling_chunks:
            yield chunk

    async def fake_generate_text(**kwargs: Any):
        harness.text_calls.append(kwargs)
        return SimpleNamespace(content="generated text", cost_usd=0.01, provider="stub")

    async def fake_describe_image(**kwargs: Any):
        return SimpleNamespace(
            content="described image", cost_usd=0.03, provider="stub"
        )

    async def fake_edit_prompt(**kwargs: Any):
        harness.text_calls.append({"edit": kwargs})
        return SimpleNamespace(content="edit prompt", cost_usd=0.02, provider="stub")

    async def fake_novelai_prompt(**kwargs: Any):
        harness.text_calls.append({"novelai": kwargs})
        return json.dumps(
            novelai_prompt_json
            or {"character": "1boy, red dress", "scene": "scene tags"}
        )

    llm = gs_module.llm_service
    monkeypatch.setattr(llm, "generate_feeling_stream", fake_feeling_stream)
    monkeypatch.setattr(llm, "generate_text", fake_generate_text)
    monkeypatch.setattr(llm, "describe_image", fake_describe_image)
    monkeypatch.setattr(llm, "generate_image_edit_prompt", fake_edit_prompt)
    monkeypatch.setattr(llm, "generate_novelai_image_prompt", fake_novelai_prompt)
    return harness


async def _run(harness: Harness, **overrides: Any) -> list[Any]:
    params: dict[str, Any] = {
        "session_id": SESSION_ID,
        "character_id": "char1",
        "character_image": None,
        "instruction": "赤いドレスに着替える",
    }
    params.update(overrides)
    return [event async for event in harness.service.play_with_stream(**params)]


def _types(events: list[Any]) -> list[str]:
    return [event.type for event in events]


def _one(events: list[Any], event_type: str) -> Any:
    matches = [event for event in events if event.type == event_type]
    assert len(matches) == 1, f"expected one {event_type}, got {len(matches)}"
    return matches[0]


# ---------------------------------------------------------------------------
# dress_up（既定）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dress_up_event_sequence_and_persistence(monkeypatch) -> None:
    harness = _build(monkeypatch)
    events = await _run(harness)

    assert _types(events) == [
        "text",
        "text",
        "tags",
        "stats",
        "image",
        "cost",
        "complete",
    ]
    complete = _one(events, "complete").data
    assert complete == {
        "session_id": SESSION_ID,
        "transformation_count": 3,
        "before_desc": "described image",
        "after_desc": "赤いドレスに着替えるに変身した姿",
        "feeling_text": "心境テキスト",
        "history_id": "hist-1",
    }
    assert _one(events, "image").data == {
        "image": "YWZ0ZXItaW1hZ2U=",
        "history_id": "hist-1",
        "seed": 4242,
    }
    # describe 0.03 + edit prompt 0.02 + image 0.5
    assert _one(events, "cost").data["cost_usd"] == pytest.approx(0.55)
    stats = _one(events, "stats").data
    assert set(stats) == {
        "bloom",
        "shame",
        "adaptation",
        "bloom_delta",
        "shame_delta",
        "adaptation_delta",
        "passedCriticalPoints",
        "difficulty",
        "nsfwMode",
        "enablePromptPreview",
    }
    assert stats["difficulty"] == "normal"

    [history] = harness.store.calls_of("add_history")
    assert history["instruction"] == "赤いドレスに着替える"
    assert history["instruction_type"] == "dress_up"
    assert history["feeling_text"] == "心境テキスト"
    assert history["before_description"] == "described image"
    assert history["after_description"] == "赤いドレスに着替えるに変身した姿"
    assert history["image_data"] == b"after-image"
    assert history["seed"] == 4242
    assert harness.store.calls_of("update_session") == [
        {"session_id": SESSION_ID, "current_image_path": "history_images/hist-1.png"}
    ]
    assert (
        harness.store.calls_of("save_transformation_tag")[0]["history_id"] == "hist-1"
    )
    assert harness.store.calls_of("increment_transformation_count") == [
        {"session_id": SESSION_ID}
    ]
    log = harness.store.calls_of("record_parameter_change_log")[0]
    assert log["reason"] == "dress_up"
    assert [name for name, *_ in log["stat_changes"]] == [
        "bloom",
        "shame",
        "adaptation",
    ]
    # 画像は前画像を元に、編集プロンプトで 1 回だけ生成する
    assert len(harness.image_calls) == 1
    assert harness.image_calls[0]["args"][0] == b"before-image"
    assert harness.image_calls[0]["args"][1] == "edit prompt"
    assert harness.image_calls[0]["nsfw_mode"] is False
    # 心境ストリームは 1 回、feeling プロンプトに現在の説明が入る
    assert len(harness.feeling_calls) == 1
    assert "described image" in harness.feeling_calls[0]["user_prompt"]


@pytest.mark.asyncio
async def test_dress_up_feeling_error_yields_fallback_text(monkeypatch) -> None:
    harness = _build(monkeypatch, feeling_error=LLMServiceError("down"))
    events = await _run(harness)

    assert _types(events) == ["text", "tags", "stats", "image", "cost", "complete"]
    assert _one(events, "text").data == {"chunk": "(心境生成に失敗しました)"}
    assert _one(events, "complete").data["feeling_text"] == "(心境生成に失敗しました)"


@pytest.mark.asyncio
async def test_dress_up_image_error_emits_error_after_text(monkeypatch) -> None:
    harness = _build(monkeypatch, image_error=RuntimeError("gpu on fire"))
    events = await _run(harness)

    assert _types(events) == ["text", "text", "error"]
    assert "画像生成エラー: gpu on fire" in _one(events, "error").data["message"]
    assert harness.store.calls_of("add_history") == []
    assert harness.store.calls_of("update_session") == []


@pytest.mark.asyncio
async def test_dress_up_prompt_override_replaces_prompt_outside_novelai(
    monkeypatch,
) -> None:
    harness = _build(monkeypatch)
    await _run(harness, prompt_override="  custom prompt  ")

    assert harness.image_calls[0]["args"][1] == "custom prompt"


# ---------------------------------------------------------------------------
# reality
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reality_adds_attribute_and_boosts_parameters(monkeypatch) -> None:
    harness = _build(monkeypatch)
    events = await _run(
        harness,
        instruction="世界の常識が変わる",
        transformation_type="reality",
        instruction_type="reality_alter",
    )

    assert _types(events) == [
        "text",
        "text",
        "tags",
        "reality_attribute_added",
        "stats",
        "image",
        "cost",
        "complete",
    ]
    assert _one(events, "reality_attribute_added").data == {
        "attribute_id": "attr-1",
        "attribute_text": "[現実改変] 世界の常識が変わる",
    }
    assert harness.store.calls_of("add_session_attribute") == [
        {"session_id": SESSION_ID, "text": "[現実改変] 世界の常識が変わる"}
    ]
    complete = _one(events, "complete").data
    assert (
        complete["after_desc"] == "「世界の常識が変わる」という現実改変により変化した姿"
    )
    [history] = harness.store.calls_of("add_history")
    assert history["instruction_type"] == "reality_alter"
    assert harness.store.calls_of("record_parameter_change_log")[0]["reason"] == (
        "reality_alter"
    )
    # 現実改変は generate_text で編集プロンプトを作る（describe 0.03 + text 0.01 + image 0.5）
    assert _one(events, "cost").data["cost_usd"] == pytest.approx(0.54)
    assert harness.image_calls[0]["args"][1] == "generated text"


@pytest.mark.asyncio
async def test_reality_does_not_duplicate_existing_attribute(monkeypatch) -> None:
    store = FakeSessionStore(attributes=["[現実改変] 世界の常識が変わる"])
    harness = _build(monkeypatch, store=store)
    events = await _run(
        harness, instruction="世界の常識が変わる", transformation_type="reality"
    )

    assert "reality_attribute_added" not in _types(events)
    assert store.calls_of("add_session_attribute") == []


# ---------------------------------------------------------------------------
# self_mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_self_mode_skips_parameters_and_uses_profile(monkeypatch) -> None:
    store = FakeSessionStore(
        self_profile={"gender": "woman", "pronoun": "私", "personality": "強気"}
    )
    harness = _build(monkeypatch, store=store, session=_session(self_mode=True))
    events = await _run(harness)

    assert _types(events) == ["text", "text", "tags", "image", "cost", "complete"]
    assert store.calls_of("update_session_stats") == []
    assert store.calls_of("record_parameter_change_log") == []
    assert store.calls_of("increment_transformation_count") == [
        {"session_id": SESSION_ID}
    ]
    assert _one(events, "complete").data["transformation_count"] == 3
    # プロフィールの一人称・性別で心境を生成する
    assert "私" in harness.feeling_calls[0]["user_prompt"] or "強気" in (
        harness.feeling_calls[0]["system_prompt"]
        + harness.feeling_calls[0]["user_prompt"]
    )


# ---------------------------------------------------------------------------
# NovelAI Opus（character/scene の分離）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_novelai_opus_dress_up_splits_characters_and_skips_vision(
    monkeypatch,
) -> None:
    store = FakeSessionStore(
        latest_history=SimpleNamespace(
            after_description="1boy, previous prompt",
            feeling_text="前回",
            instruction="前回の指示",
        )
    )
    harness = _build(monkeypatch, provider="novelai", store=store)
    events = await _run(harness)

    assert _types(events) == [
        "text",
        "text",
        "tags",
        "stats",
        "image",
        "cost",
        "complete",
    ]
    call = harness.image_calls[0]
    # scene は品質タグ付きで、characters は JSON から分離される
    assert call["args"][1] == "scene tags, very aesthetic, best quality"
    assert call["characters"] == [{"prompt": "1boy, red dress", "position": (0.5, 0.5)}]
    assert call["novelai_image_model_override"] == "nai-diffusion-4-5-curated"
    complete = _one(events, "complete").data
    assert complete["before_desc"] == "1boy, previous prompt"
    assert complete["after_desc"] == "1boy, red dress"
    # Vision LLM は呼ばない（describe 0.03 は含まれない）。画像 0.5 のみ
    assert _one(events, "cost").data["cost_usd"] == pytest.approx(0.5)
    novelai_call = next(c["novelai"] for c in harness.text_calls if "novelai" in c)
    assert novelai_call["previous_prompt"] == "1boy, previous prompt"


@pytest.mark.asyncio
async def test_novelai_opus_dress_up_falls_back_to_flat_prompt(monkeypatch) -> None:
    harness = _build(monkeypatch, provider="novelai")

    async def broken_prompt(**kwargs: Any):
        return "not json at all"

    monkeypatch.setattr(
        gs_module.llm_service, "generate_novelai_image_prompt", broken_prompt
    )
    events = await _run(harness)

    call = harness.image_calls[0]
    assert call["args"][1] == "not json at all, very aesthetic, best quality"
    assert call["characters"] is None
    assert _one(events, "complete").data["after_desc"] == (
        "not json at all, very aesthetic, best quality"
    )


# ---------------------------------------------------------------------------
# action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_streams_text_and_scene_image(monkeypatch) -> None:
    store = FakeSessionStore(
        latest_history=SimpleNamespace(
            after_description="current look",
            feeling_text="前回のモノローグ",
            instruction="前回の行動",
        )
    )
    harness = _build(monkeypatch, store=store)
    events = await _run(harness, instruction="街を歩く", instruction_type="action")

    assert _types(events) == ["text", "text", "image", "cost", "complete"]
    complete = _one(events, "complete").data
    assert complete == {
        "session_id": SESSION_ID,
        "transformation_count": 2,
        "before_desc": "current look",
        "after_desc": "generated text",
        "feeling_text": "心境テキスト",
        "history_id": "hist-1",
    }
    [history] = harness.store.calls_of("add_history")
    assert history["instruction_type"] == "action"
    assert history["image_data"] == b"after-image"
    assert history["after_description"] == "generated text"
    # 行動は変身回数もパラメータも動かさない
    assert store.calls_of("increment_transformation_count") == []
    assert store.calls_of("update_session_stats") == []
    # 状況サマリー(0.01) + 編集プロンプト(0.01) + 画像(0.5)。describe は cost に入らない
    assert _one(events, "cost").data["cost_usd"] == pytest.approx(0.52)
    # 行動の i2i は既定 0.85 で強めに書き換える
    assert harness.image_calls[0]["inpaint_strength"] == 0.85


@pytest.mark.asyncio
async def test_action_image_error_keeps_previous_image(monkeypatch) -> None:
    store = FakeSessionStore(
        latest_history=SimpleNamespace(
            after_description="current look", feeling_text="", instruction="x"
        )
    )
    harness = _build(monkeypatch, store=store, image_error=RuntimeError("no image"))
    events = await _run(harness, instruction="街を歩く", instruction_type="action")

    assert _types(events) == ["text", "text", "cost", "complete"]
    [history] = store.calls_of("add_history")
    assert history["image_data"] == b"before-image"
    assert history["after_description"] == "current look"
    assert history["seed"] is None
    assert _one(events, "complete").data["after_desc"] == "current look"


@pytest.mark.asyncio
async def test_action_text_error_uses_fallback_chunk(monkeypatch) -> None:
    store = FakeSessionStore(
        latest_history=SimpleNamespace(
            after_description="current look", feeling_text="", instruction="x"
        )
    )
    harness = _build(monkeypatch, store=store, feeling_error=LLMServiceError("down"))
    events = await _run(harness, instruction="街を歩く", instruction_type="action")

    assert _types(events) == ["text", "image", "cost", "complete"]
    assert _one(events, "text").data == {"chunk": "(行動テキスト生成に失敗しました)"}


@pytest.mark.asyncio
async def test_action_surroundings_image_on_novelai(monkeypatch, tmp_path) -> None:
    store = FakeSessionStore(
        latest_history=SimpleNamespace(
            after_description="current look", feeling_text="", instruction="x"
        )
    )
    harness = _build(monkeypatch, provider="novelai", store=store)
    monkeypatch.setattr(settings, "history_images_dir", tmp_path / "history_images")
    monkeypatch.setattr(
        harness.service,
        "_generate_surroundings_image",
        AsyncMock(return_value=(b"surroundings", 0.2, 77)),
    )
    events = await _run(
        harness,
        instruction="街を歩く",
        instruction_type="action",
        enable_surroundings_image=True,
    )

    assert _types(events) == [
        "text",
        "text",
        "image",
        "cost",
        "surroundings_image",
        "cost",
        "complete",
    ]
    surroundings = _one(events, "surroundings_image").data
    assert surroundings["history_id"] == "hist-1"
    assert surroundings["seed"] == 77
    [update] = store.calls_of("update_history_surroundings")
    assert update["history_id"] == "hist-1"
    assert update["surroundings_image_path"].startswith("history_images/surroundings_")
    costs = [event.data["cost_usd"] for event in events if event.type == "cost"]
    assert costs[1] == pytest.approx(0.2)
    saved = list((tmp_path / "history_images").glob("surroundings_*.png"))
    assert len(saved) == 1 and saved[0].read_bytes() == b"surroundings"


# ---------------------------------------------------------------------------
# 共通の前処理
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_character_references_dropped_on_v5_model(monkeypatch) -> None:
    store = FakeSessionStore()
    store.user_settings["novelai_curated_image_model"] = "nai-diffusion-5-curated"
    harness = _build(monkeypatch, provider="novelai", store=store)
    await _run(harness, character_references=[{"image": "abc", "type": "character"}])

    assert harness.image_calls[0]["character_references"] is None
    assert harness.image_calls[0]["novelai_image_model_override"] == (
        "nai-diffusion-5-curated"
    )


@pytest.mark.asyncio
async def test_session_setup_failure_emits_error_only(monkeypatch) -> None:
    harness = _build(monkeypatch)
    monkeypatch.setattr(
        harness.service,
        "_get_or_create_session_for_stream",
        AsyncMock(side_effect=RuntimeError("no session")),
    )
    events = await _run(harness)

    assert _types(events) == ["error"]
    assert _one(events, "error").data == {"message": "no session"}
