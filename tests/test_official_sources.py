from datetime import date

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.lottery import Lottery
from app.models.lottery_draw import LotteryDraw
from app.services.official_ingestion_service import OfficialIngestionService
from app.sources.base import SourceValidationError
from app.sources.baloto import BalotoAdapter
from app.sources.loteria_bogota import BogotaLotteryAdapter
from app.sources.loteria_medellin import MedellinLotteryAdapter
from app.sources.selae import SelaeAdapter

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=engine)
LotteryDraw.__table__.create(bind=engine)


def db_session():
    return SessionLocal()


def seed(db, code: str):
    lottery = Lottery(name=code, code=code, country="Test")
    db.add(lottery)
    db.commit()
    db.refresh(lottery)
    return lottery


@pytest.fixture
def db():
    db = db_session()
    try:
        yield db
    finally:
        db.close()
        cleanup = db_session()
        cleanup.execute(delete(LotteryDraw))
        cleanup.execute(delete(Lottery))
        cleanup.commit()
        cleanup.close()


BALOTO_FIXTURE = """
<div>14 de Septiembre de 2026</div>
<div>03 - 05 - 10 - 20 - 31 - 08</div>
"""

BOGOTA_FIXTURE = """
Sorteo 2859
13 de agosto 2026
Número 0872 Serie 343
"""

MEDELLIN_FIXTURE = """
Sorteo 4853
18/Septiembre/2026
Número 8535 Serie 183
"""

SELAE_FIXTURE = """
18/09/2026
NÚMEROS: 08 17 25 30 44
"""


def test_baloto_adapter_validates_ranges_and_bonus():
    draw = BalotoAdapter().parse(BALOTO_FIXTURE)
    assert draw.draw_date == date(2026, 9, 14)
    assert draw.main_numbers == [3, 5, 10, 20, 31]
    assert draw.bonus_numbers == [8]


def test_baloto_rejects_invalid_main_number():
    with pytest.raises(SourceValidationError):
        BalotoAdapter().parse(BALOTO_FIXTURE.replace("31", "44"))


def test_bogota_adapter_preserves_leading_zero_and_series():
    draw = BogotaLotteryAdapter().parse(BOGOTA_FIXTURE)
    assert draw.draw_number == "2859"
    assert draw.main_numbers == [872]
    assert draw.metadata_json["winning_number"] == "0872"
    assert draw.metadata_json["winning_series"] == "343"


def test_medellin_adapter_rejects_placeholder():
    with pytest.raises(SourceValidationError):
        MedellinLotteryAdapter().parse(MEDELLIN_FIXTURE.replace("8535", "0000").replace("183", "000"))


def test_medellin_adapter_parses_official_shape():
    draw = MedellinLotteryAdapter().parse(MEDELLIN_FIXTURE)
    assert draw.draw_number == "4853"
    assert draw.main_numbers == [8535]
    assert draw.metadata_json["winning_series"] == "183"


def test_selae_adapter_parses_documented_five_number_fixture():
    draw = SelaeAdapter().parse(SELAE_FIXTURE)
    assert draw.draw_date == date(2026, 9, 18)
    assert draw.main_numbers == [8, 17, 25, 30, 44]


def test_ingestion_is_idempotent(db):
    seed(db, "BALOTO")
    adapter = BalotoAdapter()
    first = OfficialIngestionService.ingest(db, adapter, client=_FakeClient(BALOTO_FIXTURE))
    second = OfficialIngestionService.ingest(db, adapter, client=_FakeClient(BALOTO_FIXTURE))
    assert first.id == second.id
    assert db.query(LotteryDraw).count() == 1


def test_ingestion_rejects_changed_existing_result(db):
    seed(db, "BALOTO")
    adapter = BalotoAdapter()
    OfficialIngestionService.ingest(db, adapter, client=_FakeClient(BALOTO_FIXTURE))
    changed = BALOTO_FIXTURE.replace("31", "30")
    with pytest.raises(SourceValidationError, match="conflicts"):
        OfficialIngestionService.ingest(db, adapter, client=_FakeClient(changed))


class _FakeClient:
    def __init__(self, payload: str):
        self.payload = payload

    def get(self, url: str) -> str:
        return self.payload


def test_source_client_failure_is_translated(monkeypatch):
    from app.sources.base import SourceClient

    class BrokenHttpx:
        class HTTPError(Exception):
            pass

        @staticmethod
        def get(*args, **kwargs):
            raise BrokenHttpx.HTTPError("timeout")

    monkeypatch.setitem(__import__("sys").modules, "httpx", BrokenHttpx)
    with pytest.raises(SourceValidationError, match="unavailable"):
        SourceClient().get("https://official.invalid")
