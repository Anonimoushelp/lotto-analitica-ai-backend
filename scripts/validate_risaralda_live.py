from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sources.fetchers import (
    RisaraldaOfficialSourceFetcher,
    SourceFetchError,
    SourceFetchResult,
)
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
    try:
        # Strict mode makes exactly one GET to the sales portal: no redirects
        # and no institutional fallback requests are permitted in this workflow.
        fetcher = RisaraldaOfficialSourceFetcher(
            timeout=20.0,
            allowed_hosts={"ventas.loteriadelrisaralda.com"},
            allow_institutional_fallback=False,
            follow_redirects=False,
        )
        result = fetcher.fetch(SOURCE_URL)
        if result.url != SOURCE_URL or result.status_code != 200:
            raise ValueError(
                f"Unexpected official response: HTTP {result.status_code} at {result.url}"
            )
        try:
            parsed = parse_live_html(
                content=result.content,
                content_type=result.content_type,
                fetched_at=result.fetched_at,
                url=result.url,
            )
        except ValueError:
            visible_text = " ".join(
                html.unescape(re.sub(r"<[^>]+>", " ", result.content.decode("utf-8", errors="replace"))).split()
            )
            print(f"Official response diagnostic excerpt: {visible_text[:3000]}", file=sys.stderr)
            raise
    except (SourceFetchError, ValueError) as exc:
        print(f"Risaralda live validation FAILED: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(parsed, ensure_ascii=False, indent=2))
    print("Risaralda live validation PASSED: one GET to the official portal; no fallback, database, or writes.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
