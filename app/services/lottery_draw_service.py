from datetime import date, time

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.repositories.lottery_draw_repository import LotteryDrawRepository
from app.sources.contracts import RawDrawRecord


_NON_SEMANTIC_DRAW_METADATA_KEYS = frozenset({
    "source_verified",
    "source_format",
})


def _semantic_draw_metadata(metadata: dict | None) -> dict:
    if not metadata:
        return {}
    return {
        key: value
        for key, value in metadata.items()
        if key not in _NON_SEMANTIC_DRAW_METADATA_KEYS
    }


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
        draw_number: str | None,
        draw_date: date,
        main_numbers: list[int],
        draw_type: str = "DEFAULT",
        draw_time: time | None = None,
        bonus_numbers: list[int] | None = None,
        source: str | None = None,
        source_url: str | None = None,
        source_timestamp=None,
        metadata_json: dict | None = None,
        validation_json: dict | None = None,
    ) -> LotteryDraw:
        lottery = db.get(Lottery, lottery_id)

        if lottery is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lottery not found",
            )

        if draw_number is not None:
            existing_number = LotteryDrawRepository.get_by_number(
                db=db,
                lottery_id=lottery_id,
                draw_type=draw_type,
                draw_number=draw_number,
            )

            if existing_number is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Draw number already exists for this lottery and draw type",
                )

        existing_date = LotteryDrawRepository.get_by_date(
            db=db,
            lottery_id=lottery_id,
            draw_type=draw_type,
            draw_date=draw_date,
        )

        if existing_date is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Draw date already exists for this lottery and draw type",
            )

        draw = LotteryDraw(
            lottery_id=lottery_id,
            draw_type=draw_type,
            draw_number=draw_number,
            draw_date=draw_date,
            draw_time=draw_time,
            main_numbers=main_numbers,
            bonus_numbers=bonus_numbers,
            source=source,
            source_url=str(source_url) if source_url is not None else None,
            source_timestamp=source_timestamp,
            metadata_json=metadata_json,
            validation_json=validation_json,
        )

        try:
            return LotteryDrawRepository.create(db=db, draw=draw)
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Lottery draw conflicts with an existing record",
            ) from exc

    @staticmethod
    def persist_raw_record(
        db: Session,
        record: RawDrawRecord,
    ) -> LotteryDraw:
        """Persist a canonical source record with deterministic idempotency.

        An exact repeat of the same canonical record returns the existing row.
        A conflicting payload for the same lottery/draw identity is rejected.
        """
        lottery = db.scalar(
            select(Lottery).where(func.lower(Lottery.code) == record.lottery_code.lower())
        )

        if lottery is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lottery not found for source code: {record.lottery_code}",
            )

        existing = None
        if record.draw_number is not None:
            existing = LotteryDrawRepository.get_by_number(
                db=db,
                lottery_id=lottery.id,
                draw_type=record.draw_type,
                draw_number=record.draw_number,
            )

        if existing is None:
            existing = LotteryDrawRepository.get_by_date(
                db=db,
                lottery_id=lottery.id,
                draw_type=record.draw_type,
                draw_date=record.draw_date,
            )

        if existing is not None:
            same_payload = (
                existing.draw_type == record.draw_type
                and existing.draw_number == record.draw_number
                and existing.draw_date == record.draw_date
                and existing.draw_time == record.draw_time
                and existing.main_numbers == record.main_numbers
                and existing.bonus_numbers == record.bonus_numbers
                and _semantic_draw_metadata(existing.metadata_json)
                == _semantic_draw_metadata(record.metadata)
            )
            if same_payload:
                # Provenance is traceability, not draw identity. A provider may
                # redirect or canonicalize its URL between fetches without
                # changing the published draw. Keep the newest provenance while
                # preserving the existing canonical row.
                changed = False
                if existing.source != record.source_name:
                    existing.source = record.source_name
                    changed = True
                if existing.source_url != record.source_url:
                    existing.source_url = record.source_url
                    changed = True
                if record.source_timestamp is not None and existing.source_timestamp != record.source_timestamp:
                    existing.source_timestamp = record.source_timestamp
                    changed = True
                if changed:
                    db.commit()
                    db.refresh(existing)
                return existing

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Conflicting draw payload for an existing lottery/draw identity",
            )

        return LotteryDrawService.create_draw(
            db=db,
            lottery_id=lottery.id,
            draw_number=record.draw_number,
            draw_date=record.draw_date,
            draw_time=record.draw_time,
            main_numbers=record.main_numbers,
            draw_type=record.draw_type,
            bonus_numbers=record.bonus_numbers,
            source=record.source_name,
            source_url=record.source_url,
            source_timestamp=record.source_timestamp,
            metadata_json=record.metadata,
            validation_json={
                "format_valid": True,
                "date_valid": True,
                "duplicate": False,
                "source_verified": bool(record.metadata.get("source_verified", False)),
            },
        )

    @staticmethod
    def update_draw(
        db: Session,
        draw_id: int,
        update_data: dict,
    ) -> LotteryDraw:
        draw = LotteryDrawService.get_draw(db=db, draw_id=draw_id)

        new_lottery_id = update_data.get("lottery_id", draw.lottery_id)
        new_draw_type = update_data.get("draw_type", draw.draw_type)
        new_draw_number = update_data.get("draw_number", draw.draw_number)
        new_draw_date = update_data.get("draw_date", draw.draw_date)

        lottery = db.get(Lottery, new_lottery_id)

        if lottery is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lottery not found",
            )

        if new_draw_number is not None:
            existing_number = LotteryDrawRepository.get_by_number(
                db=db,
                lottery_id=new_lottery_id,
                draw_type=new_draw_type,
                draw_number=new_draw_number,
            )

            if existing_number is not None and existing_number.id != draw_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Draw number already exists for this lottery and draw type",
                )

        existing_date = LotteryDrawRepository.get_by_date(
            db=db,
            lottery_id=new_lottery_id,
            draw_type=new_draw_type,
            draw_date=new_draw_date,
        )

        if existing_date is not None and existing_date.id != draw_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Draw date already exists for this lottery and draw type",
            )

        normalized_update_data = dict(update_data)
        if "source_url" in normalized_update_data:
            source_url = normalized_update_data["source_url"]
            normalized_update_data["source_url"] = (
                str(source_url) if source_url is not None else None
            )

        for field, value in normalized_update_data.items():
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
    def delete_draw(
        db: Session,
        draw_id: int,
    ) -> None:
        draw = LotteryDrawService.get_draw(db=db, draw_id=draw_id)

        try:
            LotteryDrawRepository.delete(db=db, draw=draw)
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Lottery draw conflicts with an existing record",
            ) from exc
