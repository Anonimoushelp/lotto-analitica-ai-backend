from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.lottery_draw import LotteryDraw


class LotteryDrawRepository:
    @staticmethod
    def get_by_id(db: Session, draw_id: int) -> LotteryDraw | None:
        return db.get(LotteryDraw, draw_id)

    @staticmethod
    def get_by_id_for_update(db: Session, draw_id: int) -> LotteryDraw | None:
        """Load a draw with a row lock for transactional mutation paths."""
        statement = select(LotteryDraw).where(LotteryDraw.id == draw_id).with_for_update()
        return db.scalar(statement)

    @staticmethod
    def list(
        db: Session,
        lottery_id: int | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> list[LotteryDraw]:
        statement = (
            select(LotteryDraw)
            .order_by(LotteryDraw.draw_date.desc(), LotteryDraw.id.desc())
            .limit(limit)
        )

        if lottery_id is not None:
            statement = statement.where(LotteryDraw.lottery_id == lottery_id)
        if source is not None:
            statement = statement.where(LotteryDraw.source == source)

        return list(db.scalars(statement).all())

    @staticmethod
    def get_by_number(
        db: Session,
        lottery_id: int,
        draw_number: str,
        source: str | None = None,
    ) -> LotteryDraw | None:
        statement = select(LotteryDraw).where(
            LotteryDraw.lottery_id == lottery_id,
            LotteryDraw.draw_number == draw_number,
        )
        if source is not None:
            statement = statement.where(LotteryDraw.source == source)
        return db.scalar(statement)

    @staticmethod
    def get_by_date(
        db: Session,
        lottery_id: int,
        draw_date,
        source: str | None = None,
    ) -> LotteryDraw | None:
        statement = select(LotteryDraw).where(
            LotteryDraw.lottery_id == lottery_id,
            LotteryDraw.draw_date == draw_date,
        )
        if source is not None:
            statement = statement.where(LotteryDraw.source == source)
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
