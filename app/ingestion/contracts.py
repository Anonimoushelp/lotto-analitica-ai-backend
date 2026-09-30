from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class IngestionDraw:
    lottery_code: str
    draw_number: str
    draw_date: date
    main_numbers: list[int]
    bonus_numbers: list[int] | None
    source: str
    metadata_json: dict[str, Any]
