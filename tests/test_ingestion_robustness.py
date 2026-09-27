from datetime import UTC, date, datetime, time

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.scheduler.draw_schedule import COLOMBIA_TZ, ScheduledDraw, due_draws
from app.services.lottery_draw_service import LotteryDrawService
from app.sources.adapters import BalotoAdapter, MiLotoAdapter, RevanchaAdapter
from app.sources.contracts import SourceAdapter
from app.sources.fetchers import SourceFetchResult
from app.sources.ingestion import SourceIngestionError, SourceIngestionPipeline

ENGINE = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=ENGINE)
LotteryDraw.__table__.create(bind=ENGINE)


def make_db():
    session = SessionLocal()
    lottery = Lottery(name="Test Lottery", code="test", country="Colombia")
    session.add(lottery)
    session.commit()
    session.refresh(lottery)
    return session, lottery


def persist(db, lottery_id, *, draw_number, draw_date, draw_type="MILOTO"):
    return LotteryDrawService.create_draw(
        db=db, lottery_id=lottery_id, draw_number=draw_number, draw_date=draw_date,
        main_numbers=[10, 15, 31, 33, 39], draw_type=draw_type,
        source="test", source_url="https://example.test/results",
        validation_json={"format_valid": True, "date_valid": True},
    )


def teardown_db(db):
    db.close()
    cleanup = SessionLocal()
    cleanup.query(LotteryDraw).delete()
    cleanup.query(Lottery).delete()
    cleanup.commit()
    cleanup.close()


def test_duplicate_draw_number_returns_conflict():
    db, lottery = make_db()
    try:
        persist(db, lottery.id, draw_number="609", draw_date=date(2026, 9, 18))
        with pytest.raises(HTTPException) as exc:
            persist(db, lottery.id, draw_number="609", draw_date=date(2026, 9, 19))
        assert exc.value.status_code == 409
        assert exc.value.detail == "Draw number already exists for this lottery and draw type"
    finally:
        teardown_db(db)


def test_duplicate_draw_date_returns_conflict():
    db, lottery = make_db()
    try:
        persist(db, lottery.id, draw_number="609", draw_date=date(2026, 9, 18))
        with pytest.raises(HTTPException) as exc:
            persist(db, lottery.id, draw_number="610", draw_date=date(2026, 9, 18))
        assert exc.value.status_code == 409
        assert exc.value.detail == "Draw date already exists for this lottery and draw type"
    finally:
        teardown_db(db)


def test_same_date_and_number_are_isolated_by_draw_type():
    db, lottery = make_db()
    try:
        first = persist(db, lottery.id, draw_number="609", draw_date=date(2026, 9, 18), draw_type="BALOTO")
        second = persist(db, lottery.id, draw_number="609", draw_date=date(2026, 9, 18), draw_type="REVANCHA")
        assert first.id != second.id
        assert first.draw_type == "BALOTO"
        assert second.draw_type == "REVANCHA"
    finally:
        teardown_db(db)


def test_not_published_is_outside_scheduler_window():
    schedule = ScheduledDraw("TEST", "DIA", time(13, 0), tolerance_minutes=30)
    assert due_draws(datetime(2026, 9, 21, 12, 59, tzinfo=COLOMBIA_TZ), schedules=(schedule,)) == []
    assert due_draws(datetime(2026, 9, 21, 13, 31, tzinfo=COLOMBIA_TZ), schedules=(schedule,)) == []


def test_holiday_can_skip_a_draw_entirely():
    schedule = ScheduledDraw(
        "TEST", "NOCHE", time(20, 0), weekdays=frozenset(range(7)),
        tolerance_minutes=30, skip_on_holiday=True,
    )
    holiday = frozenset({date(2026, 9, 21)})
    assert due_draws(
        datetime(2026, 9, 21, 20, 10, tzinfo=COLOMBIA_TZ),
        schedules=(schedule,), holiday_dates=holiday,
    ) == []


class FailingFetcher:
    def fetch(self, url: str) -> SourceFetchResult:
        raise RuntimeError("connection timeout")


class StaticParser:
    def __init__(self, payload):
        self.payload = payload

    def parse(self, result):
        return [self.payload]


class FixtureAdapter(SourceAdapter):
    spec = MiLotoAdapter().spec

    def normalize(self, payload):
        if "draw_date" not in payload:
            raise ValueError("draw_date is required")
        return payload


def test_ingestion_classifies_fetch_failure_as_source_extraction_error():
    pipeline = SourceIngestionPipeline(fetcher=FailingFetcher(), parser=StaticParser({}), adapter=MiLotoAdapter())
    with pytest.raises(SourceIngestionError, match="Source extraction failed"):
        pipeline.run("https://example.test/results")


