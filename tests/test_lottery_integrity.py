from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.lottery import Lottery
from app.repositories.lottery_repository import LotteryRepository
from app.services.lottery_service import LotteryService

engine = create_engine("sqlite://")
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=engine)


def new_lottery(code: str) -> Lottery:
    now = datetime.now(UTC)
    return Lottery(
        code=code,
        name=f"Lottery {code}",
        country="CO",
        active=True,
        created_at=now,
        updated_at=now,
    )


def test_lottery_repository_rolls_back_failed_unique_insert():
    db = TestingSessionLocal()
    try:
        db.add(new_lottery("ROLLBACK-1"))
        db.commit()

        duplicate = new_lottery("ROLLBACK-1")
        with pytest.raises(Exception):
            LotteryRepository.create(db=db, lottery=duplicate)

        db.add(new_lottery("ROLLBACK-2"))
        db.commit()
        assert db.query(Lottery).count() == 2
    finally:
        db.close()


def test_lottery_service_rejects_duplicate_code():
    db = TestingSessionLocal()
    try:
        db.add(new_lottery("DUP-1"))
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            LotteryService.create_lottery(
                db=db,
                payload={
                    "code": "DUP-1",
                    "name": "Duplicate",
                    "country": "CO",
                    "active": True,
                },
            )

        assert exc_info.value.status_code == 409
    finally:
        db.close()


def test_lottery_service_rejects_update_to_existing_code():
    db = TestingSessionLocal()
    try:
        first = new_lottery("UPD-1")
        second = new_lottery("UPD-2")
        db.add_all([first, second])
        db.commit()
        db.refresh(second)

        with pytest.raises(HTTPException) as exc_info:
            LotteryService.update_lottery(
                db=db,
                lottery_id=second.id,
                update_data={"code": "UPD-1"},
            )

        assert exc_info.value.status_code == 409
    finally:
        db.close()


def test_lottery_service_returns_404_for_missing_lottery():
    db = TestingSessionLocal()
    try:
        with pytest.raises(HTTPException) as exc_info:
            LotteryService.get_lottery(db=db, lottery_id=99999)
        assert exc_info.value.status_code == 404
    finally:
        db.close()
