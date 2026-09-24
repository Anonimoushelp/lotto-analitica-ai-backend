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
                parsed_date = self._parse_date(date_text)
                if parsed_date is None:
                    continue
                records.append(
                    {
                        "draw_type": self._draw_type(chance),
                        "draw_date": parsed_date,
                        "result": match.group(1),
                    }
                )

        if not records:
            raise SourceParseError(
                "HTML source does not contain a supported lottery result table"
            )
        return records

    @classmethod
    def _parse_date(cls, value: str) -> str | None:
        match = cls._DATE_RE.search(value)
        if not match:
            return None
        months = {
            "enero": "01",
            "febrero": "02",
            "marzo": "03",
            "abril": "04",
            "mayo": "05",
            "junio": "06",
            "julio": "07",
            "agosto": "08",
            "septiembre": "09",
            "setiembre": "09",
            "octubre": "10",
            "noviembre": "11",
            "diciembre": "12",
        }
        month_name = (
            unicodedata.normalize("NFKD", match.group("month"))
            .encode("ascii", "ignore")
            .decode("ascii")
            .casefold()
        )
        month = months.get(month_name)
        if month is None:
            return None
        return f"{match.group('year')}-{month}-{int(match.group('day')):02d}"

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


class BalotoResultPageParser:
    """Extract the latest Baloto or Revancha result from the official history page."""

    _DATE_RE = re.compile(
        r"(?P<day>\d{1,2})\s+de\s+"
        r"(?P<month>[A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+de\s+(?P<year>\d{4})",
        re.IGNORECASE,
    )
    _RESULT_RE = re.compile(
        r"(?P<result>(?:\d{1,2}\s*-\s*){5}\d{1,2})"
    )
    _MONTHS = {
        "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
        "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
        "septiembre": "09", "setiembre": "09", "octubre": "10",
        "noviembre": "11", "diciembre": "12",
    }

    def __init__(self, *, draw_type: str) -> None:
        if draw_type not in {"BALOTO", "REVANCHA"}:
            raise ValueError("draw_type must be BALOTO or REVANCHA")
        self.draw_type = draw_type

    def parse(self, result: SourceFetchResult) -> Iterable[Mapping[str, Any]]:
        try:
            html = result.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceParseError("Baloto result page is not valid UTF-8") from exc

        text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
        marker = re.search(
            r"HISTÓRICO\s+DE\s+RESULTADOS(.*?)(?:Página\s+1\s+de|BALOTO\s+\.)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        history = marker.group(1) if marker else text
        date_matches = list(self._DATE_RE.finditer(history))
        result_matches = list(self._RESULT_RE.finditer(history))
        if not date_matches or len(result_matches) < 2:
            raise SourceParseError(
                "Baloto result page is missing the official historical results"
            )

        pair_index = 0 if self.draw_type == "BALOTO" else 1
        if len(result_matches) <= pair_index or len(date_matches) <= pair_index:
            raise SourceParseError(
                "Baloto result page does not contain both Baloto and Revancha results"
            )

        date_match = date_matches[0]
        result_match = result_matches[pair_index]
        numbers = [int(value) for value in re.findall(r"\d{1,2}", result_match.group("result"))]
        if len(numbers) != 6:
            raise SourceParseError(
                "Baloto result page must contain exactly five main numbers and one bonus number"
            )

        month = self._MONTHS.get(
            unicodedata.normalize("NFKD", date_match.group("month"))
            .encode("ascii", "ignore").decode("ascii").casefold()
        )
        if month is None:
            raise SourceParseError("Baloto result page contains an unsupported month")

        return [{
            "game_type": self.draw_type,
            "draw_number": None,
            "draw_date": f"{date_match.group('year')}-{month}-{int(date_match.group('day')):02d}",
            "main_numbers": numbers[:5],
            "metadata": {
                "source_format": "official_history_page",
                "result_sequence": pair_index + 1,
            },
            "revancha_bonus" if self.draw_type == "REVANCHA" else "superbalota": [numbers[5]],
        }]


class MiLotoResultPageParser:
    """Extract the latest MiLoto result from the official historical-results page."""

    _DRAW_RE = re.compile(r"SORTEO\s*#(?P<number>\d+)", re.IGNORECASE)
    _DATE_RE = re.compile(
        r"(?P<day>\d{1,2})\s+de\s+(?P<month>[A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+de\s+(?P<year>\d{4})",
        re.IGNORECASE,
    )
    _RESULT_RE = re.compile(r"(?P<date>\d{1,2}\s+de\s+[A-Za-zÁÉÍÓÚáéíóúñÑ]+\s+de\s+\d{4})\s*(?:\.\s*)?(?P<result>(?:\d{1,2}\s*-\s*){4}\d{1,2})")
    _MONTHS = {
        "enero":"01","febrero":"02","marzo":"03","abril":"04","mayo":"05","junio":"06",
        "julio":"07","agosto":"08","septiembre":"09","setiembre":"09","octubre":"10",
        "noviembre":"11","diciembre":"12",
    }

    def parse(self, result: SourceFetchResult) -> Iterable[Mapping[str, Any]]:
        try:
            html = result.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceParseError("MiLoto result page is not valid UTF-8") from exc
        text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
        draw_match = self._DRAW_RE.search(text)
        date_match = self._DATE_RE.search(text)
        result_match = self._RESULT_RE.search(text)
        if not draw_match or not date_match or not result_match:
            raise SourceParseError("MiLoto result page is missing the latest result")
        month = self._MONTHS.get(
            unicodedata.normalize("NFKD", date_match.group("month")).encode("ascii", "ignore").decode("ascii").casefold()
        )
        if month is None:
            raise SourceParseError("MiLoto result page contains an unsupported month")
        numbers = [int(value) for value in re.findall(r"\d{1,2}", result_match.group("result"))]
        if len(numbers) != 5:
            raise SourceParseError("MiLoto result must contain exactly five numbers")
        return [{
            "draw_type": "MILOTO",
            "draw_number": draw_match.group("number"),
            "draw_date": f"{date_match.group('year')}-{month}-{int(date_match.group('day')):02d}",
            "main_numbers": numbers,
        }]


class SuperAstroResultPageParser:
    """Extract the latest Sol or Luna result from the official results tables."""

    _HEADER = {"numero", "signo", "sorteo", "fecha"}

    def __init__(self, *, draw_type: str) -> None:
        if draw_type not in {"ASTRO_SOL", "ASTRO_LUNA"}:
            raise ValueError("draw_type must be ASTRO_SOL or ASTRO_LUNA")
        self.draw_type = draw_type

    def parse(self, result: SourceFetchResult) -> Iterable[Mapping[str, Any]]:
        try:
            html = result.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceParseError("Super Astro result page is not valid UTF-8") from exc

        parser = _ResultTableParser()
        parser.feed(html)
        parser.close()

        matching_tables: list[list[list[str]]] = []
        for rows in parser.tables:
            if not rows:
                continue
            headers = [self._normalize_header(cell) for cell in rows[0]]
            if self._HEADER.issubset(set(headers)):
                matching_tables.append(rows)

        table_index = 0 if self.draw_type == "ASTRO_SOL" else 1
        if len(matching_tables) <= table_index:
            raise SourceParseError(
                "Super Astro result page is missing the requested draw table"
            )

        rows = matching_tables[table_index]
        headers = [self._normalize_header(cell) for cell in rows[0]]
        header_map = {name: index for index, name in enumerate(headers)}
        for row in rows[1:]:
            if len(row) <= max(header_map.values()):
                continue
            number = row[header_map["numero"]].strip()
            sign = row[header_map["signo"]].strip()
            draw_number = row[header_map["sorteo"]].strip()
            draw_date = row[header_map["fecha"]].strip()
            if (
                len(number) == 4 and number.isdigit()
                and draw_number.isdigit()
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}", draw_date)
                and sign
            ):
                return [{
                    "draw_type": self.draw_type,
                    "draw_number": draw_number,
                    "draw_date": draw_date,
                    "number": number,
                    "metadata": {"sign": sign},
                }]

        raise SourceParseError("Super Astro result page is missing the requested draw")

    @staticmethod
    def _normalize_header(value: str) -> str:
        value = unicodedata.normalize("NFKD", value).encode(
            "ascii", "ignore"
        ).decode("ascii").casefold()
        return " ".join(value.split())


