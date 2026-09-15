from typing import Any

from pydantic import ValidationError

from app.integrations.lottery_sources import LotteryDrawPayload, LotterySourceAdapter


class JsonLotterySourceAdapter:
    """Adapter for already-decoded provider JSON payloads.

    Network access is deliberately outside this layer. The adapter only
    normalizes and validates trusted, application-provided provider data.
    """

    def __init__(self, source_name: str) -> None:
        if not isinstance(source_name, str):
            raise TypeError("Invalid source name")
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
        if "source" in candidate:
            payload_source = candidate["source"]
            if not isinstance(payload_source, str):
                raise ValueError("Invalid provider draw payload")
            if payload_source != self.source_name:
                raise ValueError("Provider source does not match adapter")
        candidate["source"] = self.source_name

        draw_number = candidate.get("draw_number")
        if isinstance(draw_number, str) and any(
            not char.isprintable() for char in draw_number
        ):
            raise ValueError("Invalid provider draw payload")

        metadata = candidate.get("metadata")
        if isinstance(metadata, dict):
            for value in metadata.values():
                if isinstance(value, str) and any(
                    not char.isprintable() for char in value
                ):
                    raise ValueError("Invalid provider draw payload")

        try:
            return LotteryDrawPayload.model_validate(candidate)
        except (ValidationError, TypeError) as exc:
            raise ValueError("Invalid provider draw payload") from exc


class LotterySourceAdapterRegistry:
    """Explicit registry preventing arbitrary runtime source resolution."""

    def __init__(self, adapters: list[LotterySourceAdapter] | None = None) -> None:
        self._adapters: dict[str, LotterySourceAdapter] = {}
        for adapter in adapters or []:
            self.register(adapter)

    def register(self, adapter: LotterySourceAdapter) -> None:
        source_name = getattr(adapter, "source_name", "")
        parse_draw = getattr(adapter, "parse_draw", None)
        if not isinstance(source_name, str) or not source_name.strip():
            raise ValueError("Adapter source name is required")
        if len(source_name.strip()) > 255:
            raise ValueError("Invalid source name")
        if any(not char.isprintable() for char in source_name):
            raise ValueError("Invalid source name")
        if source_name != source_name.strip():
            raise ValueError("Adapter source name must be normalized")
        if not callable(parse_draw):
            raise TypeError("Adapter must implement parse_draw")
        key = source_name
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

    def parse_draw(self, source_name: str, payload: Any) -> LotteryDrawPayload:
        """Parse through a registered adapter and enforce the canonical output."""
        adapter = self.get(source_name)
        try:
            result = adapter.parse_draw(payload)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid provider draw payload") from exc
        if not isinstance(result, LotteryDrawPayload):
            raise TypeError("Adapter returned invalid draw payload")
        if result.source != adapter.source_name:
            raise ValueError("Adapter returned mismatched source")
        return result
