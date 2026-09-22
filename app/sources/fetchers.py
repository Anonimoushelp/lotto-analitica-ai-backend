from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import httpx


@dataclass(frozen=True)
class SourceFetchResult:
    url: str
    status_code: int
    content: bytes
    content_type: str
    fetched_at: datetime


class SourceFetchError(RuntimeError):
    """Raised when a configured source cannot be fetched safely."""


class SourceFetcher(Protocol):
    def fetch(self, url: str) -> SourceFetchResult:
        """Fetch one source URL and return immutable response metadata."""


class HttpSourceFetcher:
    """HTTP fetcher kept independent from parsing and persistence."""

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        user_agent: str = "Lotto-Analitica-AI/1.0",
        allowed_hosts: set[str] | None = None,
        max_response_bytes: int = 2_000_000,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be greater than zero")
        self.timeout = timeout
        self.user_agent = user_agent
        self.allowed_hosts = {host.casefold() for host in (allowed_hosts or set())}
        self.max_response_bytes = max_response_bytes
        self.transport = transport

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            raise SourceFetchError("Source URL must use HTTPS")
        if not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise SourceFetchError("Source URL must contain a valid hostname without credentials")
        if self.allowed_hosts and parsed.hostname.casefold() not in self.allowed_hosts:
            raise SourceFetchError("Source URL host is not allowlisted")

    def fetch(self, url: str) -> SourceFetchResult:
        self._validate_url(url)
        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": self.user_agent},
                transport=self.transport,
            ) as client:
                with client.stream("GET", url) as response:
                    response.raise_for_status()
                    content_length = response.headers.get("content-length")
                    if content_length is not None and int(content_length) > self.max_response_bytes:
                        raise SourceFetchError("Source response exceeds configured size limit")
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > self.max_response_bytes:
                            raise SourceFetchError("Source response exceeds configured size limit")
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    final_url = str(response.url)
                    if urlparse(final_url).hostname.casefold() not in self.allowed_hosts if self.allowed_hosts else False:
                        raise SourceFetchError("Redirected source host is not allowlisted")
        except (httpx.HTTPError, ValueError) as exc:
            raise SourceFetchError(f"Source fetch failed for {url}") from exc

        return SourceFetchResult(
            url=final_url,
            status_code=response.status_code,
            content=content,
            content_type=response.headers.get("content-type", ""),
            fetched_at=datetime.now().astimezone(),
        )
