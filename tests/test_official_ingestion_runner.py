from datetime import date

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.ingestion_run import IngestionRun
from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.services.official_ingestion_runner import OfficialIngestionRunner
from app.sources.base import NormalizedDraw, SourceValidationError

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=engine)
LotteryDraw.__table__.create(bind=engine)
IngestionRun.__table__.create(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        cleanup = SessionLocal()
        cleanup.execute(delete(IngestionRun))
        cleanup.execute(delete(LotteryDraw))
        cleanup.execute(delete(Lottery))
        cleanup.commit()
        cleanup.close()


class FakeAdapter:
    lottery_code = "AUTOMATED"

    def __init__(self, fail=False):
        self.fail = fail

    def fetch(self, client=None):
        if self.fail:
            raise SourceValidationError("source unavailable")
        return NormalizedDraw(
            lottery_code=self.lottery_code,
            draw_number="AUTO-001",
            draw_date=date(2026, 9, 20),
            main_numbers=[1, 2, 3],
            bonus_numbers=None,
            metadata_json={"test": True},
            source="test",
        )


def test_run_source_records_success_and_draw(db):
    lottery = Lottery(code="AUTOMATED", name="Automated", country="Test")
    db.add(lottery)
    db.commit()

    run = OfficialIngestionRunner.run_source(db, "test", FakeAdapter)

    assert run.status == "success"
    assert run.draw_id is not None
    assert run.finished_at is not None
    assert run.details["draw_number"] == "AUTO-001"


def test_run_source_records_failure_without_partial_draw(db):
    lottery = Lottery(code="AUTOMATED", name="Automated", country="Test")
    db.add(lottery)
    db.commit()

    run = OfficialIngestionRunner.run_source(
        db,
        "test",
        lambda: FakeAdapter(fail=True),
    )

    assert run.status == "failed"
    assert "source unavailable" in run.error_message
    assert db.query(LotteryDraw).count() == 0


def test_run_source_is_idempotent_on_existing_draw(db):
    lottery = Lottery(code="AUTOMATED", name="Automated", country="Test")
    db.add(lottery)
    db.commit()

    first = OfficialIngestionRunner.run_source(db, "test", FakeAdapter)
    second = OfficialIngestionRunner.run_source(db, "test", FakeAdapter)

    assert first.status == "success"
    assert second.status == "success"
    assert first.draw_id == second.draw_id
    assert db.query(LotteryDraw).count() == 1
    assert db.query(IngestionRun).count() == 2


def test_runner_skips_when_global_lock_is_held(monkeypatch):
    class LockedConnection:
        def scalar(self, *args, **kwargs):
            return False

        def close(self):
            pass

    class LockedEngine:
        def connect(self):
            return LockedConnection()

    class FakeDb:
        def add(self, obj):
            self.obj = obj

        def commit(self):
            pass

    monkeypatch.setattr(
        "app.services.official_ingestion_runner.engine",
        LockedEngine(),
    )
    run = OfficialIngestionRunner.run_all(FakeDb())

    assert run[0].status == "skipped"
    assert run[0].source == "all"
