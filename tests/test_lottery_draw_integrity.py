from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.services.lottery_draw_service import LotteryDrawService
from app.sources.contracts import RawDrawRecord

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=engine)
LotteryDraw.__table__.create(bind=engine)


def db_session():
    return TestingSessionLocal()


def seed_lottery(db, name: str) -> Lottery:
    lottery = Lottery(
        name=name,
        code=name.lower().replace(" ", "-"),
        country="Colombia",
    )
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    return lottery


def draw_payload(lottery_id: int, draw_number: str = "D-001", draw_date=date(2026, 9, 2)):
    return {
        "lottery_id": lottery_id,
        "draw_number": draw_number,
        "draw_date": draw_date,
        "main_numbers": [1, 2, 3, 4, 5],
        "bonus_numbers": [6],
        "source": "test",
        "metadata_json": {"fixture": True},
    }


@pytest.fixture

def db():
    session = db_session()
    try:
        yield session
    finally:
        session.close()
        cleanup = db_session()
        cleanup.execute(delete(LotteryDraw))
        cleanup.execute(delete(Lottery))
        cleanup.commit()
        cleanup.close()


def test_create_draw_persists_valid_record(db):
    lottery = seed_lottery(db, "MiLoto")

    draw = LotteryDrawService.create_draw(db=db, **draw_payload(lottery.id))

    assert draw.id is not None
    assert draw.lottery_id == lottery.id
    assert draw.draw_type == "DEFAULT"
    assert draw.draw_number == "D-001"
    assert draw.main_numbers == [1, 2, 3, 4, 5]
    assert draw.bonus_numbers == [6]
    assert draw.validation_json is None


def test_create_draw_allows_missing_draw_number(db):
    lottery = seed_lottery(db, "Antioqueñita")

    draw = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number=None,
        draw_date=date(2026, 9, 20),
        main_numbers=[153],
        draw_type="ANTIOQUENITA_1",
        source="official-html",
    )

    assert draw.id is not None
    assert draw.draw_number is None
    assert draw.draw_type == "ANTIOQUENITA_1"


def test_create_draw_rejects_missing_lottery(db):
    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.create_draw(db=db, **draw_payload(999))

    assert exc.value.status_code == 404


def test_create_draw_rejects_duplicate_number_per_lottery(db):
    lottery = seed_lottery(db, "MiLoto")
    LotteryDrawService.create_draw(db=db, **draw_payload(lottery.id))

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.create_draw(
            db=db,
            **draw_payload(lottery.id, draw_date=date(2026, 9, 3)),
        )

    assert exc.value.status_code == 409
    assert "draw number" in exc.value.detail.lower()


def test_create_draw_rejects_duplicate_date_per_lottery(db):
    lottery = seed_lottery(db, "MiLoto")
    LotteryDrawService.create_draw(db=db, **draw_payload(lottery.id))

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.create_draw(
            db=db,
            **draw_payload(lottery.id, draw_number="D-002"),
        )

    assert exc.value.status_code == 409
    assert "draw date" in exc.value.detail.lower()


def test_same_number_and_date_are_allowed_for_different_lotteries(db):
    first = seed_lottery(db, "MiLoto")
    second = seed_lottery(db, "Baloto")

    first_draw = LotteryDrawService.create_draw(db=db, **draw_payload(first.id))
    second_draw = LotteryDrawService.create_draw(db=db, **draw_payload(second.id))

    assert first_draw.id != second_draw.id


def test_update_draw_persists_valid_changes(db):
    lottery = seed_lottery(db, "MiLoto")
    draw = LotteryDrawService.create_draw(db=db, **draw_payload(lottery.id))

    updated = LotteryDrawService.update_draw(
        db=db,
        draw_id=draw.id,
        update_data={
            "draw_number": "D-002",
            "draw_date": date(2026, 9, 3),
            "main_numbers": [10, 11, 12, 13, 14],
        },
    )

    assert updated.draw_number == "D-002"
    assert updated.draw_date == date(2026, 9, 3)
    assert updated.main_numbers == [10, 11, 12, 13, 14]


def test_update_draw_rejects_duplicate_number(db):
    lottery = seed_lottery(db, "MiLoto")
    first = LotteryDrawService.create_draw(db=db, **draw_payload(lottery.id))
    second = LotteryDrawService.create_draw(
        db=db,
        **draw_payload(lottery.id, draw_number="D-002", draw_date=date(2026, 9, 3)),
    )

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.update_draw(
            db=db,
            draw_id=second.id,
            update_data={"draw_number": first.draw_number},
        )

    assert exc.value.status_code == 409


def test_update_draw_rejects_duplicate_date(db):
    lottery = seed_lottery(db, "MiLoto")
    first = LotteryDrawService.create_draw(db=db, **draw_payload(lottery.id))
    second = LotteryDrawService.create_draw(
        db=db,
        **draw_payload(lottery.id, draw_number="D-002", draw_date=date(2026, 9, 3)),
    )

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.update_draw(
            db=db,
            draw_id=second.id,
            update_data={"draw_date": first.draw_date},
        )

    assert exc.value.status_code == 409


def test_update_draw_rejects_missing_target_lottery(db):
    lottery = seed_lottery(db, "MiLoto")
    draw = LotteryDrawService.create_draw(db=db, **draw_payload(lottery.id))

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.update_draw(
            db=db,
            draw_id=draw.id,
            update_data={"lottery_id": 999},
        )

    assert exc.value.status_code == 404


