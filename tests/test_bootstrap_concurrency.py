import threading
import time

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from app.api.routes.auth import register
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import engine
from app.models.user import User
from app.schemas.user import UserCreate


pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Bootstrap advisory-lock concurrency requires PostgreSQL",
)


def test_initial_registration_allows_only_one_concurrent_bootstrap(
    monkeypatch,
):
    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    test_emails = {
        "bootstrap-concurrent-1@example.com",
        "bootstrap-concurrent-2@example.com",
    }

    cleanup = TestingSessionLocal()
    cleanup.execute(delete(User).where(User.email.in_(test_emails)))
    cleanup.commit()
    cleanup.close()

    original_registration = settings.allow_initial_registration
    settings.allow_initial_registration = True

    first_hash_started = threading.Event()
    release_first_hash = threading.Event()
    results = []
    errors = []

    original_hash_password = hash_password

    def controlled_hash_password(password):
        if not first_hash_started.is_set():
            first_hash_started.set()
            if not release_first_hash.wait(timeout=10):
                raise RuntimeError(
                    "Timed out waiting for concurrent bootstrap test"
                )
        return original_hash_password(password)

    monkeypatch.setattr(
        "app.api.routes.auth.hash_password",
        controlled_hash_password,
    )
    monkeypatch.setattr(
        "app.api.routes.auth.log_mutation",
        lambda **kwargs: None,
    )

    def attempt(email):
        db = TestingSessionLocal()
        try:
            response = register(
                UserCreate(
                    email=email,
                    password="StrongTestPassword123!",
                ),
                db=db,
            )
            results.append(("success", response.email))
        except HTTPException as exc:
            results.append(("http_error", exc.status_code))
        except Exception as exc:
            errors.append(exc)
        finally:
            db.close()

    first = threading.Thread(
        target=attempt,
        args=("bootstrap-concurrent-1@example.com",),
    )
    second = threading.Thread(
        target=attempt,
        args=("bootstrap-concurrent-2@example.com",),
    )

    try:
        first.start()
        assert first_hash_started.wait(timeout=10)

        second.start()
        time.sleep(0.5)

        assert second.is_alive(), (
            "Second bootstrap did not remain blocked while the first "
            "transaction held the advisory lock"
        )

        release_first_hash.set()

        first.join(timeout=10)
        second.join(timeout=10)

        assert not first.is_alive()
        assert not second.is_alive()
        assert not errors

        assert len(results) == 2
        assert ("success", "bootstrap-concurrent-1@example.com") in results
        assert ("http_error", 403) in results

        verification = TestingSessionLocal()
        users = verification.scalars(
            select(User).where(User.email.in_(test_emails))
        ).all()
        verification.close()

        assert len(users) == 1
        assert users[0].email == "bootstrap-concurrent-1@example.com"
        assert users[0].role == "admin"
    finally:
        release_first_hash.set()
        first.join(timeout=10)
        second.join(timeout=10)
        settings.allow_initial_registration = original_registration

        cleanup = TestingSessionLocal()
        cleanup.execute(delete(User).where(User.email.in_(test_emails)))
        cleanup.commit()
        cleanup.close()
