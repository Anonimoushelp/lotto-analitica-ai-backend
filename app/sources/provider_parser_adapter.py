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


class HtmlProviderParserAdapter:
    """Adapt a provider-neutral HTML table extractor to provider records."""

    def __init__(
        self,
        *,
        parser: Any,
        allowed_draw_types: set[str],
        metadata_keys: tuple[str, ...] = (),
        draw_type_aliases: Mapping[str, str] | None = None,
    ) -> None:
        self.parser = parser
        self.allowed_draw_types = allowed_draw_types
        self.metadata_keys = metadata_keys
        self.draw_type_aliases = {
            str(key).upper(): str(value).upper()
            for key, value in (draw_type_aliases or {}).items()
        }

    def parse(self, result: Any) -> Iterable[Mapping[str, Any]]:
        records = self.parser.parse(result)
        normalized: list[Mapping[str, Any]] = []

        for record in records:
            draw_type = str(record.get("draw_type", "")).strip().upper()
            draw_type = self.draw_type_aliases.get(draw_type, draw_type)
            if draw_type not in self.allowed_draw_types:
                raise SourceParseError(
                    f"Unsupported draw type {draw_type}; expected one of "
                    f"{', '.join(sorted(self.allowed_draw_types))}"
                )

            raw_result = str(record.get("result", "")).strip()
            if len(raw_result) != 4 or not raw_result.isdigit():
                raise SourceParseError(
                    "Four-digit result must contain exactly four digits"
                )

            metadata = dict(record.get("metadata") or {})
            metadata["raw_result"] = raw_result
            metadata["digit_count"] = 4
            for key in self.metadata_keys:
                if key in record and record[key] not in (None, ""):
                    metadata.setdefault(key, record[key])

            normalized.append(
                {
                    "draw_type": draw_type,
                    "draw_date": record.get("draw_date"),
                    "number": raw_result,
                    "metadata": metadata,
                }
            )

        return normalized
