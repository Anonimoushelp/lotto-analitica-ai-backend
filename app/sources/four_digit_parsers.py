from __future__ import annotations

import html as html_lib
import re
import unicodedata
from collections.abc import Mapping
from typing import Any, ClassVar

from app.sources.parsers import SourceParseError

# Provider-independent aliases used only for structural four-digit extraction.
_DRAW_TYPE_KEYS = ("draw_type", "game_type", "game", "tipo", "sorteo_tipo")
_DRAW_NUMBER_KEYS = ("draw_number", "draw", "sorteo", "numero_sorteo")
_DRAW_DATE_KEYS = ("draw_date", "date", "fecha")
_RESULT_KEYS = ("result", "resultado", "number", "numero")


def _require(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    raise SourceParseError(f"Missing required source field: {keys[0]}")


def parse_four_digit_record(
    payload: Mapping[str, Any],
    *,
    allowed_draw_types: set[str],
    metadata_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    raw_type = _require(payload, *_DRAW_TYPE_KEYS)
    draw_type = str(raw_type).strip().upper()
    if draw_type not in allowed_draw_types:
        allowed = ", ".join(sorted(allowed_draw_types))
        raise SourceParseError(f"Unsupported draw type {draw_type}; expected one of {allowed}")

    raw_result = str(_require(payload, *_RESULT_KEYS)).strip()
    if len(raw_result) != 4 or not raw_result.isdigit():
        raise SourceParseError("Four-digit result must contain exactly four digits")

    metadata = dict(payload.get("metadata") or {})
    metadata["raw_result"] = raw_result
    metadata["digit_count"] = 4
    for key in metadata_keys:
        if key in payload and payload[key] not in (None, "") and key not in metadata:
            metadata[key] = payload[key]

    return {
        "draw_type": draw_type,
        "draw_number": _require(payload, *_DRAW_NUMBER_KEYS),
        "draw_date": _require(payload, *_DRAW_DATE_KEYS),
        "number": raw_result,
        "metadata": metadata,
    }


class AntioquenitaHtmlParser:
    """Extract Antioqueñita results from the official Rediapuestas iframe HTML."""

    _DRAW_RE = re.compile(
        r"(?:sorteo|numero\s+de\s+sorteo)\s*(?:[#nºo.]\s*)?(?P<number>\d{3,6})",
        re.IGNORECASE,
    )
    _DATE_RE = re.compile(
        r"(?P<day>\d{1,2})\s+(?:de\s+)?"
        r"(?P<month>[a-z]+)(?:\s+(?:de|del))?\s+(?P<year>\d{4})",
        re.IGNORECASE,
    )
    _RESULT_RE = re.compile(
        r"(?:resultado|numero(?:\s+(?:ganador|premiado|favorecido))?|ganador)"
        r"\s*[:\-]?\s*(?P<number>\d\s*\d\s*\d\s*\d)(?!\d)",
        re.IGNORECASE,
    )
    _FIFTH_RE = re.compile(
        r"(?:la\s+quinta|quinta|5ta|5a\s+balota)\s*[:\-]?\s*(?P<number>\d)",
        re.IGNORECASE,
    )
    _MONTHS: ClassVar[dict[str, str]] = {
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
    _TYPE_MARKERS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("antioquenita 1", "ANTIOQUENITA_1"),
        ("antioquenita1", "ANTIOQUENITA_1"),
        ("antioquenita dia", "ANTIOQUENITA_1"),
        ("antioquenita manana", "ANTIOQUENITA_1"),
        ("antioquenita 2", "ANTIOQUENITA_2"),
        ("antioquenita2", "ANTIOQUENITA_2"),
        ("antioquenita tarde", "ANTIOQUENITA_2"),
    )

    @staticmethod
    def _ascii_text(value: str) -> str:
        return (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
            .casefold()
        )

    @classmethod
    def _parse_date(cls, value: str) -> str | None:
        match = cls._DATE_RE.search(value)
        if match is None:
            return None
        month = cls._MONTHS.get(match.group("month").casefold())
        if month is None:
            return None
        return f"{match.group('year')}-{month}-{int(match.group('day')):02d}"

    @staticmethod
    def _flatten_html(html: str) -> str:
        text = re.sub(
            r"<script[^>]*>.*?</script>|<style[^>]*>.*?</style>",
            " ",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        text = re.sub(r"<[^>]+>", " ", text)
        return " ".join(html_lib.unescape(text).split())

    def parse(self, result: Any) -> list[Mapping[str, Any]]:
        try:
            html = result.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceParseError("Antioqueñita iframe is not valid UTF-8") from exc

        text = self._ascii_text(self._flatten_html(html))
        markers: list[tuple[int, int, str]] = []
        for marker, draw_type in self._TYPE_MARKERS:
            offset = 0
            while True:
                position = text.find(marker, offset)
                if position < 0:
                    break
                markers.append((position, len(marker), draw_type))
                offset = position + len(marker)

        markers.sort()
        records: list[Mapping[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        draw_matches = 0
        date_matches = 0
        result_matches = 0
        valid_numbers = 0
        valid_dates = 0
        date_months: set[str] = set()

        for index, (position, _, draw_type) in enumerate(markers):
            next_position = (
                markers[index + 1][0]
                if index + 1 < len(markers)
                else position + 900
            )
            window = text[position : min(next_position, position + 900)]
            draw_match = self._DRAW_RE.search(window)
            date_match = self._DATE_RE.search(window)
            result_match = self._RESULT_RE.search(window)
            if draw_match is None:
                continue
            draw_matches += 1
            if date_match is None:
                continue
            date_matches += 1
            if result_match is None:
                continue
            result_matches += 1

            raw_result = re.sub(r"\s+", "", result_match.group("number"))
            if len(raw_result) != 4 or not raw_result.isdigit():
                continue
            valid_numbers += 1

            date_months.add(date_match.group("month"))
            draw_date = self._parse_date(date_match.group(0))
            if draw_date is None:
                continue
            valid_dates += 1

            fifth_match = self._FIFTH_RE.search(window)
            metadata: dict[str, Any] = {
                "raw_result": raw_result,
                "digit_count": 4,
                "source_format": "official_rediapuestas_iframe_html",
            }
            if fifth_match:
                metadata["quinta"] = int(fifth_match.group("number"))

            key = (draw_type, draw_match.group("number"), draw_date, raw_result)
            if key in seen:
                continue
            seen.add(key)
            records.append(
                {
                    "draw_type": draw_type,
                    "draw_number": draw_match.group("number"),
                    "draw_date": draw_date,
                    "number": raw_result,
                    "metadata": metadata,
                }
            )

        if not records:
            raise SourceParseError(
                "Antioqueñita iframe does not contain a valid result "
                f"(markers={len(markers)}, draw={draw_matches}, "
                f"date={date_matches}, result={result_matches}, "
                f"number={valid_numbers}, valid_date={valid_dates}, "
                f"months={','.join(sorted(date_months)) or 'none'})"
            )
        return records


class AntioquenitaJsonParser:
    def parse_record(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return parse_four_digit_record(
            payload,
            allowed_draw_types={"ANTIOQUENITA_1", "ANTIOQUENITA_2"},
        )


class ChonticoJsonParser:
    def parse_record(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return parse_four_digit_record(
            payload,
            allowed_draw_types={
                "CHONTICO_DIA",
                "CHONTICO_NOCHE",
                "CHONTICO_SUPER_NOCHE",
            },
        )


class DoradoJsonParser:
    def parse_record(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return parse_four_digit_record(
            payload,
            allowed_draw_types={"DORADO_DIA", "DORADO_TARDE", "DORADO_NOCHE"},
            metadata_keys=("additional_value", "raw_additional_value"),
        )


class CafeteritoJsonParser:
    def parse_record(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return parse_four_digit_record(
            payload,
            allowed_draw_types={"CAFETERITO_TARDE", "CAFETERITO_NOCHE"},
        )


class PaisitaJsonParser:
    def parse_record(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return parse_four_digit_record(
            payload,
            allowed_draw_types={"PAISITA_DIA", "PAISITA_NOCHE"},
            metadata_keys=("animal",),
        )


class FantasticaJsonParser:
    def parse_record(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return parse_four_digit_record(
            payload,
            allowed_draw_types={"FANTASTICA_DIA", "FANTASTICA_NOCHE"},
            metadata_keys=("additional_value", "raw_additional_value"),
        )
