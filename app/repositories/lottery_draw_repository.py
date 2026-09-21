from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.lottery_draw import LotteryDraw


class LotteryDrawRepository:
    @staticmethod
    def get_by_id(db: Session, draw_id: int) -> LotteryDraw | None:
        return db.get(LotteryDraw, draw_id)

    @staticmethod
    def list(
        db: Session,
        lottery_id: int | None = None,
        limit: int = 100,
    ) -> list[LotteryDraw]:
        statement = (
            select(LotteryDraw)
            .order_by(
                LotteryDraw.draw_datetime.desc().nullslast(),
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
    ) -> LotteryDraw | None:
        statement = select(LotteryDraw).where(
            LotteryDraw.lottery_id == lottery_id,
            LotteryDraw.draw_number == draw_number,
        )
        return db.scalar(statement)

    @staticmethod
    def get_by_ingestion_key(db: Session, ingestion_key: str) -> LotteryDraw | None:
        statement = select(LotteryDraw).where(LotteryDraw.ingestion_key == ingestion_key)
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
