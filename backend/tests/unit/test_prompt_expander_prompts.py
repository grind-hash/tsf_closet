"""Prompt Expander のプロンプト組み立てとサニタイズのテスト。"""

from __future__ import annotations

import pytest

from gateway.services.prompt_expander_prompts import (
    ADULT_CONTENT_RULE,
    BASE_SYSTEM_PROMPT_TAGS,
    PromptExpanderOutputError,
    SAFE_CONTENT_RULE,
    build_negative_system_prompt,
    build_negative_user_prompt,
    build_positive_system_prompt,
    build_positive_user_prompt,
    build_suggest_characters_prompts,
    parse_character_json,
    parse_suggestions_json,
    sanitize_prose_prompt,
    sanitize_tag_prompt,
)


class TestSystemPrompt:
    def test_tags_single_uses_ported_prompt_and_safe_rule(self):
        system = build_positive_system_prompt(
            mode="tags", character_mode=False, max_characters=6, nsfw=False
        )
        assert system.startswith(BASE_SYSTEM_PROMPT_TAGS)
        assert "Adult or explicit tags are disabled" in system
        assert "Adult content tags are allowed only" not in system
        assert "最優先指示" not in system

    def test_tags_character_mode_substitutes_max(self):
        system = build_positive_system_prompt(
            mode="tags", character_mode=True, max_characters=22, nsfw=True
        )
        assert '"base_prompt"' in system and '"character_prompts"' in system
        assert "between 1 and 22 character_prompts" in system
        assert "{max_characters}" not in system
        assert "Adult content tags are allowed only" in system

    def test_japanese_modes(self):
        single = build_positive_system_prompt(
            mode="japanese", character_mode=False, max_characters=22, nsfw=False
        )
        assert "natural Japanese prose" in single
        assert "Danbooru-style tags. Do not output JSON" not in single
        multi = build_positive_system_prompt(
            mode="japanese", character_mode=True, max_characters=22, nsfw=False
        )
        assert "between 1 and 22 character_prompts" in multi
        assert "Japanese" in multi

    def test_memory_block_is_appended_last_only_when_present(self):
        system = build_positive_system_prompt(
            mode="tags",
            character_mode=False,
            max_characters=6,
            nsfw=False,
            memory_text="金髪ツインテールが好き",
            language="ja",
        )
        assert system.endswith("金髪ツインテールが好き\n")
        assert "最優先指示" in system
        assert system.index(SAFE_CONTENT_RULE.strip()) < system.index("最優先指示")
        without = build_positive_system_prompt(
            mode="tags",
            character_mode=False,
            max_characters=6,
            nsfw=False,
            memory_text="  ",
        )
        assert "最優先指示" not in without

    def test_adult_rule_text(self):
        assert ADULT_CONTENT_RULE.startswith("\n- Adult content tags are allowed only")


class TestUserPrompt:
    def test_new_prompt_placeholder_and_closing(self):
        user = build_positive_user_prompt(instruction="赤いドレスに着替える")
        assert user.startswith("Current positive prompt:\nNone (new prompt)")
        assert "User instruction:\n赤いドレスに着替える" in user
        assert user.endswith(
            "Preserve every current element that the instruction does not explicitly change."
        )
        assert "Create the complete replacement positive prompt." in user

    def test_current_prompt_characters_and_context(self):
        user = build_positive_user_prompt(
            instruction="着せ替え",
            current_prompt="1girl, blue dress",
            current_character_prompts=["1girl, black hair", "", "1boy, glasses"],
            character_mode=True,
            context_description="A girl in a blue dress standing in a park.",
        )
        assert "Current positive prompt:\n1girl, blue dress" in user
        assert (
            "Current character prompts:\n1. 1girl, black hair\n2. 1boy, glasses" in user
        )
        assert (
            "Current image description (reference only):\nA girl in a blue dress"
            in user
        )
        assert "Create separate base_prompt and character_prompts JSON" in user

    def test_characters_ignored_when_not_character_mode(self):
        user = build_positive_user_prompt(
            instruction="x", current_character_prompts=["1girl"], character_mode=False
        )
        assert "Current character prompts" not in user

    def test_negative_prompts(self):
        system = build_negative_system_prompt(mode="tags")
        assert "negative prompt" in system
        user = build_negative_user_prompt(
            instruction="眼鏡を出さない", current_negative=None
        )
        assert "Current negative prompt:\nNone" in user
        assert "What the user wants to avoid:\n眼鏡を出さない" in user
        ja = build_negative_system_prompt(
            mode="japanese", memory_text="m", language="en"
        )
        assert "Japanese" in ja and "HIGHEST PRIORITY" in ja

    def test_suggest_prompts(self):
        system, user = build_suggest_characters_prompts(
            memory_text="銀髪の女性が好き", count=3, mode="tags", nsfw=False
        )
        assert "propose 3 favorite character designs" in system
        assert '"suggestions"' in system
        assert "1girl" in system
        assert "銀髪の女性が好き" in system
        assert user
        system_ja, _ = build_suggest_characters_prompts(
            memory_text="m", count=2, mode="japanese", nsfw=True
        )
        assert "Japanese prose" in system_ja
        assert "Adult content tags are allowed only" in system_ja


