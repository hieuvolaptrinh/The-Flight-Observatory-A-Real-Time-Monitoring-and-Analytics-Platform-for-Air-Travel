import asyncio
from contextlib import asynccontextmanager, suppress
import logging

from fastapi import FastAPI, HTTPException

from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.jobs import JobAlreadyRunning, JobRunner
from app.pipeline import Pipeline
from app.repository import PredictionRepository
from app.schemas import Job, Results

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app(settings: Settings | None = None, pipeline: Pipeline | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        active_pipeline = pipeline if pipeline is not None else Pipeline(settings=settings)
        database_url = settings.database_url
        repository = PredictionRepository(database_url) if database_url.startswith(("postgresql://", "postgres://")) else None
        if repository is not None:
            await asyncio.to_thread(repository.migrate)
        runner = JobRunner(settings.service_name, active_pipeline, repository)
        app.state.runner = runner

        task = asyncio.create_task(runner.schedule(settings.job_interval_seconds, settings.run_on_startup,
                                                   repeat=settings.scheduler_enabled))
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(
        title="Flight Delay Prediction & Classification Service",
        description="Machine Learning regression (delay minutes) and classification (risk probability) with real weather features.",
        version="1.0.0",
        root_path=settings.root_path,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["operations"])
    async def health():
        return {
            "status": "ok", "service": settings.service_name,
            "scheduler_enabled": settings.scheduler_enabled,
            "job_interval_seconds": settings.job_interval_seconds,
            "storage": app.state.runner.storage,
        }

    @app.get("/results", response_model=Results, tags=["results"])
    @app.get("/predictions", response_model=Results, tags=["results"])
    async def results():
        return await app.state.runner.get_results()

    @app.get("/jobs/latest", response_model=Job | None, tags=["operations"])
    async def latest_job():
        return app.state.runner.latest

    @app.post("/run", response_model=Job, tags=["operations"])
    async def run():
        try:
            return await app.state.runner.run_once()
        except JobAlreadyRunning as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except NotImplementedError as exc:
            raise HTTPException(
                status_code=501,
                detail=app.state.runner.latest.model_dump(mode="json"),
            ) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Pipeline failed; see service logs.") from exc

    return app


app = create_app()
