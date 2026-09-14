import pytest

from app.integrations.lottery_source_adapters import JsonLotterySourceAdapter


@pytest.mark.parametrize("value", [None, 123, 7.5, True, [], {}])
def test_json_adapter_rejects_non_string_source_name(value):
    with pytest.raises(TypeError, match="Invalid source name"):
        JsonLotterySourceAdapter(value)  # type: ignore[arg-type]


def test_json_adapter_rejects_blank_or_control_source_name():
    for value in ("", "   ", "provider\nexample", "provider\texample"):
        with pytest.raises(ValueError, match="Invalid source name"):
            JsonLotterySourceAdapter(value)


def test_json_adapter_accepts_trimmed_source_name():
    adapter = JsonLotterySourceAdapter(" provider-example ")
    assert adapter.source_name == "provider-example"