class TestSanitize:
    def test_tag_prompt_fence_newlines_and_quality(self):
        assert (
            sanitize_tag_prompt("```text\n1girl, red dress\nsmile\n```")
            == "1girl, red dress, smile, moe, anime, very aesthetic, best quality"
        )

    def test_tag_prompt_quoted_json_string_and_label(self):
        assert (
            sanitize_tag_prompt('"Prompt: 1girl, cat ears"', ensure_quality=False)
            == "1girl, cat ears"
        )
        assert (
            sanitize_tag_prompt("positive prompt: park", ensure_quality=False) == "park"
        )

    def test_tag_prompt_repeated_commas_and_trailing(self):
        assert sanitize_tag_prompt("a,, b ,,, c,", ensure_quality=False) == "a, b, c"

    def test_quality_tags_not_duplicated(self):
        result = sanitize_tag_prompt("park, Best Quality, moe")
        assert result == "park, Best Quality, moe, anime, very aesthetic"

    def test_empty_stays_empty(self):
        assert sanitize_tag_prompt("   ") == ""
        assert sanitize_prose_prompt("") == ""

    def test_prose_prompt_keeps_japanese_punctuation(self):
        raw = "```\n「プロンプト：銀髪の少女が、赤いドレスを着て微笑んでいる。背景は夕暮れの公園。」\n```"
        assert (
            sanitize_prose_prompt(raw)
            == "銀髪の少女が、赤いドレスを着て微笑んでいる。背景は夕暮れの公園。"
        )

    def test_prose_prompt_collapses_lines(self):
        assert sanitize_prose_prompt("一行目。\n\n二行目。") == "一行目。 二行目。"


class TestCharacterJson:
    def test_parses_fenced_json_and_adds_quality_to_base_only(self):
        raw = '```json\n{"base_prompt":"2girls, cafe","character_prompts":["1girl, black hair","1girl, blonde hair"]}\n```'
        base, characters = parse_character_json(raw, max_characters=6, mode="tags")
        assert base == "2girls, cafe, moe, anime, very aesthetic, best quality"
        assert characters == ["1girl, black hair", "1girl, blonde hair"]

    def test_accepts_surrounding_prose(self):
        raw = (
            'Here you go:\n{"base_prompt":"park","character_prompts":["1girl"]}\nEnjoy!'
        )
        base, characters = parse_character_json(raw, max_characters=6, mode="tags")
        assert base.startswith("park")
        assert characters == ["1girl"]

    def test_truncates_over_limit(self):
        raw = '{"base_prompt":"park","character_prompts":["a","b","c","d","e","f","g"]}'
        _, characters = parse_character_json(raw, max_characters=6, mode="tags")
        assert characters == ["a", "b", "c", "d", "e", "f"]

    def test_japanese_mode_does_not_add_quality_tags(self):
        raw = '{"base_prompt":"夕暮れの公園。","character_prompts":["銀髪の少女。"]}'
        base, characters = parse_character_json(raw, max_characters=22, mode="japanese")
        assert base == "夕暮れの公園。"
        assert characters == ["銀髪の少女。"]

    @pytest.mark.parametrize(
        "raw",
        [
            "not json",
            '{"character_prompts":["1girl"]}',
            '{"base_prompt":"park","character_prompts":[]}',
            '{"base_prompt":"park","character_prompts":"1girl"}',
            "[]",
        ],
    )
    def test_rejects_invalid(self, raw: str):
        with pytest.raises(PromptExpanderOutputError):
            parse_character_json(raw, max_characters=6, mode="tags")


class TestSuggestionsJson:
    def test_parses_and_limits(self):
        raw = '{"suggestions":[{"title":"A","prompt":"1girl, a"},{"title":"B","prompt":"1girl, b"},{"title":"C","prompt":"1girl, c"}]}'
        items = parse_suggestions_json(raw, count=2, mode="tags")
        assert items == [
            {"title": "A", "prompt": "1girl, a"},
            {"title": "B", "prompt": "1girl, b"},
        ]

    def test_accepts_bare_list_and_skips_invalid(self):
        raw = '[{"title":"A","prompt":""},{"prompt":"1boy, glasses"},"junk"]'
        items = parse_suggestions_json(raw, count=3, mode="tags")
        assert items == [{"title": "", "prompt": "1boy, glasses"}]

    def test_rejects_empty(self):
        with pytest.raises(PromptExpanderOutputError):
            parse_suggestions_json('{"suggestions":[]}', count=3, mode="tags")
