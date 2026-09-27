from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.sources.parsers import SourceParseError

# Provider-independent aliases used only for structural four-digit extraction.
_DRAW_TYPE_KEYS = ("draw_type", "game_type", "game", "tipo", "sorteo_tipo")
_DRAW_NUMBER_KEYS = ("draw_number", "draw", "sorteo", "numero_sorteo")
_DRAW_DATE_KEYS = ("draw_date", "date", "fecha")
_RESULT_KEYS = ("result", "resultado", "number", "numero")


def _require(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    raise SourceParseError(f"Missing required source field: {keys[0]}")


def parse_four_digit_record(
    payload: Mapping[str, Any],
    *,
    allowed_draw_types: set[str],
    metadata_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    raw_type = _require(payload, *_DRAW_TYPE_KEYS)
    draw_type = str(raw_type).strip().upper()
    if draw_type not in allowed_draw_types:
        allowed = ", ".join(sorted(allowed_draw_types))
        raise SourceParseError(f"Unsupported draw type {draw_type}; expected one of {allowed}")

    raw_result = str(_require(payload, *_RESULT_KEYS)).strip()
    if len(raw_result) != 4 or not raw_result.isdigit():
        raise SourceParseError("Four-digit result must contain exactly four digits")

    metadata = dict(payload.get("metadata") or {})
    metadata["raw_result"] = raw_result
    metadata["digit_count"] = 4
    for key in metadata_keys:
        if key in payload and payload[key] not in (None, "") and key not in metadata:
            metadata[key] = payload[key]

    return {
        "draw_type": draw_type,
        "draw_number": _require(payload, *_DRAW_NUMBER_KEYS),
        "draw_date": _require(payload, *_DRAW_DATE_KEYS),
        "number": raw_result,
        "metadata": metadata,
    }


class AntioquenitaJsonParser:
    def parse_record(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return parse_four_digit_record(
            payload,
            allowed_draw_types={"ANTIOQUENITA_1", "ANTIOQUENITA_2"},
        )


class ChonticoJsonParser:
    def parse_record(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return parse_four_digit_record(
            payload,
            allowed_draw_types={
                "CHONTICO_DIA",
                "CHONTICO_NOCHE",
                "CHONTICO_SUPER_NOCHE",
            },
        )


class DoradoJsonParser:
    def parse_record(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return parse_four_digit_record(
            payload,
            allowed_draw_types={"DORADO_DIA", "DORADO_TARDE", "DORADO_NOCHE"},
            metadata_keys=("additional_value", "raw_additional_value"),
        )


class CafeteritoJsonParser:
    def parse_record(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return parse_four_digit_record(
            payload,
            allowed_draw_types={"CAFETERITO_TARDE", "CAFETERITO_NOCHE"},
        )


class PaisitaJsonParser:
    def parse_record(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return parse_four_digit_record(
            payload,
            allowed_draw_types={"PAISITA_DIA", "PAISITA_NOCHE"},
            metadata_keys=("animal",),
        )


class FantasticaJsonParser:
    def parse_record(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return parse_four_digit_record(
            payload,
            allowed_draw_types={"FANTASTICA_DIA", "FANTASTICA_NOCHE"},
            metadata_keys=("additional_value", "raw_additional_value"),
        )
