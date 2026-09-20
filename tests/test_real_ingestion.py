from datetime import date

import pytest

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.draw_result import DrawResult
from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.sources.contracts import SourceDraw, SourceMetadata
from app.sources.ingestion import build_idempotency_key
from app.sources.persistence import ingest_and_persist


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=engine)
LotteryDraw.__table__.create(bind=engine)
DrawResult.__table__.create(bind=engine)


def db_session():
    return TestingSessionLocal()


class FixtureAdapter:
    source_id = "fixture-provider"

    def __init__(self, draws):
        self._draws = draws

    def fetch_draws(self):
        return self._draws


@pytest.fixture

def db():
    session = db_session()
    try:
        yield session
    finally:
        session.close()
        cleanup = db_session()
        cleanup.execute(delete(DrawResult))
        cleanup.execute(delete(LotteryDraw))
        cleanup.execute(delete(Lottery))
        cleanup.commit()
        cleanup.close()


def seed_lottery(db):
    lottery = Lottery(
        code="REAL-TEST",
        name="Real Ingestion Test",
        country="Colombia",
        modality_code="lotto",
        timezone="America/Bogota",
    )
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    return lottery


def make_draw(value="12"):
    return SourceDraw(
        draw_number="D-REAL-001",
        draw_date=date(2026, 9, 20),
        groups={"main": [value, "34", "56"]},
        metadata=SourceMetadata(
            provider="fixture-provider",
            source_type="fixture",
            reference="fixture://draw/D-REAL-001",
        ),
        raw_payload={"number": value},
    )


def test_idempotency_key_ignores_result_payload_changes():
    first = make_draw("12")
    second = make_draw("13")

    assert build_idempotency_key("fixture-provider", first) == build_idempotency_key(
        "fixture-provider", second
    )


def test_ingest_and_persist_is_idempotent(db):
    lottery = seed_lottery(db)
    adapter = FixtureAdapter([make_draw()])

    first = ingest_and_persist(db, lottery.id, adapter)
    second = ingest_and_persist(db, lottery.id, adapter)

    assert first.created == 1
    assert first.updated == 0
    assert first.skipped == 0
    assert second.created == 0
    assert second.updated == 0
    assert second.skipped == 1


def test_ingest_and_persist_updates_existing_source_draw(db):
    lottery = seed_lottery(db)
    ingest_and_persist(db, lottery.id, FixtureAdapter([make_draw("12")]))

    result = ingest_and_persist(db, lottery.id, FixtureAdapter([make_draw("13")]))

    assert result.created == 0
    assert result.updated == 1
    draw = db.query(lottery.draws.property.mapper.class_).one()
    assert [item.value for item in draw.results] == ["13", "34", "56"]
