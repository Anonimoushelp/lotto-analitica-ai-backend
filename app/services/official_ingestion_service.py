from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.repositories.lottery_draw_repository import LotteryDrawRepository
from app.services.lottery_draw_service import LotteryDrawService
from app.sources.base import OfficialSourceAdapter, SourceClient, SourceValidationError


class OfficialIngestionService:
    """Validate and persist normalized results from official lottery sources."""

    @staticmethod
    def ingest(
        db: Session,
        adapter: OfficialSourceAdapter,
        *,
        client: SourceClient | None = None,
    ) -> LotteryDraw:
        normalized = adapter.fetch(client or SourceClient()).validate()
        lottery = db.scalar(
            select(Lottery).where(Lottery.code == normalized.lottery_code)
        )
        if lottery is None:
            raise SourceValidationError(
                f"lottery is not registered: {normalized.lottery_code}"
            )

        existing = LotteryDrawRepository.get_by_date(
            db=db,
            lottery_id=lottery.id,
            draw_date=normalized.draw_date,
        )
        if existing is not None:
            if (
                existing.main_numbers != normalized.main_numbers
                or existing.bonus_numbers != normalized.bonus_numbers
                or existing.metadata_json != normalized.metadata_json
            ):
                raise SourceValidationError(
                    "official source conflicts with an already stored draw"
                )
            return existing

        return LotteryDrawService.create_draw(
            db=db,
            lottery_id=lottery.id,
            draw_number=normalized.draw_number,
            draw_date=normalized.draw_date,
            main_numbers=normalized.main_numbers,
            bonus_numbers=normalized.bonus_numbers,
            source=normalized.source,
            metadata_json=normalized.metadata_json,
        )