class PagaTodoResultPageParser:
    """Extract El Dorado results from the official Paga Todo La Quinta page."""

    _MONTHS = {
        "01": "01", "02": "02", "03": "03", "04": "04", "05": "05",
        "06": "06", "07": "07", "08": "08", "09": "09", "10": "10",
        "11": "11", "12": "12",
    }

    def __init__(self, *, draw_types: tuple[str, ...]) -> None:
        self.draw_types = draw_types

    def parse(self, result: SourceFetchResult) -> Iterable[Mapping[str, Any]]:
        try:
            html = result.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceParseError("Paga Todo result page is not valid UTF-8") from exc

        text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
        records: list[Mapping[str, Any]] = []
        aliases = {
            "DORADO_DIA": "Sorteo El Dorado Día",
            "DORADO_TARDE": "Sorteo El Dorado Tarde",
            "DORADO_NOCHE": "Sorteo El Dorado Noche",
        }
        for draw_type in self.draw_types:
            title = aliases[draw_type]
            pattern = re.compile(
                re.escape(title)
                + r".*?(?P<date>\d{2}/\d{2}/\d{4}).*?"
                + r"Número Ganador.*?(?P<number>\d\s*\d\s*\d\s*\d)"
                + r"\s*-\s*(?P<extra>\d)",
                re.IGNORECASE | re.DOTALL,
            )
            match = pattern.search(text)
            if match is None:
                raise SourceParseError(
                    f"Paga Todo result page is missing {draw_type}"
                )
            raw_number = re.sub(r"\s+", "", match.group("number"))
            day, month, year = match.group("date").split("/")
            records.append({
                "draw_type": draw_type,
                "draw_date": f"{year}-{month}-{day}",
                "result": raw_number,
                "metadata": {
                    "additional_value": match.group("extra"),
                    "source_format": "official_la_quinta_page",
                },
            })

        return records
