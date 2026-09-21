from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.sources.contracts import RawDrawRecord, SourceAdapter
from app.sources.fetchers import SourceFetcher
from app.sources.parsers import SourceParser


class SourceIngestionError(RuntimeError):
    """Raised when extraction, parsing, or normalization fails."""


class SourceIngestionPipeline:
    """Execute fetch -> parse -> normalize, with persistence kept outside."""

    def __init__(
        self,
        *,
        fetcher: SourceFetcher,
        parser: SourceParser,
        adapter: SourceAdapter,
    ) -> None:
        self.fetcher = fetcher
        self.parser = parser
        self.adapter = adapter

    def extract(self, url: str) -> list[Mapping[str, Any]]:
        """Execute fetch -> parse and preserve source fields without normalization."""
        try:
            fetched = self.fetcher.fetch(url)
            payloads = self.parser.parse(fetched)
            return [
                {
                    **payload,
                    "source_url": payload.get("source_url", fetched.url),
                    "source_timestamp": payload.get(
                        "source_timestamp", fetched.fetched_at
                    ),
                }
                for payload in payloads
            ]
        except Exception as exc:
            if isinstance(exc, SourceIngestionError):
                raise
            raise SourceIngestionError(
                f"Source extraction failed for {self.adapter.spec.lottery_code}"
            ) from exc

    def run(self, url: str) -> list[RawDrawRecord]:
        try:
            payloads = self.extract(url)
            return [self.adapter.normalize(payload) for payload in payloads]
        except Exception as exc:
            if isinstance(exc, SourceIngestionError):
                raise
            raise SourceIngestionError(
                f"Source ingestion failed for {self.adapter.spec.lottery_code}"
            ) from exc

    def normalize_payloads(
        self,
        payloads: Iterable[Mapping[str, Any]],
    ) -> list[RawDrawRecord]:
        try:
            return [self.adapter.normalize(payload) for payload in payloads]
        except Exception as exc:
            if isinstance(exc, SourceIngestionError):
                raise
            raise SourceIngestionError(
                f"Source normalization failed for {self.adapter.spec.lottery_code}"
            ) from exc
