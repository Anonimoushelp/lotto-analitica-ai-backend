import hashlib

import redis

from app.core.config import settings

LOGIN_WINDOW_SECONDS = 60
LOGIN_MAX_ATTEMPTS_PER_ACCOUNT = 5
LOGIN_MAX_ATTEMPTS_PER_IP = 20


class LoginRateLimiter:
    def __init__(self) -> None:
        self._redis = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=settings.redis_connect_timeout,
            socket_timeout=settings.redis_socket_timeout,
            health_check_interval=settings.redis_health_check_interval,
        )

    @staticmethod
    def _key(prefix: str, value: str) -> str:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return f"auth:login:{prefix}:{digest}"

    def _increment(self, key: str) -> int:
        count = int(self._redis.incr(key))
        if count == 1:
            self._redis.expire(key, LOGIN_WINDOW_SECONDS)
        return count

    def allow(self, email: str, client_ip: str) -> bool:
        account_count = self._increment(self._key("account", email.lower()))
        ip_count = self._increment(self._key("ip", client_ip))
        return (
            account_count <= LOGIN_MAX_ATTEMPTS_PER_ACCOUNT
            and ip_count <= LOGIN_MAX_ATTEMPTS_PER_IP
        )

    def reset(self, email: str, client_ip: str) -> None:
        self._redis.delete(
            self._key("account", email.lower()),
            self._key("ip", client_ip),
        )


login_rate_limiter = LoginRateLimiter()
