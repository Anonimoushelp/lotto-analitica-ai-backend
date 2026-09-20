"""Phase 378 regression coverage for prolonged multi-scope transactional cycles."""

from datetime import date

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


def frequencies(db: Session, lottery_id: int, source: str) -> dict:
    draws = LotteryDrawService.list_draws(
        db=db, lottery_id=lottery_id, source=source, limit=100
    )
    return StatisticalService.analyze(
        draws, lottery_id=lottery_id, source=source
    )["number_frequency"]


def test_phase_378_prolonged_cross_scope_correction_delete_reimport_cycle_is_atomic():
    db = SessionLocal()
    try:
        lottery_a = seed_lottery(db, "PH378-A")
        lottery_b = seed_lottery(db, "PH378-B")
        a = seed_draw(
            db, lottery_a.id, "37801", date(2026, 9, 1),
            [101, 102, 103], "baloto-colombia"
        )
        b = seed_draw(
            db, lottery_b.id, "37801", date(2026, 9, 1),
            [201, 202, 203], "baloto-colombia"
        )
        for cycle in range(3):
            LotteryDrawService.update_draw(
                db=db,
                draw_id=a.id,
                update_data={
                    "draw_number": f"3780{cycle + 2}",
                    "draw_date": date(2026, 9, 2 + cycle),
                    "main_numbers": [111 + cycle, 112 + cycle, 113 + cycle],
                },
            )
            assert frequencies(db, lottery_a.id, "baloto-colombia") == {
                111 + cycle: 1, 112 + cycle: 1, 113 + cycle: 1
            }
            LotteryDrawService.delete_draw(db=db, draw_id=a.id)
            assert frequencies(db, lottery_a.id, "baloto-colombia") == {}
            a = seed_draw(
                db, lottery_a.id, f"3781{cycle}",
                date(2026, 9, 10 + cycle),
                [121 + cycle, 122 + cycle, 123 + cycle],
                "baloto-colombia",
            )
            assert frequencies(db, lottery_b.id, "baloto-colombia") == {
                201: 1, 202: 1, 203: 1
            }
        assert db.query(LotteryDraw).filter(
            LotteryDraw.lottery_id == lottery_a.id,
            LotteryDraw.source == "baloto-colombia",
        ).count() == 1
        assert frequencies(db, lottery_a.id, "baloto-colombia") == {
            123: 1, 124: 1, 125: 1
        }
        assert frequencies(db, lottery_b.id, "baloto-colombia") == {
            201: 1, 202: 1, 203: 1
        }
        assert b.id != a.id
    finally:
        db.close()


def test_phase_378_failed_recovery_in_one_scope_preserves_three_other_scopes():
    db = SessionLocal()
    try:
        scopes = []
        for lottery_code, source, numbers in (
            ("PH378-C", "baloto-colombia", [301, 302, 303]),
            ("PH378-D", "revancha-colombia", [401, 402, 403]),
            ("PH378-E", "baloto-colombia", [501, 502, 503]),
            ("PH378-F", "revancha-colombia", [601, 602, 603]),
        ):
            lottery = seed_lottery(db, lottery_code)
            draw = seed_draw(
                db, lottery.id, "37820", date(2026, 9, 20),
                numbers, source
            )
            scopes.append((lottery, draw, source, numbers))

        target_lottery, target_draw, target_source, _ = scopes[0]
        original = [701, 702, 703]
        original_commit = Session.commit
        calls = {"count": 0}

        def fail_once(session):
            if session is db and calls["count"] == 0:
                calls["count"] += 1
                raise RuntimeError("simulated transactional failure")
            return original_commit(session)

        Session.commit = fail_once
        try:
            try:
                LotteryDrawService.update_draw(
                    db=db,
                    draw_id=target_draw.id,
                    update_data={
                        "draw_number": "37821",
                        "draw_date": date(2026, 9, 21),
                        "main_numbers": original,
                    },
                )
            except RuntimeError:
                db.rollback()
        finally:
            Session.commit = original_commit

        LotteryDrawService.update_draw(
            db=db,
            draw_id=target_draw.id,
            update_data={
                "draw_number": "37821",
                "draw_date": date(2026, 9, 21),
                "main_numbers": original,
            },
        )

        assert frequencies(db, target_lottery.id, target_source) == {
            701: 1, 702: 1, 703: 1
        }
        for lottery, _, source, numbers in scopes[1:]:
            assert frequencies(db, lottery.id, source) == {
                number: 1 for number in numbers
            }
    finally:
        db.close()


