from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.schemas.data_warehouse import (
    DataMartResponse,
    OlapCubeResponse,
    OlapQueryRequest,
    OlapQueryResponse,
    OlapQueryRow,
    WarehouseKPIResponse,
)


class DataWarehouseService:
    @staticmethod
    def kpis(db: Session) -> WarehouseKPIResponse:
        total_draws = db.query(func.count(LotteryDraw.id)).scalar() or 0
        total_lotteries = db.query(func.count(Lottery.id)).scalar() or 0
        date_from, date_to = db.query(
            func.min(LotteryDraw.draw_date), func.max(LotteryDraw.draw_date)
        ).one()
        return WarehouseKPIResponse(
            total_draws=total_draws,
            total_lotteries=total_lotteries,
            date_from=date_from,
            date_to=date_to,
            latest_draw_date=date_to,
        )

    @staticmethod
    def marts(db: Session) -> list[DataMartResponse]:
        total_draws = db.query(func.count(LotteryDraw.id)).scalar() or 0
        return [
            DataMartResponse(
                id="MART-DRAWS",
                name="Draws Analytical Mart",
                description="Vista analítica derivada de los sorteos persistidos.",
                source="lottery_draws",
                row_count=total_draws,
            )
        ]

    @staticmethod
    def cubes() -> list[OlapCubeResponse]:
        return [
            OlapCubeResponse(
                id="CUBE-DRAWS",
                name="Lottery Draw Analytics",
                dimensions=["lottery_id", "draw_date"],
                measures=["draw_count", "number_frequency"],
            )
        ]

    @staticmethod
    def query(db: Session, payload: OlapQueryRequest) -> OlapQueryResponse:
        query = db.query(LotteryDraw)
        if payload.lottery_id is not None:
            query = query.filter(LotteryDraw.lottery_id == payload.lottery_id)
        if payload.date_from is not None:
            query = query.filter(LotteryDraw.draw_date >= payload.date_from)
        if payload.date_to is not None:
            query = query.filter(LotteryDraw.draw_date <= payload.date_to)

        draws = (
            query.order_by(LotteryDraw.draw_date.desc())
            .limit(payload.limit)
            .all()
        )

        grouped: dict[int, list[LotteryDraw]] = {}
        for draw in draws:
            grouped.setdefault(draw.lottery_id, []).append(draw)

        rows: list[OlapQueryRow] = []
        for lottery_id, lottery_draws in grouped.items():
            frequency: Counter[str] = Counter()
            for draw in lottery_draws:
                for number in draw.main_numbers or []:
                    frequency[str(number)] += 1
            sorted_frequency = dict(
                sorted(frequency.items(), key=lambda item: int(item[0]))
            )
            rows.append(
                OlapQueryRow(
                    lottery_id=lottery_id,
                    draw_count=len(lottery_draws),
                    number_frequency=sorted_frequency,
                )
            )

        return OlapQueryResponse(
            executed_at=datetime.now(UTC),
            rows=rows,
        )
