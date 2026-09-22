from datetime import UTC, datetime, date

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.services.lottery_draw_service import LotteryDrawService
from app.sources.adapters import BalotoAdapter, MiLotoAdapter, RevanchaAdapter, SuperAstroAdapter
from app.sources.four_digit_adapters import AntioquenitaAdapter, CafeteritoAdapter, ChonticoAdapter, DoradoAdapter, FantasticaAdapter, PaisitaAdapter
from app.sources.four_digit_parsers import AntioquenitaJsonParser, CafeteritoJsonParser, ChonticoJsonParser, DoradoJsonParser, FantasticaJsonParser, PaisitaJsonParser
from app.sources.provider_parsers import BalotoFamilyJsonParser, MiLotoJsonParser, SuperAstroJsonParser
from app.sources.registry import get_source_spec

ENGINE = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=ENGINE)
LotteryDraw.__table__.create(bind=ENGINE)

CASES = [
    ("MILOTO", MiLotoJsonParser(), MiLotoAdapter(), {"draw_number": "609", "draw_date": "2026-09-18", "main_numbers": [10, 15, 31, 33, 39]}),
    ("BALOTO", BalotoFamilyJsonParser(), BalotoAdapter(), {"game_type": "BALOTO", "draw_number": "1234", "draw_date": "2026-09-20", "main_numbers": [5, 12, 23, 31, 42], "superbalota": 7}),
    ("REVANCHA", BalotoFamilyJsonParser(), RevanchaAdapter(), {"game_type": "REVANCHA", "draw_number": "1234", "draw_date": "2026-09-20", "main_numbers": [5, 12, 23, 31, 42], "revancha_bonus": 7}),
    ("SUPER_ASTRO", SuperAstroJsonParser(), SuperAstroAdapter(), {"draw_type": "ASTRO_SOL", "draw_number": "9876", "draw_date": "2026-09-20", "number": "0982", "sign": "Virgo"}),
    ("ANTIOQUENITA", AntioquenitaJsonParser(), AntioquenitaAdapter(), {"tipo": "ANTIOQUENITA_2", "sorteo": "20260920-2", "fecha": "2026-09-20", "resultado": "1054"}),
    ("CHONTICO", ChonticoJsonParser(), ChonticoAdapter(), {"tipo": "CHONTICO_DIA", "sorteo": "20260920-D", "fecha": "2026-09-20", "resultado": "6725"}),
    ("DORADO", DoradoJsonParser(), DoradoAdapter(), {"tipo": "DORADO_DIA", "sorteo": "20260921-D", "fecha": "2026-09-21", "resultado": "7279", "additional_value": 5}),
    ("CAFETERITO", CafeteritoJsonParser(), CafeteritoAdapter(), {"tipo": "CAFETERITO_NOCHE", "sorteo": "20260920-N", "fecha": "2026-09-20", "resultado": "3312"}),
    ("PAISITA", PaisitaJsonParser(), PaisitaAdapter(), {"tipo": "PAISITA_NOCHE", "sorteo": "20260920-N", "fecha": "2026-09-20", "resultado": "3946", "animal": "Caballo"}),
    ("FANTASTICA", FantasticaJsonParser(), FantasticaAdapter(), {"tipo": "FANTASTICA_NOCHE", "sorteo": "20260920-N", "fecha": "2026-09-20", "resultado": "2977"}),
]

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        cleanup = SessionLocal()
        cleanup.execute(delete(LotteryDraw))
        cleanup.execute(delete(Lottery))
        cleanup.commit()
        cleanup.close()

@pytest.mark.parametrize("lottery_code, parser, adapter, payload", CASES)
def test_controlled_ingestion_covers_all_ten_lotteries(lottery_code, parser, adapter, payload, db):
    spec = get_source_spec(lottery_code)
    payload = dict(payload)
    payload["source_url"] = spec.primary_url or f"https://example.test/{lottery_code.lower()}"
    payload["source_timestamp"] = datetime(2026, 9, 21, 16, 0, tzinfo=UTC)

    normalized = adapter.normalize(parser.parse_record(payload))

    assert normalized.lottery_code == lottery_code
    assert normalized.draw_type in spec.draw_types
    assert normalized.main_numbers
    assert normalized.source_url == payload["source_url"]
    assert normalized.source_timestamp == payload["source_timestamp"]

    if lottery_code in {"SUPER_ASTRO", "ANTIOQUENITA", "CHONTICO", "DORADO", "CAFETERITO", "PAISITA", "FANTASTICA"}:
        expected_raw = payload.get("number", payload.get("resultado"))
        assert normalized.metadata["raw_result"] == expected_raw
        assert normalized.metadata["digit_count"] == 4
    if lottery_code == "BALOTO":
        assert normalized.bonus_numbers == [7]
    if lottery_code == "REVANCHA":
        assert normalized.bonus_numbers == [7]
    if lottery_code == "SUPER_ASTRO":
        assert normalized.metadata["sign"] == "Virgo"
        assert normalized.metadata["raw_result"] == "0982"
    if lottery_code == "PAISITA":
        assert normalized.metadata["animal"] == "Caballo"
    if lottery_code == "DORADO":
        assert normalized.metadata["additional_value"] == 5

    lottery = Lottery(name=lottery_code, code=lottery_code.lower(), country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)

    persisted = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number=normalized.draw_number,
        draw_date=normalized.draw_date,
        draw_time=normalized.draw_time,
        main_numbers=normalized.main_numbers,
        bonus_numbers=normalized.bonus_numbers,
        draw_type=normalized.draw_type,
        source=normalized.source_name,
        source_url=normalized.source_url,
        source_timestamp=normalized.source_timestamp,
        metadata_json=normalized.metadata,
        validation_json={"format_valid": True, "date_valid": True, "duplicate": False, "source_verified": spec.primary_verified},
    )

    assert persisted.id is not None
    assert persisted.draw_type == normalized.draw_type
    assert persisted.draw_number == normalized.draw_number
    assert persisted.draw_date == normalized.draw_date
    assert persisted.main_numbers == normalized.main_numbers
    assert persisted.bonus_numbers == normalized.bonus_numbers
    assert persisted.metadata_json == normalized.metadata
    assert persisted.validation_json["format_valid"] is True

def test_controlled_ingestion_allows_html_source_without_draw_number(db):
    lottery = Lottery(name="Antioquenita", code="antioquenita", country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)

    persisted = LotteryDrawService.create_draw(
        db=db,
        lottery_id=lottery.id,
        draw_number=None,
        draw_date=date(2026, 9, 20),
        main_numbers=[153],
        draw_type="ANTIOQUENITA_1",
        source="Antioquenita",
        source_url="https://antioquenita.co/",
        validation_json={"format_valid": True, "date_valid": True, "source_verified": False},
    )

    assert persisted.draw_number is None
    assert persisted.draw_type == "ANTIOQUENITA_1"
