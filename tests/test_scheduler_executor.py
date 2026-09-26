from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.scheduler.executor import ControlledIngestionExecutor
from app.sources.fetchers import SourceFetchResult


class FakeFetcher:
    def __init__(self, content: str) -> None:
        self.content = content

    def fetch(self, url: str) -> SourceFetchResult:
        return SourceFetchResult(
            url=url,
            status_code=200,
            content=self.content.encode(),
            content_type="text/html",
            fetched_at=datetime(2026, 9, 25, 12, 0, tzinfo=UTC),
        )


class FakeDb:
    def scalar(self, _statement):
        return SimpleNamespace(id=77)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None


def test_controlled_executor_rejects_unverified_source():
    executor = ControlledIngestionExecutor(fetcher=FakeFetcher(""))
    with pytest.raises(RuntimeError, match="not verified"):
        executor("LOTERIA_META", "LOTERIA_META_ORDINARY")


def test_controlled_executor_rejects_empty_source_result(monkeypatch):
    class EmptyPipeline:
        def __init__(self, **_kwargs):
            pass

        def run(self, _url):
            return []

    monkeypatch.setattr("app.scheduler.executor.SourceIngestionPipeline", EmptyPipeline)
    executor = ControlledIngestionExecutor(fetcher=FakeFetcher(""))
    with pytest.raises(RuntimeError, match="No draw record extracted"):
        executor("LOTERIA_RISARALDA", "LOTERIA_RISARALDA_ORDINARY")


def test_controlled_executor_rejects_missing_draw_type(monkeypatch):
    record = SimpleNamespace(draw_type="OTHER_DRAW")

    class Pipeline:
        def __init__(self, **_kwargs):
            pass

        def run(self, _url):
            return [record]

    monkeypatch.setattr("app.scheduler.executor.SourceIngestionPipeline", Pipeline)
    executor = ControlledIngestionExecutor(fetcher=FakeFetcher(""))
    with pytest.raises(RuntimeError, match="no record"):
        executor("LOTERIA_RISARALDA", "LOTERIA_RISARALDA_ORDINARY")


def test_controlled_executor_rejects_multiple_matching_records(monkeypatch):
    record = SimpleNamespace(draw_type="LOTERIA_RISARALDA_ORDINARY")

    class MultiplePipeline:
        def __init__(self, **_kwargs):
            pass

        def run(self, _url):
            return [record, record]

    monkeypatch.setattr("app.scheduler.executor.SourceIngestionPipeline", MultiplePipeline)
    executor = ControlledIngestionExecutor(fetcher=FakeFetcher(""))
    with pytest.raises(RuntimeError, match="multiple records"):
        executor("LOTERIA_RISARALDA", "LOTERIA_RISARALDA_ORDINARY")


def test_controlled_executor_maps_duplicate_conflict(monkeypatch):
    html = """
    <html><body>
    Sorteo 1234
    25 de septiembre de 2026
    Resultado: 0042
    Serie: 17
    </body></html>
    """

    def duplicate_create_draw(**_kwargs):
        raise HTTPException(status_code=409, detail="Draw date already exists")

    monkeypatch.setattr(
        "app.scheduler.executor.LotteryDrawService.create_draw",
        duplicate_create_draw,
    )

    executor = ControlledIngestionExecutor(
        session_factory=lambda: FakeDb(),
        fetcher=FakeFetcher(html),
    )
    with pytest.raises(HTTPException) as exc_info:
        executor("LOTERIA_RISARALDA", "LOTERIA_RISARALDA_ORDINARY")
    assert exc_info.value.status_code == 409


def test_controlled_executor_extracts_and_persists_verified_result(monkeypatch):
    html = """
    <html><body>
    Sorteo 1234
    25 de septiembre de 2026
    Resultado: 0042
    Serie: 17
    </body></html>
    """

    captured = {}

    def fake_create_draw(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=501, draw_date=kwargs["draw_date"])

    monkeypatch.setattr(
        "app.scheduler.executor.LotteryDrawService.create_draw",
        fake_create_draw,
    )

    executor = ControlledIngestionExecutor(
        session_factory=lambda: FakeDb(),
        fetcher=FakeFetcher(html),
    )
    message = executor("LOTERIA_RISARALDA", "LOTERIA_RISARALDA_ORDINARY")

    assert "draw_id=501" in message
    assert captured["lottery_id"] == 77
    assert captured["draw_number"] == "1234"
    assert captured["draw_date"].isoformat() == "2026-09-25"
    assert captured["main_numbers"] == [42]
    assert captured["draw_type"] == "LOTERIA_RISARALDA_ORDINARY"
    assert captured["metadata_json"]["raw_result"] == "0042"
    assert captured["metadata_json"]["series"] == "17"
    assert captured["source_url"].endswith("/resultados")



def test_controlled_executor_uses_profile_fetcher(monkeypatch):
    captured = {}

    class Pipeline:
        def __init__(self, **kwargs):
            captured["fetcher"] = kwargs["fetcher"]

        def run(self, _url):
            return [
                SimpleNamespace(
                    draw_type="LOTERIA_CUNDINAMARCA_ORDINARY",
                    draw_number="4821",
                    draw_date=datetime(2026, 9, 21, tzinfo=UTC).date(),
                    draw_time=None,
                    main_numbers=[5341],
                    bonus_numbers=[],
                    source_name="Lotería de Cundinamarca — resultados",
                    source_url="https://www.loteriadecundinamarca.com.co/",
                    source_timestamp=datetime(2026, 9, 25, tzinfo=UTC),
                    metadata={"series": "078", "raw_result": "5341"},
                )
            ]

    monkeypatch.setattr("app.scheduler.executor.SourceIngestionPipeline", Pipeline)
    monkeypatch.setattr(
        "app.scheduler.executor.LotteryDrawService.create_draw",
        lambda **kwargs: SimpleNamespace(id=900, draw_date=kwargs["draw_date"]),
    )

    executor = ControlledIngestionExecutor(session_factory=lambda: FakeDb())
    executor("LOTERIA_CUNDINAMARCA", "LOTERIA_CUNDINAMARCA_ORDINARY")

    from app.sources.fetchers import CundinamarcaActaSourceFetcher

    assert isinstance(captured["fetcher"], CundinamarcaActaSourceFetcher)
