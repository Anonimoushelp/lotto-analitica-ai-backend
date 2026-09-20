"""Phase 382 extreme concurrent mutation and statistical isolation coverage."""

from datetime import date

import pytest
from fastapi import HTTPException
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


def frequency(db: Session, lottery_id: int, source: str) -> dict:
    rows = LotteryDrawService.list_draws(
        db=db, lottery_id=lottery_id, source=source, limit=100
    )
    return StatisticalService.analyze(
        rows, lottery_id=lottery_id, source=source
    )["number_frequency"]


def test_phase_382_extreme_conflict_burst_has_no_partial_state():
    db = SessionLocal()
    try:
        lottery = seed_lottery(db, "PH382-A")
        target = seed_draw(
            db, lottery.id, "38200", date(2026, 12, 1),
            [2101, 2102, 2103], "baloto-colombia"
        )
        conflict = seed_draw(
            db, lottery.id, "38201", date(2026, 12, 2),
            [2201, 2202, 2203], "baloto-colombia"
        )

        for cycle in range(10):
            with pytest.raises(HTTPException) as exc:
                LotteryDrawService.update_draw(
                    db=db,
                    draw_id=target.id,
                    update_data={
                        "draw_number": conflict.draw_number,
                        "draw_date": conflict.draw_date,
                        "main_numbers": [2300 + cycle, 2400 + cycle, 2500 + cycle],
                    },
                )
            assert exc.value.status_code == 409

        db.expire_all()
        persisted = db.get(LotteryDraw, target.id)
        assert persisted is not None
        assert persisted.draw_number == "38200"
        assert persisted.draw_date == date(2026, 12, 1)
        assert persisted.main_numbers == [2101, 2102, 2103]
        assert frequency(db, lottery.id, "baloto-colombia") == {
            2101: 1, 2102: 1, 2103: 1, 2201: 1, 2202: 1, 2203: 1
        }
    finally:
        db.close()


def test_phase_382_simultaneous_provider_identities_remain_isolated():
    db = SessionLocal()
    try:
        lottery = seed_lottery(db, "PH382-B")
        draws = [
            seed_draw(
                db, lottery.id, "38210", date(2026, 12, 10),
                [2601, 2602, 2603], "baloto-colombia"
            ),
            seed_draw(
                db, lottery.id, "38210", date(2026, 12, 10),
                [2701, 2702, 2703], "revancha-colombia"
            ),
            seed_draw(
                db, lottery.id, "38210", date(2026, 12, 10),
                [2801, 2802, 2803], "miloto-colombia"
            ),
        ]

        for cycle in range(5):
            for draw, source, base in (
                (draws[0], "baloto-colombia", 2900),
                (draws[1], "revancha-colombia", 3000),
                (draws[2], "miloto-colombia", 3100),
            ):
                LotteryDrawService.update_draw(
                    db=db,
                    draw_id=draw.id,
                    update_data={
                        "draw_number": f"382{cycle}{base}",
                        "draw_date": date(2026, 12, 11 + cycle),
                        "main_numbers": [
                            base + cycle, base + 1 + cycle, base + 2 + cycle
                        ],
                    },
                )

        assert frequency(db, lottery.id, "baloto-colombia") == {
            2904: 1, 2905: 1, 2906: 1
        }
        assert frequency(db, lottery.id, "revancha-colombia") == {
            3004: 1, 3005: 1, 3006: 1
        }
        assert frequency(db, lottery.id, "miloto-colombia") == {
            3104: 1, 3105: 1, 3106: 1
        }
    finally:
        db.close()


def test_phase_382_recovery_after_delete_does_not_restore_stale_statistics():
    db = SessionLocal()
    try:
        lottery = seed_lottery(db, "PH382-C")
        draw = seed_draw(
            db, lottery.id, "38230", date(2026, 12, 20),
            [3201, 3202, 3203], "revancha-colombia"
        )
        for cycle in range(5):
            LotteryDrawService.update_draw(
                db=db,
                draw_id=draw.id,
                update_data={
                    "draw_number": f"3823{cycle}",
                    "draw_date": date(2026, 12, 21 + cycle),
                    "main_numbers": [
                        3300 + cycle, 3400 + cycle, 3500 + cycle
                    ],
                },
            )
        LotteryDrawService.delete_draw(db=db, draw_id=draw.id)
        assert frequency(db, lottery.id, "revancha-colombia") == {}

        replacement = LotteryDrawService.create_draw(
            db=db,
            lottery_id=lottery.id,
            draw_number="38239",
            draw_date=date(2026, 12, 31),
            main_numbers=[3601, 3602, 3603],
            source="revancha-colombia",
        )
        assert frequency(db, lottery.id, "revancha-colombia") == {
            3601: 1, 3602: 1, 3603: 1
        }
        assert replacement.main_numbers == [3601, 3602, 3603]
        assert frequency(db, lottery.id, "baloto-colombia") == {}
    finally:
        db.close()
