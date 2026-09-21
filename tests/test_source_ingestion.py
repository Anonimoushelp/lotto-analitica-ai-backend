from datetime import date

import pytest

from app.sources.contracts import SourceDraw, SourceMetadata
from app.sources.ingestion import build_idempotency_key, ingest_draws


class FixtureAdapter:
    source_id = "fixture"

    def __init__(self, draws: list[SourceDraw]) -> None:
        self.draws = draws

    def fetch_draws(self) -> list[SourceDraw]:
        return self.draws


def draw(number: str = "001", values: list[str] | None = None) -> SourceDraw:
    return SourceDraw(
        draw_number=number,
        draw_date=date(2026, 9, 20),
        groups={"main": values or ["5", "12"]},
        metadata=SourceMetadata(provider="fixture", source_type="fixture"),
    )


def test_idempotency_key_is_stable() -> None:
    assert build_idempotency_key("fixture", draw()) == build_idempotency_key("fixture", draw())


def test_idempotency_key_changes_when_result_changes() -> None:
    assert build_idempotency_key("fixture", draw(values=["5", "13"])) != build_idempotency_key("fixture", draw())


def test_ingestion_normalizes_and_fingerprints() -> None:
    result = ingest_draws(FixtureAdapter([draw()]))
    assert len(result) == 1
    assert result[0].draw.groups == {"main": ("5", "12")}
    assert len(result[0].idempotency_key) == 64


def test_ingestion_rejects_duplicate_source_draws() -> None:
    with pytest.raises(ValueError, match="duplicate source draw"):
        ingest_draws(FixtureAdapter([draw(), draw()]))
