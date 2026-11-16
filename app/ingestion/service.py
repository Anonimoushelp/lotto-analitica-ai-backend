from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ingestion.contracts import IngestionDraw
from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.repositories.lottery_draw_repository import LotteryDrawRepository


@dataclass(frozen=True)
class IngestionSummary:
    received: int
    inserted: int
    duplicates: int
    rejected: int


class LotteryIngestionService:
    @staticmethod
    def ingest(
        db: Session,
        draws: list[IngestionDraw],
    ) -> IngestionSummary:
        received = len(draws)
        inserted = 0
        duplicates = 0
        rejected = 0

        for candidate in draws:
            lottery = db.query(Lottery).filter(
                Lottery.code == candidate.lottery_code
            ).one_or_none()

            if lottery is None:
                rejected += 1
                continue

            by_number = LotteryDrawRepository.get_by_number(
                db=db,
                lottery_id=lottery.id,
                draw_number=candidate.draw_number,
            )
            by_date = LotteryDrawRepository.get_by_date(
                db=db,
                lottery_id=lottery.id,
                draw_date=candidate.draw_date,
            )

            if by_number is not None or by_date is not None:
                duplicates += 1
                continue

            draw = LotteryDraw(
                lottery_id=lottery.id,
                draw_number=candidate.draw_number,
                draw_date=candidate.draw_date,
                main_numbers=candidate.main_numbers,
                bonus_numbers=candidate.bonus_numbers,
                source=candidate.source,
                metadata_json=candidate.metadata_json,
            )

            try:
                db.add(draw)
                db.commit()
                inserted += 1
            except IntegrityError:
                db.rollback()
                duplicates += 1

        return IngestionSummary(
            received=received,
            inserted=inserted,
            duplicates=duplicates,
            rejected=rejected,
        )
