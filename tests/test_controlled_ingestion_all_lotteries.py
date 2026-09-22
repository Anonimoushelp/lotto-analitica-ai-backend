import json
from datetime import UTC, date, datetime
from urllib.parse import urlparse

import pytest
from httpx import MockTransport, Response
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.services.lottery_draw_service import LotteryDrawService
from app.sources.adapters import (
    BalotoAdapter,
    MiLotoAdapter,
    RevanchaAdapter,
    SuperAstroAdapter,
)
from app.sources.contracts import SourceAdapter
from app.sources.fetchers import HttpSourceFetcher
from app.sources.four_digit_adapters import (
    AntioquenitaAdapter,
    CafeteritoAdapter,
    ChonticoAdapter,
    DoradoAdapter,
    FantasticaAdapter,
    PaisitaAdapter,
)
from app.sources.four_digit_parsers import (
    AntioquenitaJsonParser,
    CafeteritoJsonParser,
    ChonticoJsonParser,
    DoradoJsonParser,
    FantasticaJsonParser,
    PaisitaJsonParser,
)
from app.sources.ingestion import SourceIngestionPipeline
from app.sources.parsers import HtmlTableParser
from app.sources.provider_parser_adapter import ProviderParserAdapter
from app.sources.provider_parsers import (
    BalotoFamilyJsonParser,
    MiLotoJsonParser,
    SuperAstroJsonParser,
)
from app.sources.registry import get_source_spec
from app.sources.traditional_lottery import get_traditional_source
from app.sources.traditional_lottery_components import (
    TraditionalLotteryAdapter,
    TraditionalLotteryHtmlParser,
)

ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=ENGINE)
LotteryDraw.__table__.create(bind=ENGINE)

CASES = [
    ("MILOTO", MiLotoJsonParser(), MiLotoAdapter(), {"draw_number": "609", "draw_date": "2026-09-18", "main_numbers": [10, 15, 31, 33, 39]}),
    ("BALOTO", BalotoFamilyJsonParser(), BalotoAdapter(), {"game_type": "BALOTO", "draw_number": "1234", "draw_date": "2026-09-20", "main_numbers": [5, 12, 23, 31, 42], "superbalota": [7]}),
    ("REVANCHA", BalotoFamilyJsonParser(), RevanchaAdapter(), {"game_type": "REVANCHA", "draw_number": "1234", "draw_date": "2026-09-20", "main_numbers": [5, 12, 23, 31, 42], "revancha_bonus": [7]}),
    ("SUPER_ASTRO", SuperAstroJsonParser(), SuperAstroAdapter(), {"draw_type": "ASTRO_SOL", "draw_number": "9876", "draw_date": "2026-09-20", "number": "0982", "sign": "Virgo"}),
    ("ANTIOQUENITA", AntioquenitaJsonParser(), AntioquenitaAdapter(), {"tipo": "ANTIOQUENITA_2", "sorteo": "20260920-2", "fecha": "2026-09-20", "resultado": "1054"}),
    ("CHONTICO", ChonticoJsonParser(), ChonticoAdapter(), {"tipo": "CHONTICO_DIA", "sorteo": "20260920-D", "fecha": "2026-09-20", "resultado": "6725"}),
    ("DORADO", DoradoJsonParser(), DoradoAdapter(), {"tipo": "DORADO_DIA", "sorteo": "20260921-D", "fecha": "2026-09-21", "resultado": "7279", "additional_value": 5}),
    ("CAFETERITO", CafeteritoJsonParser(), CafeteritoAdapter(), {"tipo": "CAFETERITO_NOCHE", "sorteo": "20260920-N", "fecha": "2026-09-20", "resultado": "3312"}),
    ("PAISITA", PaisitaJsonParser(), PaisitaAdapter(), {"tipo": "PAISITA_NOCHE", "sorteo": "20260920-N", "fecha": "2026-09-20", "resultado": "3946", "animal": "Caballo"}),
    ("FANTASTICA", FantasticaJsonParser(), FantasticaAdapter(), {"tipo": "FANTASTICA_NOCHE", "sorteo": "20260920-N", "fecha": "2026-09-20", "resultado": "2977"}),
]

