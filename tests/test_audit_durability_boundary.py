import ast
from pathlib import Path

import pytest

from app.core import audit
from app.models.user import User

ROUTES_DIR = Path(__file__).resolve().parents[1] / "app" / "api" / "routes"
MUTATION_ROUTES = {
    "lotteries.py": ("create_lottery", "update_lottery", "delete_lottery"),
    "lottery_draws.py": ("create_draw", "update_draw", "delete_draw"),
}


def _function(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Missing mutation handler: {name}")


def _first_call_index(function: ast.FunctionDef, function_name: str) -> int:
    calls = [
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == function_name
    ]
    if not calls:
        raise AssertionError(f"Missing call: {function_name}")
    return min(calls)


def _audit_call_index(function: ast.FunctionDef) -> int:
    calls = [
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "log_mutation"
    ]
    if not calls:
        raise AssertionError("Mutation handler must emit an audit event")
    return min(calls)


def test_mutation_routes_audit_only_after_successful_service_call():
    for filename, handlers in MUTATION_ROUTES.items():
        tree = ast.parse((ROUTES_DIR / filename).read_text(encoding="utf-8"))
        for handler_name in handlers:
            function = _function(tree, handler_name)
            assert _audit_call_index(function) > _first_call_index(function, "LotteryService")


def test_audit_mutation_allowlist_is_fail_closed(monkeypatch):
    actor = User(id=1, email="audit@example.com", password_hash="x", role="admin")

    with pytest.raises(ValueError, match="Unsupported audit mutation"):
        audit.log_mutation(
            action="unsupported",
            resource="lottery",
            resource_id=1,
            actor=actor,
        )

    monkeypatch.setattr(audit.logger, "info", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("sink down")))
    with pytest.raises(RuntimeError, match="sink down"):
        audit.log_mutation(
            action="create",
            resource="lottery",
            resource_id=1,
            actor=actor,
        )
