"""Phase 383 resilience tests for chained failures and cross-scope recovery."""

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


def test_phase_383_chained_integrity_failures_never_leave_partial_mutations():
    db = SessionLocal()
    try:
        lottery = seed_lottery(db, "PH383-A")
        target = seed_draw(
            db, lottery.id, "38300", date(2026, 12, 1),
            [3701, 3702, 3703], "baloto-colombia"
        )
        conflict = seed_draw(
            db, lottery.id, "38301", date(2026, 12, 2),
            [3801, 3802, 3803], "baloto-colombia"
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
                        "draw_number": f"383{cycle}0",
                        "draw_date": date(2026, 12, 10 + cycle),
                        "main_numbers": [3900 + cycle, 4000 + cycle, 4100 + cycle],
                    },
                )
            assert exc.value.status_code == 409
            db.commit = original_commit
            db.rollback()
            db.expire_all()

        persisted = db.get(LotteryDraw, target.id)
        assert persisted is not None
        assert persisted.draw_number == "38300"
        assert persisted.main_numbers == [3701, 3702, 3703]
        assert stats(db, lottery.id, "baloto-colombia") == {
            3701: 1, 3702: 1, 3703: 1, 3801: 1, 3802: 1, 3803: 1
        }

        recovered = LotteryDrawService.update_draw(
            db=db,
            draw_id=target.id,
            update_data={
                "draw_number": "38399",
                "draw_date": date(2026, 12, 31),
                "main_numbers": [4201, 4202, 4203],
            },
        )
        assert recovered.id == target.id
        assert stats(db, lottery.id, "baloto-colombia") == {
            4201: 1, 4202: 1, 4203: 1, 3801: 1, 3802: 1, 3803: 1
        }
    finally:
        db.close()


def test_phase_383_cross_scope_failure_recovery_preserves_other_providers():
    db = SessionLocal()
    try:
        first = seed_lottery(db, "PH383-B1")
        second = seed_lottery(db, "PH383-B2")
        draws = [
            seed_draw(
                db, first.id, "38310", date(2026, 12, 10),
                [4301, 4302, 4303], "baloto-colombia"
            ),
            seed_draw(
                db, first.id, "38320", date(2026, 12, 11),
                [4401, 4402, 4403], "revancha-colombia"
            ),
            seed_draw(
                db, second.id, "38330", date(2026, 12, 12),
                [4501, 4502, 4503], "miloto-colombia"
            ),
        ]
        target = draws[0]
        for cycle in range(4):
            with pytest.raises(HTTPException) as exc:
                LotteryDrawService.update_draw(
                    db=db,
                    draw_id=target.id,
                    update_data={
                        "lottery_id": second.id,
                        "draw_number": draws[2].draw_number,
                        "draw_date": draws[2].draw_date,
                        "main_numbers": [4600 + cycle, 4700 + cycle, 4800 + cycle],
                    },
                )
            assert exc.value.status_code == 409

        assert stats(db, first.id, "baloto-colombia") == {4301: 1, 4302: 1, 4303: 1}
        assert stats(db, first.id, "revancha-colombia") == {4401: 1, 4402: 1, 4403: 1}
        assert stats(db, second.id, "miloto-colombia") == {4501: 1, 4502: 1, 4503: 1}

        LotteryDrawService.update_draw(
            db=db, draw_id=target.id,
            update_data={"lottery_id": second.id, "draw_number": "38331",
                         "draw_date": date(2026, 12, 13),
                         "main_numbers": [4901, 4902, 4903]},
        )
        assert stats(db, first.id, "baloto-colombia") == {}
        assert stats(db, second.id, "baloto-colombia") == {4901: 1, 4902: 1, 4903: 1}
        assert stats(db, second.id, "miloto-colombia") == {4501: 1, 4502: 1, 4503: 1}
    finally:
        db.close()
