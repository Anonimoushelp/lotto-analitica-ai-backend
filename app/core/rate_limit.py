import hashlib
from threading import Lock
from time import monotonic

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


class _MemoryRateLimitStore:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[int, float]] = {}
        self._lock = Lock()
        self._operations = 0

    def increment(self, key: str, window_seconds: int) -> int:
        now = monotonic()
        with self._lock:
            self._operations += 1
            entry = self._entries.get(key)
            if entry is None or now >= entry[1]:
                count = 1
                self._entries[key] = (count, now + window_seconds)
            else:
                count = entry[0] + 1
                self._entries[key] = (count, entry[1])

            if self._operations % 256 == 0:
                self._entries = {
                    stored_key: stored_entry
                    for stored_key, stored_entry in self._entries.items()
                    if now < stored_entry[1]
                }

            return count

    def reset(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._entries.pop(key, None)


class _RateLimiterBase:
    def __init__(self) -> None:
        self._redis: redis.Redis | None = None
        if settings.redis_url.strip():
            try:
                self._redis = redis.Redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=settings.redis_connect_timeout,
                    socket_timeout=settings.redis_socket_timeout,
                    health_check_interval=settings.redis_health_check_interval,
                )
            except (redis.RedisError, ValueError):
                self._redis = None
        self._memory = _MemoryRateLimitStore()

    def _increment(self, key: str, window_seconds: int) -> int:
        if self._redis is not None:
            try:
                return int(
                    self._redis.eval(
                        _INCREMENT_WITH_EXPIRY,
                        1,
                        key,
                        window_seconds,
                    )
                )
            except redis.RedisError:
                self._redis = None

        return self._memory.increment(key, window_seconds)

    def _reset(self, *keys: str) -> None:
        if self._redis is not None:
            try:
                self._redis.delete(*keys)
            except redis.RedisError:
                self._redis = None
        self._memory.reset(*keys)

    def health_check(self) -> None:
        if self._redis is None:
            return

        try:
            self._redis.ping()
        except redis.RedisError:
            self._redis = None


class LoginRateLimiter(_RateLimiterBase):
    @staticmethod
    def _key(prefix: str, value: str) -> str:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return f"auth:login:{prefix}:{digest}"

    def allow(self, email: str, client_ip: str) -> bool:
        account_count = self._increment(
            self._key("account", email.lower()),
            LOGIN_WINDOW_SECONDS,
        )
        ip_count = self._increment(
            self._key("ip", client_ip),
            LOGIN_WINDOW_SECONDS,
        )
        return (
            account_count <= LOGIN_MAX_ATTEMPTS_PER_ACCOUNT
            and ip_count <= LOGIN_MAX_ATTEMPTS_PER_IP
        )

    def reset(self, email: str, client_ip: str) -> None:
        self._reset(
            self._key("account", email.lower()),
            self._key("ip", client_ip),
        )


class AiRateLimiter(_RateLimiterBase):
    @staticmethod
    def _key(user_id: str) -> str:
        digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
        return f"ai:predictions:user:{digest}"

    def allow(self, user_id: int) -> bool:
        key = self._key(str(user_id))
        count = self._increment(key, AI_WINDOW_SECONDS)
        return count <= AI_MAX_REQUESTS_PER_USER


login_rate_limiter = LoginRateLimiter()
ai_rate_limiter = AiRateLimiter()
