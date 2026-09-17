import pytest

from app.integrations.lottery_source_adapters import (
    JsonLotterySourceAdapter,
    LotterySourceAdapterRegistry,
)


def test_registered_adapter_source_identity_cannot_change_silently():
    adapter = JsonLotterySourceAdapter("provider-a")
    registry = LotterySourceAdapterRegistry([adapter])
    adapter.source_name = "provider-b"

    with pytest.raises(ValueError, match="source has changed"):
        registry.get("provider-a")

    with pytest.raises(ValueError, match="source has changed"):
        registry.parse_draw("provider-a", {})


def test_registry_instances_are_isolated():
    first = LotterySourceAdapterRegistry([JsonLotterySourceAdapter("provider-a")])
    second = LotterySourceAdapterRegistry([JsonLotterySourceAdapter("provider-b")])

    assert first.get("provider-a").source_name == "provider-a"
    assert second.get("provider-b").source_name == "provider-b"

    with pytest.raises(KeyError, match="Unknown lottery source"):
        first.get("provider-b")
    with pytest.raises(KeyError, match="Unknown lottery source"):
        second.get("provider-a")
