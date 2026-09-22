from __future__ import annotations

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

    _DRAW_RE = re.compile(r"\b(?:sorteo|draw)\s*(?:n[úu]mero|no\.?|#)?\s*(\d{1,6})", re.IGNORECASE)
    _DATE_RE = re.compile(
        r"(\d{1,2})\s*(?:de\s+)?([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s*(?:de\s+)?(\d{4})",
        re.I,
    )
    _NUMBER_RE = re.compile(r"\b(\d{4})\b")
    _SERIES_RE = re.compile(r"(?:serie|series)\s*[:#-]?\s*(\d{1,4})", re.I)

    def parse(self, result: SourceFetchResult, lottery_code: str) -> Iterable[Mapping[str, object]]:
        try:
            html = result.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceParseError("Traditional lottery HTML is not valid UTF-8") from exc

        text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
        draw_match = self._DRAW_RE.search(text)
        date_match = self._DATE_RE.search(text)
        number_matches = self._NUMBER_RE.findall(text)
        series_match = self._SERIES_RE.search(text)

        if not date_match or not number_matches:
            raise SourceParseError(
                "Traditional lottery source does not expose a recognizable date/result"
            )

        draw_number = draw_match.group(1) if draw_match else None
        raw_number = number_matches[0]
        month = self._month(date_match.group(2))
        if month is None:
            raise SourceParseError("Traditional lottery source has an unsupported month")
        draw_date = f"{date_match.group(3)}-{month}-{int(date_match.group(1)):02d}"

        metadata = {"raw_result": raw_number, "digit_count": 4}
        if series_match:
            metadata["series"] = series_match.group(1)

        return [{
            "lottery_code": lottery_code,
            "draw_type": f"{lottery_code}_ORDINARY",
            "draw_number": draw_number,
            "draw_date": draw_date,
            "main_numbers": [int(raw_number)],
            "metadata": metadata,
            "source_url": result.url,
            "source_timestamp": result.fetched_at,
        }]

    @staticmethod
    def _month(value: str) -> str | None:
        normalized = (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
            .casefold()
        )
        return {
            "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
            "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
            "septiembre": "09", "setiembre": "09", "octubre": "10",
            "noviembre": "11", "diciembre": "12",
        }.get(normalized)


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
