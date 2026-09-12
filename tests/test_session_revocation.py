from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.user import User

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
User.__table__.create(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def seed_user(db, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password("StrongTestPassword123!"),
        role="admin",
        is_active=True,
        session_version=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def clean_users():
    db = TestingSessionLocal()
    db.execute(delete(User))
    db.commit()
    db.close()


def test_existing_token_is_revoked_after_password_change():
    db = TestingSessionLocal()
    try:
        user = seed_user(db, "session-revocation@example.com")
        token = create_access_token(str(user.id), user.role, user.session_version)

        user.session_version += 1
        db.commit()

        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
    finally:
        db.close()
        clean_users()


def test_new_token_uses_current_session_version():
    db = TestingSessionLocal()
    try:
        user = seed_user(db, "session-version@example.com")
        user.session_version = 3
        db.commit()
        db.refresh(user)

        token = create_access_token(str(user.id), user.role, user.session_version)
        app.dependency_overrides[get_db] = override_get_db
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["email"] == user.email

        stored = db.scalar(select(User).where(User.id == user.id))
        assert stored is not None
        assert stored.session_version == 3
    finally:
        db.close()
        clean_users()