TRADITIONAL_READY = (
    "LOTERIA_CUNDINAMARCA",
    "LOTERIA_TOLIMA",
    "LOTERIA_CRUZ_ROJA",
    "LOTERIA_HUILA",
    "LOTERIA_MANIZALES",
    "LOTERIA_VALLE",
    "LOTERIA_BOGOTA",
    "LOTERIA_MEDELLIN",
    "LOTERIA_SANTANDER",
    "LOTERIA_RISARALDA",
    "LOTERIA_BOYACA",
    "LOTERIA_CAUCA",
)


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
def test_controlled_ingestion_covers_all_ten_lotteries(
    lottery_code: str,
    parser,
    adapter: SourceAdapter,
    payload: dict,
    db,
):
    spec = get_source_spec(lottery_code)
    source_url = spec.primary_url or f"https://example.test/{lottery_code.lower()}"

    transport = MockTransport(
        lambda request: Response(
            200,
            content=json.dumps({"results": [payload]}).encode(),
            headers={"content-type": "application/json"},
        )
    )
    fetcher = HttpSourceFetcher(
        allowed_hosts={urlparse(source_url).hostname or ""},
        transport=transport,
    )

    pipeline = SourceIngestionPipeline(
        fetcher=fetcher,
        parser=ProviderParserAdapter(parser),
        adapter=adapter,
    )
    normalized = pipeline.run(source_url)[0]

    assert normalized.lottery_code == lottery_code
    assert normalized.draw_type in spec.draw_types
    assert normalized.main_numbers
    assert normalized.source_url == source_url
    assert normalized.source_timestamp is not None

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

    persisted = LotteryDrawService.persist_raw_record(db=db, record=normalized)

    assert persisted.id is not None
    assert persisted.draw_type == normalized.draw_type
    assert persisted.draw_number == normalized.draw_number
    assert persisted.draw_date == normalized.draw_date
    assert persisted.main_numbers == normalized.main_numbers
    assert persisted.bonus_numbers == normalized.bonus_numbers
    assert persisted.metadata_json == normalized.metadata
    assert persisted.source_url == normalized.source_url
    assert persisted.source_timestamp == normalized.source_timestamp.replace(tzinfo=None)
    assert persisted.validation_json["format_valid"] is True


@pytest.mark.parametrize("lottery_code", TRADITIONAL_READY)
def test_controlled_ingestion_covers_all_verified_traditional_lotteries(
    lottery_code: str,
    db,
):
    profile = get_traditional_source(lottery_code)
    assert profile.verified is True
    assert profile.result_url is not None

    source_url = profile.result_url
    html = (
        "<html><body>"
        "<h1>Sorteo número 4187</h1>"
        "<div>22 de septiembre de 2026</div>"
        "<div>Número: 6845</div>"
        "<div>Serie: 031</div>"
        "</body></html>"
    )

    transport = MockTransport(
        lambda request: Response(
            200,
            content=html.encode(),
            headers={"content-type": "text/html; charset=utf-8"},
        )
    )
    fetcher = HttpSourceFetcher(
        allowed_hosts={urlparse(source_url).hostname or ""},
        transport=transport,
    )

    pipeline = SourceIngestionPipeline(
        fetcher=fetcher,
        parser=TraditionalLotteryHtmlParser(lottery_code),
        adapter=TraditionalLotteryAdapter(lottery_code),
    )
    normalized = pipeline.run(source_url)[0]

    assert normalized.lottery_code == lottery_code
    assert normalized.draw_type == f"{lottery_code}_ORDINARY"
    assert normalized.draw_number == "4187"
    assert normalized.draw_date == date(2026, 9, 22)
    assert normalized.main_numbers == [6845]
    assert normalized.metadata["raw_result"] == "6845"
    assert normalized.metadata["digit_count"] == 4
    assert normalized.metadata["series"] == "031"
    assert normalized.source_url == source_url
    assert normalized.source_timestamp is not None

    lottery = Lottery(name=lottery_code, code=lottery_code.lower(), country="Colombia")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)

    persisted = LotteryDrawService.persist_raw_record(db=db, record=normalized)

    assert persisted.id is not None
    assert persisted.draw_number == "4187"
    assert persisted.draw_date == date(2026, 9, 22)
    assert persisted.main_numbers == [6845]
    assert persisted.metadata_json["series"] == "031"
    assert persisted.source_url == normalized.source_url
    assert persisted.validation_json["source_verified"] is True



