from __future__ import annotations

import html as html_lib
import re
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from io import BytesIO

from pypdf import PdfReader

from app.sources.contracts import SourceSpec
from app.sources.fetchers import SourceFetchResult
from app.sources.normalizer import MappingSourceAdapter, SourceNormalizationError
from app.sources.parsers import SourceParseError
from app.sources.traditional_lottery import get_traditional_source


class TraditionalLotteryHtmlParser:
    """Extract a four-digit major result plus series from a lottery result page."""

    _DRAW_RE = re.compile(
        r"\b(?:sorteo|draw)\s*"
        r"(?:(?:[:#-]\s*)|(?:n(?:umero|ro)?\s*[°º.]?\s*)|(?:no\.?\s*[°º.]?\s*))?"
        r"\s*(\d{1,6})",
        re.IGNORECASE,
    )
    _DATE_RE = re.compile(
        r"(?<!\d)(\d{1,2})\s*"
        r"(?:[,/-]\s*(?:(?:de|del)\s+)?|(?:de|del)\s+)?"
        r"([A-Za-zÁÉÍÓÚáéíóúñÑ]+\.?)\s*"
        r"(?:[,/-]\s*(?:(?:de|del)\s+)?|(?:de|del)\s+)?"
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
        r"\s*(?:(?:,\s*)|(?:(?:de|del)\s+))?(\d{4})\b",
        re.IGNORECASE,
    )
    _FLEXIBLE_TEXTUAL_DATE_RE = re.compile(
        r"(?<!\d)(\d{1,2})\s*(?:[,/-]\s*)?"
        r"(?:de\s+)?(enero|febrero|marzo|abril|mayo|junio|julio|"
        r"agosto|septiembre|setiembre|sept|septiembre|octubre|"
        r"noviembre|diciembre|ene|feb|mar|abr|may|jun|jul|ago|"
        r"sep|set|oct|nov|dic)\s*(?:[,/-]\s*)?"
        r"(?:de\s+)?(\d{4})(?!\d)",
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
    _WINNER_SPACED_NUMBER_RE = re.compile(
        r"\bnumero\s+ganador\b\s*[:#-]?\s*"
        r"(\d)(?:\s+(\d))(?:\s+(\d))(?:\s+(\d))\b",
        re.IGNORECASE,
    )
    _SERIES_RE = re.compile(
        r"(?:serie|series)\s*[:#-]?\s*(\d{1,4})",
        re.IGNORECASE,
    )
    _SPACED_SERIES_RE = re.compile(
        r"(?:serie|series)\s*[:#-]?\s*(\d)(?:\s+(\d))(?:\s+(\d))(?:\s+(\d))?",
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
        date_matches = list(self._DATE_RE.finditer(search_text))
        month_first_date_matches = list(self._MONTH_FIRST_DATE_RE.finditer(search_text))
        flexible_textual_date_matches = list(
            self._FLEXIBLE_TEXTUAL_DATE_RE.finditer(search_text)
        )
        numeric_date_matches = list(self._NUMERIC_DATE_RE.finditer(search_text))
        iso_date_matches = list(self._ISO_DATE_RE.finditer(search_text))
        date_match = date_matches[0] if date_matches else None
        month_first_date_match = month_first_date_matches[0] if month_first_date_matches else None
        numeric_date_match = numeric_date_matches[0] if numeric_date_matches else None
        iso_date_match = iso_date_matches[0] if iso_date_matches else None
        result_match = self._RESULT_RE.search(search_text)
        labeled_result_series_match = self._LABELED_RESULT_SERIES_RE.search(search_text)
        labeled_number_matches = self._LABELED_NUMBER_RE.findall(search_text)
        number_matches = self._NUMBER_RE.findall(text)
        winner_spaced_number_match = self._WINNER_SPACED_NUMBER_RE.search(
            search_text
        )
        spaced_number_matches = [
            "".join(match) for match in self._SPACED_NUMBER_RE.findall(text)
        ]
        series_match = self._SERIES_RE.search(search_text)
        spaced_series_matches = self._SPACED_SERIES_RE.finditer(search_text)

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
        code = (lottery_code or self.lottery_code).upper()
        profile = get_traditional_source(code)
        raw_number = (
            "".join(
                group
                for group in winner_spaced_number_match.groups()
                if group is not None
            )
            if winner_spaced_number_match
            else labeled_result_series_match.group(1)
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

        try:
            draw_date = self._parse_date(
                iso_date_matches=iso_date_matches,
                numeric_date_matches=numeric_date_matches,
                date_matches=date_matches,
                month_first_date_matches=month_first_date_matches,
                flexible_textual_date_matches=flexible_textual_date_matches,
            )
            date_inferred_from_draw_schedule = False
        except SourceParseError:
            # Risaralda's official sales page can serve the result data through
            # a dynamic renderer while omitting the human-readable date from
            # the raw HTTP HTML. The draw number is authoritative and this
            # lottery runs weekly on Fridays. Use a dated official draw anchor
            # only for this verified source as a deterministic fallback.
            if code != "LOTERIA_RISARALDA" or draw_number is None:
                raise
            anchor_draw = 2967
            anchor_date = date(2026, 9, 18)
            draw_date = (
                anchor_date + timedelta(days=(int(draw_number) - anchor_draw) * 7)
            ).isoformat()
            date_inferred_from_draw_schedule = True

        metadata = {
            "raw_result": raw_number,
            "digit_count": 4,
            "source_verified": profile.verified,
        }
        if date_inferred_from_draw_schedule:
            metadata["date_inferred_from_draw_schedule"] = True
        if labeled_result_series_match:
            metadata["series"] = labeled_result_series_match.group(2)
        else:
            for match in spaced_series_matches:
                digits = [group for group in match.groups() if group is not None]
                if 1 <= len(digits) <= 4:
                    metadata["series"] = "".join(digits)
                    break
            if "series" not in metadata and series_match:
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
        iso_date_matches: list[re.Match[str]],
        numeric_date_matches: list[re.Match[str]],
        date_matches: list[re.Match[str]],
        month_first_date_matches: list[re.Match[str]],
        flexible_textual_date_matches: list[re.Match[str]],
    ) -> str:
        # Prefer unambiguous numeric/ISO dates, then inspect every textual
        # candidate instead of trusting the first match on a long HTML page.
        for match in iso_date_matches:
            year, month, day = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
        for match in numeric_date_matches:
            day, month, year = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"

        candidates = []
        for match in month_first_date_matches:
            candidates.append((match.group(1), match.group(2), match.group(3)))
        for match in date_matches:
            candidates.append((match.group(2), match.group(1), match.group(3)))
        for match in flexible_textual_date_matches:
            candidates.append((match.group(2), match.group(1), match.group(3)))

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
        month = aliases.get(normalized)
        if month is not None:
            return month
        # Some operator pages contain truncated/typo-like month labels after
        # HTML normalization. A stable three-letter prefix is sufficient to
        # identify every supported calendar month without accepting arbitrary
        # text.
        prefixes = {
            "ene": "01", "feb": "02", "mar": "03", "abr": "04",
            "may": "05", "jun": "06", "jul": "07", "ago": "08",
            "sep": "09", "set": "09", "oct": "10", "nov": "11",
            "dic": "12", "jan": "01", "apr": "04", "aug": "08",
            "dec": "12",
        }
        return prefixes.get(normalized[:3])


class CundinamarcaActaPdfParser:
    """Parse the official Cundinamarca results acta PDF."""

    _DRAW_RE = re.compile(r"\bsorteo\s*[:#-]?\s*(\d{1,6})\b", re.IGNORECASE)
    _DATE_RE = re.compile(
        r"\ba\s+los\s+(\d{1,2})\s+del\s+mes\s+de\s+"
        r"([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+de\s+(\d{4})\b",
        re.IGNORECASE,
    )
    _MAJOR_RE = re.compile(r"\bpremio\s+mayor\b", re.IGNORECASE)
    _TOKEN_RE = re.compile(r"(?<!\d)(\d{1,4})(?!\d)")

    def __init__(self, lottery_code: str) -> None:
        self.lottery_code = lottery_code.upper()

    def parse(
        self,
        result: SourceFetchResult,
        lottery_code: str | None = None,
    ) -> Iterable[Mapping[str, object]]:
        if "pdf" not in result.content_type.casefold() and not result.content.startswith(
            b"%PDF"
        ):
            raise SourceParseError(
                "Cundinamarca official acta source is not a PDF document"
            )

        try:
            reader = PdfReader(BytesIO(result.content))
            text = " ".join(
                (page.extract_text() or "") for page in reader.pages
            )
        except Exception as exc:
            raise SourceParseError(
                "Cundinamarca official acta PDF could not be parsed"
            ) from exc

        text = " ".join(text.split())
        search_text = TraditionalLotteryHtmlParser._strip_accents(text)

        draw_match = self._DRAW_RE.search(search_text)
        date_match = self._DATE_RE.search(search_text)
        major_match = self._MAJOR_RE.search(search_text)
        if not draw_match or not date_match or not major_match:
            raise SourceParseError(
                "Cundinamarca official acta does not expose draw/date/major-result fields"
            )

        window = search_text[major_match.end() : major_match.end() + 300]
        tokens = list(self._TOKEN_RE.finditer(window))
        four_digit = [match for match in tokens if len(match.group(1)) == 4]
        if not four_digit:
            raise SourceParseError(
                "Cundinamarca official acta does not expose a four-digit major result"
            )

        major = four_digit[-1].group(1)
        series_candidates = [
            match.group(1)
            for match in tokens
            if match.start() > four_digit[-1].end()
        ]
        if not series_candidates:
            raise SourceParseError(
                "Cundinamarca official acta does not expose the major-result series"
            )

        month = TraditionalLotteryHtmlParser._month(date_match.group(2))
        if month is None:
            raise SourceParseError(
                "Cundinamarca official acta has an unsupported month"
            )

        code = (lottery_code or self.lottery_code).upper()
        profile = get_traditional_source(code)
        metadata = {
            "raw_result": major,
            "digit_count": 4,
            "series": series_candidates[0],
            "source_verified": profile.verified,
            "source_format": "official_acta_pdf",
        }
        return [
            {
                "lottery_code": code,
                "draw_type": f"{code}_ORDINARY",
                "draw_number": draw_match.group(1),
                "draw_date": (
                    f"{date_match.group(3)}-{month}-{int(date_match.group(1)):02d}"
                ),
                "main_numbers": [int(major)],
                "metadata": metadata,
                "source_url": result.url,
                "source_timestamp": result.fetched_at,
            }
        ]


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
