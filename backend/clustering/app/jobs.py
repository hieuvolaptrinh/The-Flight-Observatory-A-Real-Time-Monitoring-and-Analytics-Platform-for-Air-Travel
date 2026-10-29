import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.pipeline import Pipeline
from app.schemas import Job, Results

logger = logging.getLogger(__name__)


class JobAlreadyRunning(Exception):
    pass


class JobRunner:
    """One runner per process; run exactly one Uvicorn worker per service."""

    def __init__(self, service: str, pipeline: Pipeline):
        self.service = service
        self.pipeline = pipeline
        self.latest: Job | None = None
        self.results = Results(service=service)
        self._lock = asyncio.Lock()

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
                # Publish only a complete result; preserve the last good result on failure.
                self.results = Results(
                    service=self.service, ready=True,
                    updated_at=finished_at, output=output,
                )
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

    async def schedule(self, interval_seconds: float) -> None:
        # First run happens after one interval; each next interval follows completion.
        while True:
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
