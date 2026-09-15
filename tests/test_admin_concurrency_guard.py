from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.api.routes.auth import update_user
from app.models.user import User
from app.schemas.user import UserAdminUpdate


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def all(self):
        return self.value


class _FakeDb:
    def __init__(self, target, active_admin_ids):
        self.target = target
        self.active_admin_ids = active_admin_ids
        self.locked_query = None

    def scalar(self, statement):
        return self.target

    def scalars(self, statement):
        self.locked_query = statement
        return _ScalarResult(self.active_admin_ids)


def make_user(user_id: int, role: str, active: bool = True) -> User:
    return User(
        id=user_id,
        email=f"user-{user_id}@example.com",
        password_hash="x" * 60,
        role=role,
        is_active=active,
        session_version=0,
    )


def test_last_active_admin_guard_locks_active_admin_rows():
    target = make_user(2, "admin")
    actor = make_user(1, "admin")
    db = _FakeDb(target, [1, 2])

    update_user(
        user_id=2,
        payload=UserAdminUpdate(is_active=False),
        actor=actor,
        db=db,
    )

    assert db.locked_query is not None
    assert db.locked_query._for_update_arg is not None


def test_last_active_admin_guard_fails_closed_when_only_admin_is_active():
    target = make_user(1, "admin")
    actor = target
    db = _FakeDb(target, [1])

    with pytest.raises(HTTPException) as exc_info:
        update_user(
            user_id=1,
            payload=UserAdminUpdate(is_active=False),
            actor=actor,
            db=db,
        )

    assert exc_info.value.status_code == 400
