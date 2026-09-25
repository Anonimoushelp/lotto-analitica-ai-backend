from __future__ import annotations

import html as html_lib
import re
import unicodedata
from collections.abc import Iterable, Mapping

from app.sources.contracts import SourceSpec
from app.sources.fetchers import SourceFetchResult
from app.sources.normalizer import MappingSourceAdapter, SourceNormalizationError
from app.sources.parsers import SourceParseError
from app.sources.traditional_lottery import get_traditional_source


class TraditionalLotteryHtmlParser:
    """Extract a four-digit major result plus series from a lottery result page."""

    _DRAW_RE = re.compile(
        r"\b(?:sorteo|draw)\s*[:#-]?\s*(?:numero|no\.?)?\s*[:#-]?\s*(\d{1,6})",
        re.IGNORECASE,
    )
    _DATE_RE = re.compile(
        r"(?<!\d)(\d{1,2})\s*(?:de\s+)?"
        r"([A-Za-zÁÉÍÓÚáéíóúñÑ]+\.?)\s*(?:de\s+)?"
        r"(\d{4})(?!\d)",
        re.IGNORECASE,
    )
    _NUMERIC_DATE_RE = re.compile(
        r"(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?!\d)"
    )
    _ISO_DATE_RE = re.compile(
        r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)"
    )
    _MONTH_FIRST_DATE_RE = re.compile(
        r"\b([A-Za-zÁÉÍÓÚáéíóúñÑ]+\.?)\s*[,\s]+(\d{1,2})"
        r"\s*(?:de\s+)?(\d{4})\b",
        re.IGNORECASE,
    )
    _RESULT_RE = re.compile(
        r"\b(?:resultado|result)\s*[:#-]?\s*(\d{4})\b",
        re.IGNORECASE,
    )
    _LABELED_RESULT_SERIES_RE = re.compile(
        r"\b(?:premio\s+mayor|resultado)\s*[:#-]?\s*(\d{4})\s*-\s*(\d{1,4})\b",
        re.IGNORECASE,
    )
    _LABELED_NUMBER_RE = re.compile(
        r"\bnumero\s*[:#-]?\s*(\d{4})\b",
        re.IGNORECASE,
    )
    _NUMBER_RE = re.compile(r"\b(\d{4})\b")
    _SPACED_NUMBER_RE = re.compile(
        r"(?<!\d)(\d)\s+(\d)\s+(\d)\s+(\d)(?!\d)"
    )
    _SERIES_RE = re.compile(
        r"(?:serie|series)\s*[:#-]?\s*(\d{1,4})",
        re.IGNORECASE,
    )

    def __init__(self, lottery_code: str) -> None:
        self.lottery_code = lottery_code.upper()

    def parse(
        self,
        result: SourceFetchResult,
        lottery_code: str | None = None,
    ) -> Iterable[Mapping[str, object]]:
        try:
            html = result.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceParseError("Traditional lottery HTML is not valid UTF-8") from exc

        text = " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", html)).split())
        text = re.sub(r"\s+", " ", text).strip()
        search_text = self._strip_accents(text)
        draw_match = self._DRAW_RE.search(search_text)
        date_match = self._DATE_RE.search(search_text)
        month_first_date_match = self._MONTH_FIRST_DATE_RE.search(search_text)
        numeric_date_match = self._NUMERIC_DATE_RE.search(search_text)
        iso_date_match = self._ISO_DATE_RE.search(search_text)
        result_match = self._RESULT_RE.search(search_text)
        labeled_result_series_match = self._LABELED_RESULT_SERIES_RE.search(search_text)
        labeled_number_matches = self._LABELED_NUMBER_RE.findall(search_text)
        number_matches = self._NUMBER_RE.findall(text)
        spaced_number_matches = [
            "".join(match) for match in self._SPACED_NUMBER_RE.findall(text)
        ]
        series_match = self._SERIES_RE.search(search_text)

        if not date_match and not month_first_date_match and not numeric_date_match and not iso_date_match:
            raise SourceParseError(
                "Traditional lottery source does not expose a recognizable date/result"
            )
        if (
            not result_match
            and not labeled_number_matches
            and not number_matches
            and not spaced_number_matches
        ):
            raise SourceParseError(
                "Traditional lottery source does not expose a recognizable date/result"
            )

        draw_number = draw_match.group(1) if draw_match else None
        raw_number = (
            labeled_result_series_match.group(1)
            if labeled_result_series_match
            else result_match.group(1) if result_match else None
        )
        if raw_number is None:
            for candidate in labeled_number_matches:
                if draw_number is None or candidate != draw_number:
                    raw_number = candidate
                    break
        if raw_number is None:
            for candidate in spaced_number_matches:
                if draw_number is None or candidate != draw_number:
                    raw_number = candidate
                    break
        if raw_number is None:
            for candidate in number_matches:
                if draw_number is None or candidate != draw_number:
                    raw_number = candidate
                    break
        if raw_number is None:
            raise SourceParseError(
                "Traditional lottery source does not expose a recognizable four-digit result"
            )

        draw_date = self._parse_date(
            iso_date_match=iso_date_match,
            numeric_date_match=numeric_date_match,
            date_match=date_match,
            month_first_date_match=month_first_date_match,
        )

        code = (lottery_code or self.lottery_code).upper()
        profile = get_traditional_source(code)
        metadata = {
            "raw_result": raw_number,
            "digit_count": 4,
            "source_verified": profile.verified,
        }
        if labeled_result_series_match:
            metadata["series"] = labeled_result_series_match.group(2)
        elif series_match:
            metadata["series"] = series_match.group(1)

        return [
            {
                "lottery_code": code,
                "draw_type": f"{code}_ORDINARY",
                "draw_number": draw_number,
                "draw_date": draw_date,
                "main_numbers": [int(raw_number)],
                "metadata": metadata,
                "source_url": result.url,
                "source_timestamp": result.fetched_at,
            }
        ]

    def _parse_date(
        self,
        *,
        iso_date_match: re.Match[str] | None,
        numeric_date_match: re.Match[str] | None,
        date_match: re.Match[str] | None,
        month_first_date_match: re.Match[str] | None,
    ) -> str:
        if iso_date_match:
            year, month, day = iso_date_match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
        if numeric_date_match:
            day, month, year = numeric_date_match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
        candidates = []
        if month_first_date_match:
            candidates.append(
                (
                    month_first_date_match.group(1),
                    month_first_date_match.group(2),
                    month_first_date_match.group(3),
                )
            )
        if date_match:
            candidates.append(
                (
                    date_match.group(2),
                    date_match.group(1),
                    date_match.group(3),
                )
            )
        for month_name, day, year in candidates:
            month = self._month(month_name)
            if month is not None:
                return f"{year}-{month}-{int(day):02d}"
        raise SourceParseError("Traditional lottery source has an unsupported month")

    @staticmethod
    def _strip_accents(value: str) -> str:
        return (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
        )

    @staticmethod
    def _month(value: str) -> str | None:
        normalized = (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
            .casefold()
        )
        normalized = re.sub(r"[^a-z]", "", normalized)
        aliases = {
            "ene": "01", "enero": "01",
            "feb": "02", "febrero": "02",
            "mar": "03", "marzo": "03",
            "abr": "04", "abril": "04",
            "may": "05", "mayo": "05",
            "jun": "06", "junio": "06",
            "jul": "07", "julio": "07",
            "ago": "08", "agosto": "08",
            "sep": "09", "sept": "09", "septiembre": "09", "set": "09", "setiembre": "09",
            "oct": "10", "octubre": "10",
            "nov": "11", "noviembre": "11",
            "dic": "12", "diciembre": "12",
            "jan": "01", "january": "01",
            "february": "02",
            "march": "03",
            "april": "04",
            "june": "06",
            "july": "07",
            "august": "08",
            "september": "09",
            "october": "10",
            "november": "11",
            "december": "12",
        }
        return aliases.get(normalized)


class TraditionalLotteryAdapter(MappingSourceAdapter):
    """Normalize traditional lottery major results into the canonical contract."""

    def __init__(self, lottery_code: str) -> None:
        profile = get_traditional_source(lottery_code)
        draw_type = f"{lottery_code}_ORDINARY"
        super().__init__(
            SourceSpec(
                lottery_code=lottery_code,
                draw_types=(draw_type,),
                primary_name=profile.name,
                primary_url=profile.result_url,
                primary_verified=profile.verified,
            )
        )

    def normalize(self, payload: Mapping[str, object]):
        payload = dict(payload)
        raw = str(payload.get("metadata", {}).get("raw_result", "")).strip()
        if len(raw) != 4 or not raw.isdigit():
            raise SourceNormalizationError(
                "Traditional lottery major result must be exactly four digits"
            )
        payload["main_numbers"] = [int(raw)]
        return super().normalize(payload)
