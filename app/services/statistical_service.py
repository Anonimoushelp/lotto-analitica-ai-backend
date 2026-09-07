from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw

STATISTICAL_ALGORITHMS = (
    "frequency",
    "recency",
    "odd_even_distribution",
    "number_range_distribution",
    "pair_frequency",
    "consecutive_numbers",
    "hot_cold_classification",
    "historical_weighting",
)


class StatisticalService:
    @staticmethod
    def overview(db: Session, tenant_id: int) -> dict[str, int | str]:
        draws_analyzed = (
            db.scalar(
                select(func.count(LotteryDraw.id))
                .join(Lottery, Lottery.id == LotteryDraw.lottery_id)
                .where(Lottery.tenant_id == tenant_id)
            )
            or 0
        )
        return {
            "module_status": "READY",
            "algorithms_count": len(STATISTICAL_ALGORITHMS),
            "draws_analyzed": draws_analyzed,
        }
