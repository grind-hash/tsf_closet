from types import SimpleNamespace

from gateway.services.conversation import build_conversation_prompt


def test_build_conversation_prompt_adds_english_only_constraint() -> None:
    stats = SimpleNamespace(bloom=30)
    system_prompt, user_prompt = build_conversation_prompt(
        message="hello",
        conversation_history=[],
        stats=stats,
        current_outfit_desc="casual",
        character_name="Alice",
        pronoun="I",
        attributes=[],
        nsfw_mode=False,
        transformation_count=1,
        language="en",
    )

    assert "Respond in natural English only" in system_prompt
    assert "English only" in user_prompt
