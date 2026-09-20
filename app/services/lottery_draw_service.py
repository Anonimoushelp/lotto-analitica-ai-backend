from datetime import date
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.draw_result import DrawResult
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
        return LotteryDrawRepository.list(db=db, lottery_id=lottery_id, limit=limit)

    @staticmethod
    def get_draw(db: Session, draw_id: int) -> LotteryDraw:
        draw = LotteryDrawRepository.get_by_id(db=db, draw_id=draw_id)
        if draw is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lottery draw not found",
            )
        return draw

    @staticmethod
    def _build_results(
        draw: LotteryDraw,
        result_groups: list[dict[str, Any]] | None,
    ) -> None:
        groups = result_groups or []

        # Backward-compatible normalization of the legacy fields.
        if not groups and draw.main_numbers:
            groups.extend(
                {
                    "group_code": "main",
                    "position": position,
                    "value": str(number),
                    "numeric_value": number,
                }
                for position, number in enumerate(draw.main_numbers, start=1)
            )
            if draw.bonus_numbers:
                groups.extend(
                    {
                        "group_code": "bonus",
                        "position": position,
                        "value": str(number),
                        "numeric_value": number,
                    }
                    for position, number in enumerate(draw.bonus_numbers, start=1)
                )

        draw.results.clear()
        for item in groups:
            numeric_value = item.get("numeric_value")
            value = str(item["value"])
            if numeric_value is None:
                try:
                    numeric_value = int(value)
                except ValueError:
                    pass

            draw.results.append(
                DrawResult(
                    group_code=item["group_code"],
                    position=item["position"],
                    value=value,
                    numeric_value=numeric_value,
                )
            )

    @staticmethod
    def create_draw(
        db: Session,
        lottery_id: int,
        draw_number: str,
        draw_date: date,
        main_numbers: list[int] | None = None,
        bonus_numbers: list[int] | None = None,
        result_groups: list[dict[str, Any]] | None = None,
        draw_datetime=None,
        source: str | None = None,
        source_type: str | None = None,
        source_reference: str | None = None,
        raw_payload: dict[str, Any] | None = None,
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
        )
        if existing_number is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Draw number already exists for this lottery",
            )

        draw = LotteryDraw(
            lottery_id=lottery_id,
            draw_number=draw_number,
            draw_date=draw_date,
            draw_datetime=draw_datetime,
            main_numbers=main_numbers,
            bonus_numbers=bonus_numbers,
            source=source,
            source_type=source_type,
            source_reference=source_reference,
            raw_payload=raw_payload,
            metadata_json=metadata_json,
        )
        LotteryDrawService._build_results(draw, result_groups)

        try:
            return LotteryDrawRepository.create(db=db, draw=draw)
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
        draw = LotteryDrawService.get_draw(db=db, draw_id=draw_id)

        new_lottery_id = update_data.get("lottery_id", draw.lottery_id)
        new_draw_number = update_data.get("draw_number", draw.draw_number)

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
        )
        if existing_number is not None and existing_number.id != draw_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Draw number already exists for this lottery",
            )

        result_groups = update_data.pop("result_groups", None)
        for field, value in update_data.items():
            setattr(draw, field, value)

        if result_groups is not None:
            LotteryDrawService._build_results(draw, result_groups)
        elif "main_numbers" in update_data or "bonus_numbers" in update_data:
            LotteryDrawService._build_results(draw, None)

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
