"""開花計算と性別適合フラグのソース検証テスト。"""

from __future__ import annotations

from pathlib import Path


def test_gender_discomfort_false_branch_in_source() -> None:
    """calculate_parameter_change に gender_discomfort 分岐が存在する。"""
    src = (
        Path(__file__).resolve().parents[2]
        / "gateway"
        / "services"
        / "game_service.py"
    ).read_text(encoding="utf-8")
    assert "gender_discomfort: bool = True" in src
    assert "if not gender_discomfort:" in src
    assert "bloom_delta = 0" in src
