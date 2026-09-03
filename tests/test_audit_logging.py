from types import SimpleNamespace

from app.core.audit import log_mutation


def test_mutation_audit_log_contains_only_safe_identifiers(caplog):
    actor = SimpleNamespace(id=42, role="admin")

    with caplog.at_level("INFO", logger="lotto_analitica.audit"):
        log_mutation(
            action="update",
            resource="draw",
            resource_id=17,
            actor=actor,
        )

    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert message == (
        "audit.update resource=draw resource_id=17 "
        "actor_user_id=42 actor_role=admin"
    )
    assert "password" not in message.lower()
    assert "token" not in message.lower()
    assert "secret" not in message.lower()
    assert "@" not in message
