from typing import Any

from pydantic import ValidationError

from app.integrations.lottery_sources import LotteryDrawPayload, LotterySourceAdapter


class JsonLotterySourceAdapter:
    """Adapter for already-decoded provider JSON payloads.

    Network access is deliberately outside this layer. The adapter only
    normalizes and validates trusted, application-provided provider data.
    """

    def __init__(self, source_name: str) -> None:
        normalized = source_name.strip()
        if not normalized or len(normalized) > 255:
            raise ValueError("Invalid source name")
        if any(not char.isprintable() for char in normalized):
            raise ValueError("Invalid source name")
        self.source_name = normalized

    def parse_draw(self, payload: Any) -> LotteryDrawPayload:
        if not isinstance(payload, dict):
            raise TypeError("Provider payload must be an object")

        candidate = dict(payload)
        payload_source = candidate.get("source")
        if payload_source is not None and payload_source != self.source_name:
            raise ValueError("Provider source does not match adapter")
        candidate["source"] = self.source_name

        try:
            return LotteryDrawPayload.model_validate(candidate)
        except ValidationError as exc:
            raise ValueError("Invalid provider draw payload") from exc


class LotterySourceAdapterRegistry:
    """Explicit registry preventing arbitrary runtime source resolution."""

    def __init__(self, adapters: list[LotterySourceAdapter] | None = None) -> None:
        self._adapters: dict[str, LotterySourceAdapter] = {}
        for adapter in adapters or []:
            self.register(adapter)

    def register(self, adapter: LotterySourceAdapter) -> None:
        source_name = getattr(adapter, "source_name", "")
        if not isinstance(source_name, str) or not source_name.strip():
            raise ValueError("Adapter source name is required")
        key = source_name.strip()
        if any(not char.isprintable() for char in key):
            raise ValueError("Invalid source name")
        if key in self._adapters:
            raise ValueError("Adapter source already registered")
        self._adapters[key] = adapter

    def get(self, source_name: str) -> LotterySourceAdapter:
        if not isinstance(source_name, str):
            raise TypeError("Invalid source name")
        key = source_name.strip()
        adapter = self._adapters.get(key)
        if adapter is None:
            raise KeyError("Unknown lottery source")
        return adapter
