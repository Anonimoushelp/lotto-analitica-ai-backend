from datetime import date

from app.ingestion.contracts import IngestionDraw
from app.ingestion.loteriaya import LoteriaYaClient


def test_loteriaya_parser_maps_baloto_result():
    result = LoteriaYaClient._parse_result(
        "baloto",
        {
            "draw": "baloto",
            "name": "Baloto",
            "category": "baloto",
            "draw_date": "2026-09-16",
            "draw_number": "1234",
            "balls": [4, 17, 18, 20, 26],
            "super_ball": 5,
            "status": "confirmed",
            "published_at": "2026-09-16T23:05:00-05:00",
        },
    )

    assert result == IngestionDraw(
        lottery_code="baloto",
        draw_number="1234",
        draw_date=date(2026, 9, 16),
        main_numbers=[4, 17, 18, 20, 26],
        bonus_numbers=[5],
        source="loteriaya",
        metadata_json={
            "provider": "loteriaya",
            "provider_draw": "baloto",
            "provider_name": "Baloto",
            "category": "baloto",
            "status": "confirmed",
            "published_at": "2026-09-16T23:05:00-05:00",
            "winning_number": None,
            "winning_series": None,
        },
    )


def test_loteriaya_parser_ignores_disputed_results():
    assert (
        LoteriaYaClient._parse_result(
            "baloto",
            {
                "draw": "baloto",
                "draw_date": "2026-09-16",
                "balls": [1, 2, 3],
                "status": "disputed",
            },
        )
        is None
    )


def test_loteriaya_parser_ignores_non_ball_results():
    assert (
        LoteriaYaClient._parse_result(
            "loteria-del-huila",
            {
                "draw": "loteria-del-huila",
                "draw_date": "2026-08-25",
                "winning_number": "7401",
                "status": "confirmed",
            },
        )
        is None
    )
