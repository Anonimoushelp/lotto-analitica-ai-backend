from __future__ import annotations

import html as html_lib
import re
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
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
        r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4})(?!\d)"
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
        r"(?<!\d)(\d{1,2})\s*(?:[,./-]\s*)?"
        r"(?:(?:del?\s+mes\s+de)|(?:de\s+))?(enero|febrero|marzo|abril|mayo|junio|julio|"
        r"agosto|septiembre|setiembre|sept|octubre|noviembre|diciembre|ene|feb|mar|abr|may|jun|jul|ago|"
        r"sep|set|oct|nov|dic|january|february|march|april|june|july|august|september|october|november|december)\s*(?:[,./-]\s*)?"
        r"(?:de\s+)?(\d{4})(?!\d)",
        re.IGNORECASE,
    )
    _RESULT_RE = re.compile(
        r"\b(?:resultado|result)\s*[:#-]?\s*(\d{4})\b",
        re.IGNORECASE,
    )
    _MAJOR_RESULT_RE = re.compile(
        r"\b(?:premio\s+mayor|numero\s+ganador)\s*[:#-]?\s*"
        r"(\d{4})(?!\d)(?!\s*millon(?:es)?\b)",
        re.IGNORECASE,
    )
    _MAJOR_SPACED_RESULT_RE = re.compile(
        r"\bpremio\s+mayor\b\s*[:#-]?\s*"
        r"(\d)(?:\s+(\d))(?:\s+(\d))(?:\s+(\d))\b",
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
    _NUMBER_BEFORE_SERIES_RE = re.compile(
        r"\bnumero\b\s*[:#-]?\s*(\d{1,3})\s*(?:\||[-·])?\s*serie\b",
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
        code = (lottery_code or self.lottery_code).upper()

        if code == "LOTERIA_CAUCA":
            cauca_record = self._parse_cauca_homepage_current_result(
                search_text=search_text,
                result=result,
            )
            if cauca_record is not None:
                return [cauca_record]

        all_draw_matches = list(self._DRAW_RE.finditer(search_text))
        if code == "LOTERIA_BOYACA":
            labeled_draw_matches = list(
                re.finditer(
                    r"\bresultado\s+sorteo\s*#\s*(\d{3,6})\b",
                    search_text,
                    re.IGNORECASE,
                )
            )
            if labeled_draw_matches:
                all_draw_matches = labeled_draw_matches

        if code == "LOTERIA_RISARALDA" and not all_draw_matches:
            all_draw_matches = list(
                re.finditer(
                    r"\bsorteo\b[\s:#.\-]*(?:n(?:o|ro)?|numero|#)?"
                    r"[\s:#.\-]*(\d{3,6})\b",
                    search_text,
                    re.IGNORECASE,
                )
            )

        date_matches = list(self._DATE_RE.finditer(search_text))
        month_first_date_matches = list(self._MONTH_FIRST_DATE_RE.finditer(search_text))
        flexible_textual_date_matches = list(
            self._FLEXIBLE_TEXTUAL_DATE_RE.finditer(search_text)
        )
        numeric_date_matches = list(self._NUMERIC_DATE_RE.finditer(search_text))
        iso_date_matches = list(self._ISO_DATE_RE.finditer(search_text))

        all_number_candidates: list[tuple[str, int, int]] = []
        for match in self._WINNER_SPACED_NUMBER_RE.finditer(search_text):
            all_number_candidates.append(
                (
                    "".join(group for group in match.groups() if group is not None),
                    match.start(),
                    100,
                )
            )
        for match in self._MAJOR_SPACED_RESULT_RE.finditer(search_text):
            all_number_candidates.append(
                (
                    "".join(group for group in match.groups() if group is not None),
                    match.start(),
                    95,
                )
            )
        for match in self._MAJOR_RESULT_RE.finditer(search_text):
            all_number_candidates.append((match.group(1), match.start(), 90))
        for match in self._LABELED_RESULT_SERIES_RE.finditer(search_text):
            all_number_candidates.append((match.group(1), match.start(), 80))
        for match in self._RESULT_RE.finditer(search_text):
            all_number_candidates.append((match.group(1), match.start(), 70))
        for match in self._LABELED_NUMBER_RE.finditer(search_text):
            # "Sorteo número 4187" is a draw identity, not the winning number.
            # Ignore a labelled number when it is part of the local draw header.
            prefix = search_text[max(0, match.start() - 24):match.start()]
            if re.search(r"\bsorteo\s*$", prefix, re.IGNORECASE):
                continue
            all_number_candidates.append((match.group(1), match.start(), 60))

        number_matches = list(self._NUMBER_RE.finditer(text))
        spaced_number_matches = list(self._SPACED_NUMBER_RE.finditer(text))

        if code == "LOTERIA_RISARALDA":
            official_record = self._parse_risaralda_official(
                search_text=search_text,
                result=result,
                all_number_candidates=all_number_candidates,
            )
            if official_record is not None:
                return [official_record]

        if (
            not date_matches
            and not month_first_date_matches
            and not numeric_date_matches
            and not iso_date_matches
            and not (code == "LOTERIA_RISARALDA" and all_draw_matches)
        ):
            raise SourceParseError(
                "Traditional lottery source does not expose a recognizable date/result"
            )
        if not all_number_candidates and not number_matches and not spaced_number_matches:
            raise SourceParseError(
                "Traditional lottery source does not expose a recognizable date/result"
            )

        # Risaralda's results page may contain unrelated four-digit values
        # from embedded chance/result widgets. Prefer an explicit major-result
        # label. When only a generic labelled result is exposed, require that
        # the candidate is not locally associated with another game.
        if code == "LOTERIA_RISARALDA" and not any(
            weight >= 80 for _, _, weight in all_number_candidates
        ):
            unrelated_context = re.compile(
                r"\b(?:chontico|dorado|astro|miloto|baloto|revancha|"
                r"paisita|sinuano|caribeñ[ae]|cafeterito|fantastica|"
                r"antioqueñita|play\s+four|cash|motil[oó]n|pijao|"
                r"s[aá]man|culona)\b",
                re.IGNORECASE,
            )
            safe_candidates = []
            for raw, position, weight in all_number_candidates:
                if weight < 60:
                    continue
                context = search_text[max(0, position - 180):position + 180]
                if unrelated_context.search(context):
                    continue
                safe_candidates.append((raw, position, weight))

            if not safe_candidates:
                raise SourceParseError(
                    "Risaralda result page does not expose a recognizable major result"
                )

            series_positions = [m.start() for m in self._SERIES_RE.finditer(search_text)]
            if not series_positions:
                series_positions = [
                    m.start() for m in self._SPACED_SERIES_RE.finditer(search_text)
                ]
            if series_positions:
                raw_number, raw_number_anchor, _ = min(
                    safe_candidates,
                    key=lambda item: (
                        min(abs(item[1] - series_pos) for series_pos in series_positions),
                        -item[2],
                        -item[1],
                    ),
                )
            else:
                raw_number, raw_number_anchor, _ = max(
                    safe_candidates,
                    key=lambda item: (item[2], item[1]),
                )
        profile = get_traditional_source(code)
        reference_date = result.fetched_at.date()

        selected: tuple[str, int, int, date] | None = None
        if all_number_candidates:
            evaluated: list[tuple[int, int, int, int, int, str, int, date]] = []
            for raw, position, weight in all_number_candidates:
                try:
                    candidate_date = date.fromisoformat(
                        self._parse_date(
                            iso_date_matches=iso_date_matches,
                            numeric_date_matches=numeric_date_matches,
                            date_matches=date_matches,
                            month_first_date_matches=month_first_date_matches,
                            flexible_textual_date_matches=flexible_textual_date_matches,
                            reference_date=None,
                            anchor_position=position,
                        )
                    )
                except SourceParseError:
                    continue
                is_past_or_today = int(candidate_date <= reference_date)
                distance = abs(position - next(
                    (
                        m.start()
                        for m in (
                            [*iso_date_matches, *numeric_date_matches,
                             *date_matches, *month_first_date_matches,
                             *flexible_textual_date_matches]
                        )
                        if abs(m.start() - position) <= 600
                    ),
                    position,
                ))
                evaluated.append(
                    (
                        is_past_or_today,
                        candidate_date.toordinal(),
                        weight,
                        -distance,
                        -position,
                        raw,
                        position,
                        candidate_date,
                    )
                )
            if evaluated:
                best = max(evaluated)
                selected = (best[5], best[6], best[2], best[7])

        raw_number: str | None = selected[0] if selected else None
        raw_number_anchor: int | None = selected[1] if selected else None
        selected_draw_date: date | None = selected[3] if selected else None

        if raw_number is None:
            # Fall back to unlabeled four-digit candidates, but never treat a
            # calendar year as a winning result without an explicit result label.
            fallback_candidates: list[tuple[str, int]] = [
                (m.group(1), m.start()) for m in self._LABELED_NUMBER_RE.finditer(search_text)
            ]
            fallback_candidates.extend(
                (
                    "".join(m.groups()),
                    m.start(),
                )
                for m in spaced_number_matches
            )
            fallback_candidates.extend(
                (m.group(1), m.start()) for m in number_matches
            )
            for candidate, position in fallback_candidates:
                if int(candidate) in range(1900, 2101):
                    continue
                raw_number = candidate
                raw_number_anchor = position
                break
            if raw_number is None:
                raise SourceParseError(
                    "Traditional lottery source does not expose a recognizable four-digit result"
                )

        if selected_draw_date is not None:
            draw_date = selected_draw_date.isoformat()
        else:
            try:
                draw_date = self._parse_date(
                    iso_date_matches=iso_date_matches,
                    numeric_date_matches=numeric_date_matches,
                    date_matches=date_matches,
                    month_first_date_matches=month_first_date_matches,
                    flexible_textual_date_matches=flexible_textual_date_matches,
                    reference_date=reference_date,
                    anchor_position=raw_number_anchor,
                )
            except SourceParseError:
                draw_date = None

        draw_number: str | None = None
        if all_draw_matches:
            if raw_number_anchor is not None:
                ranked_draws = sorted(
                    all_draw_matches,
                    key=lambda m: (abs(m.start() - raw_number_anchor), m.start()),
                )
            else:
                ranked_draws = all_draw_matches
            for candidate in ranked_draws:
                value = candidate.group(1)
                if int(value) in range(1900, 2101):
                    continue
                draw_number = value
                break

        if code == "LOTERIA_RISARALDA" and draw_number is None:
            anchor_draw = 2967
            anchor_date = date(2026, 9, 18)
            today = datetime.now(UTC).date()
            expected_draw = anchor_draw + max(0, (today - anchor_date).days // 7)
            draw_number = str(expected_draw)
            excluded = {str(today.year), draw_number}
            if raw_number in excluded:
                for candidate in [m.group(1) for m in self._LABELED_NUMBER_RE.finditer(search_text)]:
                    if candidate not in excluded:
                        raw_number = candidate
                        break
            draw_date = (
                anchor_date + timedelta(days=(expected_draw - anchor_draw) * 7)
            ).isoformat()
            date_inferred_from_draw_schedule = True
        elif draw_date is None:
            if code != "LOTERIA_RISARALDA" or draw_number is None:
                raise SourceParseError(
                    "Traditional lottery source does not expose a recognizable date/result"
                )
            anchor_draw = 2967
            anchor_date = date(2026, 9, 18)
            draw_date = (
                anchor_date + timedelta(days=(int(draw_number) - anchor_draw) * 7)
            ).isoformat()
            date_inferred_from_draw_schedule = True
        else:
            date_inferred_from_draw_schedule = False

        metadata = {
            "raw_result": raw_number,
            "digit_count": 4,
            "source_verified": profile.verified,
        }
        if date_inferred_from_draw_schedule:
            metadata["date_inferred_from_draw_schedule"] = True

        series_value: str | None = None

        # Prefer a full labeled series (including spaced layouts) over the
        # generic one-digit prefix captured by _SERIES_RE.
        series_options: list[tuple[str, int, int]] = []
        for match in self._LABELED_RESULT_SERIES_RE.finditer(search_text):
            series_options.append((match.group(2), match.start(), 100))
        if not series_options:
            series_label = re.compile(
                r"\bserie\s*[:#-]?\s*(\d{1,3}(?:\s+\d{1,3}){0,2}|\d{1,3})\b",
                re.IGNORECASE,
            )
            for match in series_label.finditer(search_text):
                series_options.append(
                    ("".join(match.group(1).split()), match.start(), 95)
                )
        for match in self._NUMBER_BEFORE_SERIES_RE.finditer(search_text):
            series_options.append((match.group(1), match.start(), 95))
        for match in self._SPACED_SERIES_RE.finditer(search_text):
            digits = "".join(group for group in match.groups() if group is not None)
            series_options.append((digits, match.start(), 90))
        for match in self._SERIES_RE.finditer(search_text):
            series_options.append((match.group(1), match.start(), 50))

        if series_options:
            nearby = [
                item
                for item in series_options
                if raw_number_anchor is None or abs(item[1] - raw_number_anchor) <= 600
            ]
            if nearby:
                selected_series = min(
                    nearby,
                    key=lambda item: (
                        abs(item[1] - (raw_number_anchor or item[1])),
                        -item[2],
                        -len(item[0]),
                    ),
                )
                series_value = selected_series[0]

        if series_value is not None:
            metadata["series"] = series_value


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



    _CAUCA_HOME_RESULT_RE = re.compile(
        r"\bsorteo\s*[:#-]?\s*(?P<draw>\d{3,6})\b"
        r".*?\bfecha\s*[:#-]?\s*"
        r"(?P<date>\d{4}-\d{1,2}-\d{1,2})\b"
        r".*?\bpremio\s+mayor\b.*?"
        r"(?P<number>\d{4}|\d(?:\s+\d){3})\b"
        r".*?\bserie\s*[:#-]?\s*(?P<series>\d{1,4})\b",
        re.IGNORECASE | re.DOTALL,
    )

    def _parse_cauca_homepage_current_result(
        self,
        *,
        search_text: str,
        result: SourceFetchResult,
    ) -> Mapping[str, object] | None:
        matches = list(self._CAUCA_HOME_RESULT_RE.finditer(search_text))
        if not matches:
            return None

        reference_date = result.fetched_at.date()
        valid_matches = []
        for match in matches:
            try:
                draw_date = date.fromisoformat(match.group("date"))
            except ValueError:
                continue
            if draw_date > reference_date:
                continue
            raw_number = "".join(match.group("number").split())
            if len(raw_number) != 4 or not raw_number.isdigit():
                continue
            if int(raw_number) in range(1900, 2101):
                continue
            series = match.group("series")
            valid_matches.append(
                (draw_date, int(match.group("draw")), raw_number, series, match)
            )

        if not valid_matches:
            raise SourceParseError(
                "Lotería del Cauca homepage does not expose a valid "
                "current major result",
            )

        draw_date, draw_number, raw_number, series, _ = max(
            valid_matches,
            key=lambda item: (item[0], item[1]),
        )
        profile = get_traditional_source("LOTERIA_CAUCA")
        metadata = {
            "raw_result": raw_number,
            "digit_count": 4,
            "source_verified": profile.verified,
            "series": series,
            "source_format": "official_homepage_major_result_block",
        }
        return {
            "lottery_code": "LOTERIA_CAUCA",
            "draw_type": "LOTERIA_CAUCA_ORDINARY",
            "draw_number": str(draw_number),
            "draw_date": draw_date.isoformat(),
            "main_numbers": [int(raw_number)],
            "metadata": metadata,
            "source_url": result.url,
            "source_timestamp": result.fetched_at,
        }


    def _parse_risaralda_official(
        self,
        *,
        search_text: str,
        result: SourceFetchResult,
        all_number_candidates: list[tuple[str, int, int]],
    ) -> Mapping[str, object] | None:
        draw_match = re.search(
            r"\b(\d{3,6})\s*\+\s*sorteos\s+jugados\b",
            search_text,
            re.IGNORECASE,
        )
        if draw_match is None:
            return None

        unrelated_context = re.compile(
            r"\b(?:chontico|dorado|astro|miloto|baloto|revancha|"
            r"paisita|sinuano|caribeñ[ae]|cafeterito|fantastica|"
            r"antioqueñita|play\s+four|cash|motil[oó]n|pijao|"
            r"s[aá]man|culona)\b",
            re.IGNORECASE,
        )
        safe_candidates = []
        for raw, position, weight in all_number_candidates:
            if weight < 80:
                continue
            context = search_text[max(0, position - 180):position + 180]
            if unrelated_context.search(context):
                continue
            safe_candidates.append((raw, position, weight))

        # The institutional consultation layout labels the major result as
        # "Número 6731" under a separate "Premio Mayor" heading. Promote only
        # that explicitly scoped number; generic four-digit values remain
        # excluded from the official-result candidate set.
        major_heading = re.compile(r"premio\s+mayor", re.IGNORECASE)
        for match in self._LABELED_NUMBER_RE.finditer(search_text):
            context = search_text[max(0, match.start() - 140):match.start()]
            if not major_heading.search(context):
                continue
            local_context = search_text[max(0, match.start() - 180):match.end() + 180]
            if unrelated_context.search(local_context):
                continue
            safe_candidates.append((match.group(1), match.start(), 85))

        table_series: str | None = None
        if not safe_candidates:
            # The live institutional consultation is rendered as a table. Its
            # flattened HTML has the major row in the form:
            # "PREMIO MAYOR | $ ... | 6731 | 197 | PEREIRA".
            # There is no per-row "Número"/"Serie" label, so parse only the
            # row scoped by PREMIO MAYOR and stop before the next prize row.
            major_row = re.search(
                r"\bpremio\s+mayor\b(?P<body>.*?)(?=\bseco\b|$)",
                search_text,
                re.IGNORECASE,
            )
            if major_row is not None:
                body = major_row.group("body")
                result_matches = [
                    match
                    for match in self._NUMBER_RE.finditer(body)
                    if int(match.group(1)) not in range(1900, 2101)
                ]
                if result_matches:
                    selected_result = result_matches[0]
                    raw_number = selected_result.group(1)
                    raw_number_anchor = major_row.start("body") + selected_result.start()

                    # After the four-digit result, the next standalone
                    # 1-3 digit token is the series in this table layout.
                    series_tail = body[selected_result.end():]
                    series_match = re.search(
                        r"(?<!\d)(\d{1,3})(?!\d)",
                        series_tail,
                    )
                    if series_match is not None:
                        table_series = series_match.group(1)
                    safe_candidates.append((raw_number, raw_number_anchor, 90))

        if not safe_candidates:
            raise SourceParseError(
                "Risaralda official source does not expose a recognizable major result"
            )

        raw_number, raw_number_anchor, _ = max(
            safe_candidates,
            key=lambda item: (item[2], -item[1]),
        )
        draw_number = int(draw_match.group(1))
        anchor_draw = 2967
        anchor_date = date(2026, 9, 18)
        if draw_number < anchor_draw:
            raise SourceParseError(
                "Risaralda official draw counter is older than the verified anchor"
            )
        draw_date = (
            anchor_date + timedelta(days=(draw_number - anchor_draw) * 7)
        ).isoformat()

        series_options: list[tuple[str, int, int]] = []
        for match in self._LABELED_RESULT_SERIES_RE.finditer(search_text):
            series_options.append((match.group(2), match.start(), 100))
        for match in self._NUMBER_BEFORE_SERIES_RE.finditer(search_text):
            series_options.append((match.group(1), match.start(), 95))
        for match in self._SPACED_SERIES_RE.finditer(search_text):
            digits = "".join(group for group in match.groups() if group is not None)
            series_options.append((digits, match.start(), 90))
        for match in self._SERIES_RE.finditer(search_text):
            series_options.append((match.group(1), match.start(), 50))

        if table_series is not None:
            series_value = table_series
        else:
            nearby = [
                item
                for item in series_options
                if abs(item[1] - raw_number_anchor) <= 600
            ]
            if not nearby:
                raise SourceParseError(
                    "Risaralda official source does not expose the major-result series"
                )
            series_value = min(
                nearby,
                key=lambda item: (
                    abs(item[1] - raw_number_anchor),
                    -item[2],
                    -len(item[0]),
                ),
            )[0]

        profile = get_traditional_source("LOTERIA_RISARALDA")
        metadata = {
            "raw_result": raw_number,
            "digit_count": 4,
            "source_verified": profile.verified,
            "series": series_value,
            "date_inferred_from_draw_schedule": True,
            "source_format": "official_institutional_composite",
        }
        return {
            "lottery_code": "LOTERIA_RISARALDA",
            "draw_type": "LOTERIA_RISARALDA_ORDINARY",
            "draw_number": str(draw_number),
            "draw_date": draw_date,
            "main_numbers": [int(raw_number)],
            "metadata": metadata,
            "source_url": result.url,
            "source_timestamp": result.fetched_at,
        }


    def _parse_date(
        self,
        *,
        iso_date_matches: list[re.Match[str]],
        numeric_date_matches: list[re.Match[str]],
        date_matches: list[re.Match[str]],
        month_first_date_matches: list[re.Match[str]],
        flexible_textual_date_matches: list[re.Match[str]],
        reference_date: date | None = None,
        anchor_position: int | None = None,
    ) -> str:
        candidates: list[tuple[date, int]] = []

        def add_candidate(
            year: str,
            month: str,
            day: str,
            position: int,
        ) -> None:
            month_number = self._month(month)
            if month_number is None:
                month_number = (
                    month
                    if month.isdigit() and 1 <= int(month) <= 12
                    else None
                )
            if month_number is None:
                return
            try:
                parsed = date(int(year), int(month_number), int(day))
            except (TypeError, ValueError):
                return
            candidates.append((parsed, position))

        for match in iso_date_matches:
            year, month, day = match.groups()
            add_candidate(year, month, day, match.start())
        for match in numeric_date_matches:
            day, month, year = match.groups()
            add_candidate(year, month, day, match.start())
        for match in month_first_date_matches:
            add_candidate(
                match.group(3),
                match.group(1),
                match.group(2),
                match.start(),
            )
        for match in date_matches:
            add_candidate(
                match.group(3),
                match.group(2),
                match.group(1),
                match.start(),
            )
        for match in flexible_textual_date_matches:
            add_candidate(
                match.group(3),
                match.group(2),
                match.group(1),
                match.start(),
            )

        if not candidates:
            raise SourceParseError("Traditional lottery source has an unsupported month")

        past_or_today = (
            [item for item in candidates if reference_date is None or item[0] <= reference_date]
        )

        if anchor_position is not None:
            pool = past_or_today or candidates
            nearby = [
                item for item in pool
                if abs(item[1] - anchor_position) <= 600
            ]
            if nearby:
                selected = min(
                    nearby,
                    key=lambda item: (
                        abs(item[1] - anchor_position),
                        -item[0].toordinal(),
                    ),
                )
                return selected[0].isoformat()

        pool = past_or_today or candidates
        if reference_date is not None and not past_or_today:
            selected = min(pool, key=lambda item: (abs(item[1] - (anchor_position or 0)), item[0]))
        else:
            selected = max(pool, key=lambda item: (item[0], -item[1]))
        return selected[0].isoformat()


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
        if "loteriaya.com.co" in result.url.casefold():
            # Explicit secondary fallback used only when the official acta
            # endpoint cannot expose a parseable published PDF. Keep this
            # provenance distinct from the verified official source.
            html = result.content.decode("utf-8", errors="ignore")
            text = " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", html)).split())
            search_text = TraditionalLotteryHtmlParser._strip_accents(text)
            row_match = re.search(
                r"\b(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo)\s+"
                r"(\d{1,2})\s+de\s+([A-Za-z]+)\s*[|·—-]?\s*"
                r"(\d{3,6})\s*[|·—-]?\s*(\d{4})\s*[|·—-]?\s*(\d{1,4})\b",
                search_text,
                re.IGNORECASE,
            )
            if not row_match:
                raise SourceParseError(
                    "Cundinamarca secondary history does not expose the latest draw row"
                )
            day, month_name, draw_number, major, series = row_match.groups()
            year_match = re.search(r"\b(20\d{2})\b", search_text)
            if year_match is None:
                raise SourceParseError(
                    "Cundinamarca secondary history does not expose a four-digit year"
                )
            year = year_match.group(1)
            month = TraditionalLotteryHtmlParser._month(month_name)
            if month is None:
                raise SourceParseError(
                    "Cundinamarca secondary history has an unsupported month"
                )
            code = (lottery_code or self.lottery_code).upper()
            return [
                {
                    "lottery_code": code,
                    "draw_type": f"{code}_ORDINARY",
                    "draw_number": draw_number,
                    "draw_date": f"{year}-{month}-{int(day):02d}",
                    "main_numbers": [int(major)],
                    "metadata": {
                        "raw_result": major,
                        "digit_count": 4,
                        "series": series,
                        "source_verified": False,
                        "source_format": "secondary_html_history",
                        "primary_source": "official_cundinamarca_acta_pdf",
                    },
                    "source_url": result.url,
                    "source_timestamp": result.fetched_at,
                }
            ]

        if "pdf" not in result.content_type.casefold() and not result.content.startswith(
            b"%PDF"
        ):
            raise SourceParseError(
                "Cundinamarca official acta source is not a PDF document"
            )

        try:
            reader = PdfReader(BytesIO(result.content))
            extracted_pages = []
            for page in reader.pages:
                page_text = page.extract_text() or ""
                if not page_text.strip():
                    try:
                        page_text = page.extract_text(extraction_mode="layout") or ""
                    except TypeError:
                        pass
                extracted_pages.append(page_text)
            text = " ".join(extracted_pages)
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