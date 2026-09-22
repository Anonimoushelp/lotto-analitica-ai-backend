from datetime import UTC, datetime

import pytest

from app.sources.contracts import RawDrawRecord
from app.sources.fetchers import SourceFetchResult
from app.sources.ingestion import SourceIngestionPipeline
from app.sources.provider_registry import (
    build_html_provider_parser,
    build_provider_components,
)


@pytest.mark.parametrize(
    ("lottery_code", "payload"),
    [
        (
            "ANTIOQUENITA",
            {
                "tipo": "ANTIOQUENITA_1",
                "sorteo": 1,
                "fecha": "2026-09-20",
                "resultado": "0153",
            },
        ),
        (
            "CHONTICO",
            {
                "tipo": "CHONTICO_NOCHE",
                "sorteo": 2,
                "fecha": "2026-09-20",
                "resultado": "2958",
            },
        ),
        (
            "DORADO",
            {
                "tipo": "DORADO_TARDE",
                "sorteo": 3,
                "fecha": "2026-09-20",
                "resultado": "0982",
                "additional_value": 7,
            },
        ),
        (
            "CAFETERITO",
            {
                "tipo": "CAFETERITO_NOCHE",
                "sorteo": 4,
                "fecha": "2026-09-20",
                "resultado": "3312",
            },
        ),
        (
            "PAISITA",
            {
                "tipo": "PAISITA_NOCHE",
                "sorteo": 5,
                "fecha": "2026-09-20",
                "resultado": "3946",
                "animal": "Caballo",
            },
        ),
        (
            "FANTASTICA",
            {
                "tipo": "FANTASTICA_DIA",
                "sorteo": 6,
                "fecha": "2026-09-21",
                "resultado": "0512",
                "additional_value": 8,
            },
        ),
    ],
)
def test_four_digit_provider_is_wired_into_ingestion(
    lottery_code: str, payload: dict
) -> None:
    parser, adapter = build_provider_components(lottery_code)
    fetched_at = datetime(2026, 9, 21, 16, 0, tzinfo=UTC)

    class FakeFetcher:
        def fetch(self, url: str) -> SourceFetchResult:
            import json

            return SourceFetchResult(
                url=url,
                status_code=200,
                content=json.dumps({"results": [payload]}).encode(),
                content_type="application/json",
                fetched_at=fetched_at,
            )

    pipeline = SourceIngestionPipeline(
        fetcher=FakeFetcher(),
        parser=parser,
        adapter=adapter,
    )
    records = pipeline.run("https://example.test/results")

    assert len(records) == 1
    assert isinstance(records[0], RawDrawRecord)
    assert records[0].lottery_code == lottery_code
    assert records[0].metadata["raw_result"] == payload["resultado"]
    assert records[0].metadata["digit_count"] == 4
    assert records[0].source_url == "https://example.test/results"
    assert records[0].source_timestamp == fetched_at


def test_provider_registry_rejects_unknown_lottery() -> None:
    with pytest.raises(KeyError, match="No four-digit provider components"):
        build_provider_components("UNKNOWN")


@pytest.mark.parametrize(
    ("lottery_code", "chance", "date_text", "result_text", "expected_draw_type"),
    [
        ("ANTIOQUENITA", "Antioqueñita 1", "20 de Septiembre del 2026", "0153", "ANTIOQUENITA_1"),
        ("CAFETERITO", "Cafeterito Noche", "20 de Septiembre del 2026", "3312", "CAFETERITO_NOCHE"),
        ("CHONTICO", "Super Chontico Noche", "20 de Septiembre del 2026", "4531", "CHONTICO_SUPER_NOCHE"),
        ("DORADO", "Dorado Mañana", "21 de Septiembre del 2026", "7279", "DORADO_DIA"),
    ],
)
def test_html_provider_extraction_preserves_source_without_draw_number(
    lottery_code: str,
    chance: str,
    date_text: str,
    result_text: str,
    expected_draw_type: str,
) -> None:
    fetched_at = datetime(2026, 9, 21, 16, 0, tzinfo=UTC)
    html = (
        "<html><body><table>"
        "<thead><tr><th>Chance</th><th>Fecha</th><th>Resultado</th></tr></thead>"
        f"<tbody><tr><td>{chance}</td><td>{date_text}</td><td>{result_text}</td></tr></tbody>"
        "</table></body></html>"
    )

    class FakeFetcher:
        def fetch(self, url: str) -> SourceFetchResult:
            return SourceFetchResult(
                url=url,
                status_code=200,
                content=html.encode("utf-8"),
                content_type="text/html",
                fetched_at=fetched_at,
            )

    parser = build_html_provider_parser(lottery_code)
    pipeline = SourceIngestionPipeline(
        fetcher=FakeFetcher(),
        parser=parser,
        adapter=build_provider_components(lottery_code)[1],
    )
    extracted = pipeline.extract("https://example.test/results")

    assert len(extracted) == 1
    assert extracted[0]["draw_type"] == expected_draw_type
    assert extracted[0]["number"] == result_text
    assert extracted[0]["draw_date"] == "2026-09-20"
    assert "draw_number" not in extracted[0]
    assert extracted[0]["source_url"] == "https://example.test/results"
    assert extracted[0]["source_timestamp"] == fetched_at

    records = pipeline.run("https://example.test/results")
    assert len(records) == 1
    assert records[0].draw_number is None
    assert records[0].draw_date.isoformat() == ("2026-09-21" if lottery_code == "DORADO" else "2026-09-20")
    assert records[0].main_numbers == [int(result_text)]


def test_html_provider_registry_rejects_unknown_lottery() -> None:
    with pytest.raises(KeyError, match="No HTML provider parser configured"):
        build_html_provider_parser("UNKNOWN")
