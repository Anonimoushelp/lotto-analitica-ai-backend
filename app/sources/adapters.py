from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.sources.contracts import RawDrawRecord
from app.sources.normalizer import MappingSourceAdapter, SourceNormalizationError
from app.sources.registry import get_source_spec


class BalotoAdapter(MappingSourceAdapter):
    """Adapter for the official Baloto result structure."""

    def __init__(self) -> None:
        super().__init__(
            get_source_spec("BALOTO"),
            field_map={
                "draw_number": "draw_number",
                "draw_date": "draw_date",
                "main_numbers": "main_numbers",
                "bonus_numbers": "bonus_numbers",
            },
        )

    def normalize(self, payload: Mapping[str, Any]) -> RawDrawRecord:
        payload = dict(payload)
        if "bonus_numbers" not in payload and "superbalota" in payload:
            payload["bonus_numbers"] = payload["superbalota"]
        payload.setdefault("draw_type", "BALOTO")
        return super().normalize(payload)


class RevanchaAdapter(MappingSourceAdapter):
    """Adapter for Revancha records published with the Baloto result family."""

    def __init__(self) -> None:
        super().__init__(
            get_source_spec("REVANCHA"),
            field_map={
                "draw_number": "draw_number",
                "draw_date": "draw_date",
                "main_numbers": "main_numbers",
                "bonus_numbers": "bonus_numbers",
            },
        )

    def normalize(self, payload: Mapping[str, Any]) -> RawDrawRecord:
        payload = dict(payload)
        if "bonus_numbers" not in payload and "revancha_bonus" in payload:
            payload["bonus_numbers"] = payload["revancha_bonus"]
        payload.setdefault("draw_type", "REVANCHA")
        return super().normalize(payload)


class MiLotoAdapter(MappingSourceAdapter):
    """Adapter for the official MiLoto historical result structure."""

    def __init__(self) -> None:
        super().__init__(
            get_source_spec("MILOTO"),
            field_map={
                "draw_number": "draw_number",
                "draw_date": "draw_date",
                "main_numbers": "main_numbers",
            },
        )

    def normalize(self, payload: Mapping[str, Any]) -> RawDrawRecord:
        payload = dict(payload)
        payload.setdefault("draw_type", "MILOTO")
        return super().normalize(payload)


class SuperAstroAdapter(MappingSourceAdapter):
    """Adapter for Astro Sol/Luna, preserving four-digit formatting and sign."""

    def __init__(self) -> None:
        super().__init__(
            get_source_spec("SUPER_ASTRO"),
            field_map={
                "draw_number": "draw_number",
                "draw_date": "draw_date",
                "main_numbers": "number",
                "metadata": "metadata",
            },
        )

    def normalize(self, payload: Mapping[str, Any]) -> RawDrawRecord:
        payload = dict(payload)
        draw_type = payload.get("draw_type")
        if draw_type not in self.spec.draw_types:
            raise SourceNormalizationError(
                "Super Astro requires draw_type ASTRO_SOL or ASTRO_LUNA"
            )

        raw_number = str(payload.get("number", "")).strip()
        if len(raw_number) != 4 or not raw_number.isdigit():
            raise SourceNormalizationError(
                "Super Astro number must be exactly four digits"
            )

        metadata = dict(payload.get("metadata") or {})
        metadata["raw_result"] = raw_number
        metadata["digit_count"] = 4

        payload["number"] = [int(raw_number)]
        payload["metadata"] = metadata
        return super().normalize(payload)
