from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from html.parser import HTMLParser
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


class _ResultTableParser(HTMLParser):
    """Collect simple HTML tables as header/value mappings."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table" and self._table is None:
            self._table = []
        elif tag == "tr" and self._table is not None and self._row is None:
            self._row = []
        elif tag in {"th", "td"} and self._row is not None and self._cell is None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"th", "td"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


class HtmlTableParser:
    """Extract lottery result tables from server-rendered HTML."""

    _DATE_RE = re.compile(
        r"(?P<day>\d{1,2})\s+(?:de\s+)?"
        r"(?P<month>[A-Za-zÁÉÍÓÚáéíóúñÑ]+)(?:\s+(?:de|del))?\s+(?P<year>\d{4})",
        re.IGNORECASE,
    )
    _NUMBER_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")

    def __init__(
        self,
        *,
        chance_header: str = "Chance",
        date_header: str = "Fecha",
        result_header: str = "Resultado",
    ) -> None:
        self.chance_header = chance_header
        self.date_header = date_header
        self.result_header = result_header

    def parse(self, result: SourceFetchResult) -> Iterable[Mapping[str, Any]]:
        try:
            html = result.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceParseError("HTML source is not valid UTF-8") from exc

        parser = _ResultTableParser()
        parser.feed(html)
        parser.close()

        records: list[Mapping[str, Any]] = []
        required = {
            self._normalize_header(self.chance_header),
            self._normalize_header(self.date_header),
            self._normalize_header(self.result_header),
        }
        for rows in parser.tables:
            if not rows:
                continue
            headers = [self._normalize_header(cell) for cell in rows[0]]
            header_map = {name: index for index, name in enumerate(headers)}
            if not required.issubset(header_map):
                continue

            for row in rows[1:]:
                if len(row) <= max(header_map.values()):
                    continue
                chance = row[header_map[self._normalize_header(self.chance_header)]]
                date_text = row[header_map[self._normalize_header(self.date_header)]]
                result_text = row[header_map[self._normalize_header(self.result_header)]]
                match = self._NUMBER_RE.search(result_text)
                if not match or not self._DATE_RE.search(date_text) or not chance:
                    continue
                records.append(
                    {
                        "draw_type": self._draw_type(chance),
                        "draw_date": date_text,
                        "result": match.group(1),
                    }
                )

        if not records:
            raise SourceParseError(
                "HTML source does not contain a supported lottery result table"
            )
        return records

    @staticmethod
    def _normalize_header(value: str) -> str:
        return " ".join(value.casefold().split())

    @staticmethod
    def _draw_type(value: str) -> str:
        ascii_value = unicodedata.normalize("NFKD", value).encode(
            "ascii", "ignore"
        ).decode("ascii")
        normalized = re.sub(r"[^a-z0-9]+", "_", ascii_value.casefold()).strip("_")
        return normalized.upper()
