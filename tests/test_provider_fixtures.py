import json
from pathlib import Path

from app.sources.adapters import (
    BalotoAdapter,
    MiLotoAdapter,
    RevanchaAdapter,
    SuperAstroAdapter,
)
from app.sources.provider_parsers import (
    BalotoFamilyJsonParser,
    MiLotoJsonParser,
    SuperAstroJsonParser,
)

FIXTURES = Path(__file__).parent / "fixtures" / "providers"


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["results"]


def test_miloto_fixture_normalizes_to_canonical_record() -> None:
    raw = MiLotoJsonParser().parse_record(_load("miloto.json")[0])
    normalized = MiLotoAdapter().normalize(raw)

    assert normalized.lottery_code == "MILOTO"
    assert normalized.draw_type == "MILOTO"
    assert normalized.draw_number == "609"
    assert normalized.main_numbers == [10, 15, 31, 33, 39]


def test_baloto_fixture_keeps_baloto_and_revancha_independent() -> None:
    rows = _load("baloto_revancha.json")
    baloto = BalotoFamilyJsonParser().parse_record(rows[0])
    revancha = BalotoFamilyJsonParser().parse_record(rows[1])

    baloto_record = BalotoAdapter().normalize(baloto)
    revancha_record = RevanchaAdapter().normalize(revancha)

    assert baloto_record.lottery_code == "BALOTO"
    assert baloto_record.draw_type == "BALOTO"
    assert baloto_record.bonus_numbers == [4]

    assert revancha_record.lottery_code == "REVANCHA"
    assert revancha_record.draw_type == "REVANCHA"
    assert revancha_record.bonus_numbers == [4]

    assert baloto_record.draw_number == revancha_record.draw_number
    assert baloto_record.draw_date == revancha_record.draw_date


def test_super_astro_fixture_preserves_sign_and_leading_zero() -> None:
    rows = _load("super_astro.json")
    parser = SuperAstroJsonParser()
    adapter = SuperAstroAdapter()

    first = adapter.normalize(parser.parse_record(rows[0]))
    luna = adapter.normalize(parser.parse_record(rows[1]))
    leading_zero = adapter.normalize(parser.parse_record(rows[2]))

    assert first.lottery_code == "SUPER_ASTRO"
    assert first.draw_type == "ASTRO_SOL"
    assert first.main_numbers == [8874]
    assert first.metadata["sign"] == "Cancer"
    assert first.metadata["raw_result"] == "8874"

    assert luna.draw_type == "ASTRO_LUNA"
    assert luna.main_numbers == [1305]
    assert luna.metadata["sign"] == "Libra"

    assert leading_zero.main_numbers == [982]
    assert leading_zero.metadata["raw_result"] == "0982"
    assert leading_zero.metadata["digit_count"] == 4
