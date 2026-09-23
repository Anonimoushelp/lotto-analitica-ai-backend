from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock

from app.sources.orchestrator import IngestionJob, IngestionOrchestrator, IngestionRunResult


@dataclass(frozen=True)
class ScheduledJobState:
    job: IngestionJob
    next_run_at: datetime


class IngestionScheduler:
    """Deterministic scheduler; deployment-specific timers can trigger run_due()."""

    def __init__(
        self,
        *,
        orchestrator: IngestionOrchestrator,
        jobs: tuple[IngestionJob, ...],
    ) -> None:
        keys = [job.key for job in jobs]
        if len(keys) != len(set(keys)):
            raise ValueError("ingestion job keys must be unique")
        self.orchestrator = orchestrator
        self._jobs = {job.key: job for job in jobs}
        self._next_run: dict[str, datetime] = {}
        self._lock = Lock()

    @property
    def jobs(self) -> tuple[IngestionJob, ...]:
        return tuple(self._jobs.values())

    def initialize(self, now: datetime) -> None:
        with self._lock:
            for job in self._jobs.values():
                self._next_run.setdefault(job.key, now)

    def due_jobs(self, now: datetime) -> tuple[IngestionJob, ...]:
        with self._lock:
            return tuple(
                job
                for job in self._jobs.values()
                if job.enabled and self._next_run.get(job.key, now) <= now
            )

    def run_due(self, now: datetime) -> list[IngestionRunResult]:
        results: list[IngestionRunResult] = []
        for job in self.due_jobs(now):
            result = self.orchestrator.run_job(job)
            results.append(result)
            with self._lock:
                self._next_run[job.key] = now + timedelta(seconds=job.interval_seconds)
        return results

    def next_run_at(self, job_key: str) -> datetime | None:
        with self._lock:
            return self._next_run.get(job_key)