def test_delete_draw_removes_record(db):
    lottery = seed_lottery(db, "MiLoto")
    draw = LotteryDrawService.create_draw(db=db, **draw_payload(lottery.id))

    LotteryDrawService.delete_draw(db=db, draw_id=draw.id)

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.get_draw(db=db, draw_id=draw.id)

    assert exc.value.status_code == 404


def test_list_draws_filters_by_lottery_and_orders_by_date(db):
    first = seed_lottery(db, "MiLoto")
    second = seed_lottery(db, "Baloto")
    LotteryDrawService.create_draw(
        db=db,
        **draw_payload(first.id, draw_number="D-001", draw_date=date(2026, 9, 1)),
    )
    LotteryDrawService.create_draw(
        db=db,
        **draw_payload(first.id, draw_number="D-002", draw_date=date(2026, 9, 3)),
    )
    LotteryDrawService.create_draw(
        db=db,
        **draw_payload(second.id, draw_number="D-001", draw_date=date(2026, 9, 2)),
    )

    draws = LotteryDrawService.list_draws(db=db, lottery_id=first.id, limit=100)

    assert [item.draw_number for item in draws] == ["D-002", "D-001"]
    assert all(item.lottery_id == first.id for item in draws)


def test_same_date_is_allowed_for_different_draw_types(db):
    lottery = seed_lottery(db, "Super Astro")
    payload = draw_payload(lottery.id)

    first = LotteryDrawService.create_draw(
        db=db,
        **payload,
        draw_type="ASTRO_SOL",
        draw_time=None,
        source_url="https://example.com/sol",
        validation_json={"source_verified": True, "format_valid": True},
    )
    second = LotteryDrawService.create_draw(
        db=db,
        **payload,
        draw_type="ASTRO_LUNA",
        draw_time=None,
        source_url="https://example.com/luna",
        validation_json={"source_verified": True, "format_valid": True},
    )

    assert first.id != second.id
    assert first.draw_type == "ASTRO_SOL"
    assert second.draw_type == "ASTRO_LUNA"
    assert first.source_url == "https://example.com/sol"
    assert second.source_url == "https://example.com/luna"


def test_same_number_is_rejected_within_same_draw_type(db):
    lottery = seed_lottery(db, "Super Astro")
    LotteryDrawService.create_draw(
        db=db,
        **draw_payload(lottery.id),
        draw_type="ASTRO_SOL",
    )

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.create_draw(
            db=db,
            **draw_payload(lottery.id, draw_date=date(2026, 9, 3)),
            draw_type="ASTRO_SOL",
        )

    assert exc.value.status_code == 409
    assert "draw number" in exc.value.detail.lower()


def test_persist_raw_record_ignores_provenance_only_metadata_changes(db):
    lottery = seed_lottery(db, "MiLoto")
    first = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number="609",
        draw_date=date(2026, 9, 18),
        main_numbers=[1234],
        draw_type="MILOTO_ORDINARY",
        source="official",
        source_url="https://example.test/results",
        metadata_json={
            "raw_result": "1234",
            "series": "055",
            "source_verified": False,
        },
    )

    record = RawDrawRecord(
        lottery_code="miloto",
        draw_type="MILOTO_ORDINARY",
        draw_number="609",
        draw_date=date(2026, 9, 18),
        draw_time=None,
        main_numbers=[1234],
        metadata={
            "raw_result": "1234",
            "series": "055",
            "source_verified": True,
        },
        source_name="official",
        source_url="https://example.test/results",
    )

    same = LotteryDrawService.persist_raw_record(db=db, record=record)

    assert same.id == first.id


def test_persist_raw_record_enriches_missing_metadata_without_conflict(db):
    lottery = seed_lottery(db, "MiLoto")
    first = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number="609",
        draw_date=date(2026, 9, 18),
        main_numbers=[1234],
        draw_type="MILOTO_ORDINARY",
        source="legacy",
        metadata_json={"raw_result": "1234", "source_verified": False},
    )

    record = RawDrawRecord(
        lottery_code="miloto",
        draw_type="MILOTO_ORDINARY",
        draw_number="609",
        draw_date=date(2026, 9, 18),
        draw_time=None,
        main_numbers=[1234],
        metadata={
            "raw_result": "1234",
            "series": "055",
            "source_verified": True,
        },
        source_name="official",
        source_url="https://example.test/results",
    )

    same = LotteryDrawService.persist_raw_record(db=db, record=record)

    assert same.id == first.id
    assert same.metadata_json == {
        "raw_result": "1234",
        "source_verified": True,
        "series": "055",
    }


def test_persist_raw_record_rejects_semantic_metadata_change(db):
    lottery = seed_lottery(db, "MiLoto")
    LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number="609",
        draw_date=date(2026, 9, 18),
        main_numbers=[1234],
        draw_type="MILOTO_ORDINARY",
        source="official",
        metadata_json={"raw_result": "1234", "series": "055"},
    )

    record = RawDrawRecord(
        lottery_code="miloto",
        draw_type="MILOTO_ORDINARY",
        draw_number="609",
        draw_date=date(2026, 9, 18),
        draw_time=None,
        main_numbers=[1234],
        metadata={"raw_result": "1234", "series": "056"},
        source_name="official",
    )

    with pytest.raises(HTTPException) as exc:
        LotteryDrawService.persist_raw_record(db=db, record=record)

    assert exc.value.status_code == 409
