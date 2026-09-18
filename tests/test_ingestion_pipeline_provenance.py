from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.integrations.colombia_registry import get_colombia_source_adapter
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

@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        session.query(LotteryDraw).delete()
        session.query(Lottery).delete()
        session.commit()
        yield session
    finally:
        session.close()


def test_adapter_to_service_repository_database_and_statistics_preserves_provenance(db: Session):
    lottery = Lottery(code="PH353-A", name="Pipeline Test", country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)

    payload = {
        "sorteo": "Sorteo #88001",
        "fecha": "18 de septiembre de 2026",
        "resultado": "1-7-12-28-43-16",
        "metadata": {"provider": "baloto", "format": "historical"},
    }
    normalized = get_colombia_source_adapter("baloto-colombia").parse_draw(payload)

    draw = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number=normalized.draw_number,
        draw_date=normalized.draw_date,
        main_numbers=normalized.main_numbers,
        bonus_numbers=normalized.bonus_numbers,
        source=normalized.source,
        metadata_json=normalized.metadata,
    )

    persisted = db.scalar(select(LotteryDraw).where(LotteryDraw.id == draw.id))
    assert persisted is not None
    assert persisted.source == "baloto-colombia"
    assert persisted.draw_number == "88001"
    assert persisted.draw_date == date(2026, 9, 18)
    assert persisted.main_numbers == [1, 7, 12, 28, 43]
    assert persisted.bonus_numbers == [16]
    assert persisted.metadata_json == {"provider": "baloto", "format": "historical"}

    listed = LotteryDrawService.list_draws(
        db=db, lottery_id=lottery.id, source="baloto-colombia", limit=100
    )
    assert [item.id for item in listed] == [draw.id]

    stats = StatisticalService.analyze(
        listed, lottery_id=lottery.id, source="baloto-colombia"
    )
    assert stats["number_frequency"] == {1: 1, 7: 1, 12: 1, 28: 1, 43: 1}
    assert stats["pair_frequency"]["1-7"] == 1


def test_same_pipeline_identity_remains_isolated_for_revancha_and_miloto(db: Session):
    lottery = Lottery(code="PH353-B", name="Pipeline Isolation", country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)

    inputs = [
        ("revancha-colombia", {"sorteo": 88002, "fecha": "2026-09-18", "resultado": [2, 8, 17, 29, 41, 9]}),
        ("miloto-colombia", {"sorteo": 88002, "fecha": "2026-09-18", "resultado": [3, 8, 17, 29, 39]}),
    ]
    created = []
    for source, payload in inputs:
        normalized = get_colombia_source_adapter(source).parse_draw(payload)
        created.append(
            LotteryDrawService.create_draw(
                db=db,
                lottery_id=lottery.id,
                draw_number=normalized.draw_number,
                draw_date=normalized.draw_date,
                main_numbers=normalized.main_numbers,
                bonus_numbers=normalized.bonus_numbers,
                source=normalized.source,
                metadata_json=normalized.metadata,
            )
        )

    assert [draw.source for draw in created] == [
        "revancha-colombia",
        "miloto-colombia",
    ]
    assert StatisticalService.analyze(
        created, lottery_id=lottery.id, source="revancha-colombia"
    )["number_frequency"] == {2: 1, 8: 1, 17: 1, 29: 1, 41: 1}
    assert StatisticalService.analyze(
        created, lottery_id=lottery.id, source="miloto-colombia"
    )["number_frequency"] == {3: 1, 8: 1, 17: 1, 29: 1, 39: 1}



def test_repeated_ingestion_is_idempotent_by_source_number_and_date(db: Session):
    lottery = Lottery(code="PH354-A", name="Idempotency", country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)

    normalized = get_colombia_source_adapter("baloto-colombia").parse_draw(
        {
            "sorteo": "Sorteo #99001",
            "fecha": "2026-09-18",
            "resultado": "1-7-12-28-43-16",
        }
    )
    first = LotteryDrawService.create_draw(
        db=db, lottery_id=lottery.id, draw_number=normalized.draw_number,
        draw_date=normalized.draw_date, main_numbers=normalized.main_numbers,
        bonus_numbers=normalized.bonus_numbers, source=normalized.source,
        metadata_json=normalized.metadata,
    )
    with pytest.raises(Exception) as exc_info:
        LotteryDrawService.create_draw(
            db=db, lottery_id=lottery.id, draw_number=normalized.draw_number,
            draw_date=normalized.draw_date, main_numbers=normalized.main_numbers,
            bonus_numbers=normalized.bonus_numbers, source=normalized.source,
        )
    assert getattr(exc_info.value, "status_code", None) == 409
    assert db.query(LotteryDraw).count() == 1
    assert db.get(LotteryDraw, first.id).metadata_json is None


