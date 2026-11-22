from datetime import UTC, datetime

import pytest

from scripts.validate_risaralda_live import SOURCE_URL, parse_live_html


FETCHED_AT = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


def _html(
    *,
    draw: str = "Sorteo No. 2975",
    date: str = "viernes, 13 de noviembre de 2026",
    number: str = "8362",
    series: str = "118",
) -> bytes:
    return (
        "<html><body>"
        f"<h1>{draw}</h1><p>{date}</p>"
        f"<h2>Premio mayor</h2><span>{number}</span>"
        f"<p>Serie {series}</p>"
        "</body></html>"
    ).encode()


def test_live_validator_accepts_consistent_explicit_official_result():
    result = parse_live_html(
        content=_html(),
        content_type="text/html; charset=utf-8",
        fetched_at=FETCHED_AT,
    )

    assert result["source_url"] == SOURCE_URL
    assert result["draw_number"] == "2975"
    assert result["draw_date"] == "2026-11-13"
    assert result["winning_number"] == "8362"
    assert result["series"] == "118"
    assert result["source_format"] == "official_sales_portal_result"


@pytest.mark.parametrize(
    "content",
    [
        b"<html><body><div id='app'></div><script>hydrate()</script></body></html>",
        b"<html><body>Loading results...</body></html>",
        b"<html><body>Premio mayor 8362 Serie 118</body></html>",
    ],
)
def test_live_validator_rejects_javascript_shell_or_missing_explicit_draw(content):
    with pytest.raises(ValueError, match="incomplete or inconsistent"):
        parse_live_html(
            content=content,
            content_type="text/html; charset=utf-8",
            fetched_at=FETCHED_AT,
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"series": "18"}, "three-digit major-result series"),
        ({"series": "1188"}, "three-digit major-result series"),
        ({"number": "83"}, "recognizable major result"),
        ({"draw": "Sorteo No. 2977", "date": "viernes, 27 de noviembre de 2026"},
         "future relative to source fetch time"),
        ({"draw": "Sorteo No. 2975", "date": "martes, 17 de noviembre de 2026"},
         None),
    ],
)
def test_live_validator_rejects_inconsistent_official_fields(kwargs, message):
    content = _html(**kwargs)
    if message is None:
        # The fields are internally valid and the parser must preserve them;
        # this case guards against a hard-coded expectation of draw 2975.
        result = parse_live_html(
            content=content,
            content_type="text/html; charset=utf-8",
            fetched_at=FETCHED_AT,
        )
        assert result["draw_date"] == "2026-11-17"
        return

    with pytest.raises(ValueError, match="incomplete or inconsistent"):
        parse_live_html(
            content=content,
            content_type="text/html; charset=utf-8",
            fetched_at=FETCHED_AT,
        )


def test_live_validator_rejects_non_html_content():
    with pytest.raises(ValueError, match="Expected HTML"):
        parse_live_html(
            content=b"{}",
            content_type="application/json",
            fetched_at=FETCHED_AT,
        )


def test_live_validator_rejects_any_url_other_than_official_endpoint():
    with pytest.raises(ValueError, match="exact official results URL"):
        parse_live_html(
            content=_html(),
            content_type="text/html; charset=utf-8",
            fetched_at=FETCHED_AT,
            url="https://loteriadelrisaralda.com/",
        )


def test_live_validator_rejects_oversized_html_response():
    with pytest.raises(ValueError, match="exceeds the 2 MB safety limit"):
        parse_live_html(
            content=b"x" * (2_000_001),
            content_type="text/html; charset=utf-8",
            fetched_at=FETCHED_AT,
        )
