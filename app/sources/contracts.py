from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Protocol


@dataclass(frozen=True)
class RawDrawRecord:
    lottery_code: str
    draw_type: str
    draw_number: str | None
    draw_date: date
    draw_time: time | None
    main_numbers: list[int]
    bonus_numbers: list[int] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    source_name: str = ""
    source_url: str | None = None
    source_timestamp: datetime | None = None


@dataclass(frozen=True)
class SourceSpec:
    lottery_code: str
    draw_types: tuple[str, ...]
    primary_name: str
    primary_url: str | None
    primary_verified: bool
    secondary_names: tuple[str, ...] = ()
    notes: str = ""


class SourceAdapter(Protocol):
    spec: SourceSpec

    def normalize(self, payload: Mapping[str, Any]) -> RawDrawRecord:
        """Convert one provider record into the canonical draw contract."""
