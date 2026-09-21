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
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self.timeout = timeout
        self.user_agent = user_agent

    def fetch(self, url: str) -> SourceFetchResult:
        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": self.user_agent},
            ) as client:
                response = client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceFetchError(f"Source fetch failed for {url}") from exc

        return SourceFetchResult(
            url=str(response.url),
            status_code=response.status_code,
            content=response.content,
            content_type=response.headers.get("content-type", ""),
            fetched_at=datetime.now().astimezone(),
        )
