import logging

import pytest

from app.core import audit
from app.models.user import User


@pytest.fixture
def actor():
    return User(
        id=42,
        email="admin@example.com",
        password_hash="argon2$secret-hash",
        role="admin",
    )


def test_audit_event_contains_only_non_sensitive_identity_fields(caplog, actor):
    with caplog.at_level(logging.INFO, logger="lotto_analitica.audit"):
        audit.log_mutation(
            action="update_credentials",
            resource="user",
            resource_id=7,
            actor=actor,
        )

    message = caplog.records[-1].getMessage()
    assert "audit.update_credentials" in message
    assert "resource=user" in message
    assert "resource_id=7" in message
    assert "actor_user_id=42" in message
    assert "actor_role=admin" in message
    assert actor.email not in message
    assert actor.password_hash not in message
    assert "password" not in message.lower()


def test_audit_control_characters_are_rejected_before_logging(caplog, actor):
    with caplog.at_level(logging.INFO, logger="lotto_analitica.audit"), pytest.raises(
        ValueError, match="Unsupported audit mutation"
    ):
        audit.log_mutation(
            action="create\n",
            resource="lottery\r",
            resource_id=9,
            actor=actor,
        )

    assert not caplog.records


def test_unsupported_resource_action_pair_is_rejected_before_logging(caplog, actor):
    with caplog.at_level(logging.INFO, logger="lotto_analitica.audit"), pytest.raises(
        ValueError, match="Unsupported audit mutation"
    ):
        audit.log_mutation(
            action="create",
            resource="user",
            resource_id=7,
            actor=actor,
        )

    assert not caplog.records


def test_audit_rejects_invalid_resource_identifiers(caplog, actor):
    with caplog.at_level(logging.INFO, logger="lotto_analitica.audit"):
        for resource_id in (0, -1, True, "7", "7\n"):
            with pytest.raises(ValueError, match="Invalid audit resource identifier"):
                audit.log_mutation(
                    action="create",
                    resource="lottery",
                    resource_id=resource_id,
                    actor=actor,
                )

    assert not caplog.records


def test_audit_rejects_invalid_actor_identity_fields(caplog, actor):
    with caplog.at_level(logging.INFO, logger="lotto_analitica.audit"):
        actor.id = 0
        with pytest.raises(ValueError, match="Invalid audit actor identifier"):
            audit.log_mutation(
                action="create",
                resource="lottery",
                resource_id=7,
                actor=actor,
            )

        actor.id = 42
        actor.role = "unknown"
        with pytest.raises(ValueError, match="Invalid audit actor role"):
            audit.log_mutation(
                action="create",
                resource="lottery",
                resource_id=7,
                actor=actor,
            )


def test_audit_rejects_control_characters_in_actor_role(caplog, actor):
    for role in ("admin\n", "analyst\rforged"):
        actor.role = role
        with caplog.at_level(logging.INFO, logger="lotto_analitica.audit"), pytest.raises(
            ValueError, match="Invalid audit actor role"
        ):
            audit.log_mutation(
                action="create",
                resource="lottery",
                resource_id=7,
                actor=actor,
            )

    assert not caplog.records
