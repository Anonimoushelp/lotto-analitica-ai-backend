from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime


class SourceValidationError(ValueError):
    """Raised when an official source response cannot be trusted."""


@dataclass(frozen=True)
class NormalizedDraw:
    lottery_code: str
    draw_number: str
    draw_date: date
    main_numbers: list[int]
    bonus_numbers: list[int] | None = None
    metadata_json: dict = field(default_factory=dict)
    source: str = ""

    def validate(self) -> NormalizedDraw:
        if not self.lottery_code.strip():
            raise SourceValidationError("lottery_code is required")
        if not self.draw_number.strip() or self.draw_number == "0":
            raise SourceValidationError("invalid draw number")
        if self.draw_date > datetime.now(tz=UTC).date():
            raise SourceValidationError("draw date cannot be in the future")
        if not self.main_numbers:
            raise SourceValidationError("at least one main number is required")
        if len(self.main_numbers) != len(set(self.main_numbers)):
            raise SourceValidationError("main numbers contain duplicates")
        if any(n < 1 for n in self.main_numbers):
            raise SourceValidationError("main numbers must be positive")
        if self.bonus_numbers is not None:
            if len(self.bonus_numbers) != len(set(self.bonus_numbers)):
                raise SourceValidationError("bonus numbers contain duplicates")
            if any(n < 1 for n in self.bonus_numbers):
                raise SourceValidationError("bonus numbers must be positive")
        return self


class OfficialSourceAdapter:
    lottery_code: str
    source_url: str

    def parse(self, payload: str) -> NormalizedDraw:
        raise NotImplementedError

    def fetch(self, client: SourceClient) -> NormalizedDraw:
        return self.parse(client.get(self.source_url))


class SourceClient:
    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def get(self, url: str) -> str:
        import httpx

        try:
            response = httpx.get(url, timeout=self.timeout, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceValidationError(
                f"official source unavailable: {url}"
            ) from exc
        if not response.text.strip():
            raise SourceValidationError("official source returned an empty response")
        return response.text
