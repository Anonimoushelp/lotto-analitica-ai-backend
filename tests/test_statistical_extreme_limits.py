import json
from datetime import date, timedelta
from types import SimpleNamespace

from app.services.statistical_service import StatisticalService


def draw(numbers, draw_id, day_offset=0):
    return SimpleNamespace(
        id=draw_id,
        draw_date=date(2026, 1, 1) + timedelta(days=day_offset),
        lottery_id=1,
        main_numbers=numbers,
    )


def test_empty_analyzable_set_is_fully_zeroed_and_json_serializable():
    result = StatisticalService.analyze([draw(None, 1), draw([], 2, 1)])
    assert result["number_frequency"] == {}
    assert result["number_recency"] == {}
    assert result["even_odd_distribution"] == {}
    assert result["sum_distribution"] == {"count": 0, "minimum": None, "maximum": None, "average": None}
    assert result["pair_frequency"] == {}
    assert result["consecutive_numbers"] == {"draws_with_consecutive": 0, "total_consecutive_pairs": 0, "maximum_consecutive_pairs": 0}
    json.dumps(result, allow_nan=False)


def test_pair_and_consecutive_boundaries_for_zero_one_and_two_numbers():
    zero = StatisticalService.analyze([draw([], 1)])
    one = StatisticalService.analyze([draw([7], 2)])
    two = StatisticalService.analyze([draw([7, 8], 3)])
    assert zero["pair_frequency"] == {}
    assert zero["consecutive_numbers"]["maximum_consecutive_pairs"] == 0
    assert one["pair_frequency"] == {}
    assert one["consecutive_numbers"] == {"draws_with_consecutive": 0, "total_consecutive_pairs": 0, "maximum_consecutive_pairs": 0}
    assert two["pair_frequency"] == {"7-8": 1}
    assert two["consecutive_numbers"] == {"draws_with_consecutive": 1, "total_consecutive_pairs": 1, "maximum_consecutive_pairs": 1}


def test_single_draw_has_exact_sum_and_finite_average():
    result = StatisticalService.analyze([draw([1, 2, 3, 4, 5], 1)])
    assert result["sum_distribution"] == {"count": 1, "minimum": 15, "maximum": 15, "average": 15.0}
    json.dumps(result, allow_nan=False)


def test_large_draw_count_preserves_integer_frequencies_without_float_conversion():
    draws = [draw([1, 2, 3, 4, 5], index, index) for index in range(1, 1001)]
    result = StatisticalService.analyze(draws)
    assert result["number_frequency"] == {1: 1000, 2: 1000, 3: 1000, 4: 1000, 5: 1000}
    assert result["sum_distribution"] == {"count": 1000, "minimum": 15, "maximum": 15, "average": 15.0}
    assert result["pair_frequency"]["1-2"] == 1000
    assert result["consecutive_numbers"] == {"draws_with_consecutive": 1000, "total_consecutive_pairs": 4000, "maximum_consecutive_pairs": 4}
    json.dumps(result, allow_nan=False)


def test_large_integer_values_remain_exact_and_json_safe():
    large_numbers = [10**30, 10**30 + 2, 10**30 + 4]
    result = StatisticalService.analyze([draw(large_numbers, 1)])
    assert result["number_frequency"] == {number: 1 for number in large_numbers}
    assert result["sum_distribution"]["count"] == 1
    assert result["sum_distribution"]["minimum"] == sum(large_numbers)
    assert result["sum_distribution"]["maximum"] == sum(large_numbers)
    assert result["consecutive_numbers"]["total_consecutive_pairs"] == 0
    json.dumps(result, allow_nan=False)


def test_same_date_and_permuted_input_remain_byte_equivalent_after_json_encoding():
    draws = [draw([1, 2, 3], 1), draw([2, 4, 6], 2), draw([1, 4, 7], 3)]
    first = json.dumps(StatisticalService.analyze(draws), sort_keys=True, separators=(",", ":"), allow_nan=False)
    second = json.dumps(StatisticalService.analyze(list(reversed(draws))), sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert first == second
