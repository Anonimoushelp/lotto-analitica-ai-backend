from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.sources.parsers import SourceParseError


def _require(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    raise SourceParseError(f"Missing required source field: {keys[0]}")


def _as_numbers(value: Any, *, field: str) -> list[int]:
    if not isinstance(value, (list, tuple)):
        raise SourceParseError(f"{field} must be a list of numbers")
    try:
        numbers = [int(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise SourceParseError(f"{field} contains a non-numeric value") from exc
    if not numbers:
        raise SourceParseError(f"{field} cannot be empty")
    return numbers


class MiLotoJsonParser:
    """Extract MiLoto records from a structured provider JSON payload."""

    def parse_record(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "draw_type": "MILOTO",
            "draw_number": _require(payload, "draw_number", "draw", "sorteo"),
            "draw_date": _require(payload, "draw_date", "date", "fecha"),
            "main_numbers": _as_numbers(
                _require(payload, "main_numbers", "numbers", "result"),
                field="main_numbers",
            ),
            "metadata": dict(payload.get("metadata") or {}),
        }


class BalotoFamilyJsonParser:
    """Extract Baloto/Revancha without relying on row ordering.

    The source must explicitly identify the game as BALOTO or REVANCHA.
    """

    def parse_record(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        raw_game = _require(payload, "game_type", "game", "tipo")
        game_type = str(raw_game).strip().upper()
        aliases = {"BALOTO": "BALOTO", "REVANCHA": "REVANCHA"}
        try:
            draw_type = aliases[game_type]
        except KeyError as exc:
            raise SourceParseError(
                "Baloto family record requires explicit game_type BALOTO or REVANCHA"
            ) from exc

        bonus_key = "superbalota" if draw_type == "BALOTO" else "revancha_bonus"
        return {
            "draw_type": draw_type,
            "draw_number": _require(payload, "draw_number", "draw", "sorteo"),
            "draw_date": _require(payload, "draw_date", "date", "fecha"),
            "main_numbers": _as_numbers(
                _require(payload, "main_numbers", "numbers", "result"),
                field="main_numbers",
            ),
            "bonus_numbers": _as_numbers(
                _require(payload, bonus_key),
                field="bonus_numbers",
            ),
            "metadata": dict(payload.get("metadata") or {}),
        }


class SuperAstroJsonParser:
    """Extract Astro Sol/Luna while preserving the four-digit result."""

    def parse_record(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        raw_type = _require(payload, "draw_type", "game_type", "game", "tipo")
        draw_type = str(raw_type).strip().upper()
        if draw_type not in {"ASTRO_SOL", "ASTRO_LUNA"}:
            raise SourceParseError(
                "Super Astro record requires draw_type ASTRO_SOL or ASTRO_LUNA"
            )

        raw_number = str(_require(payload, "number", "result", "resultado")).strip()
        if len(raw_number) != 4 or not raw_number.isdigit():
            raise SourceParseError("Super Astro result must be exactly four digits")

        metadata = dict(payload.get("metadata") or {})
        if "sign" in payload and "sign" not in metadata:
            metadata["sign"] = payload["sign"]
        metadata["raw_result"] = raw_number
        metadata["digit_count"] = 4

        return {
            "draw_type": draw_type,
            "draw_number": _require(payload, "draw_number", "draw", "sorteo"),
            "draw_date": _require(payload, "draw_date", "date", "fecha"),
            "number": raw_number,
            "metadata": metadata,
        }
