"""self_mode の実績判定が使うヘルパーが条件分岐の外で束縛されているか検証する。

achievements_router の遅延 import を `if not session.self_mode:` の内側に置くと、
Python は同名をローカル変数として扱うため self_mode 側の参照が UnboundLocalError
になり、self系実績が一切解除されなくなる。
"""

import ast
from pathlib import Path

GAME_SERVICE_PATH = (
    Path(__file__).resolve().parents[2] / "gateway" / "services" / "game_service.py"
)
ACHIEVEMENT_MODULE = "routes.achievements_router"
SELF_MODE_HELPERS = {
    "ACHIEVEMENTS",
    "check_achievement",
    "get_global_stats",
    "get_user_achievements",
    "save_user_achievement",
}


def _find_function(tree: ast.Module, name: str) -> ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} が見つかりません")


def _import_nodes_outside_conditionals(
    stmts: list[ast.stmt], inside_conditional: bool
) -> list[ast.ImportFrom]:
    found: list[ast.ImportFrom] = []
    for stmt in stmts:
        if (
            isinstance(stmt, ast.ImportFrom)
            and stmt.module == ACHIEVEMENT_MODULE
            and not inside_conditional
        ):
            found.append(stmt)
        nested_conditional = inside_conditional or isinstance(
            stmt, (ast.If, ast.For, ast.AsyncFor, ast.While)
        )
        for field in ("body", "orelse", "finalbody"):
            body = getattr(stmt, field, None)
            if body:
                found.extend(
                    _import_nodes_outside_conditionals(body, nested_conditional)
                )
        for handler in getattr(stmt, "handlers", []):
            found.extend(
                _import_nodes_outside_conditionals(handler.body, nested_conditional)
            )
    return found


def test_achievement_helpers_are_bound_outside_self_mode_branch() -> None:
    tree = ast.parse(GAME_SERVICE_PATH.read_text(encoding="utf-8"))
    play_with_stream = _find_function(tree, "play_with_stream")

    unconditional_imports = _import_nodes_outside_conditionals(
        play_with_stream.body, inside_conditional=False
    )
    assert unconditional_imports, (
        "achievements_router の遅延 import が条件分岐の内側にあります。"
        "self_mode 側の実績判定が UnboundLocalError になります"
    )

    imported_names = {
        alias.asname or alias.name
        for node in unconditional_imports
        for alias in node.names
    }
    missing = SELF_MODE_HELPERS - imported_names
    assert not missing, (
        f"self_mode の実績判定で使う名前が束縛されていません: {sorted(missing)}"
    )
