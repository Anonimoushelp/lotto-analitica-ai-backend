from datetime import date

import pytest

from app.sources.contracts import SourceDraw, SourceMetadata
from app.sources.normalizer import normalize_source_draw


def make_draw(groups: dict[str, list[str]]) -> SourceDraw:
    return SourceDraw(
        draw_number="001",
        draw_date=date(2026, 9, 20),
        groups=groups,
        metadata=SourceMetadata(provider="fixture", source_type="fixture"),
        raw_payload={"fixture": True},
    )


def test_normalizer_strips_values_and_normalizes_group_codes() -> None:
    result = normalize_source_draw(
        make_draw({" Main ": [" 05 ", "12"], "BONUS": [" 7 "]})
    )

    assert result.groups == {"main": ("05", "12"), "bonus": ("7",)}
    assert result.raw_payload == {"fixture": True}


def test_normalizer_rejects_duplicate_values() -> None:
    with pytest.raises(ValueError, match="duplicate values"):
        normalize_source_draw(make_draw({"main": ["5", "5"]}))


def test_normalizer_rejects_group_code_collision() -> None:
    with pytest.raises(ValueError, match="collide"):
        normalize_source_draw(make_draw({" Main ": ["5"], "main": ["6"]}))


def test_source_contract_rejects_empty_groups() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        make_draw({"main": []})
