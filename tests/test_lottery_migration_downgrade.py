import importlib.util
from pathlib import Path

import pytest


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "1a6d8e4f2b90_scope_lotteries_to_tenants.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("lottery_scope_migration", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResult:
    def __init__(self, row):
        self.row = row

    def first(self):
        return self.row


class FakeConnection:
    def __init__(self, row):
        self.row = row
        self.executed = []

    def execute(self, statement):
        self.executed.append(statement)
        return FakeResult(self.row)


@pytest.mark.parametrize("duplicate_row", [("BALOTO",), None])
def test_downgrade_checks_duplicate_codes_before_destructive_operations(
    monkeypatch, duplicate_row
):
    migration = _load_migration()
    connection = FakeConnection(duplicate_row)
    destructive_calls = []

    monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
    for operation in (
        "drop_constraint",
        "drop_index",
        "create_index",
        "drop_column",
    ):
        monkeypatch.setattr(
            migration.op,
            operation,
            lambda *args, _operation=operation, **kwargs: destructive_calls.append(
                (_operation, args, kwargs)
            ),
        )

    if duplicate_row is not None:
        with pytest.raises(RuntimeError, match="duplicate lottery codes"):
            migration.downgrade()
        assert destructive_calls == []
    else:
        migration.downgrade()
        assert [call[0] for call in destructive_calls] == [
            "drop_constraint",
            "drop_index",
            "drop_index",
            "create_index",
            "drop_constraint",
            "drop_column",
        ]

    assert len(connection.executed) == 1
