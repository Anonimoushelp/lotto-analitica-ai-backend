from datetime import UTC, datetime

import pytest

from app.sources.adapters import MiLotoAdapter
from app.sources.contracts import RawDrawRecord
from app.sources.fetchers import HttpSourceFetcher, SourceFetchResult
from app.sources.ingestion import SourceIngestionError, SourceIngestionPipeline
from app.sources.parsers import JsonSourceParser, SourceParseError


def test_json_source_parser_returns_record_list() -> None:
    result = SourceFetchResult(
        url="https://example.test/results.json",
        status_code=200,
        content=b'{"results":[{"draw_number":609,"draw_date":"2026-09-18","main_numbers":[10,15,31,33,39]}]}',
        content_type="application/json",
        fetched_at=datetime.now(UTC),
    )

    records = list(JsonSourceParser(records_key="results").parse(result))

    assert records == [
        {
            "draw_number": 609,
            "draw_date": "2026-09-18",
            "main_numbers": [10, 15, 31, 33, 39],
        }
    ]


def test_json_source_parser_rejects_invalid_payload() -> None:
    result = SourceFetchResult(
        url="https://example.test/results.json",
        status_code=200,
        content=b"not-json",
        content_type="application/json",
        fetched_at=datetime.now(UTC),
    )

    with pytest.raises(SourceParseError):
        list(JsonSourceParser().parse(result))


def test_ingestion_pipeline_keeps_fetch_parse_and_normalize_separate() -> None:
    class FakeFetcher:
        def fetch(self, url: str) -> SourceFetchResult:
            assert url == "https://example.test/miloto"
            return SourceFetchResult(
                url=url,
                status_code=200,
                content=b"{}",
                content_type="application/json",
                fetched_at=datetime.now(UTC),
            )

    class FakeParser:
        def parse(self, result: SourceFetchResult) -> list[dict]:
            assert result.status_code == 200
            return [
                {
                    "draw_number": 609,
                    "draw_date": "2026-09-18",
                    "main_numbers": [10, 15, 31, 33, 39],
                }
            ]

    pipeline = SourceIngestionPipeline(
        fetcher=FakeFetcher(),
        parser=FakeParser(),
        adapter=MiLotoAdapter(),
    )

    records = pipeline.run("https://example.test/miloto")

    assert len(records) == 1
    assert isinstance(records[0], RawDrawRecord)
    assert records[0].lottery_code == "MILOTO"
    assert records[0].draw_number == "609"


def test_ingestion_pipeline_wraps_fetch_errors() -> None:
    class FailingFetcher:
        def fetch(self, url: str) -> SourceFetchResult:
            raise RuntimeError("network unavailable")

    class UnusedParser:
        def parse(self, result: SourceFetchResult) -> list[dict]:
            raise AssertionError("parser must not run")

    pipeline = SourceIngestionPipeline(
        fetcher=FailingFetcher(),
        parser=UnusedParser(),
        adapter=MiLotoAdapter(),
    )

    with pytest.raises(SourceIngestionError, match="MILOTO"):
        pipeline.run("https://example.test/miloto")


def test_http_fetcher_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValueError, match="timeout"):
        HttpSourceFetcher(timeout=0)
