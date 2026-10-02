from datetime import UTC, date, datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.services.lottery_draw_service import LotteryDrawService
from app.sources.contracts import RawDrawRecord

ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=ENGINE)
LotteryDraw.__table__.create(bind=ENGINE)

def _record() -> RawDrawRecord:
    return RawDrawRecord(
        lottery_code="MILOTO",
        draw_type="MILOTO",
        draw_number="IDEMP-001",
        draw_date=date(2026, 9, 30),
        draw_time=None,
        main_numbers=[1, 7, 12, 23, 35],
        bonus_numbers=None,
        source_name="Official Test Source",
        source_url="https://example.test/results",
        source_timestamp=datetime(2026, 9, 30, 23, 0, tzinfo=UTC),
        metadata={"raw_result": "0001", "digit_count": 4},
    )

def test_exact_repeat_keeps_one_canonical_row():
    db = SessionLocal()
    db.add(Lottery(name="MiLoto", code="miloto", country="Colombia"))
    db.commit()
    record = _record()

    first = LotteryDrawService.persist_raw_record(db=db, record=record)
    first_id = first.id
    first_count = db.scalar(select(func.count()).select_from(LotteryDraw))

    second = LotteryDrawService.persist_raw_record(db=db, record=record)
    second_count = db.scalar(select(func.count()).select_from(LotteryDraw))

    assert first_count == 1
    assert second.id == first_id
    assert second_count == 1
    db.close()