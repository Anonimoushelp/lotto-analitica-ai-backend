from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.lottery import Lottery


class LotteryRepository:
    @staticmethod
    def list(db: Session) -> list[Lottery]:
        statement = select(Lottery).order_by(Lottery.name)
        return list(db.scalars(statement).all())

    @staticmethod
    def get_by_id(db: Session, lottery_id: int) -> Lottery | None:
        return db.get(Lottery, lottery_id)

    @staticmethod
    def get_by_code(db: Session, code: str) -> Lottery | None:
        statement = select(Lottery).where(Lottery.code == code)
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
