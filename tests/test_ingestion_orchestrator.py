from datetime import UTC, datetime, timedelta

from app.models.lottery import Lottery
from app.sources.contracts import RawDrawRecord
from app.sources.orchestrator import IngestionJob, IngestionOrchestrator
from app.sources.scheduler import IngestionScheduler
from app.models.lottery_draw import LotteryDraw


ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False)
Lottery.__table__.create(bind=ENGINE)
LotteryDraw.__table__.create(bind=ENGINE)


class StubPipeline:
    def __init__(self, record: RawDrawRecord):
        self.record = record

    def run(self, url: str):
        return [self.record]


class FailingPipeline:
    calls = 0

    def run(self, url: str):
        type(self).calls += 1
        raise RuntimeError("source unavailable")


def _record(lottery_code: str = "MILOTO") -> RawDrawRecord:
    from datetime import date

    return RawDrawRecord(
        lottery_code=lottery_code,
        draw_type="MILOTO",
        draw_number="700",
        draw_date=date(2026, 9, 22),
        draw_time=None,
        main_numbers=[1, 2, 3, 4, 5],
        source_name="Test Source",
        source_url="https://example.test/results",
        source_timestamp=datetime(2026, 9, 22, 18, 0, tzinfo=UTC),
    )


def test_orchestrator_persists_and_is_idempotent():
    db = SessionLocal()
    lottery = Lottery(name="MiLoto", code="miloto", country="Colombia")
    db.add(lottery)
    db.commit()

    session_factory = SessionLocal
    job = IngestionJob(
        key="miloto-test",
        lottery_code="MILOTO",
        url="https://example.test/results",
        pipeline_factory=lambda: StubPipeline(_record()),
        max_attempts=1,
    )
    orchestrator = IngestionOrchestrator(
        session_factory=session_factory,
        sleep=lambda _: None,
    )

    first = orchestrator.run_job(job)
    second = orchestrator.run_job(job)

    assert first.status == "success"
    assert first.records_seen == 1
    assert first.records_persisted == 1
    assert second.status == "success"
    assert second.records_persisted == 1
    db.close()


def test_orchestrator_isolates_failure_and_retries():
    FailingPipeline.calls = 0
    job = IngestionJob(
        key="failing-source",
        lottery_code="MILOTO",
        url="https://example.test/results",
        pipeline_factory=FailingPipeline,
        max_attempts=3,
        backoff_seconds=2,
    )
    sleeps = []
    orchestrator = IngestionOrchestrator(
        session_factory=lambda: _NoopSession(),
        sleep=sleeps.append,
    )

    result = orchestrator.run_job(job)

    assert result.status == "failed"
    assert result.attempts == 3
    assert FailingPipeline.calls == 3
    assert sleeps == [2, 4]


def test_scheduler_runs_only_due_enabled_jobs():
    now = datetime(2026, 9, 22, 18, 0, tzinfo=UTC)
    executed = []

    class StubOrchestrator:
        def run_job(self, job):
            executed.append(job.key)
            return object()

    jobs = (
        IngestionJob(
            key="a",
            lottery_code="MILOTO",
            url="https://example.test/a",
            pipeline_factory=lambda: StubPipeline(_record()),
            interval_seconds=900,
        ),
        IngestionJob(
            key="b",
            lottery_code="BALOTO",
            url="https://example.test/b",
            pipeline_factory=lambda: StubPipeline(_record("BALOTO")),
            interval_seconds=900,
            enabled=False,
        ),
    )
    scheduler = IngestionScheduler(
        orchestrator=StubOrchestrator(),
        jobs=jobs,
    )
    scheduler.initialize(now)

    results = scheduler.run_due(now)
    assert len(results) == 1
    assert executed == ["a"]
    assert scheduler.next_run_at("a") == now + timedelta(seconds=900)
    assert scheduler.run_due(now) == []


class _NoopSession:
    def rollback(self):
        pass

    def close(self):
        pass
