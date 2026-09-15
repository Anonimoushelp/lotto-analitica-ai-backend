from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier, Thread

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw


@pytest.fixture
def concurrency_session_factory(tmp_path: Path):
    database_path = tmp_path / "concurrency.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 10},
        poolclass=NullPool,
    )
    Lottery.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        Lottery.metadata.drop_all(bind=engine)
        engine.dispose()


def _seed_lottery(factory):
    session = factory()
    try:
        lottery = Lottery(name="Concurrent Test", code="CONC-001", country="CO")
        session.add(lottery)
        session.commit()
        return lottery.id
    finally:
        session.close()


def test_concurrent_unique_draw_number_allows_at_most_one_persisted_row(
    concurrency_session_factory,
):
    lottery_id = _seed_lottery(concurrency_session_factory)
    barrier = Barrier(2)
    outcomes = []

    def worker():
        session = concurrency_session_factory()
        try:
            barrier.wait()
            draw = LotteryDraw(
                lottery_id=lottery_id,
                draw_number="RACE-001",
                draw_date=datetime(2026, 1, 1, tzinfo=UTC),
                main_numbers=[1, 2, 3, 4, 5],
                source="concurrency-provider",
            )
            session.add(draw)
            try:
                session.commit()
                outcomes.append("success")
            except IntegrityError:
                session.rollback()
                outcomes.append("conflict")
            except SQLAlchemyError:
                session.rollback()
                outcomes.append("database_error")
        finally:
            session.close()

    threads = [Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    session = concurrency_session_factory()
    try:
        rows = session.scalars(
            select(LotteryDraw).where(
                LotteryDraw.lottery_id == lottery_id,
                LotteryDraw.source == "concurrency-provider",
                LotteryDraw.draw_number == "RACE-001",
            )
        ).all()
        assert len(rows) <= 1
        assert len(outcomes) == 2
        assert outcomes.count("success") <= 1
        assert set(outcomes) <= {"success", "conflict", "database_error"}
    finally:
        session.close()


def test_concurrent_duplicate_draw_date_cannot_create_two_rows(
    concurrency_session_factory,
):
    lottery_id = _seed_lottery(concurrency_session_factory)
    barrier = Barrier(2)
    outcomes = []

    def worker(index):
        session = concurrency_session_factory()
        try:
            barrier.wait()
            draw = LotteryDraw(
                lottery_id=lottery_id,
                draw_number=f"RACE-DATE-{index}",
                draw_date=datetime(2026, 1, 2, tzinfo=UTC),
                main_numbers=[6, 7, 8, 9, 10],
                source="concurrency-provider",
            )
            session.add(draw)
            try:
                session.commit()
                outcomes.append("success")
            except IntegrityError:
                session.rollback()
                outcomes.append("conflict")
            except SQLAlchemyError:
                session.rollback()
                outcomes.append("database_error")
        finally:
            session.close()

    threads = [Thread(target=worker, args=(index,)) for index in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    session = concurrency_session_factory()
    try:
        rows = session.scalars(
            select(LotteryDraw).where(
                LotteryDraw.lottery_id == lottery_id,
                LotteryDraw.source == "concurrency-provider",
                LotteryDraw.draw_date == datetime(2026, 1, 2, tzinfo=UTC),
            )
        ).all()
        assert len(rows) <= 1
        assert len(outcomes) == 2
        assert outcomes.count("success") <= 1
        assert set(outcomes) <= {"success", "conflict", "database_error"}
    finally:
        session.close()
