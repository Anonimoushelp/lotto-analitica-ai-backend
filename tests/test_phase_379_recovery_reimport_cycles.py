"""Phase 379 regression coverage for repeated cross-scope recovery and reimport cycles."""

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


def test_phase_379_repeated_number_and_date_conflicts_recover_without_partial_state():
    db = SessionLocal()
    try:
        lottery_a = seed_lottery(db, "PH379-A")
        lottery_b = seed_lottery(db, "PH379-B")
        primary = seed_draw(
            db, lottery_a.id, "37901", date(2026, 10, 1),
            [101, 102, 103], "baloto-colombia"
        )
        conflict = seed_draw(
            db, lottery_b.id, "37902", date(2026, 10, 2),
            [201, 202, 203], "baloto-colombia"
        )
        original = (
            primary.lottery_id,
            primary.draw_number,
            primary.draw_date,
            list(primary.main_numbers),
        )

        for _ in range(3):
            with pytest.raises(HTTPException) as number_exc:
                LotteryDrawService.update_draw(
                    db=db,
                    draw_id=primary.id,
                    update_data={
                        "lottery_id": lottery_b.id,
                        "draw_number": conflict.draw_number,
                        "draw_date": date(2026, 10, 3),
                        "main_numbers": [301, 302, 303],
                    },
                )
            assert number_exc.value.status_code == 409

            with pytest.raises(HTTPException) as date_exc:
                LotteryDrawService.update_draw(
                    db=db,
                    draw_id=primary.id,
                    update_data={
                        "lottery_id": lottery_b.id,
                        "draw_number": "37903",
                        "draw_date": conflict.draw_date,
                        "main_numbers": [401, 402, 403],
                    },
                )
            assert date_exc.value.status_code == 409

            db.expire_all()
            current = db.get(LotteryDraw, primary.id)
            assert current is not None
            assert (
                current.lottery_id,
                current.draw_number,
                current.draw_date,
                current.main_numbers,
            ) == original

        assert frequency(db, lottery_a.id, "baloto-colombia") == {
            101: 1, 102: 1, 103: 1
        }
        assert frequency(db, lottery_b.id, "baloto-colombia") == {
            201: 1, 202: 1, 203: 1
        }

        recovered = LotteryDrawService.update_draw(
            db=db,
            draw_id=primary.id,
            update_data={
                "lottery_id": lottery_b.id,
                "draw_number": "37903",
                "draw_date": date(2026, 10, 3),
                "main_numbers": [301, 302, 303],
            },
        )
        assert recovered.id == primary.id
        assert frequency(db, lottery_a.id, "baloto-colombia") == {}
        assert frequency(db, lottery_b.id, "baloto-colombia") == {
            201: 1, 202: 1, 203: 1
        }
        assert (
            frequency(db, lottery_b.id, "baloto-colombia").keys()
            & {301, 302, 303}
        ) == {301, 302, 303}
    finally:
        db.close()


def test_phase_379_cross_provider_reimport_after_recovery_keeps_identity_scopes_isolated():
    db = SessionLocal()
    try:
        lottery = seed_lottery(db, "PH379-C")
        baloto = seed_draw(
            db, lottery.id, "37910", date(2026, 10, 10),
            [501, 502, 503], "baloto-colombia"
        )
        revancha = seed_draw(
            db, lottery.id, "37910", date(2026, 10, 10),
            [601, 602, 603], "revancha-colombia"
        )

        for cycle in range(4):
            LotteryDrawService.update_draw(
                db=db,
                draw_id=baloto.id,
                update_data={
                    "draw_number": f"3791{cycle}",
                    "draw_date": date(2026, 10, 11 + cycle),
                    "main_numbers": [511 + cycle, 512 + cycle, 513 + cycle],
                },
            )
            LotteryDrawService.update_draw(
                db=db,
                draw_id=revancha.id,
                update_data={
                    "draw_number": f"3792{cycle}",
                    "draw_date": date(2026, 10, 21 + cycle),
                    "main_numbers": [611 + cycle, 612 + cycle, 613 + cycle],
                },
            )

        assert frequency(db, lottery.id, "baloto-colombia") == {
            514: 1, 515: 1, 516: 1
        }
        assert frequency(db, lottery.id, "revancha-colombia") == {
            614: 1, 615: 1, 616: 1
        }

        LotteryDrawService.delete_draw(db=db, draw_id=baloto.id)
        assert frequency(db, lottery.id, "baloto-colombia") == {}

        reimported = LotteryDrawService.create_draw(
            db=db,
            lottery_id=lottery.id,
            draw_number="37999",
            draw_date=date(2026, 10, 31),
            main_numbers=[701, 702, 703],
            source="baloto-colombia",
        )
        assert reimported.id != baloto.id
        assert frequency(db, lottery.id, "baloto-colombia") == {
            701: 1, 702: 1, 703: 1
        }
        assert frequency(db, lottery.id, "revancha-colombia") == {
            614: 1, 615: 1, 616: 1
        }

        with pytest.raises(HTTPException) as duplicate:
            LotteryDrawService.create_draw(
                db=db,
                lottery_id=lottery.id,
                draw_number="37999",
                draw_date=date(2026, 10, 31),
                main_numbers=[801, 802, 803],
                source="baloto-colombia",
            )
        assert duplicate.value.status_code == 409
        assert frequency(db, lottery.id, "baloto-colombia") == {
            701: 1, 702: 1, 703: 1
        }
    finally:
        db.close()


