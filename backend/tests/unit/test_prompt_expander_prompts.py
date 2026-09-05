"""Prompt Expander のプロンプト組み立てとサニタイズのテスト。"""

from __future__ import annotations

import pytest

from gateway.services.prompt_expander_prompts import (
    ADULT_CONTENT_RULE,
    BASE_SYSTEM_PROMPT_TAGS,
    JAPANESE_TAG_GLOSSARY_RULE,
    SAFE_CONTENT_RULE,
    SUGGEST_INPUT_BIAS_RULE,
    SUGGEST_NO_MEMORY_RULE,
    SUGGEST_USER_PROMPT,
    PromptExpanderOutputError,
    build_negative_system_prompt,
    build_negative_user_prompt,
    build_positive_system_prompt,
    build_positive_user_prompt,
    build_suggest_characters_prompts,
    build_suggest_user_prompt,
    parse_character_json,
    parse_suggestions_json,
    replace_false_friend_tokens,
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


class TestMangaPrompt:
    """漫画モード（V5 コマ割り）の system プロンプトと JSON 解析。"""

    def test_manga_tags_character_mode_fixed_panels(self):
        from gateway.services.prompt_expander_prompts import MangaOptions

        system = build_positive_system_prompt(
            mode="tags",
            character_mode=True,
            max_characters=22,
            nsfw=False,
            manga=MangaOptions(panel_count=3, layout="vertical", text_language="en"),
        )
        assert '"base_tags"' in system and '"panel_description"' in system
        assert "Describe exactly 3 comic panels." in system
        assert "stacked vertically" in system
        assert '"english text", "text", "speech bubble", "border"' in system
        assert "between 1 and 22 items" in system
        assert "There's a speech bubble next to the girl that says \"Ha ha!" in system
        assert 'there\'s also a "SLAM"' in system
        # 通常モードの「複数コマ禁止」は含まれない
        assert "Never create before/after panels" not in system
        assert "Adult or explicit tags are disabled" in system

    def test_manga_is_english_regardless_of_expand_mode(self):
        """日本語モードでもコマ説明・外見は英語（日本語の説明文はナレーション枠として描画されるため）。"""
        from gateway.services.prompt_expander_prompts import MangaOptions

        system = build_positive_system_prompt(
            mode="japanese",
            character_mode=False,
            max_characters=22,
            nsfw=True,
            manga=MangaOptions(
                panel_count=0, dialogue=False, sound_effects=False, text_language="ja"
            ),
        )
        assert "between 2 and 4" in system
        assert "natural English prose" in system
        assert "natural Japanese prose" not in system
        assert "3コマの漫画です" not in system
        assert "Return an empty list []" in system
        assert "Do not add any speech bubbles" in system
        assert "Do not add sound effects" in system
        assert "renders Japanese prose as caption boxes" in system
        # 既定ではナレーション枠は【】で指定したときだけ
        assert "Do not invent additional narration boxes or captions" in system
        assert "Do not describe titles, signs, labels" in system
        # 文字系タグは border だけ
        assert 'and "border". Do not describe individual panels' in system

    def test_manga_single_panel_and_japanese_dialogue_examples(self):
        from gateway.services.prompt_expander_prompts import MangaOptions

        system = build_positive_system_prompt(
            mode="tags",
            character_mode=False,
            max_characters=6,
            nsfw=False,
            manga=MangaOptions(panel_count=1, text_language="ja", layout="grid"),
        )
        assert "Describe exactly 1 comic panel." in system
        assert '"japanese text", "text", "speech bubble", "border"' in system
        assert "grid of two columns" in system
        # セリフ・効果音の例文は英語の文で、引用符の中だけが日本語
        assert 'says "これ、僕にぴったり…！"' in system
        assert 'there\'s also a "ドン！" visible' in system
        assert "it must be in Japanese" in system

    def test_manga_reading_direction_defaults_to_japanese_rtl(self):
        """既定は日本式（右上始まり、右→左）。各コマの位置語を要求する。"""
        from gateway.services.prompt_expander_prompts import MangaOptions

        system = build_positive_system_prompt(
            mode="tags",
            character_mode=False,
            max_characters=6,
            nsfw=False,
            manga=MangaOptions(panel_count=4, layout="grid"),
        )
        assert "Reading order is Japanese manga style: right to left" in system
        assert "The first panel is at the top right" in system
        assert 'Begin panel_description with "read from right to left"' in system
        assert "The first panel, at the top right, shows" in system
        assert "read right to left within each row" in system
        assert "left-to-right manga" not in system

        system = build_positive_system_prompt(
            mode="tags",
            character_mode=False,
            max_characters=6,
            nsfw=False,
            manga=MangaOptions(
                panel_count=3, layout="horizontal", reading_direction="ltr"
            ),
        )
        assert "Reading order is Western style: left to right" in system
        assert 'include the tag "left-to-right manga" in base_tags' in system
        assert "the first panel is the leftmost" in system
        assert (
            "right to left"
            not in system.split("For example:")[0].split("Reading order")[0]
        )

    def test_manga_user_prompt_closing(self):
        user = build_positive_user_prompt(
            instruction="三コマで変身する", character_mode=True, manga=True
        )
        assert user.endswith(
            "Create the base_tags, panel_description and character_prompts JSON "
            "for the comic page. Preserve every current element that the "
            "instruction does not explicitly change."
        )

    def test_parse_manga_json_with_characters(self):
        from gateway.services.prompt_expander_prompts import parse_manga_json

        raw = (
            '```json\n{"base_tags":"2boys, 3girls, english text, text, speech bubble, border",'
            '"panel_description":"There are three comic panels. The first panel shows...",'
            '"character_prompts":["boy, short hair, There\'s a speech bubble next to the boy that says \\"Hi\\"", "  "]}\n```'
        )
        base, characters = parse_manga_json(raw, max_characters=22, character_mode=True)
        # 品質タグはタグ見出し側に入り、コマ説明文の後ろには付かない
        assert base == (
            "2boys, 3girls, english text, text, speech bubble, border, "
            "moe, anime, very aesthetic, best quality, "
            "There are three comic panels. The first panel shows..."
        )
        assert characters == [
            'boy, short hair, There\'s a speech bubble next to the boy that says "Hi"'
        ]

    def test_parse_manga_json_without_characters_ignores_list(self):
        from gateway.services.prompt_expander_prompts import parse_manga_json

        raw = '{"base_tags":"1girl, japanese text, text, speech bubble, border","panel_description":"There are three panels. The girl says \\"これ、私にぴったり…！\\"","character_prompts":["1girl, ignored"]}'
        base, characters = parse_manga_json(
            raw, max_characters=22, character_mode=False
        )
        assert base == (
            "1girl, japanese text, text, speech bubble, border, moe, anime, very "
            'aesthetic, best quality, There are three panels. The girl says "これ、私にぴったり…！"'
        )
        assert characters is None

    def test_parse_manga_json_errors_and_cap(self):
        from gateway.services.prompt_expander_prompts import parse_manga_json

        with pytest.raises(PromptExpanderOutputError):
            parse_manga_json(
                '{"base_tags":"1girl"}', max_characters=6, character_mode=False
            )
        with pytest.raises(PromptExpanderOutputError):
            parse_manga_json(
                '{"base_tags":"1girl","panel_description":"   ","character_prompts":[]}',
                max_characters=6,
                character_mode=False,
            )
        with pytest.raises(PromptExpanderOutputError):
            parse_manga_json(
                '{"base_tags":"1girl","panel_description":"two panels","character_prompts":[]}',
                max_characters=6,
                character_mode=True,
            )
        base, characters = parse_manga_json(
            '{"base_tags":"","panel_description":"two panels","character_prompts":["a","b","c"]}',
            max_characters=2,
            character_mode=True,
        )
        assert base == "two panels"
        assert characters == ["a", "b"]


class TestJapaneseGlossary:
    def test_glossary_rule_in_tags_and_manga_but_not_japanese(self):
        from gateway.services.prompt_expander_prompts import MangaOptions

        tags = build_positive_system_prompt(
            mode="tags", character_mode=False, max_characters=6, nsfw=False
        )
        chars = build_positive_system_prompt(
            mode="tags", character_mode=True, max_characters=6, nsfw=False
        )
        manga = build_positive_system_prompt(
            mode="tags",
            character_mode=False,
            max_characters=22,
            nsfw=False,
            manga=MangaOptions(),
        )
        ja = build_positive_system_prompt(
            mode="japanese", character_mode=False, max_characters=6, nsfw=False
        )
        assert JAPANESE_TAG_GLOSSARY_RULE in tags
        assert JAPANESE_TAG_GLOSSARY_RULE in chars
        assert JAPANESE_TAG_GLOSSARY_RULE in manga
        assert JAPANESE_TAG_GLOSSARY_RULE not in ja
        assert "ショーツ" in tags and "panties" in tags
        # 成人向けルールより前（本体の一部）に置かれる
        assert tags.index(JAPANESE_TAG_GLOSSARY_RULE) < tags.index(
            "Adult or explicit tags are disabled"
        )

    def test_glossary_rule_in_negative_tags_only(self):
        assert JAPANESE_TAG_GLOSSARY_RULE in build_negative_system_prompt(mode="tags")
        assert JAPANESE_TAG_GLOSSARY_RULE not in build_negative_system_prompt(
            mode="japanese"
        )

    @pytest.mark.parametrize(
        ("prompt", "expected"),
        [
            ("1girl, shorts, smile", "1girl, panties, smile"),
            ("shorts, 1girl", "panties, 1girl"),
            ("1girl, shorts", "1girl, panties"),
            ("1girl, Shorts", "1girl, panties"),
            ("1girl,shorts,smile", "1girl,panties,smile"),
            # 複数語・連結語はそのまま
            ("1girl, denim shorts, smile", "1girl, denim shorts, smile"),
            ("1girl, short shorts", "1girl, short shorts"),
            ("1girl, boyshorts", "1girl, boyshorts"),
            ("1girl, shortstack", "1girl, shortstack"),
        ],
    )
    def test_replace_false_friend_tokens(self, prompt, expected):
        assert replace_false_friend_tokens(prompt, "白いショーツ") == expected

    def test_replace_false_friend_tokens_requires_japanese_word(self):
        assert replace_false_friend_tokens("1girl, shorts", "short pants") == (
            "1girl, shorts"
        )
        assert replace_false_friend_tokens("1girl, shorts", None) == "1girl, shorts"
        assert replace_false_friend_tokens("", "ショーツ") == ""

    def test_replace_false_friend_tokens_keeps_multiline_layout(self):
        prompt = "1girl, shorts\nPanel 1: she smiles, shorts\n「やだ」"
        assert replace_false_friend_tokens(prompt, "ショーツ") == (
            "1girl, panties\nPanel 1: she smiles, panties\n「やだ」"
        )


class TestSuggestWithInput:
    def test_user_prompt_without_input_is_unchanged(self):
        assert build_suggest_user_prompt(None) == SUGGEST_USER_PROMPT
        assert build_suggest_user_prompt("   ") == SUGGEST_USER_PROMPT

    def test_user_prompt_with_input_prepends_draft(self):
        user = build_suggest_user_prompt("  銀髪の少女がカフェで  ")
        assert user.startswith("Current prompt draft:\n銀髪の少女がカフェで")
        assert user.endswith(SUGGEST_USER_PROMPT)

    def test_system_prompt_rules_depend_on_memory_and_input(self):
        system, user = build_suggest_characters_prompts(
            memory_text="銀髪が好き", count=2, mode="tags", nsfw=False
        )
        assert SUGGEST_INPUT_BIAS_RULE not in system
        assert SUGGEST_NO_MEMORY_RULE not in system
        assert user == SUGGEST_USER_PROMPT

        system, user = build_suggest_characters_prompts(
            memory_text="銀髪が好き",
            count=2,
            mode="tags",
            nsfw=False,
            input_text="カフェで働く少女",
        )
        assert SUGGEST_INPUT_BIAS_RULE in system
        assert SUGGEST_NO_MEMORY_RULE not in system
        assert "銀髪が好き" in system
        assert "カフェで働く少女" in user

        system, user = build_suggest_characters_prompts(
            memory_text="",
            count=2,
            mode="tags",
            nsfw=False,
            input_text="カフェで働く少女",
        )
        assert SUGGEST_INPUT_BIAS_RULE in system
        assert SUGGEST_NO_MEMORY_RULE in system
        assert "最優先指示" not in system


class TestMangaNotation:
    def test_extract_notation_kinds_and_panels(self):
        from gateway.services.prompt_expander_prompts import extract_manga_notation

        notation = extract_manga_notation(
            "①放課後の教室【放課後】\n"
            "2. 体が女性化《ドクン》\n"
            "3: 太郎「え、これ私…？」『どうして…』「」\n"
            "10:30に待ち合わせ"
        )
        assert [(t.kind, t.text, t.panel) for t in notation.texts] == [
            ("narration", "放課後", 1),
            ("sfx", "ドクン", 2),
            ("speech", "え、これ私…？", 3),
            ("monologue", "どうして…", 3),
            ("speech", "", 3),
        ]
        assert notation.panel_numbers == (1, 2, 3)
        assert notation.max_panel == 3
        assert notation.has_kind("narration") and not notation.has_kind("x")  # type: ignore[arg-type]
        assert [t.text for t in notation.required_texts()] == [
            "放課後",
            "ドクン",
            "え、これ私…？",
            "どうして…",
        ]

    def test_extract_notation_without_markers(self):
        from gateway.services.prompt_expander_prompts import extract_manga_notation

        notation = extract_manga_notation("男が女になる2コマ漫画")
        assert not notation.has_texts
        assert notation.panel_numbers == ()
        assert notation.max_panel is None

    def test_system_prompt_notation_rules(self):
        from gateway.services.prompt_expander_prompts import (
            MangaOptions,
            extract_manga_notation,
        )

        notation = extract_manga_notation("①「やだ」\n②『まさか』\n③【三日後】")
        system = build_positive_system_prompt(
            mode="tags",
            character_mode=False,
            max_characters=22,
            nsfw=False,
            manga=MangaOptions(dialogue=False, sound_effects=False),
            manga_notation=notation,
        )
        # 記法の説明と原文維持
        assert "「...」 is a spoken line (speech bubble)" in system
        assert "【...】 is narration" in system
        assert "top right corner" in system
        assert "Render every marked text verbatim" in system
        assert "Empty brackets such as 「」 or 【】" in system
        # おまかせでも記法のコマ番号に合わせる
        assert "Describe exactly 3 comic panels, following the panel numbers" in system
        # トグル OFF でも記法があれば文字系タグと吹き出しタグを入れる
        assert '"text", "speech bubble", "border"' in system
        assert "beyond the lines marked with 「...」 or 『...』" in system
        assert "beyond the ones marked with 《...》" in system
        # セリフ OFF なので思考の雲の例文は出ない
        assert "thought cloud above the girl" not in system

        auto = build_positive_system_prompt(
            mode="tags",
            character_mode=False,
            max_characters=22,
            nsfw=False,
            manga=MangaOptions(
                narration=True, text_language="ja", reading_direction="ltr"
            ),
        )
        assert "besides the ones marked with 【...】" in auto
        assert 'reads "三日後。"' in auto
        assert "top left corner" in auto
        assert "Decide how many comic panels (between 2 and 4)" in auto
        assert 'thought cloud above the girl that says "これが僕…？"' in auto

    def test_user_prompt_lists_marked_text(self):
        from gateway.services.prompt_expander_prompts import extract_manga_notation

        notation = extract_manga_notation("①「やだ」【】\n②《ドン》")
        user = build_positive_user_prompt(
            instruction="①「やだ」【】\n②《ドン》", manga=True, manga_notation=notation
        )
        assert (
            "Marked text in the instruction (render verbatim, in this order):" in user
        )
        assert '1. panel 1, speech bubble: "やだ"' in user
        assert (
            "2. panel 1, narration box: (no text given: write suitable content yourself)"
            in user
        )
        assert '3. panel 2, sound effect: "ドン"' in user
        assert user.endswith("does not explicitly change.")
        plain = build_positive_user_prompt(
            instruction="x", manga=True, manga_notation=extract_manga_notation("x")
        )
        assert "Marked text" not in plain

    def test_ensure_manga_notation_texts(self):
        from gateway.services.prompt_expander_prompts import (
            ensure_manga_notation_texts,
            extract_manga_notation,
        )

        notation = extract_manga_notation(
            "①「やだ」『まさか』\n②【三日後】《ドン》「」"
        )
        base = "1girl, There are two panels."
        characters = [
            '1girl, There\'s a speech bubble next to the girl that says "やだ"'
        ]
        # 出力に含まれるものは補わず、欠けたものだけ定型文で末尾に足す（空括弧は対象外）
        assert ensure_manga_notation_texts(base, characters, notation) == (
            "1girl, There are two panels. "
            'In panel 1, there\'s a thought cloud that says "まさか". '
            "In panel 2, there's a narration box at the top of the panel that reads "
            '"三日後". In panel 2, there\'s also a "ドン" visible in the panel.'
        )
        complete = (
            'There\'s a thought cloud that says "まさか". '
            'A narration box reads "三日後". "ドン" is visible.'
        )
        assert ensure_manga_notation_texts(complete, characters, notation) == complete
        # 記法が無ければそのまま
        assert (
            ensure_manga_notation_texts(base, None, extract_manga_notation("x")) == base
        )


class TestMangaScriptDraft:
    def test_build_manga_script_prompts_rules(self):
        from gateway.services.prompt_expander_prompts import (
            MangaOptions,
            build_manga_script_prompts,
        )

        system, user = build_manga_script_prompts(
            synopsis="  放課後、彼女が制服姿に変わってしまい戸惑う  ",
            options=MangaOptions(),
            nsfw=False,
            memory_text="銀髪が好き",
        )
        assert "Write between 2 and 4 panels." in system
        assert "circled number (①, ②, ③, ...)" in system
        assert "「...」 for a spoken line" in system
        assert "Give most panels a short spoken line" in system
        assert "Add a 《...》 sound effect only where" in system
        assert "Do not add 【...】 narration unless" in system
        assert "Adult or explicit tags are disabled" in system
        assert "銀髪が好き" in system
        assert user == (
            "Synopsis:\n放課後、彼女が制服姿に変わってしまい戸惑う\n\n"
            "Write the storyboard script now."
        )

        system, _ = build_manga_script_prompts(
            synopsis="x",
            options=MangaOptions(
                panel_count=3,
                dialogue=False,
                sound_effects=False,
                narration=True,
                text_language="en",
            ),
            nsfw=True,
        )
        assert "Write exactly 3 panels." in system
        assert "Do not write 「...」 or 『...』 lines unless" in system
        assert "Do not add 《...》 sound effects unless" in system
        assert "Add a 【...】 narration box where" in system
        assert "written in English." in system
        assert "Adult content tags are allowed" in system

    def test_sanitize_manga_script(self):
        from gateway.services.prompt_expander_prompts import sanitize_manga_script

        raw = "```\n①放課後の教室。彼女が鏡を見る「え…？」\n\n②体が変わっていく《ドクン》\n```"
        assert sanitize_manga_script(raw) == (
            "①放課後の教室。彼女が鏡を見る「え…？」\n②体が変わっていく《ドクン》"
        )
        assert (
            sanitize_manga_script("1: 鏡を見る\n2: 戸惑う") == "1: 鏡を見る\n2: 戸惑う"
        )
        with pytest.raises(PromptExpanderOutputError):
            sanitize_manga_script("   \n  ")
        with pytest.raises(PromptExpanderOutputError):
            sanitize_manga_script("彼女が鏡を見る。体が変わっていく。")


class TestTransparentBackgroundRule:
    def test_rule_added_after_body_for_tags_and_japanese(self):
        from gateway.services.prompt_expander_prompts import (
            TRANSPARENT_BACKGROUND_RULE_JA,
            TRANSPARENT_BACKGROUND_RULE_TAGS,
        )

        tags = build_positive_system_prompt(
            mode="tags",
            character_mode=False,
            max_characters=6,
            nsfw=False,
            transparent_background=True,
        )
        assert tags.startswith(
            BASE_SYSTEM_PROMPT_TAGS + TRANSPARENT_BACKGROUND_RULE_TAGS
        )
        # 語彙注意より前（本体直後）に置く
        assert tags.index(TRANSPARENT_BACKGROUND_RULE_TAGS) < tags.index(
            JAPANESE_TAG_GLOSSARY_RULE
        )
        assert TRANSPARENT_BACKGROUND_RULE_JA not in tags

        prose = build_positive_system_prompt(
            mode="japanese",
            character_mode=True,
            max_characters=22,
            nsfw=True,
            memory_text="銀髪が好み",
            transparent_background=True,
        )
        assert TRANSPARENT_BACKGROUND_RULE_JA in prose
        assert TRANSPARENT_BACKGROUND_RULE_TAGS not in prose
        # 成人向けルールとメモリ節（最優先指示）は従来どおり後ろに残る
        assert prose.index(TRANSPARENT_BACKGROUND_RULE_JA) < prose.index(
            ADULT_CONTENT_RULE
        )
        assert prose.index(ADULT_CONTENT_RULE) < prose.index("最優先指示")

    def test_rule_absent_by_default_and_in_manga_mode(self):
        from gateway.services.prompt_expander_prompts import (
            MangaOptions,
            TRANSPARENT_BACKGROUND_RULE_JA,
            TRANSPARENT_BACKGROUND_RULE_TAGS,
        )

        plain = build_positive_system_prompt(
            mode="tags", character_mode=False, max_characters=6, nsfw=False
        )
        assert TRANSPARENT_BACKGROUND_RULE_TAGS not in plain
        # 漫画モードはコマ枠ごと描くので透過ルールを足さない
        manga = build_positive_system_prompt(
            mode="tags",
            character_mode=False,
            max_characters=22,
            nsfw=False,
            manga=MangaOptions(),
            transparent_background=True,
        )
        assert TRANSPARENT_BACKGROUND_RULE_TAGS not in manga
        assert TRANSPARENT_BACKGROUND_RULE_JA not in manga
