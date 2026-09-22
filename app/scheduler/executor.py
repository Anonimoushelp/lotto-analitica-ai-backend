from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.lottery import Lottery
from app.services.lottery_draw_service import LotteryDrawService
from app.sources.fetchers import HttpSourceFetcher, SourceFetcher
from app.sources.ingestion import SourceIngestionPipeline
from app.sources.provider_registry import build_traditional_lottery_components
from app.sources.traditional_lottery import get_traditional_source


class SessionFactory(Protocol):
    def __call__(self) -> Session: ...


class ControlledIngestionExecutor:
    """Persist one verified traditional-lottery result for a scheduler cycle."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory = SessionLocal,
        fetcher: SourceFetcher | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.fetcher = fetcher or HttpSourceFetcher()

    def __call__(self, lottery_code: str, draw_type: str) -> str:
        code = lottery_code.upper()
        profile = get_traditional_source(code)
        if not profile.verified or not profile.result_url:
            raise RuntimeError(
                f"Controlled ingestion source is not verified for {code}"
            )

        parser, adapter = build_traditional_lottery_components(code)
        pipeline = SourceIngestionPipeline(
            fetcher=self.fetcher,
            parser=parser,
            adapter=adapter,
        )
        records = pipeline.run(profile.result_url)
        if not records:
            raise RuntimeError(f"No draw record extracted for {code}")

        matching = [record for record in records if record.draw_type == draw_type]
        if not matching:
            raise RuntimeError(
                f"Source returned no record for {code}/{draw_type}"
            )
        if len(matching) > 1:
            raise RuntimeError(
                f"Source returned multiple records for {code}/{draw_type}"
            )

        record = matching[0]
        with self.session_factory() as db:
            lottery = db.scalar(select(Lottery).where(Lottery.code == code))
            if lottery is None:
                raise RuntimeError(f"Lottery {code} is not registered in the database")

            draw = LotteryDrawService.create_draw(
                db=db,
                lottery_id=lottery.id,
                draw_number=record.draw_number,
                draw_date=record.draw_date,
                draw_time=record.draw_time,
                main_numbers=record.main_numbers,
                bonus_numbers=record.bonus_numbers,
                draw_type=record.draw_type,
                source=record.source_name,
                source_url=record.source_url,
                source_timestamp=record.source_timestamp,
                metadata_json=record.metadata,
            )

        return (
            f"persisted draw_id={draw.id} "
            f"lottery={code} draw_type={draw_type} "
            f"draw_date={draw.draw_date.isoformat()}"
        )


def build_controlled_executor() -> Callable[[str, str], str]:
    return ControlledIngestionExecutor()