@pytest.mark.parametrize("draw_type", ["ASTRO_SOL", "ASTRO_LUNA"])
def test_super_astro_both_draw_types_use_secure_fetcher(draw_type: str, db):
    lottery = Lottery(name="SUPER_ASTRO", code="super_astro", country="Colombia")
    db.add(lottery)
    db.commit()

    source_url = "https://example.test/super-astro"
    transport = MockTransport(
        lambda request: Response(
            200,
            content=json.dumps(
                {
                    "results": [
                        {
                            "draw_type": draw_type,
                            "draw_number": "7001",
                            "draw_date": "2026-09-22",
                            "number": "0047",
                            "sign": "Aries",
                        }
                    ]
                }
            ).encode(),
            headers={"content-type": "application/json"},
        )
    )
    fetcher = HttpSourceFetcher(
        allowed_hosts={"example.test"},
        transport=transport,
    )
    pipeline = SourceIngestionPipeline(
        fetcher=fetcher,
        parser=ProviderParserAdapter(SuperAstroJsonParser()),
        adapter=SuperAstroAdapter(),
    )

    record = pipeline.run(source_url)[0]

    assert record.draw_type == draw_type
    assert record.main_numbers == [47]
    assert record.metadata["raw_result"] == "0047"
    assert record.metadata["digit_count"] == 4
    assert record.metadata["sign"] == "Aries"
    assert record.source_url == source_url

    persisted = LotteryDrawService.persist_raw_record(db=db, record=record)
    assert persisted.draw_type == draw_type
    assert persisted.metadata_json["raw_result"] == "0047"


def test_controlled_html_table_source_uses_secure_fetcher(db):
    lottery = Lottery(name="CHONTICO", code="chontico", country="Colombia")
    db.add(lottery)
    db.commit()

    html = """
    <html><body>
      <table>
        <tr><th>Chance</th><th>Fecha</th><th>Resultado</th></tr>
        <tr><td>Chontico Día</td><td>22 de septiembre de 2026</td><td>6725</td></tr>
      </table>
    </body></html>
    """
    source_url = "https://example.test/chontico"
    transport = MockTransport(
        lambda request: Response(
            200,
            content=html.encode(),
            headers={"content-type": "text/html; charset=utf-8"},
        )
    )
    fetcher = HttpSourceFetcher(
        allowed_hosts={"example.test"},
        transport=transport,
    )
    pipeline = SourceIngestionPipeline(
        fetcher=fetcher,
        parser=HtmlTableParser(),
        adapter=ChonticoAdapter(),
    )

    record = pipeline.run(source_url)[0]

    assert record.draw_type == "CHONTICO_DIA"
    assert record.draw_date == date(2026, 9, 22)
    assert record.main_numbers == [6725]
    assert record.source_url == source_url

    persisted = LotteryDrawService.persist_raw_record(db=db, record=record)
    assert persisted.draw_type == "CHONTICO_DIA"
    assert persisted.main_numbers == [6725]


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


def test_raw_record_persistence_is_idempotent(db):
    lottery = Lottery(name="MiLoto", code="miloto", country="Colombia")
    db.add(lottery)
    db.commit()

    record = MiLotoAdapter().normalize(
        {
            "draw_number": "609",
            "draw_date": "2026-09-18",
            "main_numbers": [10, 15, 31, 33, 39],
            "source_name": "MiLoto",
            "source_url": "https://example.test/miloto",
            "source_timestamp": datetime(2026, 9, 21, 16, 0, tzinfo=UTC),
        }
    )

    first = LotteryDrawService.persist_raw_record(db=db, record=record)
    second = LotteryDrawService.persist_raw_record(db=db, record=record)

    assert second.id == first.id
    assert db.query(LotteryDraw).count() == 1
    assert second.source == record.source_name
    assert second.source_timestamp == record.source_timestamp.replace(tzinfo=None)


