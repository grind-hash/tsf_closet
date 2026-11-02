"""NovelAI のタグ生成で、指示の修飾語(色の濃淡・丈など)を落とさない規則。"""

from __future__ import annotations

import pytest

from gateway.services.prompts import get_novelai_prompt_generation_system


@pytest.mark.parametrize("nsfw_mode", [False, True])
def test_modifier_rule_is_in_both_variants_before_output_format(nsfw_mode) -> None:
    system = get_novelai_prompt_generation_system(nsfw_mode=nsfw_mode)
    assert system.count("MODIFIER RULE") == 1
    assert system.index("MODIFIER RULE") < system.index("## Output Format")
    # 実際に落ちた言い回し(優しい青色 → sky blue のまま)を対応タグへ写す例を持つ
    assert "優しい青色 → pale blue dress, pastel colors" in system
    assert "膝上" in system and "short dress or miniskirt" in system


def test_modifier_rule_coexists_with_clothing_color_rule() -> None:
    system = get_novelai_prompt_generation_system(clothing_color_consistency=True)
    assert "CLOTHING COLOR RULE" in system
    assert "MODIFIER RULE" in system
