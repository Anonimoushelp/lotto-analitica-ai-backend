from datetime import date, timedelta

from sqlalchemy import create_engine, delete, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.services.lottery_draw_service import LotteryDrawService
from app.services.lottery_service import LotteryService
from app.services.statistical_service import StatisticalService


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=engine)
LotteryDraw.__table__.create(bind=engine)


def _seed_lottery(db, code: str) -> Lottery:
    lottery = Lottery(name=code, code=code, country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    return lottery


def _cleanup() -> None:
    db = TestingSessionLocal()
    db.execute(delete(LotteryDraw))
    db.execute(delete(Lottery))
    db.commit()
    db.close()


def _seed_draw(db, lottery_id: int, source: str, draw_number: str, draw_date: date) -> LotteryDraw:
    draw = LotteryDraw(
        lottery_id=lottery_id,
        source=source,
        draw_number=draw_number,
        draw_date=draw_date,
        main_numbers=[1, 2, 3, 4, 5],
    )
    db.add(draw)
    db.commit()
    db.refresh(draw)
    return draw


def test_create_draw_is_immediately_visible_to_list_and_statistics():
    db = TestingSessionLocal()
    try:
        lottery = _seed_lottery(db, "lifecycle-create")
        draw = LotteryDrawService.create_draw(
            db=db,
            lottery_id=lottery.id,
            draw_number="D-001",
            draw_date=date(2026, 9, 10),
            main_numbers=[1, 2, 3, 4, 5],
            source="baloto-colombia",
        )

        listed = LotteryDrawService.list_draws(
            db=db, lottery_id=lottery.id, source="baloto-colombia"
        )
        overview = StatisticalService.overview(
            db=db, lottery_id=lottery.id, source="baloto-colombia"
        )

        assert [item.id for item in listed] == [draw.id]
        assert overview == {
            "module_status": "READY",
            "algorithms_count": 6,
            "draws_analyzed": 1,
        }
    finally:
        db.close()
        _cleanup()


def test_update_draw_is_immediately_visible_to_list_get_and_statistics():
    db = TestingSessionLocal()
    try:
        lottery = _seed_lottery(db, "lifecycle-update")
        draw = _seed_draw(
            db, lottery.id, "baloto-colombia", "D-001", date(2026, 9, 10)
        )

        updated = LotteryDrawService.update_draw(
            db=db,
            draw_id=draw.id,
            update_data={
                "draw_number": "D-002",
                "draw_date": date(2026, 9, 11),
                "main_numbers": [6, 7, 8, 9, 10],
            },
        )

        listed = LotteryDrawService.list_draws(
            db=db, lottery_id=lottery.id, source="baloto-colombia"
        )
        fetched = LotteryDrawService.get_draw(db=db, draw_id=draw.id)
        overview = StatisticalService.overview(
            db=db, lottery_id=lottery.id, source="baloto-colombia"
        )

        assert updated.draw_number == "D-002"
        assert updated.draw_date == date(2026, 9, 11)
        assert updated.main_numbers == [6, 7, 8, 9, 10]
        assert listed[0].draw_number == "D-002"
        assert fetched.draw_number == "D-002"
        assert fetched.main_numbers == [6, 7, 8, 9, 10]
        assert overview["draws_analyzed"] == 1
    finally:
        db.close()
        _cleanup()


def test_delete_draw_is_immediately_reflected_in_list_get_and_statistics():
    db = TestingSessionLocal()
    try:
        lottery = _seed_lottery(db, "lifecycle-delete")
        draw = _seed_draw(
            db, lottery.id, "baloto-colombia", "D-001", date(2026, 9, 10)
        )

        LotteryDrawService.delete_draw(db=db, draw_id=draw.id)

        listed = LotteryDrawService.list_draws(
            db=db, lottery_id=lottery.id, source="baloto-colombia"
        )
        overview = StatisticalService.overview(
            db=db, lottery_id=lottery.id, source="baloto-colombia"
        )

        assert listed == []
        assert overview == {
            "module_status": "STANDBY",
            "algorithms_count": 0,
            "draws_analyzed": 0,
        }
    finally:
        db.close()
        _cleanup()


def test_newer_draw_is_returned_first_after_lifecycle_mutation():
    db = TestingSessionLocal()
    try:
        lottery = _seed_lottery(db, "lifecycle-order")
        older = _seed_draw(
            db, lottery.id, "baloto-colombia", "D-001", date(2026, 9, 10)
        )
        newer = _seed_draw(
            db, lottery.id, "baloto-colombia", "D-002", date(2026, 9, 11)
        )

        LotteryDrawService.update_draw(
            db=db,
            draw_id=older.id,
            update_data={"draw_date": date(2026, 9, 12)},
        )
        listed = LotteryDrawService.list_draws(
            db=db, lottery_id=lottery.id, source="baloto-colombia"
        )

        assert [item.id for item in listed] == [older.id, newer.id]
        assert listed[0].draw_date == date(2026, 9, 12)
        assert listed[1].draw_date == date(2026, 9, 11)
    finally:
        db.close()
        _cleanup()


def test_lottery_cascade_is_immediately_reflected_in_surviving_queries():
    db = TestingSessionLocal()
    try:
        deleted_lottery = _seed_lottery(db, "lifecycle-cascade-deleted")
        surviving_lottery = _seed_lottery(db, "lifecycle-cascade-survivor")
        deleted_draw = _seed_draw(
            db,
            deleted_lottery.id,
            "baloto-colombia",
            "D-001",
            date(2026, 9, 10),
        )
        surviving_draw = _seed_draw(
            db,
            surviving_lottery.id,
            "revancha-colombia",
            "D-001",
            date(2026, 9, 10),
        )

        LotteryService.delete_lottery(db=db, lottery_id=deleted_lottery.id)

        assert LotteryDrawService.list_draws(
            db=db, lottery_id=deleted_lottery.id
        ) == []
        assert StatisticalService.overview(
            db=db, lottery_id=deleted_lottery.id
        ) == {
            "module_status": "STANDBY",
            "algorithms_count": 0,
            "draws_analyzed": 0,
        }
        assert LotteryDrawService.get_draw(
            db=db, draw_id=surviving_draw.id
        ).source == "revancha-colombia"
        assert deleted_draw.id != surviving_draw.id
    finally:
        db.close()
        _cleanup()
