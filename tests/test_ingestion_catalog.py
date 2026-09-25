from app.models.ingestion_schedule_state import IngestionScheduleState
from app.sources.catalog import build_ingestion_catalog
from app.sources.scheduler import PersistentIngestionScheduler


def test_ingestion_catalog_isolated_and_complete():
    jobs = build_ingestion_catalog()
    keys = {job.key for job in jobs}
    lotteries = {job.lottery_code for job in jobs}

    assert len(jobs) == len(keys)
    assert {"MILOTO", "BALOTO", "REVANCHA", "SUPER_ASTRO"}.issubset(lotteries)
    assert {
        "ANTIOQUENITA",
        "CHONTICO",
        "DORADO",
        "CAFETERITO",
        "PAISITA",
        "FANTASTICA",
    }.issubset(lotteries)
    assert any(job.key == "chontico-html-primary" and not job.enabled for job in jobs)
    assert any(job.lottery_code == "LOTERIA_RISARALDA" for job in jobs)
    assert all(
        job.interval_seconds in {900, 1800, 3600}
        for job in jobs
    )


def test_persistent_scheduler_claims_each_due_job_once():
    from datetime import UTC, datetime

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    IngestionScheduleState.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    class StubOrchestrator:
        def __init__(self):
            self.calls = []

        def run_job(self, job):
            self.calls.append(job.key)
            from app.sources.orchestrator import IngestionRunResult

            now = datetime.now(UTC)
            return IngestionRunResult(
                run_id="run-1",
                job_key=job.key,
                lottery_code=job.lottery_code,
                status="success",
                attempts=1,
                records_seen=0,
                records_persisted=0,
                error=None,
                started_at=now,
                finished_at=now,
            )

    from app.sources.orchestrator import IngestionJob

    job = IngestionJob(
        key="test-persistent",
        lottery_code="MILOTO",
        url="https://example.test/results",
        pipeline_factory=lambda: None,
        interval_seconds=900,
    )
    orchestrator = StubOrchestrator()
    scheduler = PersistentIngestionScheduler(
        orchestrator=orchestrator,
        jobs=(job,),
        session_factory=SessionLocal,
    )
    now = datetime(2026, 9, 22, 22, 0, tzinfo=UTC)

    first = scheduler.run_due(now)
    second = scheduler.run_due(now)

    assert len(first) == 1
    assert second == []
    assert orchestrator.calls == ["test-persistent"]

    state = SessionLocal().get(IngestionScheduleState, "test-persistent")
    assert state is not None
    assert state.last_status == "success"
    assert state.last_run_id == "run-1"


def test_traditional_catalog_uses_source_specific_endpoints_and_fetchers():
    from app.sources.catalog import _traditional_fetcher
    from app.sources.fetchers import CundinamarcaActaSourceFetcher
    from app.sources.traditional_lottery import get_traditional_source

    expected_urls = {
        "LOTERIA_CUNDINAMARCA": "https://www.loteriadecundinamarca.com.co/?p=actas-de-resultados&view=distribuidores",
        "LOTERIA_CRUZ_ROJA": "https://lotecruz.org.co/",
        "LOTERIA_VALLE": "https://loteriadelvalle.com/",
        "LOTERIA_RISARALDA": "https://ventas.loteriadelrisaralda.com/resultados",
        "LOTERIA_BOYACA": "https://loteriadeboyaca.gov.co/resultados/",
    }
    for code, expected_url in expected_urls.items():
        profile = get_traditional_source(code)
        assert profile.result_url == expected_url
        assert profile.verified is True

    assert isinstance(
        _traditional_fetcher("LOTERIA_CUNDINAMARCA"),
        CundinamarcaActaSourceFetcher,
    )
