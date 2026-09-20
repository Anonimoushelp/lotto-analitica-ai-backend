"""Phase 380 coverage for prolonged concurrent-scope statistical consistency."""

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


def test_phase_380_repeated_conflict_recovery_keeps_four_scopes_isolated():
    db = SessionLocal()
    try:
        scopes = []
        for index, source in enumerate(
            ("baloto-colombia", "revancha-colombia")
        ):
            lottery = seed_lottery(db, f"PH380-{index}")
            scopes.append(
                (
                    lottery,
                    seed_draw(
                        db, lottery.id, f"380{index}0",
                        date(2026, 12, 1 + index),
                        [100 + index, 200 + index, 300 + index],
                        source,
                    ),
                    source,
                )
            )
            second = seed_lottery(db, f"PH380-{index + 2}")
            scopes.append(
                (
                    second,
                    seed_draw(
                        db, second.id, f"380{index}1",
                        date(2026, 12, 3 + index),
                        [400 + index, 500 + index, 600 + index],
                        source,
                    ),
                    source,
                )
            )

        target_lottery, target, target_source = scopes[0]
        conflict_lottery, conflict, _ = scopes[1]

        for cycle in range(4):
            with pytest.raises(HTTPException) as exc:
                LotteryDrawService.update_draw(
                    db=db,
                    draw_id=target.id,
                    update_data={
                        "lottery_id": conflict_lottery.id,
                        "draw_number": conflict.draw_number,
                        "draw_date": conflict.draw_date,
                        "main_numbers": [700 + cycle, 800 + cycle, 900 + cycle],
                    },
                )
            assert exc.value.status_code == 409

        db.expire_all()
        persisted = db.get(LotteryDraw, target.id)
        assert persisted is not None
        assert persisted.lottery_id == target_lottery.id
        assert frequency(db, target_lottery.id, target_source) == {
            100: 1, 200: 1, 300: 1
        }
        assert frequency(db, conflict_lottery.id, conflict.source) == {
            400: 1, 500: 1, 600: 1
        }

        recovered = LotteryDrawService.update_draw(
            db=db,
            draw_id=target.id,
            update_data={
                "lottery_id": target_lottery.id,
                "draw_number": "38009",
                "draw_date": date(2026, 12, 9),
                "main_numbers": [710, 810, 910],
            },
        )
        assert recovered.id == target.id
        assert frequency(db, target_lottery.id, target_source) == {
            710: 1, 810: 1, 910: 1
        }
        assert frequency(db, conflict_lottery.id, conflict.source) == {
            101: 1, 201: 1, 301: 1
        }

        for lottery, _, source in scopes[2:]:
            assert frequency(db, lottery.id, source)
    finally:
        db.close()


def test_phase_380_cross_provider_recovery_and_reimport_never_crosses_statistics():
    db = SessionLocal()
    try:
        lottery = seed_lottery(db, "PH380-X")
        baloto = seed_draw(
            db, lottery.id, "38020", date(2026, 12, 10),
            [1101, 1102, 1103], "baloto-colombia"
        )
        revancha = seed_draw(
            db, lottery.id, "38020", date(2026, 12, 10),
            [1201, 1202, 1203], "revancha-colombia"
        )
        miloto = seed_draw(
            db, lottery.id, "38020", date(2026, 12, 10),
            [1301, 1302, 1303], "miloto-colombia"
        )

        for cycle in range(3):
            for draw, source, base in (
                (baloto, "baloto-colombia", 1400),
                (revancha, "revancha-colombia", 1500),
                (miloto, "miloto-colombia", 1600),
            ):
                LotteryDrawService.update_draw(
                    db=db,
                    draw_id=draw.id,
                    update_data={
                        "draw_number": f"380{30 + cycle}{base}",
                        "draw_date": date(2026, 12, 11 + cycle),
                        "main_numbers": [
                            base + cycle, base + 1 + cycle, base + 2 + cycle
                        ],
                    },
                )

        assert frequency(db, lottery.id, "baloto-colombia") == {
            1402: 1, 1403: 1, 1404: 1
        }
        assert frequency(db, lottery.id, "revancha-colombia") == {
            1502: 1, 1503: 1, 1504: 1
        }
        assert frequency(db, lottery.id, "miloto-colombia") == {
            1602: 1, 1603: 1, 1604: 1
        }

        LotteryDrawService.delete_draw(db=db, draw_id=revancha.id)
        assert frequency(db, lottery.id, "revancha-colombia") == {}

        replacement = LotteryDrawService.create_draw(
            db=db,
            lottery_id=lottery.id,
            draw_number="38099",
            draw_date=date(2026, 12, 31),
            main_numbers=[1701, 1702, 1703],
            source="revancha-colombia",
        )
        assert frequency(db, lottery.id, "revancha-colombia") == {
            1701: 1, 1702: 1, 1703: 1
        }
        assert replacement.id != baloto.id
        assert frequency(db, lottery.id, "baloto-colombia") == {
            1402: 1, 1403: 1, 1404: 1
        }
        assert frequency(db, lottery.id, "miloto-colombia") == {
            1602: 1, 1603: 1, 1604: 1
        }
    finally:
        db.close()


def test_phase_380_stale_sessions_observe_current_state_after_recovery_cycles():
    db = SessionLocal()
    stale = SessionLocal()
    try:
        lottery = seed_lottery(db, "PH380-S")
        draw = seed_draw(
            db, lottery.id, "38040", date(2026, 12, 20),
            [1801, 1802, 1803], "miloto-colombia"
        )
        stale_draw = stale.get(LotteryDraw, draw.id)
        assert stale_draw is not None

        for cycle in range(3):
            LotteryDrawService.update_draw(
                db=db,
                draw_id=draw.id,
                update_data={
                    "draw_number": f"3804{cycle}",
                    "draw_date": date(2026, 12, 21 + cycle),
                    "main_numbers": [
                        1810 + cycle, 1820 + cycle, 1830 + cycle
                    ],
                },
            )
            stale.expire_all()
            current = stale.get(LotteryDraw, draw.id)
            assert current is not None
            assert current.main_numbers == [
                1810 + cycle, 1820 + cycle, 1830 + cycle
            ]

        LotteryDrawService.delete_draw(db=db, draw_id=draw.id)
        stale.expunge(stale_draw)
        stale.expire_all()
        assert stale.get(LotteryDraw, draw.id) is None
        assert frequency(db, lottery.id, "miloto-colombia") == {}
    finally:
        stale.close()
        db.close()
