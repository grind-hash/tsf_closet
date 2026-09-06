"""キャラチャットのプロンプト純関数と LLM 出力モデル。"""

from __future__ import annotations

from gateway.consts.character_chat import LOOKUP_MAX_PER_TURN
from gateway.services.character_chat_models import (
    CharacterChatAppearanceOutput,
    CharacterChatPlan,
    non_english_tag_parts,
)
from gateway.services.character_chat_prompts import (
    appearance_change_system_prompt,
    appearance_change_user_prompt,
    base_persona_block,
    lookup_block,
    memory_block,
    planner_system_prompt,
    reply_system_prompt,
    session_persona_block,
)


def test_memory_block_empty_and_wrapped() -> None:
    assert memory_block("", "ja") == ""
    assert memory_block(None, "en") == ""
    block = memory_block("メイド服を好む", "ja")
    assert "この人について知っていること" in block
    assert "メイド服を好む" in block
    assert "最優先" not in block


def test_reply_system_prompt_includes_sections() -> None:
    prompt = reply_system_prompt(
        "ja",
        name="セレナ",
        pronoun="私",
        persona_block=base_persona_block("ja"),
        memory_block_text=memory_block("メイド服を好む", "ja"),
        summary_text="これまでの話題: 挨拶",
        lookup_block_text=lookup_block("## 最近のセッション\n- 1件", "ja"),
        appearance_description="紫のドレス",
        appearance_change_request="ドレスに着替えて",
    )
    assert "セレナ" in prompt
    assert "メイド服を好む" in prompt
    assert "これまでの話題: 挨拶" in prompt
    assert "最近のセッション" in prompt
    assert "紫のドレス" in prompt
    assert "着替え中" in prompt
    assert "Respond in Japanese" in prompt or "日本語" in prompt


def test_session_persona_block_reflects_stage() -> None:
    persona = {
        "character_name": "サクラ",
        "pronoun": "僕",
        "stats": {"bloom": 30, "shame": 60, "adaptation": 10},
        "transformation_count": 2,
        "attributes": ["猫耳が生えている"],
        "timeline": [{"type": "dress_up", "text": "メイド服に着替える"}],
        "outfit_description": "maid dress, apron",
        "nsfw_mode": False,
    }
    block = session_persona_block(persona, "ja")
    assert "サクラ" in block
    assert "揺らぎ・葛藤" in block
    assert "猫耳が生えている" in block
    assert "[着替] メイド服に着替える" in block
    assert "maid dress, apron" in block
    untransformed = session_persona_block({**persona, "transformation_count": 0}, "ja")
    assert "まだ変身を経験していない" in untransformed


def test_planner_prompt_lists_every_lookup_kind() -> None:
    prompt = planner_system_prompt("ja")
    for kind in (
        "recent_sessions",
        "session_detail",
        "search_sessions",
        "tendencies",
        "recent_adventures",
    ):
        assert f'"{kind}"' in prompt


def test_plan_model_is_lenient() -> None:
    plan = CharacterChatPlan.model_validate(
        {
            "lookups": [
                {"kind": "tendencies", "limit": "99"},
                {"kind": "bogus"},
                "recent_sessions",
                {"kind": "search_sessions", "query": "  メイド  服 "},
                {"kind": "session_detail", "session_id": "abc"},
                {"kind": "recent_adventures"},
            ],
            "appearance_request": "null",
        }
    )
    assert len(plan.lookups) == LOOKUP_MAX_PER_TURN
    assert plan.lookups[0].kind == "tendencies"
    assert plan.lookups[0].limit == 10
    assert plan.lookups[1].kind == "recent_sessions"
    assert plan.lookups[2].query == "メイド 服"
    assert plan.appearance_request is None

    plain = CharacterChatPlan.model_validate(
        {"lookups": "x", "appearance_request": " ドレスに着替えて "}
    )
    assert plain.lookups == []
    assert plain.appearance_request == "ドレスに着替えて"


def test_plan_query_strips_quotes() -> None:
    """判定 LLM が検索語を引用符で包んでも、LIKE に渡す語と保存する語から外す。"""

    def query(value: str) -> str | None:
        plan = CharacterChatPlan.model_validate(
            {"lookups": [{"kind": "search_sessions", "query": value}]}
        )
        return plan.lookups[0].query

    assert query('"元々男だったのに"') == "元々男だったのに"
    assert query("「元々男だったのに」") == "元々男だったのに"
    assert query("“メイド服” '猫耳'") == "メイド服 猫耳"
    assert query("メイド, 猫耳、") == "メイド 猫耳"
    assert query('""') is None
    assert query("null") is None


def test_appearance_output_cleans_tags() -> None:
    output = CharacterChatAppearanceOutput.model_validate(
        {
            "identity_tags": ["1girl", " silver hair ", ""],
            "clothing_tags": "red dress,, high heels ,",
            "description": "  赤いドレス姿  ",
        }
    )
    assert output.identity_tags == "1girl, silver hair"
    assert output.clothing_tags == "red dress, high heels"
    assert output.description == "赤いドレス姿"


def test_non_english_tag_parts_detects_japanese() -> None:
    assert non_english_tag_parts(
        "white chiffon blouse, 総レースタイトスカート, ,黒のニーハイ"
    ) == ["総レースタイトスカート", "黒のニーハイ"]
    assert non_english_tag_parts("1girl, solo, silver hair, green eyes") == []
    assert non_english_tag_parts("") == []


def test_appearance_change_prompts_require_english_tags() -> None:
    system = appearance_change_system_prompt("ja")
    assert "English only" in system
    assert "chiffon blouse" in system
    assert "Japanese" in system

    plain = appearance_change_user_prompt(
        identity_tags="1girl, solo", clothing_tags="red dress", request="着替えて"
    )
    assert "rejected_previous_output" not in plain
    retry = appearance_change_user_prompt(
        identity_tags="1girl, solo",
        clothing_tags="red dress",
        request="着替えて",
        rejected_tags="シフォンブラウス, 総レースタイトスカート",
    )
    assert "rejected_previous_output" in retry
    assert "総レースタイトスカート" in retry
    assert "translate garment names" in retry