def test_phase_378_cross_provider_same_identity_survives_repeated_mutation_cycles():
    db = SessionLocal()
    try:
        lottery = seed_lottery(db, "PH378-G")
        baloto = seed_draw(
            db, lottery.id, "37830", date(2026, 9, 30),
            [801, 802, 803], "baloto-colombia"
        )
        revancha = seed_draw(
            db, lottery.id, "37830", date(2026, 9, 30),
            [901, 902, 903], "revancha-colombia"
        )
        for cycle in range(4):
            LotteryDrawService.update_draw(
                db=db,
                draw_id=baloto.id,
                update_data={
                    "main_numbers": [811 + cycle, 812 + cycle, 813 + cycle],
                    "draw_number": f"3783{cycle}",
                    "draw_date": date(2026, 10, 1 + cycle),
                },
            )
            LotteryDrawService.update_draw(
                db=db,
                draw_id=revancha.id,
                update_data={
                    "main_numbers": [911 + cycle, 912 + cycle, 913 + cycle],
                    "draw_number": f"3784{cycle}",
                    "draw_date": date(2026, 10, 11 + cycle),
                },
            )
            assert frequencies(db, lottery.id, "baloto-colombia") == {
                811 + cycle: 1, 812 + cycle: 1, 813 + cycle: 1
            }
            assert frequencies(db, lottery.id, "revancha-colombia") == {
                911 + cycle: 1, 912 + cycle: 1, 913 + cycle: 1
            }
        assert db.query(LotteryDraw).filter(
            LotteryDraw.lottery_id == lottery.id,
            LotteryDraw.source == "baloto-colombia",
        ).count() == 1
        assert db.query(LotteryDraw).filter(
            LotteryDraw.lottery_id == lottery.id,
            LotteryDraw.source == "revancha-colombia",
        ).count() == 1
    finally:
        db.close()


def test_phase_378_conflict_during_recovery_does_not_leave_partial_cross_scope_mutation():
    db = SessionLocal()
    try:
        lottery_a = seed_lottery(db, "PH378-H")
        lottery_b = seed_lottery(db, "PH378-I")
        target = seed_draw(
            db, lottery_a.id, "37840", date(2026, 10, 20),
            [1001, 1002, 1003], "miloto-colombia"
        )
        conflict = seed_draw(
            db, lottery_b.id, "37841", date(2026, 10, 21),
            [1101, 1102, 1103], "miloto-colombia"
        )
        with __import__("pytest").raises(HTTPException) as exc:
            LotteryDrawService.update_draw(
                db=db,
                draw_id=target.id,
                update_data={
                    "lottery_id": lottery_b.id,
                    "draw_number": conflict.draw_number,
                    "draw_date": conflict.draw_date,
                    "main_numbers": [1201, 1202, 1203],
                },
            )
        assert exc.value.status_code == 409
        db.expire_all()
        current = db.get(LotteryDraw, target.id)
        assert current is not None
        assert current.lottery_id == lottery_a.id
        assert current.draw_number == "37840"
        assert current.main_numbers == [1001, 1002, 1003]
        assert frequencies(db, lottery_a.id, "miloto-colombia") == {
            1001: 1, 1002: 1, 1003: 1
        }
        assert frequencies(db, lottery_b.id, "miloto-colombia") == {
            1101: 1, 1102: 1, 1103: 1
        }
    finally:
        db.close()
