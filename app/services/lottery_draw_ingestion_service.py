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
        )
        existing_date = LotteryDrawRepository.get_by_date(
            db=db,
            lottery_id=lottery_id,
            draw_date=canonical.draw_date,
        )

        if existing_number is not None or existing_date is not None:
            if self._matches(existing_number, canonical) and self._matches(
                existing_date, canonical
            ):
                return existing_number or existing_date
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Lottery draw conflicts with an existing record",
            )

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
        )
