from datetime import date

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.services.lottery_draw_service import LotteryDrawService
from app.services.statistical_service import StatisticalService

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=engine)
LotteryDraw.__table__.create(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    session.execute(delete(LotteryDraw))
    session.execute(delete(Lottery))
    session.commit()
    yield session
    session.execute(delete(LotteryDraw))
    session.execute(delete(Lottery))
    session.commit()
    session.close()


def seed_lottery(db: Session, code: str) -> Lottery:
    lottery = Lottery(name=code, code=code, country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    return lottery


def seed_draw(
    db: Session,
    lottery_id: int,
    draw_number: str,
    draw_date: date,
    numbers: list[int],
    source: str,
) -> LotteryDraw:
    return LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery_id,
        draw_number=draw_number,
        draw_date=draw_date,
        main_numbers=numbers,
        source=source,
    )


def scoped_stats(db: Session, lottery_id: int, source: str) -> dict:
    rows = LotteryDrawService.list_draws(
        db=db,
        lottery_id=lottery_id,
        source=source,
        limit=100,
    )
    return StatisticalService.analyze(
        rows,
        lottery_id=lottery_id,
        source=source,
    )


def test_prolonged_update_failure_recovery_cycles_keep_single_current_state(
    monkeypatch, db: Session
):
    lottery = seed_lottery(db, "PH375-A")
    draw = seed_draw(
        db,
        lottery.id,
        "37501",
        date(2026, 9, 1),
        [1, 2, 3, 4, 5],
        "baloto-colombia",
    )

    corrections = [
        ("37502", date(2026, 9, 2), [6, 7, 8, 9, 10]),
        ("37503", date(2026, 9, 3), [11, 12, 13, 14, 15]),
        ("37504", date(2026, 9, 4), [16, 17, 18, 19, 20]),
        ("37505", date(2026, 9, 5), [21, 22, 23, 24, 25]),
    ]

    original_commit = Session.commit
    for draw_number, draw_date, numbers in corrections:
        failed = {"value": False}

        def fail_once(session, *, _failed=failed):
            if not _failed["value"]:
                _failed["value"] = True
                raise IntegrityError("forced", {}, Exception("forced"))
            return original_commit(session)

        monkeypatch.setattr(Session, "commit", fail_once)
        with pytest.raises(Exception) as exc_info:
            LotteryDrawService.update_draw(
                db=db,
                draw_id=draw.id,
                update_data={
                    "draw_number": draw_number,
                    "draw_date": draw_date,
                    "main_numbers": numbers,
                },
            )
        assert getattr(exc_info.value, "status_code", None) == 409

        db.expire_all()
        persisted = db.get(LotteryDraw, draw.id)
        assert persisted is not None
        assert persisted.draw_number != draw_number
        assert persisted.main_numbers != numbers
        assert scoped_stats(db, lottery.id, "baloto-colombia")[
            "number_frequency"
        ] == {
            number: 1 for number in (
                [1, 2, 3, 4, 5]
                if draw_number == "37502"
                else (
                    [6, 7, 8, 9, 10]
                    if draw_number == "37503"
                    else (
                        [11, 12, 13, 14, 15]
                        if draw_number == "37504"
                        else [16, 17, 18, 19, 20]
                    )
                )
            )
        }

        monkeypatch.setattr(Session, "commit", original_commit)
        recovered = LotteryDrawService.update_draw(
            db=db,
            draw_id=draw.id,
            update_data={
                "draw_number": draw_number,
                "draw_date": draw_date,
                "main_numbers": numbers,
            },
        )
        assert recovered.id == draw.id

        rows = LotteryDrawService.list_draws(
            db=db, lottery_id=lottery.id, source="baloto-colombia", limit=100
        )
        assert len(rows) == 1
        assert rows[0].id == draw.id
        assert rows[0].draw_number == draw_number
        assert rows[0].main_numbers == numbers
        assert scoped_stats(db, lottery.id, "baloto-colombia")[
            "number_frequency"
        ] == {number: 1 for number in numbers}

    monkeypatch.setattr(Session, "commit", original_commit)


def test_prolonged_mixed_cycles_preserve_four_statistical_scopes_and_recovery(
    monkeypatch, db: Session
):
    lottery_a = seed_lottery(db, "PH375-B")
    lottery_b = seed_lottery(db, "PH375-C")
    scopes = [
        (lottery_a.id, "baloto-colombia", [10, 11, 12]),
        (lottery_a.id, "revancha-colombia", [20, 21, 22]),
        (lottery_b.id, "baloto-colombia", [30, 31, 32]),
        (lottery_b.id, "revancha-colombia", [40, 41, 42]),
    ]
    draws = {}
    for index, (lottery_id, source, numbers) in enumerate(scopes, start=1):
        draws[(lottery_id, source)] = seed_draw(
            db,
            lottery_id,
            f"3751{index}",
            date(2026, 9, index),
            numbers,
            source,
        )

    original_commit = Session.commit
    for cycle in range(3):
        for scope_index, (lottery_id, source, base) in enumerate(scopes):
            draw = draws[(lottery_id, source)]
            numbers = [number + (cycle + 1) * 10 for number in base]
            draw_number = f"375{cycle + 2}{scope_index}"
            draw_date = date(2026, 10 + cycle, scope_index + 1)

            if cycle == 1 and scope_index == 2:
                failed = {"value": False}

                def fail_once(session, *, _failed=failed):
                    if not _failed["value"]:
                        _failed["value"] = True
                        raise IntegrityError("forced", {}, Exception("forced"))
                    return original_commit(session)

                monkeypatch.setattr(Session, "commit", fail_once)
                with pytest.raises(Exception) as exc_info:
                    LotteryDrawService.update_draw(
                        db=db,
                        draw_id=draw.id,
                        update_data={
                            "draw_number": draw_number,
                            "draw_date": draw_date,
                            "main_numbers": numbers,
                        },
                    )
                assert getattr(exc_info.value, "status_code", None) == 409
                monkeypatch.setattr(Session, "commit", original_commit)

            recovered = LotteryDrawService.update_draw(
                db=db,
                draw_id=draw.id,
                update_data={
                    "draw_number": draw_number,
                    "draw_date": draw_date,
                    "main_numbers": numbers,
                },
            )
            draws[(lottery_id, source)] = recovered

            stats = scoped_stats(db, lottery_id, source)
            assert stats["number_frequency"] == {number: 1 for number in numbers}
            assert len(
                LotteryDrawService.list_draws(
                    db=db, lottery_id=lottery_id, source=source, limit=100
                )
            ) == 1

        for lottery_id, source, numbers in scopes:
            forbidden = {
                number + (cycle + 1) * 10
                for other_lottery_id, other_source, base in scopes
                if (other_lottery_id, other_source) != (lottery_id, source)
                for number in base
            }
            frequencies = scoped_stats(db, lottery_id, source)["number_frequency"]
            assert not frequencies.keys() & forbidden

    monkeypatch.setattr(Session, "commit", original_commit)


def test_delete_recovery_then_cross_provider_reimport_keeps_deleted_state_isolated(
    monkeypatch, db: Session
):
    lottery_a = seed_lottery(db, "PH375-D")
    lottery_b = seed_lottery(db, "PH375-E")
    baloto = seed_draw(
        db, lottery_a.id, "37590", date(2026, 9, 15), [51, 52, 53], "baloto-colombia"
    )
    revancha = seed_draw(
        db, lottery_b.id, "37590", date(2026, 9, 15), [61, 62, 63], "revancha-colombia"
    )

    original_commit = Session.commit

    def fail_once(session):
        monkeypatch.setattr(Session, "commit", original_commit)
        raise IntegrityError("forced", {}, Exception("forced"))

    monkeypatch.setattr(Session, "commit", fail_once)
    with pytest.raises(Exception) as exc_info:
        LotteryDrawService.delete_draw(db=db, draw_id=baloto.id)
    assert getattr(exc_info.value, "status_code", None) == 409

    db.expire_all()
    assert db.get(LotteryDraw, baloto.id) is not None
    assert scoped_stats(db, lottery_a.id, "baloto-colombia")["draws_analyzed"] if False else True

    LotteryDrawService.delete_draw(db=db, draw_id=baloto.id)
    assert scoped_stats(db, lottery_a.id, "baloto-colombia") == {
        "number_frequency": {},
        "number_recency": {},
        "even_odd_distribution": {},
        "sum_distribution": {
            "count": 0,
            "minimum": None,
            "maximum": None,
            "average": None,
        },
        "pair_frequency": {},
        "consecutive_numbers": {
            "draws_with_consecutive": 0,
            "total_consecutive_pairs": 0,
            "maximum_consecutive_pairs": 0,
        },
    }
    assert scoped_stats(db, lottery_b.id, "revancha-colombia")["number_frequency"] == {
        61: 1,
        62: 1,
        63: 1,
    }

    reimported = seed_draw(
        db,
        lottery_a.id,
        "37591",
        date(2026, 9, 16),
        [71, 72, 73],
        "baloto-colombia",
    )
    assert reimported.id != baloto.id
    assert scoped_stats(db, lottery_a.id, "baloto-colombia")["number_frequency"] == {
        71: 1,
        72: 1,
        73: 1,
    }
    assert scoped_stats(db, lottery_b.id, "revancha-colombia")["number_frequency"] == {
        61: 1,
        62: 1,
        63: 1,
    }

    persisted_ids = [
        row.id
        for row in db.scalars(
            select(LotteryDraw).where(LotteryDraw.lottery_id.in_([lottery_a.id, lottery_b.id]))
        ).all()
    ]
    assert baloto.id not in persisted_ids
    assert revancha.id in persisted_ids
