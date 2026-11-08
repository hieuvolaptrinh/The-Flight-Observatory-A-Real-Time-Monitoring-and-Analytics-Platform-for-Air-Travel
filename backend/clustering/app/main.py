import asyncio
from contextlib import asynccontextmanager, suppress
import logging
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.jobs import JobAlreadyRunning, JobRunner
from app.pipeline import Pipeline
from app.schemas import Job, Results
from app.train import train_and_save_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app(settings: Settings | None = None, pipeline: Pipeline | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        active_pipeline = pipeline if pipeline is not None else Pipeline(settings=settings)
        runner = JobRunner(settings.service_name, active_pipeline)
        app.state.runner = runner
        task = (
            asyncio.create_task(
                runner.schedule(settings.job_interval_seconds, run_on_startup=settings.run_on_startup)
            )
            if settings.scheduler_enabled else None
        )
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(
        title="Flight Clustering Service",
        description="Clusters US airports and flight routes with KMeans + PCA, persists centroids & cluster labels to DB.",
        version="1.1.0",
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
        runner: JobRunner = app.state.runner
        return {
            "status": "ok",
            "service": settings.service_name,
            "scheduler_enabled": settings.scheduler_enabled,
            "job_interval_seconds": settings.job_interval_seconds,
            "storage": runner.pipeline.repository.storage_type,
            "model_path": settings.model_path,
        }

    @app.get("/results", response_model=Results, tags=["results"])
    @app.get("/clusters", response_model=Results, tags=["results"])
    async def results(
        entity_type: Literal["airport", "route"] = Query(
            default="airport",
            description="Select clustered entities: 'airport' (default) or 'route'",
        ),
        cluster_id: int | None = Query(
            default=None,
            ge=0,
            le=9,
            description="Optional filter by semantic cluster_id (0..3)",
        ),
    ):
        runner: JobRunner = app.state.runner
        return await asyncio.to_thread(runner.get_results, entity_type=entity_type, cluster_id=cluster_id)

    @app.delete("/clusters", tags=["operations"])
    async def clear_clusters():
        """Delete clustering results from DB (Demo step: clear DB -> Web shows missing -> POST /run recovers without training)."""
        runner: JobRunner = app.state.runner
        deleted = await asyncio.to_thread(runner.pipeline.repository.clear_all)
        return {"status": "cleared", "deleted_records": deleted}

    @app.post("/train", tags=["operations"])
    async def train_model():
        """Explicitly re-train and save the KMeans + PCA model bundle to disk."""
        bundle = await asyncio.to_thread(train_and_save_model, settings)
        return {
            "status": "trained",
            "model_version": bundle["model_version"],
            "n_clusters": bundle["n_clusters"],
            "silhouette_score": bundle["silhouette_score"],
            "training_airports_count": bundle["training_airports_count"],
            "trained_at": bundle["trained_at"],
        }

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
            raise HTTPException(status_code=500, detail=f"Pipeline failed: {exc}") from exc

    return app


app = create_app()
