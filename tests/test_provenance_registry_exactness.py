import pytest

from app.integrations.lottery_source_adapters import (
    JsonLotterySourceAdapter,
    LotterySourceAdapterRegistry,
)


def test_registry_rejects_whitespace_variants_of_registered_source():
    registry = LotterySourceAdapterRegistry(
        [JsonLotterySourceAdapter("provider-example")]
    )

    with pytest.raises(ValueError, match="must be normalized"):
        registry.get(" provider-example")

    with pytest.raises(ValueError, match="must be normalized"):
        registry.get("provider-example ")


def test_registry_parse_draw_rejects_whitespace_source_aliases():
    registry = LotterySourceAdapterRegistry(
        [JsonLotterySourceAdapter("provider-example")]
    )

    with pytest.raises(ValueError, match="must be normalized"):
        registry.parse_draw(" provider-example", {})
