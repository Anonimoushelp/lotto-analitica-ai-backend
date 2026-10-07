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


def reset_admin_password(db: Session, *, email: str, password: str) -> User:
    """Reset an existing active administrator password through an explicit ops action.

    This path is intentionally not exposed through the public API and does not
    depend on ALLOW_INITIAL_REGISTRATION. It requires the target account to
    already exist, be active, and have the admin role.
    """
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(831746291)"))

    normalized_email = email.strip().lower()
    payload = UserCreate(email=normalized_email, password=password, role="admin")

    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        raise RuntimeError("Administrator account not found")
    if user.role != "admin" or not user.is_active:
        raise RuntimeError("Target account is not an active administrator")

    user.password_hash = hash_password(payload.password)
    db.add(user)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(user)
    log_mutation(
        action="update",
        resource="admin_password",
        resource_id=user.id,
        actor=user,
    )
    return user


def main() -> None:
    email = input("Admin email: ").strip()
    password = getpass.getpass("New admin password: ")
    confirmation = getpass.getpass("Confirm new admin password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")

    db = SessionLocal()
    try:
        user = reset_admin_password(db, email=email, password=password)
    finally:
        db.close()

    logger.info("Administrator password reset successfully user_id=%s", user.id)
    print(f"Administrator password reset successfully: {user.email}")


if __name__ == "__main__":
    main()
