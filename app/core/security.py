from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
JWT_CLOCK_SKEW_SECONDS = 5
ALLOWED_ROLES = frozenset({"admin", "analyst", "viewer", "service"})
password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(
    subject: str, role: str, session_version: int = 0
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "role": role,
        "session_version": session_version,
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[ALGORITHM],
        options={
            "require": ["sub", "role", "session_version", "iat", "exp", "type"],
            "verify_iat": False,
        },
    )

    if not isinstance(payload["sub"], str) or not payload["sub"].strip():
        raise jwt.InvalidTokenError("Invalid subject")
    if not isinstance(payload["role"], str) or payload["role"] not in ALLOWED_ROLES:
        raise jwt.InvalidTokenError("Invalid role")
    if not isinstance(payload["session_version"], int) or isinstance(
        payload["session_version"], bool
    ) or payload["session_version"] < 0:
        raise jwt.InvalidTokenError("Invalid session version")
    if not isinstance(payload["iat"], int) or isinstance(payload["iat"], bool):
        raise jwt.InvalidTokenError("Invalid issued-at claim")
    if not isinstance(payload["exp"], int) or isinstance(payload["exp"], bool):
        raise jwt.InvalidTokenError("Invalid expiration claim")
    now = datetime.now(UTC)
    issued_at = datetime.fromtimestamp(payload["iat"], tz=UTC)
    if issued_at > now + timedelta(seconds=JWT_CLOCK_SKEW_SECONDS):
        raise jwt.InvalidTokenError("Token issued in the future")
    if payload["type"] != "access":
        raise jwt.InvalidTokenError("Invalid token type")
    return payload
