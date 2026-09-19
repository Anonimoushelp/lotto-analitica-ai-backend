from datetime import date

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.lottery_draw import LotteryDraw
from app.services.lottery_draw_service import LotteryDrawService
from app.services.statistical_service import StatisticalService

from tests.test_phase_375_prolonged_cycles import SessionLocal, Lottery, seed_draw, seed_lottery


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


def stats(db, lottery_id, source):
    rows = LotteryDrawService.list_draws(
        db=db, lottery_id=lottery_id, source=source, limit=100
    )
    return StatisticalService.analyze(rows, lottery_id=lottery_id, source=source)


def test_phase_376_repeated_cross_lottery_recovery_cycles_keep_single_current_record(
    monkeypatch, db: Session
):
    lottery_a = seed_lottery(db, "PH376-A")
    lottery_b = seed_lottery(db, "PH376-B")
    draw_a = seed_draw(
        db, lottery_a.id, "37601", date(2026, 9, 1), [101, 102, 103], "baloto-colombia"
    )
    draw_b = seed_draw(
        db, lottery_b.id, "37602", date(2026, 9, 2), [201, 202, 203], "baloto-colombia"
    )

    original_commit = Session.commit
    for cycle in range(4):
        new_numbers_a = [111 + cycle, 112 + cycle, 113 + cycle]
        new_numbers_b = [211 + cycle, 212 + cycle, 213 + cycle]
        updates = (
            (draw_a, lottery_a.id, new_numbers_a, f"376A{cycle}", date(2026, 10 + cycle)),
            (draw_b, lottery_b.id, new_numbers_b, f"376B{cycle}", date(2026, 11 + cycle)),
        )
        for index, (draw, lottery_id, numbers, number, draw_date) in enumerate(updates):
            if cycle in {1, 3} and index == 0:
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
                            "draw_number": number,
                            "draw_date": draw_date,
                            "main_numbers": numbers,
                        },
                    )
                assert getattr(exc_info.value, "status_code", None) == 409
                monkeypatch.setattr(Session, "commit", original_commit)

            LotteryDrawService.update_draw(
                db=db,
                draw_id=draw.id,
                update_data={
                    "draw_number": number,
                    "draw_date": draw_date,
                    "main_numbers": numbers,
                },
            )

            db.expire_all()
            persisted = db.get(LotteryDraw, draw.id)
            assert persisted is not None
            assert persisted.main_numbers == numbers
            assert len(
                LotteryDrawService.list_draws(
                    db=db, lottery_id=lottery_id, source="baloto-colombia", limit=100
                )
            ) == 1
            assert stats(db, lottery_id, "baloto-colombia")["number_frequency"] == {
                number: 1 for number in numbers
            }

    monkeypatch.setattr(Session, "commit", original_commit)


def test_phase_376_delete_recover_reassign_and_reimport_remain_isolated(
    monkeypatch, db: Session
):
    lottery_a = seed_lottery(db, "PH376-C")
    lottery_b = seed_lottery(db, "PH376-D")
    baloto = seed_draw(
        db, lottery_a.id, "37610", date(2026, 9, 10), [301, 302, 303], "baloto-colombia"
    )
    revancha = seed_draw(
        db, lottery_a.id, "37611", date(2026, 9, 11), [401, 402, 403], "revancha-colombia"
    )
    other = seed_draw(
        db, lottery_b.id, "37612", date(2026, 9, 12), [501, 502, 503], "baloto-colombia"
    )

    original_commit = Session.commit
    failed = {"value": False}

    def fail_delete(session):
        if not failed["value"]:
            failed["value"] = True
            raise IntegrityError("forced", {}, Exception("forced"))
        return original_commit(session)

    monkeypatch.setattr(Session, "commit", fail_delete)
    with pytest.raises(Exception) as exc_info:
        LotteryDrawService.delete_draw(db=db, draw_id=baloto.id)
    assert getattr(exc_info.value, "status_code", None) == 409
    monkeypatch.setattr(Session, "commit", original_commit)

    assert db.get(LotteryDraw, baloto.id) is not None
    LotteryDrawService.update_draw(
        db=db,
        draw_id=baloto.id,
        update_data={
            "lottery_id": lottery_b.id,
            "draw_number": "37613",
            "draw_date": date(2026, 9, 13),
            "main_numbers": [601, 602, 603],
        },
    )

    assert stats(db, lottery_a.id, "baloto-colombia")["draws_analyzed"] == 0
    assert stats(db, lottery_b.id, "baloto-colombia")["number_frequency"] == {
        501: 1, 502: 1, 503: 1, 601: 1, 602: 1, 603: 1
    }
    assert stats(db, lottery_a.id, "revancha-colombia")["number_frequency"] == {
        401: 1, 402: 1, 403: 1
    }

    LotteryDrawService.delete_draw(db=db, draw_id=baloto.id)
    assert stats(db, lottery_b.id, "baloto-colombia")["number_frequency"] == {
        501: 1, 502: 1, 503: 1
    }

    reimported = seed_draw(
        db, lottery_a.id, "37614", date(2026, 9, 14), [701, 702, 703], "baloto-colombia"
    )
    assert stats(db, lottery_a.id, "baloto-colombia")["number_frequency"] == {
        701: 1, 702: 1, 703: 1
    }
    assert stats(db, lottery_a.id, "revancha-colombia")["number_frequency"] == {
        401: 1, 402: 1, 403: 1
    }


def test_phase_376_stale_session_after_cross_scope_recovery_reads_only_current_state(
    db: Session,
):
    lottery_a = seed_lottery(db, "PH376-E")
    lottery_b = seed_lottery(db, "PH376-F")
    draw = seed_draw(
        db, lottery_a.id, "37620", date(2026, 9, 20), [801, 802, 803], "miloto-colombia"
    )
    stale = SessionLocal()
    try:
        stale_draw = stale.get(LotteryDraw, draw.id)
        assert stale_draw is not None
        LotteryDrawService.update_draw(
            db=db,
            draw_id=draw.id,
            update_data={
                "lottery_id": lottery_b.id,
                "draw_number": "37621",
                "draw_date": date(2026, 9, 21),
                "main_numbers": [901, 902, 903],
            },
        )
        stale.expire_all()
        current = stale.get(LotteryDraw, draw.id)
        assert current is not None
        assert current.lottery_id == lottery_b.id
        assert current.main_numbers == [901, 902, 903]
        assert stats(db, lottery_a.id, "miloto-colombia")["draws_analyzed"] == 0
        assert stats(db, lottery_b.id, "miloto-colombia")["number_frequency"] == {
            901: 1, 902: 1, 903: 1
        }
    finally:
        stale.close()
