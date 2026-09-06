from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.lottery import Lottery


class LotteryRepository:
    @staticmethod
    def list(db: Session, tenant_id: int) -> list[Lottery]:
        statement = (
            select(Lottery)
            .where(Lottery.tenant_id == tenant_id)
            .order_by(Lottery.name)
        )
        return list(db.scalars(statement).all())

    @staticmethod
    def get_by_id(db: Session, lottery_id: int, tenant_id: int) -> Lottery | None:
        statement = select(Lottery).where(
            Lottery.id == lottery_id,
            Lottery.tenant_id == tenant_id,
        )
        return db.scalar(statement)

    @staticmethod
    def get_by_code(db: Session, code: str, tenant_id: int) -> Lottery | None:
        statement = select(Lottery).where(
            Lottery.code == code,
            Lottery.tenant_id == tenant_id,
        )
        return db.scalar(statement)

    @staticmethod
    def create(db: Session, lottery: Lottery) -> Lottery:
        db.add(lottery)
        try:
            db.commit()
            db.refresh(lottery)
        except SQLAlchemyError:
            db.rollback()
            raise
        return lottery

    @staticmethod
    def update(db: Session, lottery: Lottery) -> Lottery:
        try:
            db.commit()
            db.refresh(lottery)
        except SQLAlchemyError:
            db.rollback()
            raise
        return lottery

    @staticmethod
    def delete(db: Session, lottery: Lottery) -> None:
        db.delete(lottery)
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            raise
