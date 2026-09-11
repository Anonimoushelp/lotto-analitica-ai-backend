import getpass
import logging

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.audit import log_mutation
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User
from app.schemas.user import UserCreate

logger = logging.getLogger(__name__)


def bootstrap_admin(db: Session, *, email: str, password: str) -> User:
    """Create the first administrator through an explicit ops action.

    This path intentionally does not depend on ALLOW_INITIAL_REGISTRATION, so
    production can keep public registration disabled at all times.
    """
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(831746291)"))

    if db.scalar(select(User.id).limit(1)) is not None:
        raise RuntimeError("Bootstrap already completed; an administrator exists")

    payload = UserCreate(email=email.strip().lower(), password=password, role="admin")
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role="admin",
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(user)
    log_mutation(
        action="create",
        resource="bootstrap_admin",
        resource_id=user.id,
        actor=user,
    )
    return user


def main() -> None:
    email = input("Admin email: ").strip()
    password = getpass.getpass("Admin password: ")
    confirmation = getpass.getpass("Confirm admin password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")

    db = SessionLocal()
    try:
        user = bootstrap_admin(db, email=email, password=password)
    finally:
        db.close()

    logger.info("Bootstrap administrator created successfully user_id=%s", user.id)
    print(f"Bootstrap administrator created: {user.email}")


if __name__ == "__main__":
    main()
