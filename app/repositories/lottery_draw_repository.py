from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw


class LotteryDrawRepository:
    @staticmethod
    def get_by_id(
        db: Session,
        draw_id: int,
        tenant_id: int,
    ) -> LotteryDraw | None:
        statement = (
            select(LotteryDraw)
            .join(Lottery, Lottery.id == LotteryDraw.lottery_id)
            .where(
                LotteryDraw.id == draw_id,
                Lottery.tenant_id == tenant_id,
            )
        )
        return db.scalar(statement)

    @staticmethod
    def list(
        db: Session,
        tenant_id: int,
        lottery_id: int | None = None,
        limit: int = 100,
    ) -> list[LotteryDraw]:
        statement = (
            select(LotteryDraw)
            .join(Lottery, Lottery.id == LotteryDraw.lottery_id)
            .where(Lottery.tenant_id == tenant_id)
            .order_by(
                LotteryDraw.draw_date.desc(),
                LotteryDraw.id.desc(),
            )
            .limit(limit)
        )

        if lottery_id is not None:
            statement = statement.where(LotteryDraw.lottery_id == lottery_id)

        return list(db.scalars(statement).all())

    @staticmethod
    def get_by_number(
        db: Session,
        lottery_id: int,
        draw_number: str,
        tenant_id: int,
    ) -> LotteryDraw | None:
        statement = (
            select(LotteryDraw)
            .join(Lottery, Lottery.id == LotteryDraw.lottery_id)
            .where(
                LotteryDraw.lottery_id == lottery_id,
                LotteryDraw.draw_number == draw_number,
                Lottery.tenant_id == tenant_id,
            )
        )
        return db.scalar(statement)

    @staticmethod
    def get_by_date(
        db: Session,
        lottery_id: int,
        draw_date,
        tenant_id: int,
    ) -> LotteryDraw | None:
        statement = (
            select(LotteryDraw)
            .join(Lottery, Lottery.id == LotteryDraw.lottery_id)
            .where(
                LotteryDraw.lottery_id == lottery_id,
                LotteryDraw.draw_date == draw_date,
                Lottery.tenant_id == tenant_id,
            )
        )
        return db.scalar(statement)

    @staticmethod
    def create(db: Session, draw: LotteryDraw) -> LotteryDraw:
        db.add(draw)
        try:
            db.commit()
            db.refresh(draw)
        except SQLAlchemyError:
            db.rollback()
            raise
        return draw

    @staticmethod
    def delete(db: Session, draw: LotteryDraw) -> None:
        db.delete(draw)
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            raise
