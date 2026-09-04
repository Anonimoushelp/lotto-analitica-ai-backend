import hashlib

import redis

from app.core.config import settings

LOGIN_WINDOW_SECONDS = 60
LOGIN_MAX_ATTEMPTS_PER_ACCOUNT = 5
LOGIN_MAX_ATTEMPTS_PER_IP = 20

AI_WINDOW_SECONDS = 60
AI_MAX_REQUESTS_PER_USER = 10

_INCREMENT_WITH_EXPIRY = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


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
        return int(
            self._redis.eval(
                _INCREMENT_WITH_EXPIRY,
                1,
                key,
                LOGIN_WINDOW_SECONDS,
            )
        )

    def health_check(self) -> None:
        self._redis.ping()

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


class AiRateLimiter:
    def __init__(self) -> None:
        self._redis = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=settings.redis_connect_timeout,
            socket_timeout=settings.redis_socket_timeout,
            health_check_interval=settings.redis_health_check_interval,
        )

    @staticmethod
    def _key(user_id: str) -> str:
        digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
        return f"ai:predictions:user:{digest}"

    def allow(self, user_id: int) -> bool:
        key = self._key(str(user_id))
        count = int(
            self._redis.eval(
                _INCREMENT_WITH_EXPIRY,
                1,
                key,
                AI_WINDOW_SECONDS,
            )
        )
        return count <= AI_MAX_REQUESTS_PER_USER


login_rate_limiter = LoginRateLimiter()
ai_rate_limiter = AiRateLimiter()
