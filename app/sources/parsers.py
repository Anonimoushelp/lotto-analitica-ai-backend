from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from app.sources.fetchers import SourceFetchResult


class SourceParseError(ValueError):
    """Raised when fetched source content cannot be extracted."""


class SourceParser(Protocol):
    def parse(self, result: SourceFetchResult) -> Iterable[Mapping[str, Any]]:
        """Extract provider records without normalizing or persisting them."""


class JsonSourceParser:
    """Parse JSON sources while leaving provider field semantics untouched."""

    def __init__(self, *, records_key: str | None = None) -> None:
        self.records_key = records_key

    def parse(self, result: SourceFetchResult) -> Iterable[Mapping[str, Any]]:
        try:
            payload = json.loads(result.content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceParseError("Source content is not valid UTF-8 JSON") from exc

        if self.records_key is None:
            records = payload
        elif isinstance(payload, Mapping):
            records = payload.get(self.records_key)
        else:
            records = None

        if isinstance(records, Mapping):
            return [records]
        if isinstance(records, list) and all(isinstance(item, Mapping) for item in records):
            return records
        raise SourceParseError("JSON source does not contain a supported record collection")


class HtmlJsonLdParser:
    """Extract record collections from JSON-LD script tags in HTML sources."""

    _SCRIPT_RE = re.compile(
        rb'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )

    def __init__(self, *, records_key: str | None = None) -> None:
        self.records_key = records_key

    def parse(self, result: SourceFetchResult) -> Iterable[Mapping[str, Any]]:
        documents: list[Any] = []
        for match in self._SCRIPT_RE.finditer(result.content):
            try:
                documents.append(json.loads(match.group(1).decode("utf-8").strip()))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SourceParseError("HTML contains invalid JSON-LD") from exc

        if not documents:
            raise SourceParseError("HTML source does not contain JSON-LD")

        for payload in documents:
            records = payload
            if self.records_key is not None and isinstance(payload, Mapping):
                records = payload.get(self.records_key)
            if isinstance(records, Mapping):
                return [records]
            if isinstance(records, list) and all(isinstance(item, Mapping) for item in records):
                return records

        raise SourceParseError(
            "JSON-LD source does not contain a supported record collection"
        )
