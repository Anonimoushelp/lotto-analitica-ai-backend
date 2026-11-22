from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

import httpx

from app.sources.fetchers import SourceFetchResult
from app.sources.parsers import SourceParseError
from app.sources.provider_registry import build_traditional_lottery_components

SOURCE_URL = "https://ventas.loteriadelrisaralda.com/resultados"
MAX_RESPONSE_BYTES = 2_000_000


def parse_live_html(
    *,
    content: bytes,
    content_type: str,
    fetched_at: datetime,
    url: str = SOURCE_URL,
) -> dict[str, object]:
    """Validate one server-rendered official result without persistence."""
    if url != SOURCE_URL:
        raise ValueError("Live validation accepts only the exact official results URL")
    if "text/html" not in content_type.casefold():
        raise ValueError(f"Expected HTML, received content-type: {content_type}")
    if not content or len(content) > MAX_RESPONSE_BYTES:
        raise ValueError("Official HTML is empty or exceeds the 2 MB safety limit")

    result = SourceFetchResult(
        url=url,
        status_code=200,
        content=content,
        content_type=content_type,
        fetched_at=fetched_at,
    )
    parser, adapter = build_traditional_lottery_components("LOTERIA_RISARALDA")
    try:
        records = list(parser.parse(result))
    except SourceParseError as exc:
        raise ValueError(f"Official result HTML is incomplete or inconsistent: {exc}") from exc

    if len(records) != 1:
        raise ValueError(f"Expected exactly one major-result record, received {len(records)}")

    normalized = adapter.normalize(records[0])
    metadata = normalized.metadata
    draw_number = str(normalized.draw_number)
    draw_date = normalized.draw_date.isoformat()
    main_numbers = normalized.main_numbers
    winning_number = str(metadata.get("raw_result", ""))
    series = str(metadata.get("series", ""))

    if not draw_number.isdigit() or not 3 <= len(draw_number) <= 6:
        raise ValueError(f"Invalid explicit draw number: {draw_number!r}")
    if len(main_numbers) != 1 or not winning_number.isdigit() or len(winning_number) != 4:
        raise ValueError(f"Invalid major winning number: {winning_number!r}")
    if not series.isdigit() or len(series) != 3:
        raise ValueError(f"Invalid major prize series: {series!r}")
    if int(winning_number) != int(main_numbers[0]):
        raise ValueError("Winning number disagrees with normalized main_numbers")
    if metadata.get("date_inferred_from_draw_schedule") is not False:
        raise ValueError("Draw date must come from the explicit official result context")
    if metadata.get("source_format") != "official_sales_portal_result":
        raise ValueError("Result did not originate from the direct official sales portal")

    return {
        "source_url": url,
        "draw_number": draw_number,
        "draw_date": draw_date,
        "winning_number": winning_number,
        "series": series,
        "source_format": metadata["source_format"],
        "fetched_at": fetched_at.isoformat(),
    }


def main() -> int:
    timeout = httpx.Timeout(20.0, connect=10.0)
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            headers={"User-Agent": "LottoAnaliticaAI-RisaraldaLiveValidation/1.0"},
        ) as client:
            # Exactly one outbound request: GET to the official sales results URL.
            response = client.get(SOURCE_URL)
            if response.status_code != 200:
                raise ValueError(
                    f"Official endpoint returned HTTP {response.status_code}; "
                    "redirects and non-200 responses are not followed"
                )
            if str(response.url) != SOURCE_URL:
                raise ValueError(f"Unexpected response URL: {response.url}")
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise ValueError("Official HTML exceeds the 2 MB safety limit")
            result = parse_live_html(
                content=response.content,
                content_type=response.headers.get("content-type", ""),
                fetched_at=datetime.now(UTC),
                url=str(response.url),
            )
    except (httpx.HTTPError, ValueError) as exc:
        print(f"Risaralda live validation FAILED: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("Risaralda live validation PASSED: one GET; no fallback, database, or writes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
