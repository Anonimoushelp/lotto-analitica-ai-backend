from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    provider: str
    source_type: str
    reference: str | None = None
    retrieved_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider cannot be empty")
        if not self.source_type.strip():
            raise ValueError("source_type cannot be empty")


@dataclass(frozen=True, slots=True)
class SourceDraw:
    draw_number: str
    draw_date: date
    groups: dict[str, list[str]]
    metadata: SourceMetadata
    draw_datetime: datetime | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.draw_number.strip():
            raise ValueError("draw_number cannot be empty")
        if not self.groups:
            raise ValueError("groups cannot be empty")
        if any(not code.strip() for code in self.groups):
            raise ValueError("group codes cannot be empty")
        if any(not values for values in self.groups.values()):
            raise ValueError("result groups cannot be empty")


@dataclass(frozen=True, slots=True)
class CanonicalDraw:
    draw_number: str
    draw_date: date
    groups: dict[str, tuple[str, ...]]
    metadata: SourceMetadata
    draw_datetime: datetime | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)
