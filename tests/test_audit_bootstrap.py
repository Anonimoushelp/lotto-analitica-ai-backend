from unittest.mock import patch

from app.models.user import User


def test_bootstrap_registration_emits_safe_audit_event(client, db_session, monkeypatch):
    monkeypatch.setattr("app.api.routes.auth.settings.allow_initial_registration", True)

    with patch("app.api.routes.auth.log_mutation") as audit:
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "bootstrap@example.com", "password": "StrongPassword123!"},
        )

    assert response.status_code == 201
    user = db_session.query(User).filter_by(email="bootstrap@example.com").one()
    audit.assert_called_once_with(
        action="create",
        resource="bootstrap_admin",
        resource_id=user.id,
        actor=user,
    )


def test_bootstrap_registration_does_not_audit_rejected_second_user(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.auth.settings.allow_initial_registration", True)
    client.post(
        "/api/v1/auth/register",
        json={"email": "first@example.com", "password": "StrongPassword123!"},
    )

    with patch("app.api.routes.auth.log_mutation") as audit:
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "second@example.com", "password": "StrongPassword123!"},
        )

    assert response.status_code == 403
    audit.assert_not_called()
