"""Phase 384 resilience tests for extreme recovery/reimport cycles."""

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.services.lottery_draw_service import LotteryDrawService
from app.services.statistical_service import StatisticalService
from tests.test_phase_375_prolonged_cycles import SessionLocal, seed_draw


def seed_lottery(db: Session, code: str) -> Lottery:
    lottery = Lottery(name=code, code=code, country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    return lottery


def stats(db: Session, lottery_id: int, source: str) -> dict:
    rows = LotteryDrawService.list_draws(db, lottery_id, source, 100)
    return StatisticalService.analyze(rows, lottery_id=lottery_id, source=source)[
        "number_frequency"
    ]


def test_phase_384_failed_delete_recovery_then_cross_provider_reimport_is_atomic():
    db = SessionLocal()
    try:
        lottery = seed_lottery(db, "PH384-A")
        target = seed_draw(
            db, lottery.id, "38400", date(2027, 1, 1),
            [5101, 5102, 5103], "baloto-colombia"
        )
        survivor = seed_draw(
            db, lottery.id, "38401", date(2027, 1, 2),
            [5201, 5202, 5203], "revancha-colombia"
        )

        original_commit = db.commit
        db.commit = lambda: (_ for _ in ()).throw(
            IntegrityError("forced", {}, Exception())
        )
        with pytest.raises(HTTPException) as exc:
            LotteryDrawService.delete_draw(db, target.id)
        assert exc.value.status_code == 409
        db.commit = original_commit
        db.rollback()
        db.expire_all()

        assert db.get(LotteryDraw, target.id) is not None
        assert stats(db, lottery.id, "baloto-colombia") == {
            5101: 1, 5102: 1, 5103: 1
        }
        assert stats(db, lottery.id, "revancha-colombia") == {
            5201: 1, 5202: 1, 5203: 1
        }

        LotteryDrawService.delete_draw(db, target.id)
        assert stats(db, lottery.id, "baloto-colombia") == {}
        assert stats(db, lottery.id, "revancha-colombia") == {
            5201: 1, 5202: 1, 5203: 1
        }

        reimported = LotteryDrawService.create_draw(
            db=db,
            lottery_id=lottery.id,
            draw_number="38402",
            draw_date=date(2027, 1, 3),
            main_numbers=[5301, 5302, 5303],
            source="miloto-colombia",
        )
        assert reimported.source == "miloto-colombia"
        assert stats(db, lottery.id, "baloto-colombia") == {}
        assert stats(db, lottery.id, "revancha-colombia") == {
            5201: 1, 5202: 1, 5203: 1
        }
        assert stats(db, lottery.id, "miloto-colombia") == {
            5301: 1, 5302: 1, 5303: 1
        }
        assert db.get(LotteryDraw, target.id) is None
        assert db.get(LotteryDraw, survivor.id) is not None
    finally:
        db.close()


def test_phase_384_failed_cross_lottery_reassignment_then_reimport_keeps_four_scopes_isolated():
    db = SessionLocal()
    try:
        first = seed_lottery(db, "PH384-B1")
        second = seed_lottery(db, "PH384-B2")
        target = seed_draw(
            db, first.id, "38410", date(2027, 1, 10),
            [5401, 5402, 5403], "baloto-colombia"
        )
        conflict = seed_draw(
            db, second.id, "38411", date(2027, 1, 11),
            [5501, 5502, 5503], "baloto-colombia"
        )
        revancha = seed_draw(
            db, second.id, "38412", date(2027, 1, 12),
            [5601, 5602, 5603], "revancha-colombia"
        )
        miloto = seed_draw(
            db, first.id, "38413", date(2027, 1, 13),
            [5701, 5702, 5703], "miloto-colombia"
        )

        original_commit = db.commit
        for cycle in range(3):
            db.commit = lambda: (_ for _ in ()).throw(
                IntegrityError("forced", {}, Exception())
            )
            with pytest.raises(HTTPException) as exc:
                LotteryDrawService.update_draw(
                    db=db,
                    draw_id=target.id,
                    update_data={
                        "lottery_id": second.id,
                        "draw_number": conflict.draw_number,
                        "draw_date": conflict.draw_date,
                        "main_numbers": [5801 + cycle, 5802 + cycle, 5803 + cycle],
                    },
                )
            assert exc.value.status_code == 409
            db.commit = original_commit
            db.rollback()
            db.expire_all()

        assert stats(db, first.id, "baloto-colombia") == {
            5401: 1, 5402: 1, 5403: 1
        }
        assert stats(db, first.id, "miloto-colombia") == {
            5701: 1, 5702: 1, 5703: 1
        }
        assert stats(db, second.id, "baloto-colombia") == {
            5501: 1, 5502: 1, 5503: 1
        }
        assert stats(db, second.id, "revancha-colombia") == {
            5601: 1, 5602: 1, 5603: 1
        }

        LotteryDrawService.delete_draw(db, target.id)
        LotteryDrawService.create_draw(
            db=db,
            lottery_id=first.id,
            draw_number="38414",
            draw_date=date(2027, 1, 14),
            main_numbers=[5901, 5902, 5903],
            source="baloto-colombia",
        )

        assert stats(db, first.id, "baloto-colombia") == {
            5901: 1, 5902: 1, 5903: 1
        }
        assert stats(db, first.id, "miloto-colombia") == {
            5701: 1, 5702: 1, 5703: 1
        }
        assert stats(db, second.id, "baloto-colombia") == {
            5501: 1, 5502: 1, 5503: 1
        }
        assert stats(db, second.id, "revancha-colombia") == {
            5601: 1, 5602: 1, 5603: 1
        }
        assert db.get(LotteryDraw, target.id) is None
    finally:
        db.close()


def test_phase_384_stale_session_after_failed_recovery_cannot_restore_cross_scope_state():
    db = SessionLocal()
    stale = SessionLocal()
    try:
        lottery = seed_lottery(db, "PH384-C")
        target = seed_draw(
            db, lottery.id, "38420", date(2027, 1, 20),
            [6001, 6002, 6003], "baloto-colombia"
        )
        survivor = seed_draw(
            db, lottery.id, "38421", date(2027, 1, 21),
            [6101, 6102, 6103], "revancha-colombia"
        )

        stale_target = stale.get(LotteryDraw, target.id)
        assert stale_target is not None

        original_commit = db.commit
        db.commit = lambda: (_ for _ in ()).throw(
            IntegrityError("forced", {}, Exception())
        )
        with pytest.raises(HTTPException) as exc:
            LotteryDrawService.update_draw(
                db=db,
                draw_id=target.id,
                update_data={
                    "draw_number": "38499",
                    "draw_date": date(2027, 1, 31),
                    "main_numbers": [6201, 6202, 6203],
                },
            )
        assert exc.value.status_code == 409
        db.commit = original_commit
        db.rollback()
        db.expire_all()

        assert stats(db, lottery.id, "baloto-colombia") == {
            6001: 1, 6002: 1, 6003: 1
        }
        assert stats(db, lottery.id, "revancha-colombia") == {
            6101: 1, 6102: 1, 6103: 1
        }

        stale.expunge(stale_target)
        refreshed = stale.get(LotteryDraw, target.id)
        assert refreshed is not None
        assert refreshed.draw_number == "38420"
        assert refreshed.main_numbers == [6001, 6002, 6003]
        assert stats(stale, lottery.id, "baloto-colombia") == {
            6001: 1, 6002: 1, 6003: 1
        }
        assert db.get(LotteryDraw, survivor.id) is not None
    finally:
        stale.close()
        db.close()
