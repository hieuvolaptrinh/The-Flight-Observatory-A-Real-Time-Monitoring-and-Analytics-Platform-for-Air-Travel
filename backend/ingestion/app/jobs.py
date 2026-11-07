import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.pipeline import Pipeline
from app.schemas import Job, PipelineOutput, Results

logger = logging.getLogger(__name__)


class JobAlreadyRunning(Exception):
    pass


class JobRunner:
    """One runner per process; run exactly one Uvicorn worker per service."""

    def __init__(self, service: str, pipeline: Pipeline):
        self.service = service
        self.pipeline = pipeline
        self.latest: Job | None = None
        self._lock = asyncio.Lock()

    def get_results(
        self,
        origin: str | None = None,
        dest: str | None = None,
        carrier: str | None = None,
        status: str | None = None,
        search: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> Results:
        queried = self.pipeline.repository.query_flights(
            origin=origin,
            dest=dest,
            carrier=carrier,
            status=status,
            search=search,
            limit=limit,
            offset=offset,
        )
        return Results(
            service=self.service,
            storage=self.pipeline.repository.storage_type,
            ready=queried["ready"],
            updated_at=queried["updated_at"],
            output=PipelineOutput(
                items=queried["items"],
                metadata=queried["metadata"],
            ),
        )

    @property
    def results(self) -> Results:
        return self.get_results()

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
                await self.pipeline.run()
                job.status = "completed"
            except NotImplementedError as exc:
                job.status = "not_implemented"
                job.error = str(exc)
                raise
            except Exception as exc:
                job.status = "failed"
                job.error = str(exc)
                logger.exception("Job failed: service=%s id=%s", self.service, job.id)
                raise
            finally:
                job.finished_at = datetime.now(timezone.utc)
                logger.info("Job finished: service=%s id=%s status=%s", self.service, job.id, job.status)
            return job

    async def schedule(self, interval_seconds: float) -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await self.run_once(trigger="schedule")
            except JobAlreadyRunning:
                logger.info("Scheduled run skipped: service=%s is busy", self.service)
            except NotImplementedError:
                logger.warning("Pipeline is not implemented: service=%s", self.service)
            except Exception:
                continue
