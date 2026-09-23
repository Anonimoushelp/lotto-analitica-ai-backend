from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ingestion_schedule_state import IngestionScheduleState
from app.sources.orchestrator import (
    IngestionJob,
    IngestionOrchestrator,
    IngestionRunResult,
)


class IngestionScheduler:
    """Deterministic in-memory scheduler used by unit tests and local callers."""

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

    @property
    def jobs(self) -> tuple[IngestionJob, ...]:
        return tuple(self._jobs.values())

    def initialize(self, now: datetime) -> None:
        for job in self._jobs.values():
            self._next_run.setdefault(job.key, now)

    def due_jobs(self, now: datetime) -> tuple[IngestionJob, ...]:
        return tuple(
            job
            for job in self._jobs.values()
            if job.enabled and self._next_run.get(job.key, now) <= now
        )

    def run_due(self, now: datetime) -> list[IngestionRunResult]:
        results: list[IngestionRunResult] = []
        for job in self.due_jobs(now):
            results.append(self.orchestrator.run_job(job))
            self._next_run[job.key] = now + timedelta(seconds=job.interval_seconds)
        return results

    def next_run_at(self, job_key: str) -> datetime | None:
        return self._next_run.get(job_key)


class PersistentIngestionScheduler:
    """Database-backed scheduler safe across ephemeral Railway cron executions."""

    def __init__(
        self,
        *,
        orchestrator: IngestionOrchestrator,
        jobs: tuple[IngestionJob, ...],
        session_factory: callable,
    ) -> None:
        keys = [job.key for job in jobs]
        if len(keys) != len(set(keys)):
            raise ValueError("ingestion job keys must be unique")
        self.orchestrator = orchestrator
        self._jobs = {job.key: job for job in jobs}
        self.session_factory = session_factory

    @property
    def jobs(self) -> tuple[IngestionJob, ...]:
        return tuple(self._jobs.values())

    def run_due(self, now: datetime) -> list[IngestionRunResult]:
        results: list[IngestionRunResult] = []
        for job in self._jobs.values():
            if not job.enabled:
                continue
            if not self._claim(job, now):
                continue
            result = self.orchestrator.run_job(job)
            self._record_result(job, result)
            results.append(result)
        return results

    def _claim(self, job: IngestionJob, now: datetime) -> bool:
        db: Session = self.session_factory()
        try:
            state = db.execute(
                select(IngestionScheduleState)
                .where(IngestionScheduleState.job_key == job.key)
                .with_for_update()
            ).scalar_one_or_none()
            if state is None:
                state = IngestionScheduleState(
                    job_key=job.key,
                    next_run_at=now,
                    updated_at=now,
                )
                db.add(state)
                db.flush()
            if state.next_run_at > now:
                db.rollback()
                return False
            state.next_run_at = now + timedelta(seconds=job.interval_seconds)
            state.updated_at = now
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _record_result(
        self,
        job: IngestionJob,
        result: IngestionRunResult,
    ) -> None:
        db: Session = self.session_factory()
        try:
            state = db.get(IngestionScheduleState, job.key)
            if state is None:
                return
            state.last_run_at = result.finished_at
            state.last_run_id = result.run_id
            state.last_status = result.status
            state.last_attempts = result.attempts
            state.last_error = result.error
            state.updated_at = result.finished_at
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
