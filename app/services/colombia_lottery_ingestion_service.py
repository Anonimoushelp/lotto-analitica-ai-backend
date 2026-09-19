from typing import Any

from sqlalchemy.orm import Session

from app.integrations.colombia_registry import get_colombia_source_adapter
from app.integrations.lottery_source_adapters import LotterySourceAdapterRegistry
from app.services.lottery_draw_ingestion_service import LotteryDrawIngestionService


class ColombiaLotteryIngestionService:
    """Controlled facade for ingesting explicitly supported Colombian sources."""

    def __init__(self, registry: LotterySourceAdapterRegistry | None = None) -> None:
        self._registry = registry

    def ingest(
        self,
        db: Session,
        lottery_id: int,
        source_name: str,
        provider_payload: Any,
    ) -> object:
        adapter = self._resolve(source_name)
        return LotteryDrawIngestionService(adapter).ingest(
            db=db,
            lottery_id=lottery_id,
            provider_payload=provider_payload,
        )

    def _resolve(self, source_name: str):
        if self._registry is not None:
            return self._registry.get(source_name)
        return get_colombia_source_adapter(source_name)
