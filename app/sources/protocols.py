from typing import Protocol

from app.sources.contracts import SourceDraw


class LotterySourceAdapter(Protocol):
    """Contract implemented by every external lottery source adapter."""

    @property
    def source_id(self) -> str:
        ...

    def fetch_draws(self) -> list[SourceDraw]:
        """Fetch source data without writing to the database."""
        ...
