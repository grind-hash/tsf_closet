"""サロンの来店と経営: 予約・接客の開始・会計・断る・週の締め・倒産・決算。

セッションと依頼の生成、口コミの LLM 呼び出しは差し替え、来店とセッション・依頼の
紐づけ、数値の反映を一時 SQLite で確かめる。
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import update

from gateway.consts.salon import (
    SALON_BASE_PRICE,
    SALON_DIFFICULTY_INITIAL_CASH,
    SALON_INITIAL_REPUTATION,
    SALON_QUESTION_LIMIT,
    SALON_TOTAL_WEEKS,
    SALON_TURN_LIMIT,
    SALON_WEEKLY_FIXED_COST,
    SALON_WEEKLY_SALARY,
)
from gateway.databases.models import History, SalonRun, SalonVisit, User
from gateway.schemas.salon import (
    SalonCheckoutResponse,
    SalonRunResponse,
    SalonVisitStartResponse,
)
from gateway.services import salon_service as salon_module
from gateway.services.cost_tracker import record_cost
from gateway.services.salon_prompts import returning_visit_summary
from gateway.services.salon_rules import Customer
from gateway.services.salon_service import SalonError, salon_service
from gateway.services.session import DEFAULT_USER_ID, session_store
from gateway.services.session_branch_service import SessionBranchError

NORMAL_CASH = SALON_DIFFICULTY_INITIAL_CASH["normal"]


class _Stubs:
    def __init__(self) -> None:
        self.started: list[tuple[str, str]] = []
        self.request_calls: list[dict[str, Any]] = []
        self.views: dict[str, dict[str, Any]] = {}
        self.review: str | Exception = "すてきな髪飾りでした。また来ます。"
        self.review_prompts: list[str] = []
        self.branched: list[dict[str, Any]] = []
        self.branch_error: SessionBranchError | None = None
        self.nsfw_modes: list[bool] = []
        self.pool: list[Customer] = [
            Customer("template", "yuya", "水瀬ユウヤ"),
            Customer("template", "emi", "星野エミ"),
            Customer("custom", "custom-1", "サクラ"),
        ]


@pytest.fixture
async def stubs(isolated_db, monkeypatch) -> _Stubs:
    async with isolated_db.async_factory() as db:
        db.add(User(id=DEFAULT_USER_ID))
        await db.commit()
    state = _Stubs()

    async def fake_pool(_db):
        return list(state.pool)

    monkeypatch.setattr(salon_module, "_customer_pool", fake_pool)

    async def fake_start_session(*, character_id, nsfw_mode, **_kwargs):
        state.started.append(("template", character_id))
        state.nsfw_modes.append(nsfw_mode)
        session = await session_store.create_session(
            image_path="", character_id=character_id
        )
        return session, None, "normal"

    async def fake_start_custom_session(
        *, custom_character_id, use_saved_profile, nsfw_mode, **_
    ):
        assert use_saved_profile is True
        state.started.append(("custom", custom_character_id))
        state.nsfw_modes.append(nsfw_mode)
        session = await session_store.create_session(image_path="")
        return session, None, "normal"

    async def fake_create_request(
        session_id,
        *,
        language,
        turn_limit,
        question_limit,
        emphasize_hints,
        previous_visit,
        sensitive,
    ):
        state.request_calls.append(
            {
                "session_id": session_id,
                "language": language,
                "turn_limit": turn_limit,
                "question_limit": question_limit,
                "emphasize_hints": emphasize_hints,
                "previous_visit": previous_visit,
                "sensitive": sensitive,
            }
        )
        view = {
            "wish": "ふんわりした姿に",
            "threshold": 70,
            "turns_used": 0,
            "sensitive": sensitive,
        }
        state.views[session_id] = view
        return view, 0.001

    async def fake_get_request_view(session_id):
        return state.views.get(session_id)

    async def fake_profile(_session_id):
        return {"name": "客", "personality": "", "tsf_attitude": ""}

    async def fake_branch(history_id, **kwargs):
        if state.branch_error is not None:
            raise state.branch_error
        state.branched.append({"history_id": history_id, **kwargs})
        session = await session_store.create_session(image_path="")
        return SimpleNamespace(session_id=session.id)

    async def fake_customer_text(system, _user, *, novelai_model):
        state.review_prompts.append(system)
        if isinstance(state.review, Exception):
            raise state.review
        record_cost(0.002)
        return state.review

    async def fake_start_preset_session(*, preset_id, nsfw_mode, **_):
        state.started.append(("preset", preset_id))
        state.nsfw_modes.append(nsfw_mode)
        session = await session_store.create_session(image_path="")
        return session, None, "normal"

    monkeypatch.setattr(salon_module.game_service, "start_session", fake_start_session)
    monkeypatch.setattr(
        salon_module.game_service, "start_preset_session", fake_start_preset_session
    )
    monkeypatch.setattr(
        salon_module.game_service, "start_custom_session", fake_start_custom_session
    )
    monkeypatch.setattr(
        salon_module.session_request_service, "create_request", fake_create_request
    )
    monkeypatch.setattr(
        salon_module.session_request_service, "get_request_view", fake_get_request_view
    )
    monkeypatch.setattr(salon_module, "branch_session_from_history", fake_branch)
    monkeypatch.setattr(salon_module, "session_profile", fake_profile)
    monkeypatch.setattr(salon_module, "generate_customer_text", fake_customer_text)
    return state


async def _set_run(isolated_db, run_id: str, **values: Any) -> None:
    async with isolated_db.async_factory() as db:
        run = await db.get(SalonRun, run_id)
        for key, value in values.items():
            setattr(run, key, value)
        await db.commit()


def _booked(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        visit
        for visit in run["visits"]
        if visit["week"] == run["week"] and visit["status"] == "booked"
    ]


async def test_create_run_opens_with_initial_cash_and_week_one_bookings(stubs) -> None:
    run = await salon_service.create_run("  サロン・ド・  テスト ")

    SalonRunResponse(**run)
    assert run["name"] == "サロン・ド・ テスト"
    assert run["status"] == "active"
    assert run["week"] == 1
    assert run["total_weeks"] == SALON_TOTAL_WEEKS
    assert run["difficulty"] == "normal"
    assert run["cash"] == run["initial_cash"] == NORMAL_CASH
    assert run["reputation"] == SALON_INITIAL_REPUTATION
    assert len(_booked(run)) == 1
    assert run["visits"][0]["visit_number"] == 1
    assert [item["id"] for item in await salon_service.list_runs()] == [run["id"]]


@pytest.mark.parametrize("difficulty", ["easy", "normal", "hard"])
async def test_difficulty_decides_opening_funds(stubs, difficulty) -> None:
    run = await salon_service.create_run("店", difficulty)

    assert run["difficulty"] == difficulty
    assert run["cash"] == SALON_DIFFICULTY_INITIAL_CASH[difficulty]
    assert run["initial_cash"] == SALON_DIFFICULTY_INITIAL_CASH[difficulty]


@pytest.mark.parametrize(
    ("difficulty", "emphasized"), [("easy", True), ("normal", True), ("hard", False)]
)
async def test_difficulty_decides_hint_emphasis(stubs, difficulty, emphasized) -> None:
    run = await salon_service.create_run("店", difficulty)
    visit = _booked(run)[0]

    await salon_service.start_visit(run["id"], visit["id"], language="ja")

    assert stubs.request_calls[-1]["emphasize_hints"] is emphasized


async def test_create_run_rejects_unknown_difficulty(stubs) -> None:
    with pytest.raises(SalonError) as error:
        await salon_service.create_run("店", "nightmare")
    assert error.value.code == "invalid_difficulty"


async def test_season_success_line_is_the_runs_own_opening_funds(
    stubs, isolated_db
) -> None:
    hard_cash = SALON_DIFFICULTY_INITIAL_CASH["hard"]
    run = await salon_service.create_run("店", "hard")
    # 締めた後の現金がちょうど開業資金に戻る(上回らない)
    await _set_run(
        isolated_db,
        run["id"],
        week=SALON_TOTAL_WEEKS,
        cash=hard_cash - SALON_WEEKLY_SALARY + SALON_WEEKLY_FIXED_COST,
    )

    closed = (await salon_service.close_week(run["id"]))["run"]

    assert closed["result"] == {"outcome": "partial", "cash": hard_cash, "profit": 0}


async def test_create_run_rejects_blank_name(stubs) -> None:
    with pytest.raises(SalonError) as error:
        await salon_service.create_run("   ")
    assert error.value.code == "empty_name"


async def test_start_visit_links_session_with_salon_request_limits(stubs) -> None:
    run = await salon_service.create_run("店")
    visit = _booked(run)[0]

    result = await salon_service.start_visit(run["id"], visit["id"], language="ja")

    SalonVisitStartResponse(**result)
    assert stubs.started == [(visit["customer"]["source"], visit["customer"]["id"])]
    assert stubs.request_calls == [
        {
            "session_id": result["session_id"],
            "language": "ja",
            "turn_limit": SALON_TURN_LIMIT,
            "question_limit": SALON_QUESTION_LIMIT,
            "emphasize_hints": True,
            "previous_visit": None,
            "sensitive": False,
        }
    ]
    assert stubs.nsfw_modes == [False]
    started = result["run"]["visits"][0]
    assert started["status"] == "serving"
    assert started["session_id"] == result["session_id"]
    assert result["cost_usd"] == pytest.approx(0.001)


async def test_start_visit_resumes_serving_session_and_reactivates_it(stubs) -> None:
    run = await salon_service.create_run("店")
    visit = _booked(run)[0]
    first = await salon_service.start_visit(run["id"], visit["id"], language="ja")
    # 通常画面で別のセッションを始めた状態
    await session_store.reset_session()

    again = await salon_service.start_visit(run["id"], visit["id"], language="ja")

    assert again["session_id"] == first["session_id"]
    assert len(stubs.started) == 1
    assert len(stubs.request_calls) == 1
    active = await session_store.get_active_session()
    assert active is not None and active.id == first["session_id"]


async def test_only_one_customer_is_served_at_a_time(stubs, monkeypatch) -> None:
    monkeypatch.setattr(salon_module, "SALON_INITIAL_REPUTATION", 50)
    run = await salon_service.create_run("店")
    first, second = _booked(run)[:2]
    await salon_service.start_visit(run["id"], first["id"], language="ja")

    with pytest.raises(SalonError) as error:
        await salon_service.start_visit(run["id"], second["id"], language="ja")
    assert error.value.code == "serving_other"


async def test_checkout_requires_at_least_one_turn(stubs) -> None:
    run = await salon_service.create_run("店")
    visit = _booked(run)[0]
    await salon_service.start_visit(run["id"], visit["id"], language="ja")

    with pytest.raises(SalonError) as error:
        await salon_service.checkout_visit(run["id"], visit["id"], language="ja")
    assert error.value.code == "not_served"


async def test_checkout_fulfilled_pays_premium_and_raises_reputation(stubs) -> None:
    run = await salon_service.create_run("店")
    visit = _booked(run)[0]
    started = await salon_service.start_visit(run["id"], visit["id"], language="ja")
    stubs.views[started["session_id"]].update(
        status="fulfilled", satisfaction=82, turns_used=3
    )

    result = await salon_service.checkout_visit(run["id"], visit["id"], language="ja")

    SalonCheckoutResponse(**result)
    done = result["visit"]
    assert done["status"] == "done"
    assert done["satisfaction"] == 82
    assert done["fulfilled"] is True
    assert done["payment"] == int(SALON_BASE_PRICE * 1.5)
    assert done["reputation_delta"] == 8
    assert done["review"] == "すてきな髪飾りでした。また来ます。"
    assert result["cost_usd"] == pytest.approx(0.002)
    assert result["run"]["cash"] == NORMAL_CASH + done["payment"]
    assert result["run"]["reputation"] == SALON_INITIAL_REPUTATION + 8

    with pytest.raises(SalonError) as error:
        await salon_service.checkout_visit(run["id"], visit["id"], language="ja")
    assert error.value.code == "not_serving"


async def test_checkout_low_satisfaction_uses_fallback_review_on_failure(
    stubs,
) -> None:
    stubs.review = RuntimeError("provider down")
    run = await salon_service.create_run("店")
    visit = _booked(run)[0]
    started = await salon_service.start_visit(run["id"], visit["id"], language="ja")
    stubs.views[started["session_id"]].update(
        status="active", satisfaction=30, turns_used=3
    )

    result = await salon_service.checkout_visit(run["id"], visit["id"], language="ja")

    done = result["visit"]
    assert done["payment"] == int(SALON_BASE_PRICE * 0.5)
    assert done["reputation_delta"] == -5
    assert done["review"] == "今回は、思い描いていた姿とは遠かったかな……。"
    assert result["run"]["reputation"] == SALON_INITIAL_REPUTATION - 5


async def test_decline_lowers_reputation_once(stubs) -> None:
    run = await salon_service.create_run("店")
    visit = _booked(run)[0]

    declined = await salon_service.decline_visit(run["id"], visit["id"])

    assert declined["visits"][0]["status"] == "declined"
    assert declined["reputation"] == SALON_INITIAL_REPUTATION - 3
    with pytest.raises(SalonError) as error:
        await salon_service.decline_visit(run["id"], visit["id"])
    assert error.value.code == "visit_closed"


async def test_close_week_waits_for_checkout(stubs) -> None:
    run = await salon_service.create_run("店")
    visit = _booked(run)[0]
    await salon_service.start_visit(run["id"], visit["id"], language="ja")

    with pytest.raises(SalonError) as error:
        await salon_service.close_week(run["id"])
    assert error.value.code == "serving_open"


async def test_close_week_settles_costs_and_books_next_week(stubs) -> None:
    run = await salon_service.create_run("店")

    closed = (await salon_service.close_week(run["id"]))["run"]

    SalonRunResponse(**closed)
    assert closed["week"] == 2
    # 接客しなかった予約は断った扱い
    assert closed["visits"][0]["status"] == "declined"
    assert closed["reputation"] == SALON_INITIAL_REPUTATION - 3
    expected_cash = NORMAL_CASH + SALON_WEEKLY_SALARY - SALON_WEEKLY_FIXED_COST
    assert closed["cash"] == expected_cash
    assert closed["weeks"] == [
        {
            "week": 1,
            "revenue": 0,
            "salary": SALON_WEEKLY_SALARY,
            "fixed_cost": SALON_WEEKLY_FIXED_COST,
            "served": 0,
            "declined": 1,
            "cash_end": expected_cash,
            "reputation_end": SALON_INITIAL_REPUTATION - 3,
        }
    ]
    assert len(_booked(closed)) == 1
    with pytest.raises(SalonError) as error:
        await salon_service.start_visit(
            run["id"], closed["visits"][0]["id"], language="ja"
        )
    assert error.value.code == "not_this_week"


async def test_regular_customer_shows_visit_number_and_previous_review(
    stubs, monkeypatch
) -> None:
    stubs.pool = [Customer("custom", "c1", "サクラ")]
    run = await salon_service.create_run("店")
    visit = _booked(run)[0]
    started = await salon_service.start_visit(run["id"], visit["id"], language="ja")
    stubs.views[started["session_id"]].update(satisfaction=60, turns_used=2)
    await salon_service.checkout_visit(run["id"], visit["id"], language="ja")

    closed = (await salon_service.close_week(run["id"]))["run"]

    returning = _booked(closed)[0]
    assert stubs.started == [("custom", "c1")]
    assert returning["visit_number"] == 2
    assert returning["previous_review"] == "すてきな髪飾りでした。また来ます。"
    # 願いを叶えていないので、元の姿で来る
    assert returning["returning_look"] is False


async def _add_turn(isolated_db, session_id: str, history_id: str) -> None:
    """施術の手番(依頼の評価が付く)を1件足す。"""
    async with isolated_db.async_factory() as db:
        db.add(
            History(
                id=history_id,
                session_id=session_id,
                instruction="淡い水色のワンピース",
                image_path=f"img/{history_id}.png",
                after_description="1girl, pale blue dress",
                instruction_type="dress_up",
                request_evaluation_json='{"fit": "good", "satisfaction": 82}',
                created_at=datetime(2026, 11, 1, 12, 0),
            )
        )
        await db.commit()


async def _add_experience(isolated_db, session_id: str, history_id: str) -> None:
    """お披露目の体験の場面(行動の手番。依頼の評価は付かない)を1件足す。"""
    async with isolated_db.async_factory() as db:
        db.add(
            History(
                id=history_id,
                session_id=session_id,
                instruction="顔の見えない成人男性に抱き寄せられる",
                image_path=f"img/{history_id}.png",
                after_description="1girl, 1boy, faceless male, pale blue dress",
                feeling_text="胸が高鳴って、思わず目を閉じた。",
                instruction_type="action",
                created_at=datetime(2026, 11, 1, 12, 5),
            )
        )
        await db.commit()


async def _serve_fulfilled(stubs, isolated_db, run: dict[str, Any]) -> dict[str, Any]:
    visit = _booked(run)[0]
    started = await salon_service.start_visit(run["id"], visit["id"], language="ja")
    session_id = started["session_id"]
    await session_store.save_session_request(
        session_id, wish="ふんわりした姿に", preferences=[], language="ja"
    )
    await _add_turn(isolated_db, session_id, f"turn-{visit['id']}")
    stubs.views[session_id].update(status="fulfilled", satisfaction=82, turns_used=2)
    return await salon_service.checkout_visit(run["id"], visit["id"], language="ja")


async def test_fulfilled_customer_keeps_look_and_comes_back_next_week(
    stubs, isolated_db
) -> None:
    run = await salon_service.create_run("店")
    first = _booked(run)[0]

    done = (await _serve_fulfilled(stubs, isolated_db, run))["visit"]

    assert done["kept_look"] is True
    assert "keeps_this_look is true" in stubs.review_prompts[-1]
    closed = (await salon_service.close_week(run["id"]))["run"]
    # 評判が上がって予約は2件。持ち越しのお客様が先頭で、もう1件は別のお客様
    booked = _booked(closed)
    assert len(booked) == 2
    returning, fresh = booked
    assert returning["customer"] == first["customer"]
    assert returning["returning_look"] is True
    assert fresh["customer"] != first["customer"]
    assert fresh["returning_look"] is False

    started = await salon_service.start_visit(run["id"], returning["id"], language="ja")

    assert stubs.branched == [
        {
            "history_id": f"turn-{first['id']}",
            "inherit_stats": True,
            "self_mode": False,
            "language": "ja",
            "summary": returning_visit_summary("ja"),
        }
    ]
    # 分岐から始めたので、元の姿のセッションは作らない
    assert len(stubs.started) == 1
    assert stubs.request_calls[-1]["session_id"] == started["session_id"]
    assert stubs.request_calls[-1]["previous_visit"] == {
        "wish": "ふんわりした姿に",
        "review": "すてきな髪飾りでした。また来ます。",
    }


async def test_kept_look_falls_back_to_original_look_when_branch_fails(
    stubs, isolated_db
) -> None:
    run = await salon_service.create_run("店")
    await _serve_fulfilled(stubs, isolated_db, run)
    closed = (await salon_service.close_week(run["id"]))["run"]
    returning = _booked(closed)[0]
    stubs.branch_error = SessionBranchError("image_not_found", "画像がありません")

    await salon_service.start_visit(run["id"], returning["id"], language="ja")

    assert len(stubs.started) == 2
    assert stubs.request_calls[-1]["previous_visit"] is None


async def test_fulfilled_customer_in_final_week_does_not_keep_look(
    stubs, isolated_db
) -> None:
    run = await salon_service.create_run("店")
    await _set_run(isolated_db, run["id"], week=SALON_TOTAL_WEEKS)
    # 最終週の予約にする
    async with isolated_db.async_factory() as db:
        await db.execute(
            update(SalonVisit)
            .where(SalonVisit.salon_id == run["id"])
            .values(week=SALON_TOTAL_WEEKS)
        )
        await db.commit()
    run = await salon_service.get_run(run["id"])

    done = (await _serve_fulfilled(stubs, isolated_db, run))["visit"]

    assert done["fulfilled"] is True
    assert done["kept_look"] is False
    assert "keeps_this_look is true" not in stubs.review_prompts[-1]


async def test_close_week_with_negative_cash_goes_bankrupt(stubs, isolated_db) -> None:
    run = await salon_service.create_run("店")
    await _set_run(isolated_db, run["id"], cash=100_000)

    closed = (await salon_service.close_week(run["id"]))["run"]

    assert closed["status"] == "bankrupt"
    assert closed["result"]["outcome"] == "bankrupt"
    assert closed["week"] == 1
    with pytest.raises(SalonError) as error:
        await salon_service.close_week(run["id"])
    assert error.value.code == "salon_closed"


async def test_closing_last_week_settles_the_season(stubs, isolated_db) -> None:
    run = await salon_service.create_run("店")
    await _set_run(isolated_db, run["id"], week=SALON_TOTAL_WEEKS, cash=4_000_000)

    closed = (await salon_service.close_week(run["id"]))["run"]

    assert closed["status"] == "completed"
    assert closed["week"] == SALON_TOTAL_WEEKS
    expected_cash = 4_000_000 + SALON_WEEKLY_SALARY - SALON_WEEKLY_FIXED_COST
    assert closed["result"] == {
        "outcome": "success",
        "cash": expected_cash,
        "profit": expected_cash - NORMAL_CASH,
    }
    # 決算後は翌週の予約を入れない
    assert all(item["week"] == 1 for item in closed["visits"])


async def test_delete_run_and_unknown_run(stubs) -> None:
    run = await salon_service.create_run("店")
    await salon_service.delete_run(run["id"])

    with pytest.raises(SalonError) as error:
        await salon_service.get_run(run["id"])
    assert error.value.code == "salon_not_found"


async def test_review_prompt_uses_the_customers_own_profile(stubs, monkeypatch) -> None:
    from gateway.services import session_request_service as request_module

    monkeypatch.setattr(salon_module, "session_profile", request_module.session_profile)
    prompts: list[str] = []

    async def capture(_system, user, *, novelai_model):
        prompts.append(user)
        return "「ありがとう。」"

    monkeypatch.setattr(salon_module, "generate_customer_text", capture)
    stubs.pool = [Customer("template", "char1", "水瀬ユウヤ")]
    run = await salon_service.create_run("店")
    visit = _booked(run)[0]
    started = await salon_service.start_visit(run["id"], visit["id"], language="ja")
    stubs.views[started["session_id"]].update(satisfaction=60, turns_used=1)

    result = await salon_service.checkout_visit(run["id"], visit["id"], language="ja")

    character = salon_module.character_manager.get_by_id("char1")
    assert "水瀬ユウヤ" in prompts[0]
    assert character.personality[:10] in prompts[0]
    # 括弧は外して保存する
    assert result["visit"]["review"] == "ありがとう。"


async def test_hard_season_with_big_profit_unlocks_every_salon_achievement(
    stubs, isolated_db
) -> None:
    hard_cash = SALON_DIFFICULTY_INITIAL_CASH["hard"]
    run = await salon_service.create_run("店", "hard")
    await _set_run(
        isolated_db,
        run["id"],
        week=SALON_TOTAL_WEEKS,
        cash=hard_cash + 500_000 - SALON_WEEKLY_SALARY + SALON_WEEKLY_FIXED_COST,
    )

    result = await salon_service.close_week(run["id"])

    assert result["run"]["result"]["profit"] == 500_000
    assert [item["achievement_id"] for item in result["achievements"]] == [
        "salon_first_season",
        "salon_success",
        "salon_success_hard",
        "salon_profit_30",
        "salon_profit_50",
    ]
    assert all(item["category"] == "salon" for item in result["achievements"])

    # 解除済みの実績は、次の決算で再び通知しない
    second = await salon_service.create_run("店", "hard")
    await _set_run(
        isolated_db,
        second["id"],
        week=SALON_TOTAL_WEEKS,
        cash=hard_cash + 500_000 - SALON_WEEKLY_SALARY + SALON_WEEKLY_FIXED_COST,
    )
    assert (await salon_service.close_week(second["id"]))["achievements"] == []


async def test_partial_season_unlocks_only_the_first_season(stubs, isolated_db) -> None:
    run = await salon_service.create_run("店", "easy")
    await _set_run(isolated_db, run["id"], week=SALON_TOTAL_WEEKS)

    result = await salon_service.close_week(run["id"])

    assert result["run"]["result"]["outcome"] == "partial"
    assert [item["achievement_id"] for item in result["achievements"]] == [
        "salon_first_season"
    ]


async def test_bankruptcy_and_mid_season_close_unlock_nothing(
    stubs, isolated_db
) -> None:
    run = await salon_service.create_run("店")
    assert (await salon_service.close_week(run["id"]))["achievements"] == []

    await _set_run(isolated_db, run["id"], cash=0)
    result = await salon_service.close_week(run["id"])

    assert result["run"]["status"] == "bankrupt"
    assert result["achievements"] == []


async def test_checkout_releases_the_customers_session(stubs) -> None:
    run = await salon_service.create_run("店")
    visit = _booked(run)[0]
    started = await salon_service.start_visit(run["id"], visit["id"], language="ja")
    stubs.views[started["session_id"]].update(satisfaction=60, turns_used=1)
    active = await session_store.get_active_session()
    assert active is not None and active.id == started["session_id"]

    await salon_service.checkout_visit(run["id"], visit["id"], language="ja")

    assert await session_store.get_active_session() is None


async def _set_nsfw_mode(isolated_db, enabled: bool) -> None:
    async with isolated_db.async_factory() as db:
        await db.execute(
            update(User).where(User.id == DEFAULT_USER_ID).values(nsfw_mode=enabled)
        )
        await db.commit()


async def test_sensitive_setting_defaults_off_and_is_saved(stubs) -> None:
    run = await salon_service.create_run("店")
    assert run["sensitive"] is False

    updated = await salon_service.update_settings(run["id"], sensitive=True)

    SalonRunResponse(**updated)
    assert updated["sensitive"] is True
    assert (await salon_service.get_run(run["id"]))["sensitive"] is True
    # 難易度など、ほかの設定は消えない
    assert updated["difficulty"] == run["difficulty"]
    assert updated["initial_cash"] == run["initial_cash"]


async def test_sensitive_setting_cannot_change_after_the_season(
    stubs, isolated_db
) -> None:
    run = await salon_service.create_run("店")
    await _set_run(isolated_db, run["id"], status="completed")

    with pytest.raises(SalonError) as error:
        await salon_service.update_settings(run["id"], sensitive=True)
    assert error.value.code == "salon_closed"


@pytest.mark.parametrize(
    ("sensitive", "nsfw_mode", "adult"),
    [(True, True, True), (True, False, False), (False, True, False)],
)
async def test_sensitive_requests_need_nsfw_mode(
    stubs, isolated_db, sensitive, nsfw_mode, adult
) -> None:
    await _set_nsfw_mode(isolated_db, nsfw_mode)
    run = await salon_service.create_run("店")
    await salon_service.update_settings(run["id"], sensitive=sensitive)
    visit = _booked(run)[0]

    await salon_service.start_visit(run["id"], visit["id"], language="ja")

    # 依頼も、接客のセッション(画像・心境)も同じ値にそろう
    assert stubs.request_calls[-1]["sensitive"] is adult
    assert stubs.nsfw_modes == [adult]


async def test_experience_scene_is_not_kept_and_feeds_the_review(
    stubs, isolated_db
) -> None:
    run = await salon_service.create_run("店")
    await _set_nsfw_mode(isolated_db, True)
    await salon_service.update_settings(run["id"], sensitive=True)
    visit = _booked(run)[0]
    started = await salon_service.start_visit(run["id"], visit["id"], language="ja")
    session_id = started["session_id"]
    await session_store.save_session_request(
        session_id, wish="ふんわりした姿に", preferences=[], language="ja"
    )
    await _add_turn(isolated_db, session_id, "styled")
    await _add_experience(isolated_db, session_id, "experience")
    stubs.views[session_id].update(status="fulfilled", satisfaction=82, turns_used=1)

    done = await salon_service.checkout_visit(run["id"], visit["id"], language="ja")

    async with isolated_db.async_factory() as db:
        kept = (await db.get(SalonVisit, visit["id"])).kept_history_id
    # 持ち帰るのは最後の施術の姿で、体験の場面ではない
    assert kept == "styled"
    assert done["visit"]["kept_look"] is True
    prompt = stubs.review_prompts[-1]
    assert "Sexual content is allowed" in prompt
    assert "experience is how the customer felt" in prompt


async def test_all_ages_review_ignores_a_later_non_styling_turn(
    stubs, isolated_db
) -> None:
    run = await salon_service.create_run("店")
    visit = _booked(run)[0]
    started = await salon_service.start_visit(run["id"], visit["id"], language="ja")
    session_id = started["session_id"]
    await _add_turn(isolated_db, session_id, "styled")
    await _add_experience(isolated_db, session_id, "experience")
    stubs.views[session_id].update(status="active", satisfaction=50, turns_used=1)

    await salon_service.checkout_visit(run["id"], visit["id"], language="ja")

    prompt = stubs.review_prompts[-1]
    assert "Never write sexual content." in prompt
    assert "experience is how" not in prompt


async def test_character_maker_customer_starts_from_the_character(stubs) -> None:
    stubs.pool = [Customer("preset", "preset-1", "ミナト")]
    run = await salon_service.create_run("店")
    visit = _booked(run)[0]
    assert visit["customer"] == {"source": "preset", "id": "preset-1", "name": "ミナト"}

    await salon_service.start_visit(run["id"], visit["id"], language="ja")

    assert stubs.started == [("preset", "preset-1")]
