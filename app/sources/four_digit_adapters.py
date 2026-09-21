from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.sources.contracts import RawDrawRecord
from app.sources.normalizer import MappingSourceAdapter, SourceNormalizationError
from app.sources.registry import get_source_spec


class FourDigitAdapter(MappingSourceAdapter):
    """Adapter for a provider parser's canonical four-digit result."""

    def normalize(self, payload: Mapping[str, Any]) -> RawDrawRecord:
        payload = dict(payload)
        draw_type = payload.get("draw_type")
        if draw_type not in self.spec.draw_types:
            raise SourceNormalizationError("Unsupported draw type for source")
        raw_number = str(payload.get("number", "")).strip()
        if len(raw_number) != 4 or not raw_number.isdigit():
            raise SourceNormalizationError(
                "Four-digit number must be exactly four digits"
            )
        metadata = dict(payload.get("metadata") or {})
        metadata["raw_result"] = raw_number
        metadata["digit_count"] = 4
        payload["main_numbers"] = [int(raw_number)]
        payload["metadata"] = metadata
        return super().normalize(payload)


class AntioquenitaAdapter(FourDigitAdapter):
    def __init__(self) -> None:
        super().__init__(get_source_spec("ANTIOQUENITA"))


class ChonticoAdapter(FourDigitAdapter):
    def __init__(self) -> None:
        super().__init__(get_source_spec("CHONTICO"))


class DoradoAdapter(FourDigitAdapter):
    def __init__(self) -> None:
        super().__init__(get_source_spec("DORADO"))


class CafeteritoAdapter(FourDigitAdapter):
    def __init__(self) -> None:
        super().__init__(get_source_spec("CAFETERITO"))


class PaisitaAdapter(FourDigitAdapter):
    def __init__(self) -> None:
        super().__init__(get_source_spec("PAISITA"))


class FantasticaAdapter(FourDigitAdapter):
    def __init__(self) -> None:
        super().__init__(get_source_spec("FANTASTICA"))
