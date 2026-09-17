"""Explicit registry of supported Colombian lottery providers."""

from __future__ import annotations

from app.integrations.colombia_lotteries import BalotoAdapter, MiLotoAdapter
from app.integrations.lottery_sources import LotterySourceAdapter

_MAX_SOURCE_NAME_LENGTH = 255


class RevanchaAdapter(BalotoAdapter):
    """Normalize Revancha using its five-ball plus bonus-ball shape."""

    source_name = "revancha-colombia"


def build_colombia_source_adapters() -> dict[str, LotterySourceAdapter]:
    """Return only explicitly supported production source adapters."""

    adapters: list[LotterySourceAdapter] = [
        BalotoAdapter(),
        RevanchaAdapter(),
        MiLotoAdapter(),
    ]
    return {adapter.source_name: adapter for adapter in adapters}


def get_colombia_source_adapter(source_name: str) -> LotterySourceAdapter:
    """Resolve a configured Colombian provider; reject arbitrary sources."""

    if not isinstance(source_name, str):
        raise TypeError("Invalid source name")
    if any(not char.isprintable() for char in source_name):
        raise ValueError("Invalid source name")
    key = source_name.strip()
    if not key or len(key) > _MAX_SOURCE_NAME_LENGTH:
        raise ValueError("Invalid source name")
    adapter = build_colombia_source_adapters().get(key)
    if adapter is None:
        raise KeyError("Unknown lottery source")
    return adapter
