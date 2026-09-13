import ast
from pathlib import Path

ROUTES_DIR = Path(__file__).resolve().parents[1] / "app" / "api" / "routes"

EXPECTED_AUDITED_MUTATIONS = {
    "auth.py": {
        ("register", "create", "bootstrap_admin"),
        ("update_user", "update_credentials", "user"),
    },
    "lotteries.py": {
        ("create_lottery", "create", "lottery"),
        ("update_lottery", "update", "lottery"),
        ("delete_lottery", "delete", "lottery"),
    },
    "lottery_draws.py": {
        ("create_draw", "create", "draw"),
        ("update_draw", "update", "draw"),
        ("delete_draw", "delete", "draw"),
    },
}


def _mutation_calls(function: ast.FunctionDef) -> set[tuple[str, str, str]]:
    calls: set[tuple[str, str, str]] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "log_mutation":
            continue
        values = {}
        for keyword in node.keywords:
            if keyword.arg in {"action", "resource"} and isinstance(keyword.value, ast.Constant):
                values[keyword.arg] = keyword.value.value
        if len(values) == 2:
            calls.add((function.name, values["action"], values["resource"]))
    return calls


def test_all_supported_mutation_routes_emit_audit_events():
    for filename, expected in EXPECTED_AUDITED_MUTATIONS.items():
        tree = ast.parse((ROUTES_DIR / filename).read_text(encoding="utf-8"))
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        actual = set()
        for function in functions.values():
            actual.update(_mutation_calls(function))
        assert actual == expected


def test_audit_route_coverage_does_not_include_read_or_login_handlers():
    for filename, expected in EXPECTED_AUDITED_MUTATIONS.items():
        tree = ast.parse((ROUTES_DIR / filename).read_text(encoding="utf-8"))
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        audited_functions = {entry[0] for entry in expected}
        for name, function in functions.items():
            if name not in audited_functions:
                assert not _mutation_calls(function)
