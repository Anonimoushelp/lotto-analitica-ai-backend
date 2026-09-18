from datetime import date

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
        source: str | None = None,
        limit: int = 100,
    ) -> list[LotteryDraw]:
        return LotteryDrawRepository.list(
            db=db,
            lottery_id=lottery_id,
            source=source,
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
        draw_date: date,
        main_numbers: list[int],
        bonus_numbers: list[int] | None = None,
        source: str = "legacy-import",
        metadata_json: dict | None = None,
    ) -> LotteryDraw:
        lottery = db.get(Lottery, lottery_id)

        if lottery is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lottery not found",
            )

        if not isinstance(source, str) or not source.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Lottery draw source is required",
            )
        source = source.strip()

        existing_number = LotteryDrawRepository.get_by_number(
            db=db,
            lottery_id=lottery_id,
            draw_number=draw_number,
            source=source,
        )

        if existing_number is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Draw number already exists for this lottery",
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
                detail="Draw date already exists for this lottery",
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
        draw = LotteryDrawRepository.get_by_id_for_update(
            db=db,
            draw_id=draw_id,
        )
        if draw is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lottery draw not found",
            )

        new_lottery_id = update_data.get("lottery_id", draw.lottery_id)
        new_draw_number = update_data.get("draw_number", draw.draw_number)
        new_draw_date = update_data.get("draw_date", draw.draw_date)

        source_was_provided = "source" in update_data
        requested_source = update_data.get("source")
        if source_was_provided:
            if not isinstance(requested_source, str) or not requested_source.strip():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Lottery draw source is required",
                )
            if requested_source.strip() != draw.source:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Lottery draw source is immutable",
                )

        new_source = draw.source

        if not isinstance(new_source, str) or not new_source.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Lottery draw source is required",
            )
        new_source = new_source.strip()

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
                detail="Draw number already exists for this lottery",
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
                detail="Draw date already exists for this lottery",
            )

        merged_main_numbers = update_data.get("main_numbers", draw.main_numbers)
        merged_bonus_numbers = update_data.get("bonus_numbers", draw.bonus_numbers)
        if (
            merged_main_numbers is not None
            and merged_bonus_numbers is not None
            and set(merged_main_numbers) & set(merged_bonus_numbers)
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="bonus_numbers cannot overlap main_numbers",
            )

        for field, value in update_data.items():
            setattr(draw, field, new_source if field == "source" else value)

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
                detail="Lottery draw conflicts with an existing record",
            ) from exc
