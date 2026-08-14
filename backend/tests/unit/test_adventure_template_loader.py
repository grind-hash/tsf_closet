import logging

from gateway.services.adventure_template_loader import (
    SCENARIO_TEMPLATES,
    _warn_shared_item_aliases,
)


def _rule(shared_aliases: list[str] | None = None) -> dict:
    rule: dict = {
        "items": [
            {"id": "panties", "aliases": ["ショーツ", "下着"]},
            {"id": "bra", "aliases": ["ブラ", "下着"]},
        ]
    }
    if shared_aliases is not None:
        rule["shared_aliases"] = shared_aliases
    return rule


def test_undeclared_shared_alias_warns(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        _warn_shared_item_aliases("sample", _rule())
    assert "shares equipment aliases" in caplog.text


def test_declared_shared_alias_does_not_warn(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        _warn_shared_item_aliases("sample", _rule(["下着"]))
    assert caplog.text == ""


def test_stale_declaration_warns(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        _warn_shared_item_aliases("sample", _rule(["下着", "ソックス"]))
    assert "not shared" in caplog.text
    assert "ソックス" in caplog.text


def test_bundled_scenarios_declare_their_shared_aliases(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        for template_id, template in SCENARIO_TEMPLATES.items():
            _warn_shared_item_aliases(template_id, template["rule"])
    assert caplog.text == ""
