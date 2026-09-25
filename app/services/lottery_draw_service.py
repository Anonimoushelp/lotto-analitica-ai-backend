from datetime import date, time

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.repositories.lottery_draw_repository import LotteryDrawRepository
from app.sources.contracts import RawDrawRecord


class LotteryDrawService:
    _INGESTION_PARSER_VERSION = "2026-09-25-v2"
    _NON_SEMANTIC_DRAW_METADATA_KEYS = frozenset({
        "source_verified",
        "source_format",
    })

    @staticmethod
    def _metadata_comparison_value(key: str, value):
        if key == "raw_result" and value is not None:
            return str(value).zfill(4)
        if key == "digit_count" and value is not None:
            return int(value)
        return value

    @classmethod
    def _merge_draw_metadata(
        cls,
        existing_metadata: dict | None,
        incoming_metadata: dict | None,
    ) -> tuple[bool, dict]:
        existing = dict(existing_metadata or {})
        incoming = dict(incoming_metadata or {})
        merged = dict(existing)

        for key, value in incoming.items():
            if key in cls._NON_SEMANTIC_DRAW_METADATA_KEYS:
                if merged.get(key) != value:
                    merged[key] = value
                continue
            if key in merged:
                existing_value = cls._metadata_comparison_value(key, merged[key])
                incoming_value = cls._metadata_comparison_value(key, value)
                if existing_value != incoming_value:
                    return False, existing
            merged[key] = value

        return True, merged

    @staticmethod
    def _core_payload_compatible(existing: LotteryDraw, record: RawDrawRecord) -> bool:
        """Treat omitted optional source fields as non-conflicting."""
        return (
            existing.draw_type == record.draw_type
            and (
                record.draw_number is None
                or existing.draw_number == record.draw_number
            )
            and (
                record.draw_date is None
                or existing.draw_date == record.draw_date
            )
            and (
                record.draw_time is None
                or existing.draw_time == record.draw_time
            )
            and (
                record.main_numbers is None
                or existing.main_numbers == record.main_numbers
            )
            and (
                record.bonus_numbers is None
                or existing.bonus_numbers == record.bonus_numbers
            )
        )

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

        incoming_metadata = dict(record.metadata or {})
        incoming_metadata["parser_version"] = LotteryDrawService._INGESTION_PARSER_VERSION

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
            same_core_payload = LotteryDrawService._core_payload_compatible(
                existing,
                record,
            )
            metadata_compatible, merged_metadata = LotteryDrawService._merge_draw_metadata(
                existing.metadata_json,
                incoming_metadata,
            )
            if same_core_payload and metadata_compatible:
                # Provenance and newly available metadata may be refreshed
                # without creating a second row. Source records may omit
                # optional core fields such as draw_time/bonus_numbers; those
                # omissions must not turn an otherwise identical identity into
                # a conflict.
                changed = existing.metadata_json != merged_metadata
                if changed:
                    existing.metadata_json = merged_metadata
                if existing.source != record.source_name:
                    existing.source = record.source_name
                    changed = True
                if existing.source_url != record.source_url:
                    existing.source_url = record.source_url
                    changed = True
                if (
                    record.source_timestamp is not None
                    and existing.source_timestamp != record.source_timestamp
                ):
                    existing.source_timestamp = record.source_timestamp
                    changed = True
                if changed:
                    db.commit()
                    db.refresh(existing)
                return existing

            existing_parser_version = (existing.metadata_json or {}).get("parser_version")
            incoming_is_verified = bool(record.metadata.get("source_verified", False))
            if existing_parser_version is None and incoming_is_verified:
                # Repair rows created by the pre-v2 parser when the source now
                # provides the same draw identity but a corrected canonical
                # payload. Once repaired, subsequent conflicts remain strict.
                existing.draw_time = record.draw_time
                existing.main_numbers = record.main_numbers
                existing.bonus_numbers = record.bonus_numbers
                existing.metadata_json = incoming_metadata
                existing.source = record.source_name
                existing.source_url = record.source_url
                existing.source_timestamp = record.source_timestamp
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
            metadata_json=incoming_metadata,
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
