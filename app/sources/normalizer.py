from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time
from typing import Any

from app.sources.contracts import RawDrawRecord, SourceSpec


class SourceNormalizationError(ValueError):
    """Raised when provider data cannot be mapped to the canonical contract."""


class MappingSourceAdapter:
    """Normalize provider dictionaries without coupling providers to persistence."""

    def __init__(self, spec: SourceSpec, *, field_map: Mapping[str, str] | None = None) -> None:
        self.spec = spec
        self.field_map = dict(field_map or {})

    def normalize(self, payload: Mapping[str, Any]) -> RawDrawRecord:
        lottery_code = str(self._get(payload, "lottery_code", self.spec.lottery_code))
        draw_type = str(self._get(payload, "draw_type"))
        if draw_type not in self.spec.draw_types:
            raise SourceNormalizationError(f"Unsupported draw type '{draw_type}' for {lottery_code}")
        draw_number = str(self._get(payload, "draw_number"))
        draw_date = self._coerce_date(self._get(payload, "draw_date"))
        draw_time = self._coerce_time(self._get(payload, "draw_time", None))
        main_numbers = self._coerce_numbers(self._get(payload, "main_numbers"), "main_numbers")
        bonus_value = self._get(payload, "bonus_numbers", None)
        bonus_numbers = self._coerce_numbers(bonus_value, "bonus_numbers") if bonus_value is not None else None
        metadata = dict(self._get(payload, "metadata", {}))
        source_name = str(self._get(payload, "source_name", self.spec.primary_name))
        source_url = self._get(payload, "source_url", self.spec.primary_url)
        source_timestamp = self._get(payload, "source_timestamp", None)
        return RawDrawRecord(
            lottery_code=lottery_code,
            draw_type=draw_type,
            draw_number=draw_number,
            draw_date=draw_date,
            draw_time=draw_time,
            main_numbers=main_numbers,
            bonus_numbers=bonus_numbers,
            metadata=metadata,
            source_name=source_name,
            source_url=str(source_url) if source_url is not None else None,
            source_timestamp=source_timestamp,
        )

    def _get(self, payload: Mapping[str, Any], field: str, default: Any = ...):
        key = self.field_map.get(field, field)
        if key in payload:
            return payload[key]
        if default is not ...:
            return default
        raise SourceNormalizationError(f"Missing required source field: {field}")

    @staticmethod
    def _coerce_date(value: Any) -> date:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        try:
            return date.fromisoformat(str(value))
        except ValueError as exc:
            raise SourceNormalizationError(f"Invalid draw_date: {value!r}") from exc

    @staticmethod
    def _coerce_time(value: Any) -> time | None:
        if value is None or isinstance(value, time):
            return value
        try:
            return time.fromisoformat(str(value))
        except ValueError as exc:
            raise SourceNormalizationError(f"Invalid draw_time: {value!r}") from exc

    @staticmethod
    def _coerce_numbers(value: Any, field: str) -> list[int]:
        if not isinstance(value, (list, tuple)) or not value:
            raise SourceNormalizationError(f"{field} must be a non-empty list")
        try:
            numbers = [int(item) for item in value]
        except (TypeError, ValueError) as exc:
            raise SourceNormalizationError(f"{field} must contain integers") from exc
        if any(number < 1 or number > 1000 for number in numbers):
            raise SourceNormalizationError(f"{field} numbers must be between 1 and 1000")
        if len(numbers) != len(set(numbers)):
            raise SourceNormalizationError(f"{field} cannot contain duplicates")
        return numbers