def test_same_draw_identity_can_repeat_across_providers_without_collision(db: Session):
    lottery = Lottery(code="PH354-B", name="Provider Idempotency", country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)

    for source, result in (
        ("baloto-colombia", "1-7-12-28-43-16"),
        ("revancha-colombia", "2-8-17-29-41-9"),
    ):
        normalized = get_colombia_source_adapter(source).parse_draw(
            {"sorteo": "Sorteo #99002", "fecha": "2026-09-18", "resultado": result}
        )
        LotteryDrawService.create_draw(
            db=db, lottery_id=lottery.id, draw_number=normalized.draw_number,
            draw_date=normalized.draw_date, main_numbers=normalized.main_numbers,
            bonus_numbers=normalized.bonus_numbers, source=normalized.source,
        )

    assert db.query(LotteryDraw).count() == 2
    assert {draw.source for draw in db.query(LotteryDraw).all()} == {
        "baloto-colombia", "revancha-colombia"
    }



def test_historical_out_of_order_ingestion_keeps_database_and_statistics_consistent(db: Session):
    lottery = Lottery(code="PH355-A", name="Historical Order", country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    adapter = get_colombia_source_adapter("baloto-colombia")
    payloads = [
        {"sorteo": 10003, "fecha": "2026-09-18", "resultado": [3, 4, 10, 20, 30, 7]},
        {"sorteo": 10001, "fecha": "2026-09-10", "resultado": [1, 5, 10, 20, 30, 6]},
        {"sorteo": 10002, "fecha": "2026-09-14", "resultado": [2, 5, 10, 20, 31, 8]},
    ]
    for payload in payloads:
        n = adapter.parse_draw(payload)
        LotteryDrawService.create_draw(
            db=db, lottery_id=lottery.id, draw_number=n.draw_number,
            draw_date=n.draw_date, main_numbers=n.main_numbers,
            bonus_numbers=n.bonus_numbers, source=n.source,
        )
    listed = LotteryDrawService.list_draws(
        db=db, lottery_id=lottery.id, source="baloto-colombia", limit=100
    )
    assert [d.draw_number for d in listed] == ["10003", "10002", "10001"]
    stats = StatisticalService.analyze(listed, lottery_id=lottery.id, source="baloto-colombia")
    assert stats["number_frequency"][10] == 3
    assert stats["number_recency"][10]["last_seen_draw"] == 3


def test_partial_reimport_does_not_mutate_existing_historical_record(db: Session):
    lottery = Lottery(code="PH355-B", name="Partial Reimport", country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    adapter = get_colombia_source_adapter("miloto-colombia")
    n = adapter.parse_draw({"sorteo": 10004, "fecha": "2026-09-18", "resultado": [1, 7, 12, 28, 39], "metadata": {"batch": "original"}})
    first = LotteryDrawService.create_draw(
        db=db, lottery_id=lottery.id, draw_number=n.draw_number,
        draw_date=n.draw_date, main_numbers=n.main_numbers,
        source=n.source, metadata_json=n.metadata,
    )
    retry = adapter.parse_draw({"sorteo": 10004, "fecha": "2026-09-18", "resultado": [1, 7, 12, 28, 39], "metadata": {"batch": "retry"}})
    with pytest.raises(Exception) as exc_info:
        LotteryDrawService.create_draw(
            db=db, lottery_id=lottery.id, draw_number=retry.draw_number,
            draw_date=retry.draw_date, main_numbers=retry.main_numbers,
            source=retry.source, metadata_json=retry.metadata,
        )
    assert getattr(exc_info.value, "status_code", None) == 409
    persisted = db.get(LotteryDraw, first.id)
    assert persisted.metadata_json == {"batch": "original"}


def test_corrected_historical_draw_is_updated_atomically(db: Session):
    lottery = Lottery(code="PH355-C", name="Historical Correction", country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    adapter = get_colombia_source_adapter("baloto-colombia")
    n = adapter.parse_draw({"sorteo": 10005, "fecha": "2026-09-18", "resultado": [1, 7, 12, 28, 43, 16]})
    first = LotteryDrawService.create_draw(
        db=db, lottery_id=lottery.id, draw_number=n.draw_number,
        draw_date=n.draw_date, main_numbers=n.main_numbers,
        bonus_numbers=n.bonus_numbers, source=n.source,
    )
    corrected = adapter.parse_draw({"sorteo": 10005, "fecha": "2026-09-18", "resultado": [1, 7, 13, 28, 43, 16]})
    updated = LotteryDrawService.update_draw(
        db=db, draw_id=first.id, update_data={
            "main_numbers": corrected.main_numbers,
            "bonus_numbers": corrected.bonus_numbers,
        }
    )
    assert updated.id == first.id
    assert updated.main_numbers == [1, 7, 13, 28, 43]
    assert updated.bonus_numbers == [16]
    stats = StatisticalService.analyze([updated], lottery_id=lottery.id, source=n.source)
    assert stats["number_frequency"] == {1: 1, 7: 1, 13: 1, 28: 1, 43: 1}
    assert 12 not in stats["number_frequency"]



def test_corrupt_provider_payload_fails_before_any_database_mutation(db: Session):
    lottery = Lottery(code="PH356-A", name="Corrupt Provider", country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    adapter = get_colombia_source_adapter("baloto-colombia")
    with pytest.raises(ValueError):
        adapter.parse_draw({"sorteo": "Sorteo #20001", "fecha": "2026-09-18", "resultado": [1, 2, 3, 4, 5, 6], "unexpected": "corrupt"})
    assert db.query(LotteryDraw).filter(LotteryDraw.lottery_id == lottery.id).count() == 0


def test_partial_batch_with_late_corrupt_payload_keeps_only_committed_valid_draws(db: Session):
    lottery = Lottery(code="PH356-B", name="Partial Batch", country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    adapter = get_colombia_source_adapter("miloto-colombia")
    valid = adapter.parse_draw({"sorteo": 20002, "fecha": "2026-09-18", "resultado": [1, 7, 12, 28, 39]})
    LotteryDrawService.create_draw(db=db, lottery_id=lottery.id, draw_number=valid.draw_number, draw_date=valid.draw_date, main_numbers=valid.main_numbers, source=valid.source)
    with pytest.raises(ValueError):
        adapter.parse_draw({"sorteo": 20003, "fecha": "2026-09-19", "resultado": [1, 7, 12, 28, 39], "metadata": ["malformed"]})
    persisted = LotteryDrawService.list_draws(db=db, lottery_id=lottery.id, source=valid.source, limit=100)
    assert len(persisted) == 1
    assert persisted[0].draw_number == "20002"


def test_database_conflict_during_ingestion_does_not_leave_partial_record(db: Session):
    lottery = Lottery(code="PH356-C", name="Conflict Rollback", country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    adapter = get_colombia_source_adapter("miloto-colombia")
    first = adapter.parse_draw({"sorteo": 20004, "fecha": "2026-09-20", "resultado": [2, 8, 17, 29, 39]})
    LotteryDrawService.create_draw(db=db, lottery_id=lottery.id, draw_number=first.draw_number, draw_date=first.draw_date, main_numbers=first.main_numbers, source=first.source)
    with pytest.raises(Exception) as exc_info:
        LotteryDrawService.create_draw(db=db, lottery_id=lottery.id, draw_number=first.draw_number, draw_date=first.draw_date, main_numbers=first.main_numbers, source=first.source)
    assert getattr(exc_info.value, "status_code", None) == 409
    assert db.query(LotteryDraw).filter(LotteryDraw.lottery_id == lottery.id).count() == 1



def test_corrupt_provider_payload_fails_before_persistence(db: Session):
    lottery = Lottery(code="PH356-A", name="Corrupt Payload", country="Colombia")
    db.add(lottery)
    db.commit()
    adapter = get_colombia_source_adapter("baloto-colombia")
    with pytest.raises(ValueError, match="Invalid provider draw payload"):
        adapter.parse_draw({"sorteo": 20001, "fecha": "2026-09-18", "resultado": [1, 7, 12, 28, 43, 16], "metadata": ["corrupt"]})
    assert db.query(LotteryDraw).count() == 0


def test_repository_failure_rolls_back_partial_ingestion(monkeypatch, db: Session):
    lottery = Lottery(code="PH356-B", name="Rollback Ingestion", country="Colombia")
    db.add(lottery)
    db.commit()
    original_commit = db.commit
    def fail_commit():
        raise SQLAlchemyError("forced ingestion failure")
    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(SQLAlchemyError):
        LotteryDrawService.create_draw(db=db, lottery_id=lottery.id, draw_number="20002", draw_date=date(2026, 9, 18), main_numbers=[1, 7, 12, 28, 43], source="baloto-colombia")
    monkeypatch.setattr(db, "commit", original_commit)
    db.rollback()
    assert db.query(LotteryDraw).count() == 0


def test_invalid_historical_correction_does_not_partially_mutate_record(db: Session):
    lottery = Lottery(code="PH356-C", name="Atomic Correction", country="Colombia")
    db.add(lottery)
    db.commit()
    draw = LotteryDrawService.create_draw(db=db, lottery_id=lottery.id, draw_number="20003", draw_date=date(2026, 9, 18), main_numbers=[1, 7, 12, 28, 43], bonus_numbers=[16], source="baloto-colombia")
    with pytest.raises(Exception) as exc_info:
        LotteryDrawService.update_draw(db=db, draw_id=draw.id, update_data={"main_numbers": [1, 7, 12, 28, 43], "bonus_numbers": [43]})
    assert getattr(exc_info.value, "status_code", None) == 422
    persisted = db.get(LotteryDraw, draw.id)
    assert persisted.main_numbers == [1, 7, 12, 28, 43]
    assert persisted.bonus_numbers == [16]



def test_reimport_failure_preserves_prior_committed_draws(db: Session):
    lottery = Lottery(code="PH357-A", name="Batch Boundary", country="Colombia")
    db.add(lottery)
    db.commit()
    adapter = get_colombia_source_adapter("miloto-colombia")

    first = adapter.parse_draw(
        {"sorteo": 30001, "fecha": "2026-09-16", "resultado": [1, 7, 12, 28, 39]}
    )
    LotteryDrawService.create_draw(
        db=db, lottery_id=lottery.id, draw_number=first.draw_number,
        draw_date=first.draw_date, main_numbers=first.main_numbers, source=first.source,
    )

    duplicate = adapter.parse_draw(
        {"sorteo": 30001, "fecha": "2026-09-16", "resultado": [1, 7, 12, 28, 39]}
    )
    with pytest.raises(Exception) as exc_info:
        LotteryDrawService.create_draw(
            db=db, lottery_id=lottery.id, draw_number=duplicate.draw_number,
            draw_date=duplicate.draw_date, main_numbers=duplicate.main_numbers,
            source=duplicate.source,
        )
    assert getattr(exc_info.value, "status_code", None) == 409
    rows = db.query(LotteryDraw).all()
    assert len(rows) == 1
    assert rows[0].draw_number == "30001"

def test_reimport_duplicate_does_not_remove_other_committed_history(db: Session):
    lottery = Lottery(code="PH357-B", name="Batch Duplicate", country="Colombia")
    db.add(lottery)
    db.commit()
    adapter = get_colombia_source_adapter("miloto-colombia")
    for number, day in (("30003", "2026-09-18"), ("30004", "2026-09-17")):
        n = adapter.parse_draw({"sorteo": number, "fecha": day, "resultado": [1, 7, 12, 28, 39]})
        LotteryDrawService.create_draw(
            db=db, lottery_id=lottery.id, draw_number=n.draw_number,
            draw_date=n.draw_date, main_numbers=n.main_numbers, source=n.source,
        )
    duplicate = adapter.parse_draw({"sorteo": "30003", "fecha": "2026-09-18", "resultado": [1, 7, 12, 28, 39]})
    with pytest.raises(Exception) as exc_info:
        LotteryDrawService.create_draw(
            db=db, lottery_id=lottery.id, draw_number=duplicate.draw_number,
            draw_date=duplicate.draw_date, main_numbers=duplicate.main_numbers,
            source=duplicate.source,
        )
    assert getattr(exc_info.value, "status_code", None) == 409
    assert db.query(LotteryDraw).count() == 2



def test_concurrent_duplicate_ingestion_is_database_safe(db: Session):
    lottery = Lottery(code="PH358-A", name="Concurrent Ingestion", country="Colombia")
    db.add(lottery)
    db.commit()
    first = LotteryDraw(
        lottery_id=lottery.id, draw_number="40001", draw_date=date(2026, 9, 18),
        main_numbers=[1, 7, 12, 28, 39], source="miloto-colombia",
    )
    second = LotteryDraw(
        lottery_id=lottery.id, draw_number="40001", draw_date=date(2026, 9, 18),
        main_numbers=[1, 7, 12, 28, 39], source="miloto-colombia",
    )
    db.add(first)
    db.commit()
    with pytest.raises(Exception) as exc_info:
        LotteryDrawService.create_draw(
            db=db, lottery_id=lottery.id, draw_number=second.draw_number,
            draw_date=second.draw_date, main_numbers=second.main_numbers,
            source=second.source,
        )
    assert getattr(exc_info.value, "status_code", None) == 409
    assert db.query(LotteryDraw).count() == 1


def test_concurrent_same_identity_remains_isolated_by_provider(db: Session):
    lottery = Lottery(code="PH358-B", name="Concurrent Providers", country="Colombia")
    db.add(lottery)
    db.commit()
    for source, numbers in (
        ("baloto-colombia", [1, 7, 12, 28, 43]),
        ("revancha-colombia", [2, 8, 17, 29, 41]),
    ):
        LotteryDrawService.create_draw(
            db=db, lottery_id=lottery.id, draw_number="40002",
            draw_date=date(2026, 9, 18), main_numbers=numbers,
            bonus_numbers=[16 if source == "baloto-colombia" else 9], source=source,
        )
    assert db.query(LotteryDraw).count() == 2
    assert {draw.source for draw in db.query(LotteryDraw).all()} == {
        "baloto-colombia", "revancha-colombia"
    }


def test_concurrent_retry_conflict_cannot_duplicate_statistical_counts(db: Session):
    lottery = Lottery(code="PH359-A", name="Concurrent Statistics", country="Colombia")
    db.add(lottery)
    db.commit()
    adapter = get_colombia_source_adapter("miloto-colombia")
    normalized = adapter.parse_draw(
        {"sorteo": 50001, "fecha": "2026-09-18", "resultado": [1, 7, 12, 28, 39]}
    )

    LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number=normalized.draw_number,
        draw_date=normalized.draw_date,
        main_numbers=normalized.main_numbers,
        source=normalized.source,
    )

    with pytest.raises(Exception) as exc_info:
        LotteryDrawService.create_draw(
            db=db,
            lottery_id=lottery.id,
            draw_number=normalized.draw_number,
            draw_date=normalized.draw_date,
            main_numbers=normalized.main_numbers,
            source=normalized.source,
        )

    assert getattr(exc_info.value, "status_code", None) == 409
    persisted = LotteryDrawService.list_draws(
        db=db, lottery_id=lottery.id, source="miloto-colombia", limit=100
    )
    stats = StatisticalService.analyze(
        persisted, lottery_id=lottery.id, source="miloto-colombia"
    )
    assert len(persisted) == 1
    assert stats["sum_distribution"]["count"] == 1
    assert stats["number_frequency"] == {1: 1, 7: 1, 12: 1, 28: 1, 39: 1}


def test_concurrent_provider_retries_do_not_cross_contaminate_statistics(db: Session):
    lottery = Lottery(code="PH359-B", name="Provider Statistics Isolation", country="Colombia")
    db.add(lottery)
    db.commit()

    payloads = {
        "baloto-colombia": [1, 7, 12, 28, 43],
        "revancha-colombia": [2, 8, 17, 29, 41],
    }
    for source, numbers in payloads.items():
        LotteryDrawService.create_draw(
            db=db,
            lottery_id=lottery.id,
            draw_number="50002",
            draw_date=date(2026, 9, 18),
            main_numbers=numbers,
            bonus_numbers=[16 if source == "baloto-colombia" else 9],
            source=source,
        )

    for source, numbers in payloads.items():
        with pytest.raises(Exception) as exc_info:
            LotteryDrawService.create_draw(
                db=db,
                lottery_id=lottery.id,
                draw_number="50002",
                draw_date=date(2026, 9, 18),
                main_numbers=numbers,
                bonus_numbers=[16 if source == "baloto-colombia" else 9],
                source=source,
            )
        assert getattr(exc_info.value, "status_code", None) == 409

    all_draws = LotteryDrawService.list_draws(
        db=db, lottery_id=lottery.id, limit=100
    )
    assert len(all_draws) == 2

    for source, numbers in payloads.items():
        provider_draws = LotteryDrawService.list_draws(
            db=db, lottery_id=lottery.id, source=source, limit=100
        )
        stats = StatisticalService.analyze(
            provider_draws, lottery_id=lottery.id, source=source
        )
        assert stats["number_frequency"] == {number: 1 for number in numbers}
        assert stats["sum_distribution"]["count"] == 1


def test_historical_correction_removes_old_values_from_statistics(db: Session):
    lottery = Lottery(
        code="PH360-A",
        name="Concurrent Historical Correction",
        country="Colombia",
    )
    db.add(lottery)
    db.commit()

    draw = LotteryDrawService.create_draw(
        db=db, lottery_id=lottery.id, draw_number="60001",
        draw_date=date(2026, 9, 18), main_numbers=[1, 7, 12, 28, 39],
        source="miloto-colombia",
    )
    before = StatisticalService.analyze(
        [draw], lottery_id=lottery.id, source="miloto-colombia"
    )
    assert before["number_frequency"][12] == 1

    updated = LotteryDrawService.update_draw(
        db=db, draw_id=draw.id,
        update_data={"main_numbers": [2, 8, 17, 29, 39]},
    )
    after = StatisticalService.analyze(
        [updated], lottery_id=lottery.id, source="miloto-colombia"
    )
    assert after["number_frequency"] == {2: 1, 8: 1, 17: 1, 29: 1, 39: 1}
    assert 12 not in after["number_frequency"]


def test_delete_after_concurrent_retry_leaves_statistics_empty(db: Session):
    lottery = Lottery(
        code="PH360-B",
        name="Delete Retry Statistics",
        country="Colombia",
    )
    db.add(lottery)
    db.commit()

    draw = LotteryDrawService.create_draw(
        db=db, lottery_id=lottery.id, draw_number="60002",
        draw_date=date(2026, 9, 18), main_numbers=[3, 8, 17, 29, 39],
        source="miloto-colombia",
    )
    with pytest.raises(Exception) as exc_info:
        LotteryDrawService.create_draw(
            db=db, lottery_id=lottery.id, draw_number="60002",
            draw_date=date(2026, 9, 18), main_numbers=[3, 8, 17, 29, 39],
            source="miloto-colombia",
        )
    assert getattr(exc_info.value, "status_code", None) == 409

    LotteryDrawService.delete_draw(db=db, draw_id=draw.id)
    remaining = LotteryDrawService.list_draws(
        db=db, lottery_id=lottery.id, source="miloto-colombia", limit=100
    )
    assert remaining == []
    assert StatisticalService.overview(
        db=db, lottery_id=lottery.id, source="miloto-colombia"
    ) == {
        "module_status": "STANDBY",
        "algorithms_count": 0,
        "draws_analyzed": 0,
    }


def test_historical_correction_preserves_other_provider_statistics(db: Session):
    lottery = Lottery(
        code="PH360-C",
        name="Correction Provider Isolation",
        country="Colombia",
    )
    db.add(lottery)
    db.commit()

    baloto = LotteryDrawService.create_draw(
        db=db, lottery_id=lottery.id, draw_number="60003",
        draw_date=date(2026, 9, 18), main_numbers=[1, 7, 12, 28, 43],
        bonus_numbers=[16], source="baloto-colombia",
    )
    LotteryDrawService.create_draw(
        db=db, lottery_id=lottery.id, draw_number="60003",
        draw_date=date(2026, 9, 18), main_numbers=[2, 8, 17, 29, 41],
        bonus_numbers=[9], source="revancha-colombia",
    )

    LotteryDrawService.update_draw(
        db=db, draw_id=baloto.id,
        update_data={"main_numbers": [3, 8, 18, 30, 43]},
    )

    baloto_stats = StatisticalService.analyze(
        LotteryDrawService.list_draws(
            db=db, lottery_id=lottery.id, source="baloto-colombia", limit=100
        ),
        lottery_id=lottery.id, source="baloto-colombia",
    )
    revancha_stats = StatisticalService.analyze(
        LotteryDrawService.list_draws(
            db=db, lottery_id=lottery.id, source="revancha-colombia", limit=100
        ),
        lottery_id=lottery.id, source="revancha-colombia",
    )

    assert baloto_stats["number_frequency"] == {3: 1, 8: 1, 18: 1, 30: 1, 43: 1}
    assert revancha_stats["number_frequency"] == {2: 1, 8: 1, 17: 1, 29: 1, 41: 1}


def test_concurrent_reassignment_keeps_statistics_isolated_by_lottery_and_provider(db: Session):
    source_lottery = Lottery(
        code="PH361-A",
        name="Concurrent Reassignment Source",
        country="Colombia",
    )
    target_lottery = Lottery(
        code="PH361-B",
        name="Concurrent Reassignment Target",
        country="Colombia",
    )
    db.add_all([source_lottery, target_lottery])
    db.commit()
    db.refresh(source_lottery)
    db.refresh(target_lottery)

    baloto = LotteryDrawService.create_draw(
        db=db,
        lottery_id=source_lottery.id,
        draw_number="61001",
        draw_date=date(2026, 9, 18),
        main_numbers=[1, 7, 12, 28, 43],
        bonus_numbers=[16],
        source="baloto-colombia",
    )
    revancha = LotteryDrawService.create_draw(
        db=db,
        lottery_id=source_lottery.id,
        draw_number="61001",
        draw_date=date(2026, 9, 18),
        main_numbers=[2, 8, 17, 29, 41],
        bonus_numbers=[9],
        source="revancha-colombia",
    )

    reassignment_session = SessionLocal()
    statistics_session = SessionLocal()
    try:
        reassigned = LotteryDrawService.update_draw(
            db=reassignment_session,
            draw_id=baloto.id,
            update_data={"lottery_id": target_lottery.id},
        )
        assert reassigned.lottery_id == target_lottery.id

        source_baloto = StatisticalService.analyze(
            LotteryDrawService.list_draws(
                db=statistics_session,
                lottery_id=source_lottery.id,
                source="baloto-colombia",
                limit=100,
            ),
            lottery_id=source_lottery.id,
            source="baloto-colombia",
        )
        source_revancha = StatisticalService.analyze(
            LotteryDrawService.list_draws(
                db=statistics_session,
                lottery_id=source_lottery.id,
                source="revancha-colombia",
                limit=100,
            ),
            lottery_id=source_lottery.id,
            source="revancha-colombia",
        )
        target_baloto = StatisticalService.analyze(
            LotteryDrawService.list_draws(
                db=statistics_session,
                lottery_id=target_lottery.id,
                source="baloto-colombia",
                limit=100,
            ),
            lottery_id=target_lottery.id,
            source="baloto-colombia",
        )

        assert source_baloto == {
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
        assert source_revancha["number_frequency"] == {
            2: 1,
            8: 1,
            17: 1,
            29: 1,
            41: 1,
        }
        assert target_baloto["number_frequency"] == {
            1: 1,
            7: 1,
            12: 1,
            28: 1,
            43: 1,
        }
        assert revancha.lottery_id == source_lottery.id
    finally:
        reassignment_session.close()
        statistics_session.close()


def test_stale_concurrent_update_reloads_reassigned_draw_before_statistics(db: Session):
    source_lottery = Lottery(
        code="PH361-C",
        name="Stale Reassignment Source",
        country="Colombia",
    )
    target_lottery = Lottery(
        code="PH361-D",
        name="Stale Reassignment Target",
        country="Colombia",
    )
    db.add_all([source_lottery, target_lottery])
    db.commit()
    db.refresh(source_lottery)
    db.refresh(target_lottery)

    draw = LotteryDrawService.create_draw(
        db=db,
        lottery_id=source_lottery.id,
        draw_number="61002",
        draw_date=date(2026, 9, 18),
        main_numbers=[3, 8, 17, 29, 39],
        source="miloto-colombia",
    )

    stale_session = SessionLocal()
    reassignment_session = SessionLocal()
    try:
        stale_draw = stale_session.get(LotteryDraw, draw.id)
        assert stale_draw is not None
        assert stale_draw.lottery_id == source_lottery.id

        LotteryDrawService.update_draw(
            db=reassignment_session,
            draw_id=draw.id,
            update_data={"lottery_id": target_lottery.id},
        )

        updated = LotteryDrawService.update_draw(
            db=stale_session,
            draw_id=draw.id,
            update_data={"main_numbers": [4, 9, 18, 30, 38]},
        )

        assert updated.lottery_id == target_lottery.id
        assert updated.main_numbers == [4, 9, 18, 30, 38]

        source_stats = StatisticalService.analyze(
            LotteryDrawService.list_draws(
                db=stale_session,
                lottery_id=source_lottery.id,
                source="miloto-colombia",
                limit=100,
            ),
            lottery_id=source_lottery.id,
            source="miloto-colombia",
        )
        target_stats = StatisticalService.analyze(
            LotteryDrawService.list_draws(
                db=stale_session,
                lottery_id=target_lottery.id,
                source="miloto-colombia",
                limit=100,
            ),
            lottery_id=target_lottery.id,
            source="miloto-colombia",
        )

        assert source_stats["sum_distribution"]["count"] == 0
        assert target_stats["number_frequency"] == {
            4: 1,
            9: 1,
            18: 1,
            30: 1,
            38: 1,
        }
        assert 3 not in target_stats["number_frequency"]
    finally:
        stale_session.close()
        reassignment_session.close()


def test_update_then_concurrent_delete_leaves_statistics_empty_and_allows_reingestion(db: Session):
    lottery = Lottery(
        code="PH363-A",
        name="Update Delete Reingestion",
        country="Colombia",
    )
    db.add(lottery)
    db.commit()
    db.refresh(lottery)

    draw = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number="63001",
        draw_date=date(2026, 9, 18),
        main_numbers=[1, 7, 12, 28, 39],
        source="miloto-colombia",
    )

    update_session = SessionLocal()
    delete_session = SessionLocal()
    try:
        updated = LotteryDrawService.update_draw(
            db=update_session,
            draw_id=draw.id,
            update_data={"main_numbers": [2, 8, 17, 29, 39]},
        )
        assert updated.main_numbers == [2, 8, 17, 29, 39]

        LotteryDrawService.delete_draw(db=delete_session, draw_id=draw.id)

        assert LotteryDrawService.list_draws(
            db=db, lottery_id=lottery.id, source="miloto-colombia", limit=100
        ) == []
        assert StatisticalService.overview(
            db=db, lottery_id=lottery.id, source="miloto-colombia"
        ) == {
            "module_status": "STANDBY",
            "algorithms_count": 0,
            "draws_analyzed": 0,
        }

        reingested = LotteryDrawService.create_draw(
            db=db,
            lottery_id=lottery.id,
            draw_number="63001",
            draw_date=date(2026, 9, 18),
            main_numbers=[4, 9, 18, 30, 38],
            source="miloto-colombia",
        )
        stats = StatisticalService.analyze(
            [reingested],
            lottery_id=lottery.id,
            source="miloto-colombia",
        )
        assert stats["number_frequency"] == {
            4: 1,
            9: 1,
            18: 1,
            30: 1,
            38: 1,
        }
    finally:
        update_session.close()
        delete_session.close()


def test_stale_update_after_concurrent_delete_cannot_restore_deleted_statistics(db: Session):
    lottery = Lottery(
        code="PH363-B",
        name="Stale Delete Update",
        country="Colombia",
    )
    db.add(lottery)
    db.commit()
    db.refresh(lottery)

    draw = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number="63002",
        draw_date=date(2026, 9, 18),
        main_numbers=[3, 8, 17, 29, 39],
        source="miloto-colombia",
    )

    stale_session = SessionLocal()
    delete_session = SessionLocal()
    try:
        stale_draw = stale_session.get(LotteryDraw, draw.id)
        assert stale_draw is not None

        LotteryDrawService.delete_draw(db=delete_session, draw_id=draw.id)

        with pytest.raises(Exception) as exc_info:
            LotteryDrawService.update_draw(
                db=stale_session,
                draw_id=draw.id,
                update_data={"main_numbers": [4, 9, 18, 30, 38]},
            )
        assert getattr(exc_info.value, "status_code", None) == 404

        assert LotteryDrawService.list_draws(
            db=db, lottery_id=lottery.id, source="miloto-colombia", limit=100
        ) == []
        assert StatisticalService.overview(
            db=db, lottery_id=lottery.id, source="miloto-colombia"
        ) == {
            "module_status": "STANDBY",
            "algorithms_count": 0,
            "draws_analyzed": 0,
        }
    finally:
        stale_session.close()
        delete_session.close()


def test_concurrent_historical_corrections_leave_only_latest_values_and_single_record(db: Session):
    lottery = Lottery(
        code="PH364-A",
        name="Concurrent Corrections",
        country="Colombia",
    )
    db.add(lottery)
    db.commit()
    db.refresh(lottery)

    draw = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number="64001",
        draw_date=date(2026, 9, 18),
        main_numbers=[1, 7, 12, 28, 39],
        source="miloto-colombia",
    )

    first_session = SessionLocal()
    second_session = SessionLocal()
    try:
        first = LotteryDrawService.update_draw(
            db=first_session,
            draw_id=draw.id,
            update_data={"main_numbers": [2, 8, 17, 29, 39]},
        )
        second = LotteryDrawService.update_draw(
            db=second_session,
            draw_id=draw.id,
            update_data={"main_numbers": [4, 9, 18, 30, 38]},
        )

        assert first.id == second.id == draw.id
        persisted = db.get(LotteryDraw, draw.id)
        assert persisted is not None
        assert persisted.main_numbers == [4, 9, 18, 30, 38]

        rows = LotteryDrawService.list_draws(
            db=db,
            lottery_id=lottery.id,
            source="miloto-colombia",
            limit=100,
        )
        stats = StatisticalService.analyze(
            rows,
            lottery_id=lottery.id,
            source="miloto-colombia",
        )
        assert len(rows) == 1
        assert stats["number_frequency"] == {
            4: 1,
            9: 1,
            18: 1,
            30: 1,
            38: 1,
        }
        assert 1 not in stats["number_frequency"]
        assert 2 not in stats["number_frequency"]
    finally:
        first_session.close()
        second_session.close()


def test_reimport_after_historical_correction_preserves_corrected_record_and_statistics(
    db: Session,
):
    lottery = Lottery(
        code="PH364-B",
        name="Correction Reimport",
        country="Colombia",
    )
    db.add(lottery)
    db.commit()
    db.refresh(lottery)

    adapter = get_colombia_source_adapter("baloto-colombia")
    original = adapter.parse_draw(
        {
            "sorteo": 64002,
            "fecha": "2026-09-18",
            "resultado": [1, 7, 12, 28, 43, 16],
        }
    )
    draw = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number=original.draw_number,
        draw_date=original.draw_date,
        main_numbers=original.main_numbers,
        bonus_numbers=original.bonus_numbers,
        source=original.source,
    )

    corrected = LotteryDrawService.update_draw(
        db=db,
        draw_id=draw.id,
        update_data={
            "main_numbers": [3, 8, 18, 30, 43],
            "bonus_numbers": [16],
        },
    )

    retry = adapter.parse_draw(
        {
            "sorteo": 64002,
            "fecha": "2026-09-18",
            "resultado": [1, 7, 12, 28, 43, 16],
        }
    )
    with pytest.raises(Exception) as exc_info:
        LotteryDrawService.create_draw(
            db=db,
            lottery_id=lottery.id,
            draw_number=retry.draw_number,
            draw_date=retry.draw_date,
            main_numbers=retry.main_numbers,
            bonus_numbers=retry.bonus_numbers,
            source=retry.source,
        )
    assert getattr(exc_info.value, "status_code", None) == 409

    persisted = db.get(LotteryDraw, corrected.id)
    assert persisted is not None
    assert persisted.main_numbers == [3, 8, 18, 30, 43]
    assert persisted.bonus_numbers == [16]

    stats = StatisticalService.analyze(
        [persisted],
        lottery_id=lottery.id,
        source="baloto-colombia",
    )
    assert stats["number_frequency"] == {3: 1, 8: 1, 18: 1, 30: 1, 43: 1}
    assert 1 not in stats["number_frequency"]
    assert 12 not in stats["number_frequency"]


def test_multiple_historical_corrections_and_reimports_preserve_provider_isolation(
    db: Session,
):
    lottery = Lottery(
        code="PH364-C",
        name="Corrections Provider Isolation",
        country="Colombia",
    )
    db.add(lottery)
    db.commit()
    db.refresh(lottery)

    baloto = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number="64003",
        draw_date=date(2026, 9, 18),
        main_numbers=[1, 7, 12, 28, 43],
        bonus_numbers=[16],
        source="baloto-colombia",
    )
    revancha = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number="64003",
        draw_date=date(2026, 9, 18),
        main_numbers=[2, 8, 17, 29, 41],
        bonus_numbers=[9],
        source="revancha-colombia",
    )

    LotteryDrawService.update_draw(
        db=db,
        draw_id=baloto.id,
        update_data={"main_numbers": [4, 9, 18, 30, 43]},
    )
    LotteryDrawService.update_draw(
        db=db,
        draw_id=baloto.id,
        update_data={"main_numbers": [5, 10, 19, 31, 42]},
    )

    for source, numbers, bonus in (
        ("baloto-colombia", [1, 7, 12, 28, 43], [16]),
        ("revancha-colombia", [2, 8, 17, 29, 41], [9]),
    ):
        with pytest.raises(Exception) as exc_info:
            LotteryDrawService.create_draw(
                db=db,
                lottery_id=lottery.id,
                draw_number="64003",
                draw_date=date(2026, 9, 18),
                main_numbers=numbers,
                bonus_numbers=bonus,
                source=source,
            )
        assert getattr(exc_info.value, "status_code", None) == 409

    baloto_stats = StatisticalService.analyze(
        LotteryDrawService.list_draws(
            db=db,
            lottery_id=lottery.id,
            source="baloto-colombia",
            limit=100,
        ),
        lottery_id=lottery.id,
        source="baloto-colombia",
    )
    revancha_stats = StatisticalService.analyze(
        LotteryDrawService.list_draws(
            db=db,
            lottery_id=lottery.id,
            source="revancha-colombia",
            limit=100,
        ),
        lottery_id=lottery.id,
        source="revancha-colombia",
    )

    assert baloto_stats["number_frequency"] == {
        5: 1,
        10: 1,
        19: 1,
        31: 1,
        42: 1,
    }
    assert revancha_stats["number_frequency"] == {
        2: 1,
        8: 1,
        17: 1,
        29: 1,
        41: 1,
    }
    assert baloto.lottery_id == revancha.lottery_id == lottery.id
