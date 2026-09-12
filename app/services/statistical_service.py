from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.lottery_draw import LotteryDraw


class StatisticalService:
    @staticmethod
    def overview(db: Session) -> dict[str, int | str]:
        draws_analyzed = db.scalar(select(func.count(LotteryDraw.id))) or 0
        return {
            "module_status": "STANDBY",
            "algorithms_count": 0,
            "draws_analyzed": draws_analyzed,
        }
