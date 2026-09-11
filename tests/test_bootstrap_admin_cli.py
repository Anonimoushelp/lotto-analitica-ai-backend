from unittest.mock import patch

import pytest
from sqlalchemy import delete, select

from app.cli.bootstrap_admin import bootstrap_admin
from app.core.security import verify_password
from app.models.user import User
from tests.test_auth import TestingSessionLocal


@pytest.fixture(autouse=True)
def clean_users():
    db = TestingSessionLocal()
    db.execute(delete(User))
    db.commit()
    db.close()
    yield
    db = TestingSessionLocal()
    db.execute(delete(User))
    db.commit()
    db.close()


def test_bootstrap_admin_creates_first_admin_without_registration_flag():
    db = TestingSessionLocal()
    with patch("app.cli.bootstrap_admin.log_mutation") as audit:
        user = bootstrap_admin(
            db,
            email=" Bootstrap@Example.com ",
            password="StrongTestPassword123!",
        )
    db.close()

    assert user.email == "bootstrap@example.com"
    assert user.role == "admin"
    assert user.is_active is True
    assert user.password_hash != "StrongTestPassword123!"
    assert verify_password("StrongTestPassword123!", user.password_hash)
    audit.assert_called_once()
    assert audit.call_args.kwargs["resource"] == "bootstrap_admin"


def test_bootstrap_admin_is_one_time():
    db = TestingSessionLocal()
    bootstrap_admin(
        db,
        email="first@example.com",
        password="StrongTestPassword123!",
    )
    with pytest.raises(RuntimeError, match="Bootstrap already completed"):
        bootstrap_admin(
            db,
            email="second@example.com",
            password="StrongTestPassword123!",
        )
    db.close()

    db = TestingSessionLocal()
    users = db.scalars(select(User)).all()
    db.close()
    assert len(users) == 1
    assert users[0].email == "first@example.com"


def test_bootstrap_admin_validates_email_and_password():
    db = TestingSessionLocal()
    with pytest.raises(ValueError):
        bootstrap_admin(
            db,
            email="not-an-email",
            password="StrongTestPassword123!",
        )
    with pytest.raises(ValueError):
        bootstrap_admin(db, email="valid@example.com", password="short")
    db.close()
