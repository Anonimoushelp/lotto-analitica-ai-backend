from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from app.sources.parsers import SourceParseError


class ProviderRecordParser(Protocol):
    def parse_record(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """Parse one provider-specific record."""


class ProviderParserAdapter:
    """Adapt a provider record parser to the generic source parser contract."""

    def __init__(self, parser: ProviderRecordParser) -> None:
        self.parser = parser

    def parse(self, result: Any) -> Iterable[Mapping[str, Any]]:
        import json

        try:
            payload = json.loads(result.content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SourceParseError("Source content is not valid UTF-8 JSON") from exc

        if isinstance(payload, Mapping):
            records = payload.get("results", payload)
        else:
            records = payload

        if isinstance(records, Mapping):
            records = [records]

        if not isinstance(records, list) or not all(
            isinstance(item, Mapping) for item in records
        ):
            raise SourceParseError(
                "JSON source does not contain a supported provider record collection"
            )

        return [self.parser.parse_record(record) for record in records]
