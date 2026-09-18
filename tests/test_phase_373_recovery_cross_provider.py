from datetime import date

import pytest
from sqlalchemy import select

from app.models.lottery_draw import LotteryDraw
from app.services.lottery_draw_service import LotteryDrawService
from app.services.statistical_service import StatisticalService

from tests.test_statistics_reassignment_integrity import seed_draw, seed_lottery


def test_repeated_conflict_recovery_preserves_scope_and_allows_cross_provider_reimport(db):
    lottery_a = seed_lottery(db, "PH373-A")
    lottery_b = seed_lottery(db, "PH373-B")
    baloto = seed_draw(
        db,
        lottery_a.id,
        "37301",
        date(2026, 9, 1),
        [1, 2, 3, 4, 5],
        "baloto-colombia",
    )
    blocker = seed_draw(
        db,
        lottery_b.id,
        "37302",
        date(2026, 9, 2),
        [11, 12, 13, 14, 15],
        "baloto-colombia",
    )
    original = (
        baloto.lottery_id,
        baloto.draw_number,
        baloto.draw_date,
        list(baloto.main_numbers),
        baloto.source,
    )

    for _ in range(4):
        with pytest.raises(Exception) as exc_info:
            LotteryDrawService.update_draw(
                db=db,
                draw_id=baloto.id,
                update_data={
                    "lottery_id": lottery_b.id,
                    "draw_number": blocker.draw_number,
                    "draw_date": date(2026, 9, 20),
                    "main_numbers": [101, 102, 103, 104, 105],
                },
            )
        assert getattr(exc_info.value, "status_code", None) == 409
        db.expire_all()
        current = db.get(LotteryDraw, baloto.id)
        assert current is not None
        assert (
            current.lottery_id,
            current.draw_number,
            current.draw_date,
            current.main_numbers,
            current.source,
        ) == original

    recovered = LotteryDrawService.update_draw(
        db=db,
        draw_id=baloto.id,
        update_data={
            "draw_number": "373-recovered",
            "draw_date": date(2026, 9, 20),
            "main_numbers": [21, 22, 23, 24, 25],
        },
    )
    assert recovered.id == baloto.id

    reimported = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery_a.id,
        draw_number="373-recovered-reimport",
        draw_date=date(2026, 9, 21),
        main_numbers=[31, 32, 33, 34, 35],
        source="revancha-colombia",
    )

    baloto_rows = LotteryDrawService.list_draws(
        db=db, lottery_id=lottery_a.id, source="baloto-colombia", limit=100
    )
    revancha_rows = LotteryDrawService.list_draws(
        db=db, lottery_id=lottery_a.id, source="revancha-colombia", limit=100
    )
    assert [row.id for row in baloto_rows] == [baloto.id]
    assert [row.id for row in revancha_rows] == [reimported.id]
    assert StatisticalService.analyze(
        baloto_rows, lottery_id=lottery_a.id, source="baloto-colombia"
    )["number_frequency"] == {21: 1, 22: 1, 23: 1, 24: 1, 25: 1}
    assert StatisticalService.analyze(
        revancha_rows, lottery_id=lottery_a.id, source="revancha-colombia"
    )["number_frequency"] == {31: 1, 32: 1, 33: 1, 34: 1, 35: 1}


def test_cross_provider_recovery_after_delete_never_restores_deleted_statistics(db):
    lottery = seed_lottery(db, "PH373-C")
    baloto = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number="37310",
        draw_date=date(2026, 9, 10),
        main_numbers=[41, 42, 43, 44, 45],
        source="baloto-colombia",
    )
    revancha = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number="37310",
        draw_date=date(2026, 9, 11),
        main_numbers=[51, 52, 53, 54, 55],
        source="revancha-colombia",
    )

    LotteryDrawService.delete_draw(db=db, draw_id=baloto.id)
    updated_revancha = LotteryDrawService.update_draw(
        db=db,
        draw_id=revancha.id,
        update_data={"main_numbers": [61, 62, 63, 64, 65]},
    )

    recovered_baloto = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number="37311",
        draw_date=date(2026, 9, 12),
        main_numbers=[71, 72, 73, 74, 75],
        source="baloto-colombia",
    )

    baloto_rows = LotteryDrawService.list_draws(
        db=db, lottery_id=lottery.id, source="baloto-colombia", limit=100
    )
    revancha_rows = LotteryDrawService.list_draws(
        db=db, lottery_id=lottery.id, source="revancha-colombia", limit=100
    )
    assert [row.id for row in baloto_rows] == [recovered_baloto.id]
    assert [row.id for row in revancha_rows] == [updated_revancha.id]
    assert 41 not in StatisticalService.analyze(
        baloto_rows, lottery_id=lottery.id, source="baloto-colombia"
    )["number_frequency"]
    assert StatisticalService.analyze(
        revancha_rows, lottery_id=lottery.id, source="revancha-colombia"
    )["number_frequency"] == {61: 1, 62: 1, 63: 1, 64: 1, 65: 1}
    assert StatisticalService.overview(
        db, lottery_id=lottery.id, source="baloto-colombia"
    )["draws_analyzed"] == 1


def test_recovery_cycle_keeps_single_database_record_and_statistics_after_stale_read(db):
    lottery = seed_lottery(db, "PH373-D")
    draw = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number="37320",
        draw_date=date(2026, 9, 13),
        main_numbers=[81, 82, 83, 84, 85],
        source="miloto-colombia",
    )
    stale = type(db)(db.bind, autoflush=False, autocommit=False)
    try:
        stale_draw = stale.get(LotteryDraw, draw.id)
        assert stale_draw is not None

        for cycle in range(3):
            numbers = [91 + cycle * 5 + offset for offset in range(5)]
            LotteryDrawService.update_draw(
                db=db,
                draw_id=draw.id,
                update_data={
                    "draw_number": f"3732{cycle + 1}",
                    "draw_date": date(2026, 9, 14 + cycle),
                    "main_numbers": numbers,
                },
            )
            stale.expire_all()
            current = stale.get(LotteryDraw, draw.id)
            assert current is not None
            assert current.main_numbers == numbers
            rows = LotteryDrawService.list_draws(
                db=db, lottery_id=lottery.id, source="miloto-colombia", limit=100
            )
            assert len(rows) == 1
            assert StatisticalService.analyze(
                rows, lottery_id=lottery.id, source="miloto-colombia"
            )["number_frequency"] == {number: 1 for number in numbers}

        persisted = db.scalar(select(LotteryDraw).where(LotteryDraw.id == draw.id))
        assert persisted is not None
        assert persisted.main_numbers == [101, 102, 103, 104, 105]
    finally:
        stale.close()
