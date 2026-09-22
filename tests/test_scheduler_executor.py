from datetime import datetime
from types import SimpleNamespace

import pytest

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
            fetched_at=datetime(2026, 9, 25, 12, 0),
        )


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True


def test_controlled_executor_rejects_unverified_source():
    executor = ControlledIngestionExecutor(fetcher=FakeFetcher(""))
    with pytest.raises(RuntimeError, match="not verified"):
        executor("LOTERIA_META", "LOTERIA_META_ORDINARY")


def test_controlled_executor_extracts_and_persists_verified_result(monkeypatch):
    html = """
    <html><body>
    Sorteo 1234
    25 de septiembre de 2026
    Resultado: 0042
    Serie: 17
    </body></html>
    """

    session = FakeSession()

    class FakeDb:
        def scalar(self, _statement):
            return SimpleNamespace(id=77)

    session_factory = lambda: FakeDb()

    captured = {}

    def fake_create_draw(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id=501, draw_date=kwargs["draw_date"])

    monkeypatch.setattr(
        "app.scheduler.executor.LotteryDrawService.create_draw",
        fake_create_draw,
    )

    executor = ControlledIngestionExecutor(
        session_factory=session_factory,
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
