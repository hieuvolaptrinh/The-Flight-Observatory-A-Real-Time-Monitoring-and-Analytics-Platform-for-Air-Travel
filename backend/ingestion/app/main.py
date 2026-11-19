import asyncio
from contextlib import asynccontextmanager, suppress
import logging
from typing import Literal

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.jobs import JobRunner
from app.pipeline import Pipeline
from app.schemas import Job, Results

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
        title="Flight Ingestion Service",
        description="Archives API responses in the raw database before normalizing flights and weather into the processed database.",
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
        deadline = runner.next_scheduled_run
        return {
            "status": "ok",
            "service": settings.service_name,
            "scheduler_enabled": settings.scheduler_enabled,
            "job_interval_seconds": settings.job_interval_seconds,
            "next_run_in_seconds": (
                max(0, deadline - asyncio.get_running_loop().time()) if deadline is not None else None
            ),
            "job_running": runner.latest is not None and runner.latest.status == "running",
            "source": "airlabs",
            "provider_status": runner.pipeline.providers.last_status,
            "storage": runner.pipeline.repository.storage_type,
            "raw_database": runner.pipeline.raw_store.database_name,
        }

    @app.get("/providers", tags=["operations"])
    async def providers():
        store = app.state.runner.pipeline.providers.store
        status, _ = await asyncio.to_thread(store.cached, "ingestion_status")
        return {"status": status, "usage": await asyncio.to_thread(store.usage)}

    @app.get("/raw", tags=["results"])
    async def raw_flights(cursor: int = Query(0, ge=0), window_size: int = Query(12, ge=1, le=100)):
        return await asyncio.to_thread(app.state.runner.pipeline.raw_store.flights, cursor, window_size)

    @app.get("/results", response_model=Results, tags=["results"])
    @app.get("/flights", response_model=Results, tags=["results"])
    async def results(
        origin: str | None = Query(default=None, description="Filter by origin airport IATA code"),
        dest: str | None = Query(default=None, description="Filter by destination airport IATA code"),
        carrier: str | None = Query(default=None, description="Filter by carrier code (e.g. AA, DL, UA, WN)"),
        status: str | None = Query(default=None, description="Filter by delay_status: on_time, moderate_delay, severe_delay"),
        search: str | None = Query(default=None, description="Search by flight code, airport, carrier, or tail number"),
        sort: str | None = Query(default="time", description="Sort by: time, delay, distance"),
        limit: int = Query(default=5, ge=1, le=1000, description="Max records to return"),
        offset: int = Query(default=0, ge=0, description="Pagination offset"),
        source: Literal["all", "airlabs", "legacy"] = "all",
        cluster_id: int | None = Query(default=None, ge=0),
        overview: bool = False,
    ):
        runner: JobRunner = app.state.runner
        return await asyncio.to_thread(
            runner.get_results,
            origin=origin,
            dest=dest,
            carrier=carrier,
            status=status,
            search=search,
            sort=sort,
            limit=limit,
            offset=offset,
            source=source,
            cluster_id=cluster_id,
            include_overview=overview,
        )

    @app.delete("/flights", tags=["operations"])
    async def clear_flights():
        """Clear all ingested flights from DB (useful for testing/demo reset)."""
        runner: JobRunner = app.state.runner
        deleted = await asyncio.to_thread(runner.pipeline.repository.clear_all)
        return {"status": "cleared", "deleted_records": deleted}

    @app.get("/jobs/latest", response_model=Job | None, tags=["operations"])
    async def latest_job():
        return app.state.runner.latest

    return app


app = create_app()
