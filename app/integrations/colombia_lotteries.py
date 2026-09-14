"""Concrete adapters for official Colombian lottery result shapes.

These adapters do not perform HTTP requests. A separate, fixed/configured
fetcher is responsible for obtaining and decoding provider data before it
reaches this boundary.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from pydantic import ValidationError

from app.integrations.lottery_sources import LotteryDrawPayload

_ALLOWED_FIELDS = {"sorteo", "fecha", "resultado", "metadata"}
_MONTHS_ES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


class _ColombiaLotteryAdapter:
    source_name: str
    main_count: int
    main_max: int
    bonus_max: int | None = None

    def parse_draw(self, payload: Any) -> LotteryDrawPayload:
        if not isinstance(payload, dict):
            raise TypeError("Provider payload must be an object")
        if set(payload) - _ALLOWED_FIELDS:
            raise ValueError("Invalid provider draw payload")

        draw_number = self._draw_number(payload.get("sorteo"))
        draw_date = self._draw_date(payload.get("fecha"))
        numbers = self._numbers(payload.get("resultado"))
        expected = self.main_count + (1 if self.bonus_max else 0)
        if len(numbers) != expected:
            raise ValueError("Invalid provider draw payload")

        main_numbers = numbers[: self.main_count]
        bonus_numbers = numbers[self.main_count :] or None
        if any(number > self.main_max for number in main_numbers):
            raise ValueError("Invalid provider draw payload")
        if bonus_numbers and any(number > self.bonus_max for number in bonus_numbers):
            raise ValueError("Invalid provider draw payload")

        metadata = payload.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("Invalid provider draw payload")

        try:
            return LotteryDrawPayload(
                draw_number=draw_number,
                draw_date=draw_date,
                main_numbers=main_numbers,
                bonus_numbers=bonus_numbers,
                source=self.source_name,
                metadata=metadata,
            )
        except (ValidationError, TypeError) as exc:
            raise ValueError("Invalid provider draw payload") from exc

    @staticmethod
    def _draw_number(value: Any) -> str:
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return str(value)
        if isinstance(value, str):
            match = re.fullmatch(
                r"\s*(?:sorteo\s*#?\s*)?(\d+)\s*", value, re.IGNORECASE
            )
            if match:
                return match.group(1)
        raise ValueError("Invalid provider draw payload")

    @staticmethod
    def _draw_date(value: Any) -> date:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            raise TypeError("Invalid provider draw date type")
        normalized = " ".join(value.strip().lower().split())
        iso_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", normalized)
        if iso_match:
            try:
                return date(*map(int, iso_match.groups()))
            except ValueError as exc:
                raise ValueError("Invalid provider draw payload") from exc
        match = re.fullmatch(
            r"(?:\w+\s+)?(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})",
            normalized,
        )
        if not match or match.group(2) not in _MONTHS_ES:
            raise ValueError("Invalid provider draw payload")
        try:
            return date(
                int(match.group(3)),
                _MONTHS_ES[match.group(2)],
                int(match.group(1)),
            )
        except ValueError as exc:
            raise ValueError("Invalid provider draw payload") from exc

    @staticmethod
    def _numbers(value: Any) -> list[int]:
        if isinstance(value, list) and all(
            isinstance(n, int) and not isinstance(n, bool) for n in value
        ):
            numbers = value
        elif isinstance(value, str):
            tokens = [
                token for token in re.split(r"\s*-\s*", value.strip()) if token
            ]
            if not tokens or any(not token.isdigit() for token in tokens):
                raise ValueError("Invalid provider draw payload")
            numbers = [int(token) for token in tokens]
        else:
            raise TypeError("Invalid provider draw numbers type")
        if any(number <= 0 for number in numbers) or len(numbers) != len(set(numbers)):
            raise ValueError("Invalid provider draw payload")
        return numbers


class BalotoAdapter(_ColombiaLotteryAdapter):
    """Normalize Baloto/Revancha: five main balls plus Superbalota."""

    source_name = "baloto-colombia"
    main_count = 5
    main_max = 43
    bonus_max = 16


class MiLotoAdapter(_ColombiaLotteryAdapter):
    """Normalize MiLoto: five main numbers from 1 through 39."""

    source_name = "miloto-colombia"
    main_count = 5
    main_max = 39
    bonus_max = None
