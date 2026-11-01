"""依頼モード(session_requests)のサービス・ストア・応答のテスト。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import update

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
    evaluation_record,
    feeling_context,
    grounded_met_ids,
    is_fulfilled,
    listening_bonus,
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
    }
    assert not is_fulfilled(partial)
    complete = evaluation_record(
        _output([("p1", "pale pink dress"), ("p2", "long dress")], hint="残り"),
        _PREFERENCES,
        look_text=_LOOK,
        look_is_tags=True,
    )
    assert complete["hint"] == ""
    assert is_fulfilled(complete)


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
        }
    ]
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
        "s1", "好きな色はある？", language="ja"
    )
    assert view["questions"] == [
        {
            "question": "好きな色はある？",
            "answer": "春に咲く花みたいな、やわらかい色が好きなんだ",
            "reflected": False,
        }
    ]
    assert view["questions_remaining"] == 0
    # 伏せた好みは手掛かりにするため答える側へ渡すが、画面へは本文を送らない
    payload = json.loads(prompts[0][1])
    assert payload["hidden_preferences"][0]["text"] == "淡いピンクのドレス"
    assert payload["stylist_question"] == "好きな色はある？"
    assert "without ever stating the preference itself" in prompts[0][0]
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
    system = prompts[0][0]
    assert "Sexual content is allowed" in system
    assert "18 or older" in system
    assert '"experience"' in system


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