def test_phase_379_stale_sessions_cannot_restore_deleted_or_recovered_statistics():
    db = SessionLocal()
    stale = SessionLocal()
    try:
        lottery = seed_lottery(db, "PH379-D")
        draw = seed_draw(
            db, lottery.id, "37920", date(2026, 11, 1),
            [901, 902, 903], "miloto-colombia"
        )
        stale_draw = stale.get(LotteryDraw, draw.id)
        assert stale_draw is not None

        LotteryDrawService.update_draw(
            db=db,
            draw_id=draw.id,
            update_data={
                "draw_number": "37921",
                "draw_date": date(2026, 11, 2),
                "main_numbers": [911, 912, 913],
            },
        )
        stale.expire_all()
        current = stale.get(LotteryDraw, draw.id)
        assert current is not None
        assert current.main_numbers == [911, 912, 913]

        LotteryDrawService.delete_draw(db=db, draw_id=draw.id)
        stale.expire_all()
        assert stale.get(LotteryDraw, draw.id) is None
        assert frequency(db, lottery.id, "miloto-colombia") == {}

        replacement = LotteryDrawService.create_draw(
            db=db,
            lottery_id=lottery.id,
            draw_number="37922",
            draw_date=date(2026, 11, 3),
            main_numbers=[921, 922, 923],
            source="miloto-colombia",
        )
        assert replacement.id != draw.id
        stale.expire_all()
        assert stale.get(LotteryDraw, draw.id) is None
        assert frequency(db, lottery.id, "miloto-colombia") == {
            921: 1, 922: 1, 923: 1
        }
        assert 911 not in frequency(db, lottery.id, "miloto-colombia")
    finally:
        stale.close()
        db.close()


def test_phase_379_recovery_conflict_then_cross_provider_reimport_preserves_three_scopes():
    db = SessionLocal()
    try:
        scopes = [
            ("PH379-E", "baloto-colombia", [1001, 1002, 1003]),
            ("PH379-F", "baloto-colombia", [1101, 1102, 1103]),
            ("PH379-G", "miloto-colombia", [1201, 1202, 1203]),
        ]
        records = []
        for index, (code, source, numbers) in enumerate(scopes):
            lottery = seed_lottery(db, code)
            records.append(
                (
                    lottery,
                    seed_draw(
                        db, lottery.id, f"3793{index}",
                        date(2026, 11, 10 + index),
                        numbers, source
                    ),
                    source,
                )
            )

        target_lottery, target, target_source = records[0]
        conflict_lottery, conflict, _ = records[1]

        for cycle in range(2):
            with pytest.raises(HTTPException) as exc:
                LotteryDrawService.update_draw(
                    db=db,
                    draw_id=target.id,
                    update_data={
                        "lottery_id": conflict_lottery.id,
                        "draw_number": conflict.draw_number,
                        "draw_date": conflict.draw_date,
                        "main_numbers": [1301 + cycle, 1302 + cycle, 1303 + cycle],
                    },
                )
            assert exc.value.status_code == 409

        LotteryDrawService.delete_draw(db=db, draw_id=target.id)
        reimported = LotteryDrawService.create_draw(
            db=db,
            lottery_id=target_lottery.id,
            draw_number="37939",
            draw_date=date(2026, 11, 20),
            main_numbers=[1401, 1402, 1403],
            source=target_source,
        )
        assert reimported.id != target.id

        assert frequency(db, target_lottery.id, target_source) == {
            1401: 1, 1402: 1, 1403: 1
        }
        assert frequency(
            db, conflict_lottery.id, "baloto-colombia"
        ) == {1101: 1, 1102: 1, 1103: 1}
        third_lottery, _, third_source = records[2]
        assert frequency(db, third_lottery.id, third_source) == {
            1201: 1, 1202: 1, 1203: 1
        }
    finally:
        db.close()
