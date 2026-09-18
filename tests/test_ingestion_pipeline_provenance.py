from datetime import date



import pytest
from sqlalchemy import create_engine, select
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
    lottery = Lottery(code="PH353-A", name="Pipeline Test")
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
    lottery = Lottery(code="PH353-B", name="Pipeline Isolation")
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