def test_ingestion_classifies_normalization_failure_separately():
    class SuccessfulFetcher:
        def fetch(self, url: str) -> SourceFetchResult:
            return SourceFetchResult(
                url=url, status_code=200, content=b"ignored", content_type="application/json",
                fetched_at=datetime(2026, 9, 21, 16, 0, tzinfo=UTC),
            )

    pipeline = SourceIngestionPipeline(
        fetcher=SuccessfulFetcher(), parser=StaticParser({"draw_number": "609"}), adapter=FixtureAdapter()
    )
    with pytest.raises(SourceIngestionError, match="Source ingestion failed"):
        pipeline.run("https://example.test/results")


def test_full_ingestion_duplicate_is_rejected_at_persistence_boundary():
    db, lottery = make_db()
    try:
        payload = {
            "draw_number": "609",
            "draw_date": date(2026, 9, 18),
            "main_numbers": [10, 15, 31, 33, 39],
            "draw_type": "MILOTO",
        }
        pipeline = SourceIngestionPipeline(
            fetcher=SuccessfulPayloadFetcher(payload),
            parser=StaticParser(payload),
            adapter=MiLotoAdapter(),
        )
        records = pipeline.run("https://example.test/results")
        first = records[0]
        persist(
            db,
            lottery.id,
            draw_number=first.draw_number,
            draw_date=first.draw_date,
            draw_type=first.draw_type,
        )
        with pytest.raises(HTTPException) as exc:
            persist(
                db,
                lottery.id,
                draw_number=first.draw_number,
                draw_date=first.draw_date,
                draw_type=first.draw_type,
            )
        assert exc.value.status_code == 409
        assert exc.value.detail == "Draw number already exists for this lottery and draw type"
    finally:
        teardown_db(db)


class SuccessfulPayloadFetcher:
    def __init__(self, payload):
        self.payload = payload

    def fetch(self, url: str) -> SourceFetchResult:
        return SourceFetchResult(
            url=url,
            status_code=200,
            content=b"ignored",
            content_type="application/json",
            fetched_at=datetime(2026, 9, 21, 16, 0, tzinfo=UTC),
        )


def test_parser_failure_is_classified_as_extraction_error():
    class FailingParser:
        def parse(self, result):
            raise ValueError("unsupported source format")

    pipeline = SourceIngestionPipeline(
        fetcher=SuccessfulPayloadFetcher({}),
        parser=FailingParser(),
        adapter=MiLotoAdapter(),
    )
    with pytest.raises(SourceIngestionError, match="Source extraction failed"):
        pipeline.run("https://example.test/results")


def test_same_ingestion_date_can_persist_for_different_draw_types():
    db, lottery = make_db()
    try:
        baloto = {
            "draw_number": "609",
            "draw_date": date(2026, 9, 18),
            "main_numbers": [10, 15, 31, 33, 39],
            "draw_type": "BALOTO",
        }
        revancha = {
            **baloto,
            "draw_type": "REVANCHA",
        }
        first = SourceIngestionPipeline(
            fetcher=SuccessfulPayloadFetcher(baloto),
            parser=StaticParser(baloto),
            adapter=BalotoAdapter(),
        ).run("https://example.test/baloto")[0]
        second = SourceIngestionPipeline(
            fetcher=SuccessfulPayloadFetcher(revancha),
            parser=StaticParser(revancha),
            adapter=RevanchaAdapter(),
        ).run("https://example.test/revancha")[0]
        saved_first = persist(
            db,
            lottery.id,
            draw_number=first.draw_number,
            draw_date=first.draw_date,
            draw_type="BALOTO",
        )
        saved_second = persist(
            db,
            lottery.id,
            draw_number=second.draw_number,
            draw_date=second.draw_date,
            draw_type="REVANCHA",
        )
        assert saved_first.id != saved_second.id
        assert {saved_first.draw_type, saved_second.draw_type} == {"BALOTO", "REVANCHA"}
    finally:
        teardown_db(db)


def test_holiday_override_uses_holiday_time_instead_of_skipping():
    schedule = ScheduledDraw(
        "TEST",
        "NOCHE",
        time(20, 0),
        weekdays=frozenset(range(7)),
        tolerance_minutes=30,
        holiday_times=(time(21, 0),),
        skip_on_holiday=True,
    )
    holiday = frozenset({date(2026, 9, 21)})
    assert due_draws(
        datetime(2026, 9, 21, 20, 10, tzinfo=COLOMBIA_TZ),
        schedules=(schedule,),
        holiday_dates=holiday,
    ) == []
    assert due_draws(
        datetime(2026, 9, 21, 21, 10, tzinfo=COLOMBIA_TZ),
        schedules=(schedule,),
        holiday_dates=holiday,
    ) == [schedule]
