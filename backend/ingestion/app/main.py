import asyncio
from contextlib import asynccontextmanager, suppress
import json
import logging
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.jobs import JobRunner
from app.pipeline import Pipeline
from app.schemas import Job, Results
from app.live_store import LiveStore

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

    @app.get("/raw/batches", tags=["results"])
    async def raw_flight_batches(limit: int = Query(20, ge=1, le=50)):
        rows = await asyncio.to_thread(app.state.runner.pipeline.raw_store.flight_batches, limit)
        return {"items": rows}

    @app.get("/poll/latest", tags=["results"])
    async def latest_schedule_poll():
        active = app.state.runner.pipeline

        def read():
            store = LiveStore(active.repository)
            with store.connect() as conn:
                if active.repository.is_postgres:
                    conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                batch = conn.execute("""
                    SELECT batch_id, fetched_at, created_at, inserted_count, updated_count FROM ingestion_batches
                    WHERE source='airlabs' ORDER BY created_at DESC, batch_id DESC LIMIT 1
                """).fetchone()
                if batch is None:
                    return {"batch": None, "raw": [], "processed": []}
                rows = conn.execute(store.sql("""
                    SELECT flight_key, flight_code, origin, dest, fl_date, crs_dep_time,
                           crs_arr_time, distance, delay_minutes, delay_status
                    FROM ingested_flights WHERE fetched_at=? AND raw_response_id IS NOT NULL
                    ORDER BY origin, crs_dep_time, flight_key
                """), (batch["fetched_at"],)).fetchall()
            return {"batch": dict(batch),
                    "raw": active.raw_store.schedule_poll_rows(batch["fetched_at"], batch["created_at"]),
                    "processed": [dict(row) for row in rows]}

        return await asyncio.to_thread(read)

    @app.get("/raw/batches/{response_id}", tags=["results"])
    async def raw_flight_batch(response_id: str, offset: int = Query(0, ge=0),
                               limit: int = Query(5, ge=1, le=100)):
        active = app.state.runner.pipeline

        def read():
            result = active.raw_store.flight_batch_rows(response_id, offset, limit)
            keys = sorted({item["processed_flight_key"] for item in result["items"] if item["processed_flight_key"]})
            present = set()
            if keys:
                store = LiveStore(active.repository)
                placeholders = ", ".join("?" for _ in keys)
                with store.connect() as conn:
                    rows = conn.execute(store.sql(
                        f"SELECT flight_key FROM ingested_flights WHERE flight_key IN ({placeholders})"
                    ), keys).fetchall()
                present = {row["flight_key"] for row in rows}
            for item in result["items"]:
                item["has_processed"] = item["processed_flight_key"] in present
            return result

        return await asyncio.to_thread(read)

    @app.get("/raw/{raw_id}/comparison", tags=["results"])
    async def compare_flight(raw_id: int):
        active = app.state.runner.pipeline
        def read():
            raw = active.raw_store.flight(raw_id)
            if raw is None:
                raise HTTPException(404, "Raw flight not found")
            store = LiveStore(active.repository)
            with store.connect() as conn:
                found = conn.execute(store.sql("""
                    SELECT f.*, d.payload AS comparison_payload
                    FROM ingested_flights f LEFT JOIN live_flight_details d USING (flight_key)
                    WHERE f.flight_key=?
                """),
                    (raw["processed_flight_key"],)).fetchone()
            processed = dict(found) if found else None
            payload = processed.pop("comparison_payload") if processed is not None else None
            details = json.loads(payload) if payload else {}
            actual_delay = details.get("dep_delay_min") if details.get("flight_status") == "landed" else None
            original = raw["raw"] if isinstance(raw["raw"], dict) else {}
            fields = (("Hãng bay", "airline_iata", "op_unique_carrier"),
                ("Số hiệu", "flight_number", "op_carrier_fl_num"),
                ("Giờ khởi hành", "dep_time", "crs_dep_time"),
                ("Giờ đến", "arr_time", "crs_arr_time"),
                ("Khoảng cách (dặm)", "distance", "distance"),
                ("Thời lượng (phút)", "duration", "crs_elapsed_time"))
            return {"raw": raw, "processed": processed,
                "matches_current_source": bool(processed and processed.get("raw_response_id") == raw["response_id"]
                    and processed.get("raw_row_index") == raw["row_index"]),
                "fields": [{"label": label, "raw": original.get(source),
                    "processed": processed.get(target) if processed else None} for label, source, target in fields]
                + [{"label": "Chậm khởi hành thực tế (phút)", "raw": None, "processed": actual_delay}],
                "departure_delay_minutes": actual_delay}
        return await asyncio.to_thread(read)

    @app.get("/weather", tags=["results"])
    async def weather(limit: int = Query(12, ge=1, le=100)):
        active = app.state.runner.pipeline
        def read():
            store = LiveStore(active.repository)
            with store.connect() as conn:
                rows = conn.execute(store.sql("""SELECT * FROM airport_weather
                    ORDER BY observed_at DESC,airport_code LIMIT ?"""), (limit,)).fetchall()
            items = []
            for row in rows:
                processed = dict(row)
                processed.pop("raw_json", None)
                raw = active.raw_store.weather(processed.get("raw_response_id"))
                items.append({"raw": raw, "processed": processed})
            return {"items": items}
        return await asyncio.to_thread(read)

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
        source: Literal["all", "airlabs", "legacy", "combined"] = "all",
        cluster_id: int | None = Query(default=None, ge=0),
        overview: bool = False,
        hourly_days: int = Query(1, ge=1, le=30, description="Days ending on the latest matching flight date for hourly overview"),
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
            hourly_days=hourly_days,
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
