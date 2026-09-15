from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from app.core.audit import log_mutation


def test_unsupported_mutation_fails_closed_without_emitting_audit(caplog):
    actor = SimpleNamespace(id=42, role="admin")

    with caplog.at_level("INFO", logger="lotto_analitica.audit"), pytest.raises(
        ValueError, match="Unsupported audit mutation"
    ):
        log_mutation(
            action="delete",
            resource="unsupported",
            resource_id=17,
            actor=actor,
        )

    assert caplog.records == []


def test_concurrent_audit_events_remain_complete_and_non_interleaved(caplog):
    actors = [SimpleNamespace(id=100 + index, role="admin") for index in range(20)]

    def emit(actor):
        log_mutation(
            action="update",
            resource="draw",
            resource_id=1000 + actor.id,
            actor=actor,
        )

    with caplog.at_level("INFO", logger="lotto_analitica.audit"), ThreadPoolExecutor(
        max_workers=8
    ) as executor:
        list(executor.map(emit, actors))

    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) == len(actors)
    assert len(set(messages)) == len(actors)
    for actor in actors:
        expected = (
            f"audit.update resource=draw resource_id={1000 + actor.id} "
            f"actor_user_id={actor.id} actor_role=admin"
        )
        assert messages.count(expected) == 1


def test_audit_rejects_malformed_actor_roles_before_concurrent_emission(caplog):
    actors = [
        SimpleNamespace(id=201, role="analyst\nforged"),
        SimpleNamespace(id=202, role="viewer\rforged"),
    ]

    def emit(actor):
        with pytest.raises(ValueError, match="Invalid audit actor role"):
            log_mutation(
                action="update",
                resource="draw",
                resource_id=actor.id,
                actor=actor,
            )

    with caplog.at_level("INFO", logger="lotto_analitica.audit"), ThreadPoolExecutor(
        max_workers=2
    ) as executor:
        list(executor.map(emit, actors))

    assert caplog.records == []


def test_audit_rejects_control_characters_in_action_and_resource(caplog):
    actor = SimpleNamespace(id=203, role="admin")

    with caplog.at_level("INFO", logger="lotto_analitica.audit"), pytest.raises(
        ValueError, match="Unsupported audit mutation"
    ):
        log_mutation(
            action="update\nforged",
            resource="draw\rforged",
            resource_id=203,
            actor=actor,
        )

    assert caplog.records == []
