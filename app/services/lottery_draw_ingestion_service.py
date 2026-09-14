from collections.abc import Callable

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.integrations.lottery_sources import LotteryDrawPayload, LotterySourceAdapter
from app.repositories.lottery_draw_repository import LotteryDrawRepository
from app.services.lottery_draw_service import LotteryDrawService


class LotteryDrawIngestionService:
    """Persist normalized provider draws with deterministic idempotency semantics."""

    def __init__(
        self,
        adapter: LotterySourceAdapter,
        create_draw: Callable[..., object] | None = None,
    ) -> None:
        self.adapter = adapter
        self._create_draw = create_draw or LotteryDrawService.create_draw

    def ingest(self, db: Session, lottery_id: int, provider_payload: object) -> object:
        canonical = self.adapter.parse_draw(provider_payload)
        existing_number = LotteryDrawRepository.get_by_number(
            db=db,
            lottery_id=lottery_id,
            draw_number=canonical.draw_number,
            source=canonical.source,
        )
        existing_date = LotteryDrawRepository.get_by_date(
            db=db,
            lottery_id=lottery_id,
            draw_date=canonical.draw_date,
            source=canonical.source,
        )

        existing = self._resolve_existing(existing_number, existing_date, canonical)
        if existing is not None:
            return existing

        try:
            return self._create_draw(
                db=db,
                lottery_id=lottery_id,
                draw_number=canonical.draw_number,
                draw_date=canonical.draw_date,
                main_numbers=canonical.main_numbers,
                bonus_numbers=canonical.bonus_numbers,
                source=canonical.source,
                metadata_json=canonical.metadata,
            )
        except HTTPException as exc:
            if exc.status_code != status.HTTP_409_CONFLICT:
                raise
            return self._resolve_race_after_conflict(db, lottery_id, canonical, exc)

    @classmethod
    def _resolve_race_after_conflict(
        cls,
        db: Session,
        lottery_id: int,
        canonical: LotteryDrawPayload,
        conflict: HTTPException,
    ) -> object:
        existing_number = LotteryDrawRepository.get_by_number(
            db=db,
            lottery_id=lottery_id,
            draw_number=canonical.draw_number,
            source=canonical.source,
        )
        existing_date = LotteryDrawRepository.get_by_date(
            db=db,
            lottery_id=lottery_id,
            draw_date=canonical.draw_date,
            source=canonical.source,
        )
        existing = cls._resolve_existing(existing_number, existing_date, canonical)
        if existing is not None:
            return existing
        raise conflict

    @staticmethod
    def _resolve_existing(
        existing_number: object | None,
        existing_date: object | None,
        canonical: LotteryDrawPayload,
    ) -> object | None:
        if existing_number is None and existing_date is None:
            return None
        if LotteryDrawIngestionService._matches(existing_number, canonical) and LotteryDrawIngestionService._matches(
            existing_date, canonical
        ):
            return existing_number or existing_date
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lottery draw conflicts with an existing record",
        )

    @staticmethod
    def _matches(existing: object | None, canonical: LotteryDrawPayload) -> bool:
        if existing is None:
            return True
        return (
            getattr(existing, "draw_number", None) == canonical.draw_number
            and getattr(existing, "draw_date", None) == canonical.draw_date
            and getattr(existing, "main_numbers", None) == canonical.main_numbers
            and getattr(existing, "bonus_numbers", None) == canonical.bonus_numbers
            and getattr(existing, "source", None) == canonical.source
            and getattr(existing, "metadata_json", None) == canonical.metadata
        )
