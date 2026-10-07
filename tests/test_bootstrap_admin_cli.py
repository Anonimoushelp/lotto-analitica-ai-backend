from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.cli.bootstrap_admin import bootstrap_admin
from app.cli.reset_admin_password import reset_admin_password
from app.core.security import verify_password
from app.models.user import User


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
User.__table__.create(bind=engine)


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


def test_reset_admin_password_updates_existing_admin_and_audits():
    db = TestingSessionLocal()
    bootstrap_admin(
        db,
        email=" Admin@Example.com ",
        password="OldStrongPassword123!",
    )
    with patch("app.cli.reset_admin_password.log_mutation") as audit:
        user = reset_admin_password(
            db,
            email=" ADMIN@example.com ",
            password="NewStrongPassword456!",
        )
    db.close()

    assert user.email == "admin@example.com"
    assert verify_password("NewStrongPassword456!", user.password_hash)
    assert not verify_password("OldStrongPassword123!", user.password_hash)
    audit.assert_called_once()
    assert audit.call_args.kwargs["action"] == "update"
    assert audit.call_args.kwargs["resource"] == "admin_password"


def test_reset_admin_password_rejects_missing_or_non_admin_target():
    db = TestingSessionLocal()
    with pytest.raises(RuntimeError, match="Administrator account not found"):
        reset_admin_password(
            db,
            email="missing@example.com",
            password="NewStrongPassword456!",
        )

    user = User(
        email="viewer@example.com",
        password_hash="placeholder",
        role="viewer",
        is_active=True,
    )
    db.add(user)
    db.commit()

    with pytest.raises(RuntimeError, match="active administrator"):
        reset_admin_password(
            db,
            email="viewer@example.com",
            password="NewStrongPassword456!",
        )
    db.close()


def test_reset_admin_password_validates_email_and_password():
    db = TestingSessionLocal()
    with pytest.raises(ValueError):
        reset_admin_password(
            db,
            email="not-an-email",
            password="StrongTestPassword123!",
        )
    with pytest.raises(ValueError):
        reset_admin_password(
            db,
            email="valid@example.com",
            password="short",
        )
    db.close()
