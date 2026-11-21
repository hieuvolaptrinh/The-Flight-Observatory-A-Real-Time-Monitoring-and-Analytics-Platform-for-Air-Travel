import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.pipeline import Pipeline
from app.repository import PredictionRepository
from app.schemas import Job, PipelineOutput, Results

logger = logging.getLogger(__name__)


class JobAlreadyRunning(Exception):
    pass


class JobRunner:
    """One runner per process; run exactly one Uvicorn worker per service."""

    def __init__(self, service: str, pipeline: Pipeline, repository: PredictionRepository | None = None):
        self.service = service
        self.pipeline = pipeline
        self.repository = repository
        self.storage = "postgresql" if repository is not None else "memory"
        self.latest: Job | None = None
        self.results = Results(service=service, storage=self.storage,
                               output=PipelineOutput(metadata={"reason": "results_missing"}))
        self._lock = asyncio.Lock()

    async def get_results(self) -> Results:
        if self.repository is None:
            return self.results
        result = await asyncio.to_thread(self.repository.latest, self.service)
        if result is not None:
            return result
        return Results(service=self.service, storage=self.storage, output=self.results.output)

    async def run_once(self, trigger: str = "manual") -> Job:
        if self._lock.locked():
            raise JobAlreadyRunning("A job is already running.")
        async with self._lock:
            job = Job(
                id=str(uuid4()), service=self.service, trigger=trigger,
                status="running", started_at=datetime.now(timezone.utc),
            )
            self.latest = job
            logger.info("Job started: service=%s id=%s trigger=%s", self.service, job.id, trigger)
            try:
                output = await self.pipeline.run()
                finished_at = datetime.now(timezone.utc)
                ready = bool(output.metadata.get("ready", True))
                if self.repository is not None and ready:
                    await asyncio.to_thread(self.repository.save, job.id, finished_at, output)
                    output = PipelineOutput(metadata={"reason": "results_missing"})
                self.results = Results(service=self.service, storage=self.storage,
                                       ready=ready and self.repository is None,
                                       updated_at=finished_at, output=output)
                job.status = "completed"
            except NotImplementedError as exc:
                job.status = "not_implemented"
                job.error = str(exc)
                raise
            except Exception:
                job.status = "failed"
                job.error = "Pipeline failed; see service logs."
                logger.exception("Job failed: service=%s id=%s", self.service, job.id)
                raise
            finally:
                job.finished_at = datetime.now(timezone.utc)
                logger.info("Job finished: service=%s id=%s status=%s", self.service, job.id, job.status)
            return job

    async def schedule(self, interval_seconds: float, run_on_startup: bool = False, *, repeat: bool = True) -> None:
        if run_on_startup:
            try:
                await self.run_once(trigger="startup")
            except Exception as exc:
                logger.warning("Startup prediction run failed: %s", exc)

        while repeat:
            await asyncio.sleep(interval_seconds)
            try:
                await self.run_once(trigger="schedule")
            except JobAlreadyRunning:
                logger.info("Scheduled run skipped: service=%s is busy", self.service)
            except NotImplementedError:
                logger.warning("Pipeline is not implemented: service=%s", self.service)
            except Exception:
                # run_once logs the failure; keep the scheduler alive for the next run.
                continue
