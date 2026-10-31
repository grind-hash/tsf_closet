"""依頼モード(session_requests)のサービス・ストア・応答のテスト。"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy import update

from gateway.consts.session_request import REQUEST_FULFILL_THRESHOLD
from gateway.databases.models import History as HistoryORM
from gateway.databases.models import Session as SessionORM
from gateway.databases.models import SessionCharacter, User
from gateway.services import session_request_service as request_module
from gateway.services.achievements import (
    ACHIEVEMENTS,
    check_achievement,
    get_global_stats,
)
from gateway.services.prompts import build_request_feeling_prompt
from gateway.services.session import DEFAULT_USER_ID, session_store
from gateway.services.session_request_service import (
    GeneratedRequest,
    RequestEvaluationOutput,
    SessionRequestError,
    compute_satisfaction,
    evaluation_record,
    feeling_context,
    is_fulfilled,
    public_request_view,
    session_request_service,
)
from gateway.services.session_response import build_session_response

_PREFERENCES = [
    {"id": "p1", "text": "淡いピンクのドレス", "hint": "色合い"},
    {"id": "p2", "text": "膝より長い丈", "hint": "丈"},
]
_REQUEST = {"wish": "舞踏会のお姫様になってみたい", "preferences": _PREFERENCES}


def test_compute_satisfaction_combines_fit_and_preferences() -> None:
    assert compute_satisfaction("none", 0, 2) == 0
    assert compute_satisfaction("good", 1, 2) == 60
    assert compute_satisfaction("perfect", 2, 2) == 100
    assert compute_satisfaction("unknown", 0, 0) == 0
    # 願いにかなり近く(good)好みを全部満たせば達成ラインに届く
    assert compute_satisfaction("good", 2, 2) >= REQUEST_FULFILL_THRESHOLD


def test_evaluation_record_drops_unknown_ids_and_clears_hint_when_all_met() -> None:
    partial = evaluation_record(
        RequestEvaluationOutput.model_validate(
            {"fit": "GOOD", "met_preference_ids": ["p2", "p9"], "hint": "色が気になる"}
        ),
        _PREFERENCES,
    )
    assert partial == {
        "satisfaction": 60,
        "fit": "good",
        "met_preference_ids": ["p2"],
        "hint": "色が気になる",
    }
    assert not is_fulfilled(partial)
    complete = evaluation_record(
        RequestEvaluationOutput.model_validate(
            {"fit": "good", "met_preference_ids": ["p1", "p2"], "hint": "残り"}
        ),
        _PREFERENCES,
    )
    assert complete["hint"] == ""
    assert is_fulfilled(complete)
    # 語彙外の fit は none に倒す
    assert RequestEvaluationOutput.model_validate({"fit": "great"}).fit == "none"


def test_generated_request_requires_two_preferences_and_clips() -> None:
    generated = GeneratedRequest.model_validate(
        {
            "wish": "  お姫様に\nなりたい ",
            "preferences": [
                {"text": "淡い色", "hint": "色合い"},
                {"text": "", "hint": "空"},
                {"text": "長い丈", "hint": "丈"},
                {"text": "ティアラ", "hint": "小物"},
                {"text": "手袋", "hint": "小物"},
            ],
        }
    )
    assert generated.wish == "お姫様に なりたい"
    assert [item.text for item in generated.preferences] == [
        "淡い色",
        "長い丈",
        "ティアラ",
    ]
    with pytest.raises(ValueError):
        GeneratedRequest.model_validate(
            {"wish": "願い", "preferences": [{"text": "一つだけ"}]}
        )


def test_public_request_view_reveals_only_preferences_met_at_least_once() -> None:
    hidden = public_request_view(_REQUEST, [], can_regenerate=True)
    assert hidden["satisfaction"] == 0
    assert [item["text"] for item in hidden["preferences"]] == [None, None]
    assert hidden["preferences"][0]["hint"] == "色合い"

    evaluations = [
        {"satisfaction": 60, "fit": "good", "met_preference_ids": ["p1"], "hint": ""},
        {"satisfaction": 20, "fit": "partial", "met_preference_ids": [], "hint": "丈"},
    ]
    view = public_request_view(_REQUEST, evaluations, can_regenerate=False)
    # 一度満たした好みは開示したままにし、満たしているかは最新の手番で判定する
    assert view["preferences"][0] == {
        "id": "p1",
        "hint": "色合い",
        "text": "淡いピンクのドレス",
        "met": False,
    }
    assert view["preferences"][1]["text"] is None
    assert view["satisfaction"] == 20
    assert view["hint"] == "丈"
    assert view["evaluated_turns"] == 2


def test_feeling_context_hints_unmet_preferences_without_naming_rule() -> None:
    evaluation = {"fit": "partial", "met_preference_ids": ["p1"]}
    text = feeling_context(_REQUEST, evaluation, "ja")
    assert "舞踏会のお姫様になってみたい" in text
    assert "満たされた好み: 淡いピンクのドレス" in text
    assert "名指しせず" in text and "膝より長い丈" in text
    english = feeling_context(_REQUEST, None, "en")
    assert "never name them outright" in english


async def _seed_session(
    factory, *, self_mode: bool = False, transformation_count: int = 0
) -> None:
    async with factory() as db:
        db.add(User(id=DEFAULT_USER_ID))
        db.add(
            SessionORM(
                id="s1",
                user_id=DEFAULT_USER_ID,
                current_image_path="img/s1.png",
                character_id=None,
                self_mode=self_mode,
                transformation_count=transformation_count,
            )
        )
        db.add(
            HistoryORM(
                id="h0",
                session_id="s1",
                instruction="初期状態",
                image_path="img/h0.png",
                after_description="制服姿の少年",
                created_at=datetime(2026, 10, 31, 10, 0),
            )
        )
        await db.commit()


def _fake_generation(monkeypatch, payloads: list[dict]) -> list[str]:
    calls: list[str] = []

    async def fake(system_prompt: str, user_prompt: str, *, novelai_model):
        calls.append(user_prompt)
        return json.dumps(payloads[min(len(calls), len(payloads)) - 1])

    monkeypatch.setattr(request_module, "_generate_text", fake)
    return calls


_GENERATED = {
    "wish": "一度でいいから、舞踏会のお姫様になってみたいんだ",
    "preferences": [
        {"text": "淡いピンクのドレス", "hint": "色合い"},
        {"text": "膝より長い丈", "hint": "丈"},
    ],
}


@pytest.mark.asyncio
async def test_create_request_saves_hidden_preferences_and_locks_after_first_turn(
    isolated_db, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory)
    calls = _fake_generation(monkeypatch, [_GENERATED])

    view, _cost = await session_request_service.create_request("s1", language="ja")

    assert view["wish"] == _GENERATED["wish"]
    assert view["can_regenerate"] is True
    assert [item["text"] for item in view["preferences"]] == [None, None]
    assert "制服姿の少年" in calls[0]
    stored = await session_store.get_session_request("s1")
    assert [item["id"] for item in stored["preferences"]] == ["p1", "p2"]
    assert stored["preferences"][0]["text"] == "淡いピンクのドレス"

    # 最初の着せ替えの前は作り直せる
    await session_request_service.create_request("s1", language="ja")
    async with isolated_db.async_factory() as db:
        await db.execute(
            update(SessionORM)
            .where(SessionORM.id == "s1")
            .values(transformation_count=1)
        )
        await db.commit()
    with pytest.raises(SessionRequestError) as locked:
        await session_request_service.create_request("s1", language="ja")
    assert locked.value.code == "request_locked"


@pytest.mark.asyncio
async def test_create_request_rejects_self_mode_and_unknown_session(
    isolated_db, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory, self_mode=True)
    _fake_generation(monkeypatch, [_GENERATED])
    with pytest.raises(SessionRequestError) as self_mode:
        await session_request_service.create_request("s1", language="ja")
    assert self_mode.value.code == "self_mode"
    with pytest.raises(SessionRequestError) as missing:
        await session_request_service.create_request("nope", language="ja")
    assert missing.value.code == "session_not_found"


@pytest.mark.asyncio
async def test_evaluate_turn_returns_none_when_generation_fails(monkeypatch) -> None:
    async def broken(system_prompt: str, user_prompt: str, *, novelai_model):
        raise TimeoutError()

    monkeypatch.setattr(request_module, "_generate_text", broken)
    assert (
        await session_request_service.evaluate_turn(
            _REQUEST,
            current_look="pink dress",
            instruction="ドレスを着せる",
            language="ja",
            novelai_model=None,
        )
        is None
    )


@pytest.mark.asyncio
async def test_session_response_and_achievement_follow_turn_evaluations(
    isolated_db, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory, transformation_count=2)
    await session_store.save_session_request(
        "s1", wish=_REQUEST["wish"], preferences=_PREFERENCES, language="ja"
    )
    async with isolated_db.async_factory() as db:
        for index, evaluation in enumerate(
            [
                {"satisfaction": 60, "fit": "good", "met_preference_ids": ["p1"]},
                {
                    "satisfaction": 100,
                    "fit": "perfect",
                    "met_preference_ids": ["p1", "p2"],
                },
            ],
            start=1,
        ):
            db.add(
                HistoryORM(
                    id=f"h{index}",
                    session_id="s1",
                    instruction=f"着せ替え{index}",
                    image_path=f"img/h{index}.png",
                    created_at=datetime(2026, 10, 31, 10, index),
                    request_evaluation_json=json.dumps(evaluation),
                )
            )
        await db.commit()

    response = await build_session_response(session_store, "s1")
    assert response.request is not None
    assert response.request.satisfaction == 100
    assert response.request.can_regenerate is False
    assert [item.text for item in response.request.preferences] == [
        "淡いピンクのドレス",
        "膝より長い丈",
    ]

    assert get_global_stats().request_fulfilled_count == 0
    await session_store.mark_session_request_fulfilled("s1", "h2")
    # 達成済みを再度記録しても最初の手番のまま
    await session_store.mark_session_request_fulfilled("s1", "h9")
    stored = await session_store.get_session_request("s1")
    assert stored["status"] == "fulfilled"
    assert stored["fulfilled_history_id"] == "h2"
    stats = get_global_stats()
    assert stats.request_fulfilled_count == 1
    assert check_achievement(ACHIEVEMENTS["request_first"], stats)


def _request_prompt(**overrides):
    params = {
        "before_desc": "制服の少年",
        "after_desc": "pink ball gown",
        "instruction": "お姫様のドレスにする",
        "is_reality": False,
        "transformation_count": 2,
    }
    params.update(overrides)
    return build_request_feeling_prompt(**params)


def test_request_feeling_prompt_uses_bloom_for_openness_not_resistance() -> None:
    low, _ = _request_prompt(bloom=10)
    high, _ = _request_prompt(bloom=90)
    first, _ = _request_prompt(bloom=90, transformation_count=0)
    assert "嬉しさを素直に口に出せません" in low
    assert "次はどんな姿になりたいかを自分から思い描いています" in high
    assert "初めて願いが形になる瞬間" in first
    for prompt in (low, high, first):
        assert "強制ではなく" in prompt
        assert "NSFWモード" not in prompt
    nsfw, _ = _request_prompt(nsfw_mode=True)
    assert "NSFWモード" in nsfw


def test_request_feeling_prompt_adds_tsf_attitude_even_without_personality() -> None:
    system_prompt, user_prompt = _request_prompt(tsf_attitude="女の子になるのは苦手")
    assert "【このキャラクターの性格】\n- TSFへの態度: 女の子になるのは苦手" in (
        system_prompt
    )
    assert "冒頭は「" in user_prompt
    reality, reality_user = _request_prompt(is_reality=True, personality="恥ずかしがり")
    assert "- TSFへの態度:" not in reality
    assert "- 性格: 恥ずかしがり" in reality
    assert "という現実改変で、世界ごと姿が書き換わった" in reality_user


@pytest.mark.asyncio
async def test_get_protagonist_profile_reads_panel_protagonist(isolated_db) -> None:
    await _seed_session(isolated_db.async_factory)
    assert await session_store.get_protagonist_profile("s1") is None
    async with isolated_db.async_factory() as db:
        db.add(
            SessionCharacter(
                id="c-other",
                session_id="s1",
                name="友人",
                slot_index=1,
                profile_json=json.dumps({"tsf_attitude": "他人の設定"}),
            )
        )
        db.add(
            SessionCharacter(
                id="c-main",
                session_id="s1",
                name="主人公",
                slot_index=0,
                is_protagonist=True,
                profile_json=json.dumps(
                    {"tsf_attitude": "可愛い姿に憧れている"}, ensure_ascii=False
                ),
            )
        )
        await db.commit()
    profile = await session_store.get_protagonist_profile("s1")
    assert profile == {"tsf_attitude": "可愛い姿に憧れている"}
