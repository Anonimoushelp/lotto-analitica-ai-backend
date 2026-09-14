from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.repositories.lottery_draw_repository import LotteryDrawRepository


class LotteryDrawService:
    @staticmethod
    def list_draws(
        db: Session,
        lottery_id: int | None = None,
        limit: int = 100,
    ) -> list[LotteryDraw]:
        return LotteryDrawRepository.list(
            db=db,
            lottery_id=lottery_id,
            limit=limit,
        )

    @staticmethod
    def get_draw(
        db: Session,
        draw_id: int,
    ) -> LotteryDraw:
        draw = LotteryDrawRepository.get_by_id(
            db=db,
            draw_id=draw_id,
        )

        if draw is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lottery draw not found",
            )

        return draw

    @staticmethod
    def create_draw(
        db: Session,
        lottery_id: int,
        draw_number: str,
        draw_date,
        main_numbers: list[int],
        bonus_numbers: list[int] | None = None,
        source: str | None = None,
        metadata_json: dict | None = None,
    ) -> LotteryDraw:
        lottery = db.get(Lottery, lottery_id)

        if lottery is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lottery not found",
            )

        existing_number = LotteryDrawRepository.get_by_number(
            db=db,
            lottery_id=lottery_id,
            draw_number=draw_number,
            source=source,
        )

        if existing_number is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Draw number already exists for this lottery and source",
            )

        existing_date = LotteryDrawRepository.get_by_date(
            db=db,
            lottery_id=lottery_id,
            draw_date=draw_date,
            source=source,
        )

        if existing_date is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Draw date already exists for this lottery and source",
            )

        draw = LotteryDraw(
            lottery_id=lottery_id,
            draw_number=draw_number,
            draw_date=draw_date,
            main_numbers=main_numbers,
            bonus_numbers=bonus_numbers,
            source=source,
            metadata_json=metadata_json,
        )

        try:
            return LotteryDrawRepository.create(
                db=db,
                draw=draw,
            )
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Lottery draw conflicts with an existing record",
            ) from exc

    @staticmethod
    def update_draw(
        db: Session,
        draw_id: int,
        update_data: dict,
    ) -> LotteryDraw:
        draw = LotteryDrawService.get_draw(
            db=db,
            draw_id=draw_id,
        )

        new_lottery_id = update_data.get("lottery_id", draw.lottery_id)
        new_draw_number = update_data.get("draw_number", draw.draw_number)
        new_draw_date = update_data.get("draw_date", draw.draw_date)
        new_source = update_data.get("source", draw.source)

        lottery = db.get(Lottery, new_lottery_id)

        if lottery is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lottery not found",
            )

        existing_number = LotteryDrawRepository.get_by_number(
            db=db,
            lottery_id=new_lottery_id,
            draw_number=new_draw_number,
            source=new_source,
        )

        if existing_number is not None and existing_number.id != draw_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Draw number already exists for this lottery and source",
            )

        existing_date = LotteryDrawRepository.get_by_date(
            db=db,
            lottery_id=new_lottery_id,
            draw_date=new_draw_date,
            source=new_source,
        )

        if existing_date is not None and existing_date.id != draw_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Draw date already exists for this lottery and source",
            )

        for field, value in update_data.items():
            setattr(draw, field, value)

        try:
            db.commit()
            db.refresh(draw)
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Lottery draw conflicts with an existing record",
            ) from exc

        return draw

    @staticmethod
    def delete_draw(db: Session, draw_id: int) -> None:
        draw = LotteryDrawService.get_draw(db=db, draw_id=draw_id)
        try:
            LotteryDrawRepository.delete(db=db, draw=draw)
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Lottery draw cannot be deleted",
            ) from exc