def test_raw_record_persistence_rejects_conflicting_duplicate(db):
    lottery = Lottery(name="MiLoto", code="miloto", country="Colombia")
    db.add(lottery)
    db.commit()

    first = MiLotoAdapter().normalize(
        {
            "draw_number": "609",
            "draw_date": "2026-09-18",
            "main_numbers": [10, 15, 31, 33, 39],
            "source_name": "MiLoto",
            "source_url": "https://example.test/miloto",
        }
    )
    conflicting = MiLotoAdapter().normalize(
        {
            "draw_number": "609",
            "draw_date": "2026-09-18",
            "main_numbers": [1, 2, 3, 4, 5],
            "source_name": "MiLoto",
            "source_url": "https://example.test/miloto",
        }
    )

    LotteryDrawService.persist_raw_record(db=db, record=first)

    with pytest.raises(Exception) as exc:
        LotteryDrawService.persist_raw_record(db=db, record=conflicting)

    assert getattr(exc.value, "status_code", None) == 409
    assert db.query(LotteryDraw).count() == 1


def test_controlled_ingestion_uses_real_http_fetcher_json_to_raw_record(db):
    lottery = Lottery(name="MiLoto", code="miloto", country="Colombia")
    db.add(lottery)
    db.commit()

    transport = MockTransport(
        lambda request: Response(
            200,
            content=json.dumps(
                {
                    "results": [
                        {
                            "draw_number": "610",
                            "draw_date": "2026-09-19",
                            "main_numbers": [4, 9, 18, 27, 35],
                        }
                    ]
                }
            ).encode(),
            headers={"content-type": "application/json"},
        )
    )
    fetcher = HttpSourceFetcher(
        allowed_hosts={"example.test"},
        transport=transport,
    )
    pipeline = SourceIngestionPipeline(
        fetcher=fetcher,
        parser=ProviderParserAdapter(MiLotoJsonParser()),
        adapter=MiLotoAdapter(),
    )

    normalized = pipeline.run("https://example.test/miloto")
    assert len(normalized) == 1
    record = normalized[0]
    assert record.lottery_code == "MILOTO"
    assert record.draw_number == "610"
    assert record.main_numbers == [4, 9, 18, 27, 35]
    assert record.source_url == "https://example.test/miloto"
    assert record.source_timestamp is not None

    persisted = LotteryDrawService.persist_raw_record(db=db, record=record)

    assert persisted.id is not None
    assert persisted.draw_number == "610"
    assert persisted.main_numbers == [4, 9, 18, 27, 35]
    assert persisted.source_url == record.source_url
    assert persisted.source_timestamp == record.source_timestamp.replace(tzinfo=None)


def test_controlled_ingestion_uses_real_http_fetcher_html_to_raw_record(db):
    lottery_code = "LOTERIA_RISARALDA"
    lottery = Lottery(name=lottery_code, code=lottery_code.lower(), country="Colombia")
    db.add(lottery)
    db.commit()

    html = (
        "<html><body>"
        "<h1>Sorteo número 4188</h1>"
        "<div>23 de septiembre de 2026</div>"
        "<div>Resultado: 7316</div>"
        "<div>Serie: 032</div>"
        "</body></html>"
    )
    transport = MockTransport(
        lambda request: Response(
            200,
            content=html.encode(),
            headers={"content-type": "text/html; charset=utf-8"},
        )
    )
    fetcher = HttpSourceFetcher(
        allowed_hosts={"example.test"},
        transport=transport,
    )
    pipeline = SourceIngestionPipeline(
        fetcher=fetcher,
        parser=TraditionalLotteryHtmlParser(lottery_code),
        adapter=TraditionalLotteryAdapter(lottery_code),
    )

    record = pipeline.run("https://example.test/risaralda")[0]

    assert record.draw_number == "4188"
    assert record.draw_date == date(2026, 9, 23)
    assert record.main_numbers == [7316]
    assert record.metadata["series"] == "032"
    assert record.source_url == "https://example.test/risaralda"
    assert record.source_timestamp is not None

    persisted = LotteryDrawService.persist_raw_record(db=db, record=record)

    assert persisted.id is not None
    assert persisted.main_numbers == [7316]
    assert persisted.metadata_json["series"] == "032"
    assert persisted.source_url == record.source_url
    assert persisted.source_timestamp == record.source_timestamp.replace(tzinfo=None)
