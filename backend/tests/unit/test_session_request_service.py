"""依頼モード(session_requests)のサービス・ストア・応答のテスト。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import update

from gateway.consts.sensitive_desires import SENSITIVE_DESIRES
from gateway.consts.session_request import REQUEST_FULFILL_THRESHOLD
from gateway.databases.models import History as HistoryORM
from gateway.databases.models import Session as SessionORM
from gateway.databases.models import SessionCharacter, User
from gateway.models import Character
from gateway.services import session_request_service as request_module
from gateway.services.achievements import (
    ACHIEVEMENTS,
    check_achievement,
    get_global_stats,
)
from gateway.services.prompts import build_request_feeling_prompt
from gateway.services.session import DEFAULT_USER_ID, session_store
from gateway.services.session_request_prompts import build_request_generation_prompt
from gateway.services.session_request_service import (
    GeneratedRequest,
    GeneratedSensitiveRequest,
    RequestEvaluationOutput,
    SessionRequestError,
    compute_satisfaction,
    crush_wording_fits,
    evaluation_record,
    experience_feeling_context,
    feeling_context,
    grounded_met_ids,
    is_fulfilled,
    listening_bonus,
    pick_sensitive_candidates,
    pick_sensitive_motive,
    public_request_view,
    sensitive_body_options,
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


_LOOK = (
    "1boy, solo, short black hair, princess dress, frills, pale pink dress, long dress"
)


def _output(met: list[tuple[str, str]], fit: str = "good", hint: str = "") -> Any:
    return RequestEvaluationOutput.model_validate(
        {
            "fit": fit,
            "met_preferences": [{"id": i, "evidence": e} for i, e in met],
            "hint": hint,
        }
    )


def test_evaluation_record_drops_unknown_ids_and_clears_hint_when_all_met() -> None:
    partial = evaluation_record(
        _output([("p1", "pale pink dress"), ("p9", "frills")], fit="GOOD", hint="丈"),
        _PREFERENCES,
        look_text=_LOOK,
        look_is_tags=True,
    )
    assert partial == {
        "satisfaction": 60,
        "fit": "good",
        "met_preference_ids": ["p1"],
        "reflected_answers": [],
        "listening_bonus": 0,
        "hint": "丈",
        "focus_preference_id": "p2",
    }
    assert not is_fulfilled(partial)
    complete = evaluation_record(
        _output([("p1", "pale pink dress"), ("p2", "long dress")], hint="残り"),
        _PREFERENCES,
        look_text=_LOOK,
        look_is_tags=True,
    )
    assert complete["hint"] == ""
    assert complete["focus_preference_id"] is None
    assert is_fulfilled(complete)


def test_evaluation_record_hint_follows_the_python_focus_preference() -> None:
    """ヒントは根拠の検証後に満たしていない先頭の好みを指す(LLM の思い込みで選ばない)。"""
    output = RequestEvaluationOutput.model_validate(
        {
            "fit": "good",
            # p1 を満たしたと言うが根拠が姿に無い → 検証で落ち、p1 が注目する好みになる
            "met_preferences": [{"id": "p1", "evidence": "pastel"}],
            "hints": [
                {"id": "p2", "text": "裾がもう少し長いと落ち着きそう"},
                {"id": "x", "text": "無関係"},
            ],
            "hint": "旧形式の1文",
        }
    )
    record = evaluation_record(output, _PREFERENCES, look_text=_LOOK, look_is_tags=True)
    assert record["met_preference_ids"] == []
    assert record["focus_preference_id"] == "p1"
    # p1 のヒントは書かれていない。未達が2つあるので旧形式の1文は使わず、分類から作る
    assert record["hint"] == "「色合い」のあたりが、まだ少し気になっているようです"

    written = RequestEvaluationOutput.model_validate(
        {
            "fit": "good",
            "met_preferences": [{"id": "p1", "evidence": "pale pink dress"}],
            "hints": [{"id": "p2", "text": "裾がもう少し長いと落ち着きそう"}],
        }
    )
    record = evaluation_record(
        written, _PREFERENCES, look_text=_LOOK, look_is_tags=True
    )
    assert record["focus_preference_id"] == "p2"
    assert record["hint"] == "裾がもう少し長いと落ち着きそう"


@pytest.mark.parametrize(
    ("questions", "topic_id", "expected"),
    [
        ([], None, "p1"),
        ([], "p2", "p2"),
        ([], "p9", "p1"),
        ([{"target_id": "p1"}], None, "p2"),
        ([{"target_id": "p1"}, {"target_id": "p2"}], None, "p1"),
        ([{}], None, "p1"),
    ],
)
def test_question_target_picks_chosen_or_least_hinted_preference(
    questions, topic_id, expected
) -> None:
    from gateway.services.session_request_service import question_target

    assert question_target(_PREFERENCES, questions, topic_id)["id"] == expected
    assert question_target([], questions, topic_id) is None


@pytest.mark.parametrize(
    ("current", "previous", "trend"),
    [(70, 60, "up"), (50, 60, "down"), (60, 60, "same"), (60, None, None)],
)
def test_satisfaction_trend(current, previous, trend) -> None:
    from gateway.services.session_request_service import satisfaction_trend

    assert satisfaction_trend(current, previous) == trend


@pytest.mark.parametrize(
    ("evidence", "met"),
    [
        # 実際の誤判定: 短い髪・タグの一部・説明全体・無関係な服のタグを丈の根拠にした
        ("short black hair", False),
        ("short", False),
        ("short black hair, princess dress, frills, pale pink dress", False),
        ("princess dress", False),
        # 丈を表す完全なタグなら認める(強調記号付きでもよい)
        ("long dress", True),
        ("{long dress}", True),
    ],
)
def test_grounded_met_ids_rejects_unsupported_length_evidence(evidence, met) -> None:
    ids = grounded_met_ids(
        _output([("p2", evidence)]), _PREFERENCES, _LOOK, look_is_tags=True
    )
    assert (ids == ["p2"]) is met


def test_grounded_met_ids_allows_hair_tags_for_head_accessories() -> None:
    preferences = [
        {"id": "p1", "text": "リボンつきのヘッドアクセサリー", "hint": "小物"},
        {"id": "p2", "text": "淡いパステルカラー", "hint": "色合い"},
    ]
    look = "1boy, solo, short black hair, pale blue dress, hair ribbon"
    ids = grounded_met_ids(
        _output([("p1", "hair ribbon"), ("p2", "short black hair")]),
        preferences,
        look,
        look_is_tags=True,
    )
    # 頭の飾りの好みには髪のタグを使えるが、色の好みに髪のタグは使えない
    assert ids == ["p1"]
    # 画像を読むプロバイダーの自然文では、部分一致で照合する
    natural = grounded_met_ids(
        _output([("p2", "淡いパステルカラーのドレス")]),
        preferences,
        "「淡いパステルカラーのドレスにする」に変身した姿",
    )
    assert natural == ["p2"]


def test_evaluation_record_falls_back_to_category_hint() -> None:
    record = evaluation_record(
        _output([("p1", "pale pink dress")]),
        _PREFERENCES,
        look_text=_LOOK,
        look_is_tags=True,
        language="ja",
    )
    assert record["hint"] == "「丈」のあたりが、まだ少し気になっているようです"

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
    assert "名指ししない" in text and "膝より長い丈" in text
    # 評価が無ければ、まだの好み全部を名指しせずにほのめかす(以前の書き方)
    english = feeling_context(_REQUEST, None, "en")
    assert "never name them outright" in english


def test_feeling_context_hints_only_the_focus_and_follows_the_trend() -> None:
    request = {**_REQUEST, "emphasize_hints": True}
    evaluation = {
        "fit": "partial",
        "satisfaction": 40,
        "met_preference_ids": [],
        "focus_preference_id": "p2",
    }
    text = feeling_context(request, evaluation, "ja", previous=60)
    # まだの好みは2つとも挙げるが、ほのめかすのは画面のヒントと同じ1つだけ
    assert "まだ満たされていない好み: 淡いピンクのドレス、膝より長い丈" in text
    assert "ほかの好みはほのめかさない）: 膝より長い丈" in text
    assert "前の姿のほうが好みに合っていて" in text
    rising = feeling_context(
        request, {**evaluation, "satisfaction": 70}, "en", previous=60
    )
    assert "do not hint at the others): 膝より長い丈" in rising
    assert "the mood has lifted" in rising
    assert "previous look" not in feeling_context(request, evaluation, "en")


def test_experience_feeling_context_frames_the_scene_as_the_salon_dream() -> None:
    sensitive = {**_REQUEST, "sensitive": True}
    ja = experience_feeling_context(sensitive, "ja")
    assert "サロンが見せる夢" in ja
    assert "舞踏会のお姫様になってみたい" in ja
    assert "周囲の視線についての指示より、こちらを優先" in ja
    assert "A dream the salon shows" in experience_feeling_context(sensitive, "en")
    # 全年齢の依頼の行動の手番には添えない
    assert experience_feeling_context(_REQUEST, "ja") == ""


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


@pytest.mark.asyncio
async def test_create_request_passes_tsf_attitude_with_panel_priority(
    isolated_db, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory)
    async with isolated_db.async_factory() as db:
        await db.execute(
            update(SessionORM).where(SessionORM.id == "s1").values(character_id="c1")
        )
        await db.commit()
    monkeypatch.setattr(
        request_module.character_manager,
        "get_by_id",
        lambda _id: Character(
            id="c1",
            name="テスト",
            image_path="x.png",
            description="",
            tsf_attitude="お嬢様にずっと憧れている",
        ),
    )
    calls = _fake_generation(monkeypatch, [_GENERATED])

    await session_request_service.create_request("s1", language="ja")
    assert json.loads(calls[0])["character"]["tsf_attitude"] == (
        "お嬢様にずっと憧れている"
    )

    # 人物パネルの主人公に設定があれば、そちらを優先する
    async with isolated_db.async_factory() as db:
        db.add(
            SessionCharacter(
                id="c-main",
                session_id="s1",
                name="主人公",
                is_protagonist=True,
                profile_json=json.dumps(
                    {"tsf_attitude": "王子様になってみたい"}, ensure_ascii=False
                ),
            )
        )
        await db.commit()
    await session_request_service.create_request("s1", language="ja")
    assert json.loads(calls[1])["character"]["tsf_attitude"] == "王子様になってみたい"


def test_public_request_view_counts_failed_turns_and_questions() -> None:
    request = {
        **_REQUEST,
        "turn_limit": 3,
        "question_limit": 2,
        "questions": [{"question": "好きな色は？", "answer": "春の花みたいな色かな"}],
    }
    evaluations = [
        {"satisfaction": 60, "fit": "good", "met_preference_ids": ["p1"]},
        {"failed": True},
    ]
    view = public_request_view(request, evaluations, can_regenerate=False)
    # 失敗した手番は満足度に使わないが、手数には数える
    assert view["satisfaction"] == 60
    assert view["evaluated_turns"] == 1
    assert view["turns_used"] == 2
    assert view["turns_remaining"] == 1
    assert view["questions"] == [
        {
            "question": "好きな色は？",
            "answer": "春の花みたいな色かな",
            "reflected": False,
            "target_id": None,
        }
    ]
    assert view["previous_satisfaction"] is None
    assert view["focus_preference_id"] == "p2"
    assert view["clue_level"] == "normal"
    assert view["questions_remaining"] == 1
    unlimited = public_request_view(_REQUEST, evaluations, can_regenerate=False)
    assert unlimited["turn_limit"] is None
    assert unlimited["turns_remaining"] is None
    assert unlimited["questions_remaining"] == 0


def test_feeling_context_includes_counselling_answers() -> None:
    request = {
        **_REQUEST,
        "questions": [{"question": "好きな色は？", "answer": "春の花みたいな色かな"}],
    }
    text = feeling_context(request, None, "ja")
    assert "カウンセリングで本人が答えたこと" in text
    assert "「好きな色は？」→「春の花みたいな色かな」" in text
    assert "What the character said in counselling" in feeling_context(
        request, None, "en"
    )


def test_feeling_context_marks_hint_sentence_only_when_emphasized() -> None:
    evaluation = {"fit": "partial", "met_preference_ids": ["p1"]}
    emphasized = {**_REQUEST, "emphasize_hints": True}

    ja = feeling_context(emphasized, evaluation, "ja")
    en = feeling_context(emphasized, evaluation, "en")

    assert "〔と〕で囲んで" in ja
    assert "in 〔 and 〕" in en
    assert "〔" not in feeling_context(_REQUEST, evaluation, "ja")
    # 好みを全部満たしたら、ほのめかす一文が無いので目印も頼まない
    all_met = {"fit": "perfect", "met_preference_ids": ["p1", "p2"]}
    assert "〔" not in feeling_context(emphasized, all_met, "ja")


@pytest.mark.asyncio
async def test_create_request_normalizes_limits_and_resets_questions(
    isolated_db, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory)
    _fake_generation(monkeypatch, [_GENERATED])

    view, _ = await session_request_service.create_request(
        "s1", language="ja", turn_limit=99, question_limit=-1
    )
    assert view["turn_limit"] == 20
    assert view["question_limit"] == 0

    await session_store.append_request_question("s1", question="Q", answer="A")
    view, _ = await session_request_service.create_request(
        "s1", language="ja", turn_limit=3, question_limit=None
    )
    # 作り直すと質問のやり取りも初期化し、回数は既定に戻る
    assert view["turn_limit"] == 3
    assert view["question_limit"] == 2
    assert view["questions"] == []
    assert view["emphasize_hints"] is False


@pytest.mark.asyncio
async def test_create_request_builds_on_the_kept_look_of_the_previous_visit(
    isolated_db, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory)
    calls = _fake_generation(monkeypatch, [_GENERATED, _GENERATED])

    await session_request_service.create_request("s1", language="ja")
    await session_request_service.create_request(
        "s1",
        language="ja",
        previous_visit={"wish": "ふんわりした姿に", "review": "また来ます"},
    )

    first, second = (json.loads(call) for call in calls)
    assert "previous_visit" not in first
    assert second["previous_visit"] == {
        "wish": "ふんわりした姿に",
        "review": "また来ます",
    }
    assert second["current_look"] == "制服姿の少年"


def test_request_generation_asks_for_an_additional_request_on_kept_look() -> None:
    profile = {"name": "サクラ", "gender": "man"}
    plain_system, _ = build_request_generation_prompt(profile, "1girl, dress", "ja")
    system, user = build_request_generation_prompt(
        profile, "1girl, dress", "ja", {"wish": "W", "review": "R"}
    )

    assert "previous_visit" not in plain_system
    assert "additional request that builds on current_look" in system
    assert "never a request to undo it" in system
    assert json.loads(user)["previous_visit"] == {"wish": "W", "review": "R"}


@pytest.mark.asyncio
async def test_create_request_stores_hint_emphasis(isolated_db, monkeypatch) -> None:
    await _seed_session(isolated_db.async_factory)
    _fake_generation(monkeypatch, [_GENERATED])

    view, _ = await session_request_service.create_request(
        "s1", language="ja", emphasize_hints=True
    )

    assert view["emphasize_hints"] is True
    stored = await session_store.get_session_request("s1")
    assert stored["emphasize_hints"] is True
    assert "〔" in feeling_context(stored, None, "ja")


@pytest.mark.asyncio
async def test_ask_question_answers_in_character_up_to_the_limit(
    isolated_db, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory)
    await session_store.save_session_request(
        "s1",
        wish=_REQUEST["wish"],
        preferences=_PREFERENCES,
        language="ja",
        question_limit=1,
    )
    prompts: list[tuple[str, str]] = []

    async def fake(system_prompt: str, user_prompt: str, *, novelai_model):
        prompts.append((system_prompt, user_prompt))
        return "「 春に咲く花みたいな、やわらかい色が好きなんだ 」"

    monkeypatch.setattr(request_module, "_generate_text", fake)

    with pytest.raises(SessionRequestError) as empty:
        await session_request_service.ask_question("s1", "   ", language="ja")
    assert empty.value.code == "empty_question"

    view, _ = await session_request_service.ask_question(
        "s1", "好きな色はある？", language="ja", topic_id="p2"
    )
    assert view["questions"] == [
        {
            "question": "好きな色はある？",
            "answer": "春に咲く花みたいな、やわらかい色が好きなんだ",
            "reflected": False,
            "target_id": "p2",
        }
    ]
    assert view["questions_remaining"] == 0
    # 手掛かりの対象の好み1つだけを答える側へ渡し、画面へは本文を送らない
    payload = json.loads(prompts[0][1])
    assert payload["target_preference"] == {"text": "膝より長い丈", "category": "丈"}
    assert "hidden_preferences" not in payload
    assert payload["stylist_question"] == "好きな色はある？"
    assert "let exactly one clue about target_preference slip" in prompts[0][0]
    assert "Do this even when the question is about something else" in prompts[0][0]
    assert all(item["text"] is None for item in view["preferences"])

    with pytest.raises(SessionRequestError) as limit:
        await session_request_service.ask_question("s1", "もう一つ", language="ja")
    assert limit.value.code == "request_question_limit"

    with pytest.raises(SessionRequestError) as missing:
        await session_request_service.ask_question("s9", "質問", language="ja")
    assert missing.value.code == "session_not_found"


def test_evaluation_prompt_requires_evidence_and_previous_look() -> None:
    from gateway.services.session_request_prompts import build_request_evaluation_prompt

    system, user = build_request_evaluation_prompt(
        wish="お姫様",
        preferences=_PREFERENCES,
        current_look="「リボンを付ける」に変身した姿",
        instruction="リボンを付ける",
        language="ja",
        previous_look="a boy in a pale pink dress",
    )
    assert '"met_preferences":[{"id":"p1","evidence":"..."}]' in system
    assert "a short hairstyle says nothing about the length of a dress" in system
    assert "judge the look as previous_look updated by that change" in system
    assert json.loads(user)["previous_look"] == "a boy in a pale pink dress"
    tags_only, tags_user = build_request_evaluation_prompt(
        wish="お姫様",
        preferences=_PREFERENCES,
        current_look="1boy, pale pink dress",
        instruction="ピンク",
        language="ja",
    )
    assert "previous_look" not in tags_only and "previous_look" not in tags_user


@pytest.mark.asyncio
async def test_evaluate_turn_strips_worn_under_layers(monkeypatch) -> None:
    prompts: list[str] = []

    async def fake(system_prompt: str, user_prompt: str, *, novelai_model):
        prompts.append(user_prompt)
        return json.dumps(
            {
                "fit": "good",
                "met_preferences": [{"id": "p1", "evidence": "pink lace panties"}],
            }
        )

    monkeypatch.setattr(request_module, "_generate_text", fake)
    record = await session_request_service.evaluate_turn(
        _REQUEST,
        current_look="1boy, white dress\n\nWORN_UNDER_LAYERS: pink lace panties",
        instruction="ドレス",
        language="ja",
        novelai_model=None,
        look_is_tags=True,
    )
    # 重ね着の記録(見えない下着)は評価に渡さず、根拠にも使わせない
    assert "WORN_UNDER_LAYERS" not in prompts[0]
    assert record["met_preference_ids"] == []


_QUESTIONS = [
    {"question": "何色が好き？", "answer": "桜が咲く頃の空みたいな、柔らかい色かな"},
    {
        "question": "どんな気分？",
        "answer": "なんだか、ふわふわした気持ちになりたいんだ",
    },
]


def test_listening_bonus_is_capped_and_lowers_the_bar() -> None:
    assert listening_bonus(0) == 0
    assert listening_bonus(1) == 10
    assert listening_bonus(5) == 20
    # 好みを全部満たさなくても、ヒアリングを汲めば達成ラインに届く
    assert compute_satisfaction("good", 1, 2) < REQUEST_FULFILL_THRESHOLD
    assert compute_satisfaction("good", 1, 2, 1) >= REQUEST_FULFILL_THRESHOLD
    assert compute_satisfaction("perfect", 2, 2, 2) == 100


def test_evaluation_record_credits_grounded_counselling_answers() -> None:
    output = RequestEvaluationOutput.model_validate(
        {
            "fit": "good",
            "met_preferences": [],
            "reflected_answers": [
                {"index": 1, "evidence": "pale blue dress"},
                # 気分の答えに、色の答えと関係ない髪のタグを根拠にしたものは捨てる
                {"index": 2, "evidence": "short black hair"},
                {"index": 9, "evidence": "frills"},
                {"index": "x", "evidence": "frills"},
            ],
        }
    )
    record = evaluation_record(
        output,
        _PREFERENCES,
        look_text="1boy, short black hair, pale blue dress, frills",
        look_is_tags=True,
        questions=_QUESTIONS,
    )
    assert record["reflected_answers"] == [1]
    assert record["listening_bonus"] == 10
    assert record["satisfaction"] == 50
    # 色の答えを、色の語が無いタグで裏付けることはできない
    frills_only = evaluation_record(
        RequestEvaluationOutput.model_validate(
            {"fit": "good", "reflected_answers": [{"index": 1, "evidence": "frills"}]}
        ),
        _PREFERENCES,
        look_text="1boy, pale blue dress, frills",
        look_is_tags=True,
        questions=_QUESTIONS,
    )
    assert frills_only["reflected_answers"] == []


def test_public_view_marks_reflected_answers_and_bonus() -> None:
    request = {**_REQUEST, "question_limit": 2, "questions": _QUESTIONS}
    view = public_request_view(
        request,
        [
            {
                "satisfaction": 60,
                "fit": "good",
                "met_preference_ids": [],
                "reflected_answers": [1],
                "listening_bonus": 10,
            }
        ],
        can_regenerate=False,
    )
    assert [item["reflected"] for item in view["questions"]] == [True, False]
    assert view["listening_bonus"] == 10
    assert view["threshold"] == REQUEST_FULFILL_THRESHOLD


def test_evaluation_prompt_lists_counselling_only_when_asked() -> None:
    from gateway.services.session_request_prompts import build_request_evaluation_prompt

    system, user = build_request_evaluation_prompt(
        wish="お姫様",
        preferences=_PREFERENCES,
        current_look="1boy, pale blue dress",
        instruction="青",
        language="ja",
        questions=_QUESTIONS,
    )
    assert '"reflected_answers":[{"index":1,"evidence":"..."}]' in system
    assert json.loads(user)["counselling"][0] == {
        "index": 1,
        "question": "何色が好き？",
        "answer": "桜が咲く頃の空みたいな、柔らかい色かな",
    }
    plain, plain_user = build_request_evaluation_prompt(
        wish="お姫様",
        preferences=_PREFERENCES,
        current_look="1boy, pale blue dress",
        instruction="青",
        language="ja",
    )
    assert "reflected_answers" not in plain
    assert "counselling" not in plain_user


_SENSITIVE_GENERATED = {
    **_GENERATED,
    "wish": "胸の大きな美女になって、男の人に抱きしめられてみたいんだ",
    "experience": "仕上がった姿で、顔の見えない成人男性に後ろから抱きしめられる",
}


def _fake_generation_with_prompts(
    monkeypatch, replies: list[str]
) -> list[tuple[str, str]]:
    prompts: list[tuple[str, str]] = []

    async def fake(system_prompt: str, user_prompt: str, *, novelai_model):
        prompts.append((system_prompt, user_prompt))
        return replies[min(len(prompts), len(replies)) - 1]

    monkeypatch.setattr(request_module, "_generate_text", fake)
    return prompts


@pytest.mark.asyncio
async def test_create_request_sensitive_saves_the_experience(
    isolated_db, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory)
    prompts = _fake_generation_with_prompts(
        monkeypatch, [json.dumps(_SENSITIVE_GENERATED)]
    )

    view, _ = await session_request_service.create_request(
        "s1", language="ja", sensitive=True
    )

    assert view["sensitive"] is True
    assert view["sensitive_fallback"] is False
    assert view["experience"] == _SENSITIVE_GENERATED["experience"]
    stored = await session_store.get_session_request("s1")
    assert stored["sensitive"] is True
    assert stored["experience"] == _SENSITIVE_GENERATED["experience"]
    system, user = prompts[0]
    assert "Write the sexual content of wish and experience explicitly" in system
    assert "a hug, a kiss, or being held is never enough" in system
    assert "18 or older" in system
    assert '"experience"' in system
    assert "Never pair a male body with a male partner" in system
    # 願う行為は Python が選んだテーマの候補で、異性の体と同性の体の両方が並ぶ
    payload = json.loads(user)
    candidates = payload["desire_candidates"]
    assert {item["act"] for item in candidates} <= {
        item.act for item in SENSITIVE_DESIRES
    }
    assert {item["target_body"] for item in candidates} == {"female", "male"}
    assert payload["motive"] in {"self", "crush"}


@pytest.mark.parametrize(
    ("wish", "word", "fits"),
    [
        ("僕を女の子にして、好きな彼に舐められたいんだ", "彼", True),
        # 実際の生成: 相手は男性なのに「あの子」で、女の子に読めた
        ("僕を女の子にして…あの子に舐められたいんだ", "彼", False),
        ("好きな彼女のために女の子になりたい", "彼", False),
        # 実際の生成: 相手は女性なのに「彼」と書いた
        ("男らしい体にして、好きな彼とセックスしたい", "彼女", False),
        ("男らしい体にして、好きな彼女を抱きたい", "彼女", True),
        ("Make me a girl he would love, so he can lick me", "him", True),
        ("Make me a girl she would love", "him", False),
    ],
)
def test_crush_wording_fits_the_partner_sex(wish: str, word: str, fits: bool) -> None:
    assert crush_wording_fits(wish, word) is fits


def _crush_generation(monkeypatch) -> None:
    # 意中の相手のための願いで、候補は「男性に舐められる」と百合の2つにする
    desires = {item.id: item for item in SENSITIVE_DESIRES}
    monkeypatch.setattr(request_module, "pick_sensitive_motive", lambda seed: "crush")
    monkeypatch.setattr(
        request_module,
        "pick_sensitive_candidates",
        lambda bodies, seed, *, motive: [
            desires["cunnilingus"],
            desires["yuri_fingering"],
        ],
    )


_CRUSH_GENERATED = {
    **_SENSITIVE_GENERATED,
    "desire_id": "cunnilingus",
    "wish": "僕を女の子にして…あの子に舐められたいんだ",
    "experience": "夢の中の寝室で、ユウは顔の見えない彼に脚を開かれ、舌で愛撫される",
}


@pytest.mark.asyncio
async def test_create_request_repairs_the_crush_wording(
    isolated_db, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory)
    _crush_generation(monkeypatch)
    repaired = {
        **_CRUSH_GENERATED,
        "wish": "僕を女の子にして…好きな彼に舐められたいんだ",
    }
    prompts = _fake_generation_with_prompts(
        monkeypatch, [json.dumps(_CRUSH_GENERATED), json.dumps(repaired)]
    )

    view, _ = await session_request_service.create_request(
        "s1", language="ja", sensitive=True
    )

    assert view["wish"] == repaired["wish"]
    assert "wish and experience must refer to the loved person as 彼" in prompts[1][1]
    candidates = json.loads(prompts[0][1])["desire_candidates"]
    assert [item["partner_word"] for item in candidates] == ["彼", "彼女"]


@pytest.mark.asyncio
async def test_create_request_retries_as_self_when_only_the_wording_is_off(
    isolated_db, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory)
    _crush_generation(monkeypatch)
    # 実際の生成: 相手は女性なのに、修復しても願いと体験で「彼」と書き続けた。
    # 相手の性別を取り違えたまま出さず、動機を自分の憧れにして作り直す(全年齢には落とさない)
    wrong = {
        **_CRUSH_GENERATED,
        "desire_id": "yuri_fingering",
        "wish": "可愛い女の子にして、好きな彼に指で愛されたい",
        "experience": "夢の中の寝室で、ユウは顔の見えない彼に指で愛される",
    }
    self_generated = {
        **_CRUSH_GENERATED,
        "wish": "僕を女の子にして、男の人に舐められてみたいんだ",
        "experience": "夢の中の寝室で、ユウは顔の見えない男性に舌で愛撫される",
    }
    prompts = _fake_generation_with_prompts(
        monkeypatch,
        [json.dumps(wrong), json.dumps(wrong), json.dumps(self_generated)],
    )

    view, _ = await session_request_service.create_request(
        "s1", language="ja", sensitive=True
    )

    assert view["sensitive"] is True
    assert view["sensitive_fallback"] is False
    assert view["wish"] == self_generated["wish"]
    assert len(prompts) == 3
    retry_payload = json.loads(prompts[2][1])
    assert retry_payload["motive"] == "self"
    assert all(
        "partner_word" not in item for item in retry_payload["desire_candidates"]
    )


@pytest.mark.asyncio
async def test_create_request_falls_back_to_all_ages_when_the_model_declines(
    isolated_db, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory)
    # 生成と修復の2回とも JSON にならない(応じない)と、全年齢で作り直す
    prompts = _fake_generation_with_prompts(
        monkeypatch,
        ["その依頼には応じられません", "応じられません", json.dumps(_GENERATED)],
    )

    view, _ = await session_request_service.create_request(
        "s1", language="ja", sensitive=True
    )

    assert view["sensitive"] is False
    assert view["sensitive_fallback"] is True
    assert view["experience"] == ""
    assert view["wish"] == _GENERATED["wish"]
    assert "Never write sexual content." in prompts[-1][0]
    stored = await session_store.get_session_request("s1")
    assert stored["sensitive"] is False
    assert stored["experience"] == ""


@pytest.mark.asyncio
async def test_all_ages_request_hides_sexual_content_and_experience(
    isolated_db, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory)
    # 全年齢の依頼では、モデルが experience を返しても保存しない
    prompts = _fake_generation_with_prompts(
        monkeypatch, [json.dumps(_SENSITIVE_GENERATED)]
    )

    view, _ = await session_request_service.create_request("s1", language="ja")

    assert view["sensitive"] is False
    assert view["experience"] == ""
    assert "Never write sexual content." in prompts[0][0]
    assert '"experience"' not in prompts[0][0]
    assert (await session_store.get_session_request("s1"))["experience"] == ""


def test_generated_sensitive_request_requires_the_experience() -> None:
    with pytest.raises(ValueError):
        GeneratedSensitiveRequest.model_validate(_GENERATED)
    with pytest.raises(ValueError):
        GeneratedSensitiveRequest.model_validate({**_GENERATED, "experience": "  "})


@pytest.mark.asyncio
async def test_ask_question_allows_adult_answers_only_for_sensitive_requests(
    isolated_db, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory)
    prompts = _fake_generation_with_prompts(monkeypatch, ["ないしょだよ"])

    for sensitive in (False, True):
        await session_store.save_session_request(
            "s1",
            wish=_REQUEST["wish"],
            preferences=_PREFERENCES,
            language="ja",
            sensitive=sensitive,
            experience="抱きしめられる" if sensitive else None,
        )
        await session_request_service.ask_question("s1", "好きな服は？", language="ja")

    assert "Never write sexual content." in prompts[0][0]
    assert "Sexual content is allowed" in prompts[1][0]
    assert "18 or older" in prompts[1][0]


def test_grounded_met_ids_accepts_body_and_lingerie_tags() -> None:
    preferences = [
        {"id": "p1", "text": "大きな胸", "hint": "体型"},
        {"id": "p2", "text": "黒いランジェリー", "hint": "下着"},
    ]
    look = "1girl, solo, long black hair, large breasts, black lingerie, garter belt"
    ids = grounded_met_ids(
        _output([("p1", "large breasts"), ("p2", "black lingerie")]),
        preferences,
        look,
        look_is_tags=True,
    )
    assert ids == ["p1", "p2"]
    # 体型の好みに髪のタグは根拠にならない
    hair = grounded_met_ids(
        _output([("p1", "long black hair")]), preferences, look, look_is_tags=True
    )
    assert hair == []


def test_catalog_never_pairs_a_male_body_with_a_male_partner() -> None:
    assert all(
        not (item.body == "male" and item.partner == "man")
        for item in SENSITIVE_DESIRES
    )
    # 女性の体で男性と・女性と(百合)・ひとり、男性の体で女性と・ひとりのテーマがある
    pairs = {(item.body, item.partner) for item in SENSITIVE_DESIRES}
    assert pairs == {
        ("female", "man"),
        ("female", "woman"),
        ("female", "none"),
        ("male", "woman"),
        ("male", "none"),
    }


@pytest.mark.parametrize(
    ("look", "returning", "bodies"),
    [
        # 初めての来店は異性の体も同性の体もありうる(生成が態度から選ぶ)
        ("1boy, short black hair", False, ("female", "male")),
        ("1girl, long hair", False, ("female", "male")),
        # 前回の姿のまま来たお客様は、いまの姿の体のまま
        ("1girl, long black hair, large breasts", True, ("female",)),
        ("1boy, suit", True, ("male",)),
        ("", True, ("female", "male")),
    ],
)
def test_sensitive_body_options(look, returning, bodies) -> None:
    assert sensitive_body_options(look, returning=returning) == bodies


def test_candidates_cover_each_body_and_vary() -> None:
    seen: set[str] = set()
    for index in range(40):
        candidates = pick_sensitive_candidates(
            ("female", "male"), f"s{index}", motive="self"
        )
        assert len(candidates) == 3
        assert {item.body for item in candidates} == {"female", "male"}
        assert len({item.id for item in candidates}) == 3
        seen.update(item.id for item in candidates)
    assert len(seen) > 8
    # 前回の姿のまま来たお客様は、その体のテーマだけ
    returning = pick_sensitive_candidates(("female",), "s1", motive="self")
    assert {item.body for item in returning} == {"female"}
    # 意中の相手のための願いには、ひとりのテーマを入れない
    for index in range(40):
        crush = pick_sensitive_candidates(
            ("female", "male"), f"c{index}", motive="crush"
        )
        assert not any(item.solo for item in crush)


def test_motive_is_crush_for_about_a_third_of_visits() -> None:
    motives = [pick_sensitive_motive(f"m{index}") for index in range(1000)]
    rate = motives.count("crush") / len(motives)
    assert 0.25 < rate < 0.35
    assert pick_sensitive_motive("m1") == pick_sensitive_motive("m1")


def test_generation_prompt_offers_candidates_and_follows_the_motive() -> None:
    profile = {"name": "ユウ", "gender": "man", "pronoun": "僕"}
    candidates = pick_sensitive_candidates(("female", "male"), "s1", motive="crush")

    with pytest.raises(ValueError):
        build_request_generation_prompt(profile, "1boy", "ja", sensitive=True)
    crush_system, crush_user = build_request_generation_prompt(
        profile, "1boy", "ja", sensitive=True, desires=candidates, motive="crush"
    )
    self_system, _ = build_request_generation_prompt(
        profile, "1boy", "ja", sensitive=True, desires=candidates, motive="self"
    )

    payload = json.loads(crush_user)
    assert [item["id"] for item in payload["desire_candidates"]] == [
        item.id for item in candidates
    ]
    assert payload["desire_candidates"][0]["partner"] in {"man", "woman", "none"}
    assert "desire_id" in crush_system
    assert "one who has never wished to change sex stays their own sex" in crush_system
    assert "motive is crush" in crush_system
    assert "motive is self" in self_system
    assert "faceless adult" in crush_system
    # 体験は、施術の直後にサロンが見せる夢の中の場面
    assert "the salon lets the character dream" in self_system
    assert "never the salon or anywhere with onlookers" in self_system
    # 意中の相手は、テーマの相手の性別が分かる言葉で呼び、体験でも同じ人にする
    assert "partner_word" in crush_system
    assert "never as a stranger" in crush_system
    assert "partner_word" not in self_system
    words = {"man": "彼", "woman": "彼女"}
    for item in payload["desire_candidates"]:
        assert item.get("partner_word") == words.get(item["partner"])
    _, self_user = build_request_generation_prompt(
        profile, "1boy", "ja", sensitive=True, desires=candidates, motive="self"
    )
    assert all(
        "partner_word" not in item
        for item in json.loads(self_user)["desire_candidates"]
    )
    _, english_user = build_request_generation_prompt(
        profile, "1boy", "en", sensitive=True, desires=candidates, motive="crush"
    )
    english_words = {"man": "him", "woman": "her"}
    for item in json.loads(english_user)["desire_candidates"]:
        assert item.get("partner_word") == english_words.get(item["partner"])
    # 全年齢の依頼には行為の候補を渡さない
    _, plain_user = build_request_generation_prompt(profile, "1boy", "ja")
    assert "desire_candidates" not in json.loads(plain_user)


@pytest.mark.parametrize(
    ("preference", "evidence", "met"),
    [
        # 実際の誤判定: ミモレ丈の好みを miniskirt で満たしたことにし、mid-calf を通さなかった
        ("ふわっとしたミモレ丈のスカート", "blue miniskirt", False),
        ("ふわっとしたミモレ丈のスカート", "mid-calf skirt", True),
        ("ふわっとしたミモレ丈のスカート", "long skirt", True),
        ("膝上の短い丈", "miniskirt", True),
        ("膝上の短い丈", "long skirt", False),
        ("膝丈のスカート", "knee-length skirt", True),
    ],
)
def test_grounded_met_ids_requires_the_same_length_direction(
    preference, evidence, met
) -> None:
    preferences = [{"id": "p1", "text": preference, "hint": "丈"}]
    ids = grounded_met_ids(
        _output([("p1", evidence)]),
        preferences,
        f"1girl, white blouse, {evidence}",
        look_is_tags=True,
    )
    assert (ids == ["p1"]) is met


def test_evaluation_prompt_judges_only_the_look_for_sensitive_requests() -> None:
    from gateway.services.session_request_prompts import (
        build_request_evaluation_prompt,
    )

    args = {
        "wish": "女の子にして、クンニされたい",
        "preferences": _PREFERENCES,
        "current_look": "1girl, frills skirt",
        "instruction": "フリルスカート",
        "language": "ja",
    }
    sensitive_system, _ = build_request_evaluation_prompt(**args, sensitive=True)
    plain_system, _ = build_request_evaluation_prompt(**args)

    assert "never lower fit because the act itself is not shown" in sensitive_system
    assert "never lower fit" not in plain_system
    # ヒントはまだ満たしていない好みについて、どちらへ変えるかを示す
    assert "never base it on counselling answers" in plain_system
    assert "say which way to change the current look" in plain_system
    assert '"hints":[{"id":"p2","text":"..."}]' in plain_system


def test_experience_bonus_is_added_and_capped() -> None:
    from gateway.services.session_request_service import with_experience

    assert with_experience(57, True) == 72
    assert with_experience(57, False) == 57
    assert with_experience(95, True) == 100


# --- サロンの来客の種類: 願う体 ---


@pytest.mark.asyncio
async def test_create_request_follows_the_salon_target_body(
    isolated_db, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory)
    prompts = _fake_generation_with_prompts(
        monkeypatch, [json.dumps(_SENSITIVE_GENERATED)]
    )

    await session_request_service.create_request(
        "s1", language="ja", sensitive=True, target_body="female"
    )

    system, user = prompts[0]
    payload = json.loads(user)
    # 願う体は Python が決め、行為の候補もその体のものだけにする
    assert {item["target_body"] for item in payload["desire_candidates"]} == {"female"}
    assert payload["target_body"] == "female"
    assert "target_body is given" in system


@pytest.mark.asyncio
async def test_returning_customer_ignores_the_target_body(
    isolated_db, monkeypatch
) -> None:
    await _seed_session(isolated_db.async_factory)
    calls = _fake_generation(monkeypatch, [_GENERATED])

    await session_request_service.create_request(
        "s1",
        language="ja",
        previous_visit={"wish": "ふんわりした姿に", "review": "また来ます"},
        target_body="male",
    )

    assert "target_body" not in json.loads(calls[0])


def test_all_ages_request_prompt_carries_the_target_body() -> None:
    profile = {"name": "ユウヤ", "gender": "man"}

    system, user = build_request_generation_prompt(
        profile, "1boy", "ja", target_body="female"
    )
    plain_system, plain_user = build_request_generation_prompt(profile, "1boy", "ja")

    assert json.loads(user)["target_body"] == "female"
    assert "turned into the other sex" in system
    assert "target_body" not in json.loads(plain_user)
    assert "target_body is given" not in plain_system
