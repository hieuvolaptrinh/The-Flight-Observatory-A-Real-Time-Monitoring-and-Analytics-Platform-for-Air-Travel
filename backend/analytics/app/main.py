import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import date
import logging
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import Settings
from app.forecast import forecast, schedule_forecasts
from app.jobs import JobAlreadyRunning, JobRunner
from app.pipeline import Pipeline, summary
from app.schemas import Job, PipelineOutput, Results

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


class DateWindow(BaseModel):
    date_from: date | None = None
    date_to: date | None = None

    def bounds(self):
        start, end = self.date_from, self.date_to
        if (start is None) != (end is None) or (start and end and not 1 <= (end - start).days <= 1096):
            raise HTTPException(422, "Provide both dates with an exclusive end, spanning 1 to 1096 days")
        return start, end


class Page(DateWindow):
    limit: int = Field(5, ge=1, le=500)
    offset: int = Field(0, ge=0)

    def response(self, rows, **metadata):
        return {"items": rows[:self.limit], "limit": self.limit, "offset": self.offset,
                "has_more": len(rows) > self.limit, **metadata}

    def slice(self, rows):
        return rows[self.offset:self.offset + self.limit + 1]


class Chart(Page):
    grain: Literal["day", "week", "month"] = "day"
    period_start: date | None = None


class Component(Page):
    grain: Literal["auto", "week", "month"] = "auto"


def create_app(settings: Settings | None = None, pipeline: Pipeline | None = None) -> FastAPI:
    settings = settings or Settings()
    active = pipeline if pipeline is not None else Pipeline(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runner = JobRunner(settings.service_name, active)
        app.state.runner = runner
        tasks = []
        if settings.scheduler_enabled:
            tasks.append(asyncio.create_task(runner.schedule(settings.job_interval_seconds)))
            if settings.gemini_api_key:
                tasks.append(asyncio.create_task(schedule_forecasts(active)))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(
        title=settings.service_name,
        description="PostgreSQL-backed flight charts and Gemini forecasts for the stored flight timeline.",
        version="0.1.0",
        root_path=settings.root_path,
        lifespan=lifespan,
    )

    @app.get("/health", tags=["operations"])
    async def health():
        return {
            "status": "ok", "service": settings.service_name,
            "scheduler_enabled": settings.scheduler_enabled,
            "job_interval_seconds": settings.job_interval_seconds,
            "storage": "postgresql",
        }

    @app.get("/coverage", tags=["results"])
    async def coverage():
        async with await active.connect() as db:
            return await (await db.execute("""
                SELECT min(flight_date) AS first_date, max(flight_date) AS last_date
                FROM flight_data.flights
            """)).fetchone()

    @app.get("/dataset", tags=["results"])
    async def dataset():
        async with await active.connect() as db:
            rows = await db.execute("""
                SELECT source, count(*) AS flights, min(flight_date) AS first_date,
                       max(flight_date) AS last_date,
                       count(*) FILTER (
                           WHERE delay_minutes IS NOT NULL AND scheduled_at IS NOT NULL
                             AND distance > 0 AND crs_elapsed_time > 0
                       ) AS training_samples
                FROM flight_data.model_flights
                GROUP BY source ORDER BY source
            """)
            return {"sources": await rows.fetchall()}

    @app.get("/results", response_model=Results, tags=["results"])
    @app.get("/summary", response_model=Results, tags=["results"])
    async def results(window: Annotated[DateWindow, Query()]):
        snapshot = await active.snapshot(*window.bounds())
        metadata = summary(snapshot)
        return Results(service=settings.service_name, ready=metadata["ready"], updated_at=metadata.get("updated_at"),
                       output=PipelineOutput(metadata=metadata))

    async def snapshot_chart(key, query):
        snapshot = await active.snapshot(*query.bounds())
        period = query.period_start.isoformat() if query.period_start else None
        rows = [row for row in snapshot["payload"][key] if row["grain"] == query.grain
                and (period is None or row["period_start"] == period)] if snapshot else []
        return query.response(query.slice(rows),
                              grain=query.grain, summary=summary(snapshot))

    @app.get("/line", tags=["charts"])
    async def line(query: Annotated[Chart, Query()]):
        return await snapshot_chart("series", query)

    @app.get("/histogram", tags=["charts"])
    async def histogram(query: Annotated[Chart, Query()]):
        return await snapshot_chart("histogram", query)

    @app.get("/scatter", tags=["charts"])
    async def scatter(query: Annotated[Chart, Query()]):
        snapshot = await active.snapshot(*query.bounds())
        metadata = summary(snapshot)
        period = query.period_start.isoformat() if query.period_start else None
        key = "date" if query.grain == "day" else query.grain
        rows = [{**row, "period_start": row[key]} for row in snapshot["payload"]["scatter"]
                if period is None or row[key] == period] if snapshot else []
        return query.response(query.slice(rows), grain=query.grain, summary=metadata)

    async def component(query, field):
        snapshot = await active.snapshot(*query.bounds())
        saved = snapshot["payload"][field] if snapshot else {}
        grain = saved.get("auto_grain", "week") if query.grain == "auto" else query.grain
        component = saved.get(grain, {"items": [], "ready": False, "seasonal_period": None})
        response = query.response(query.slice(component["items"]), grain=grain, ready=component["ready"],
                                  seasonal_period=component["seasonal_period"], summary=summary(snapshot))
        if field == "seasonality":
            series = snapshot["payload"]["series"] if snapshot else []
            response["observed_periods"] = sum(row["grain"] == grain and row["flight_count"] > 0 for row in series)
            response["minimum_periods"] = 24 if grain == "month" else 8
            if not component["ready"]:
                response["hourly_profile"] = saved.get("hourly_profile", [])
        return response

    @app.get("/trend", tags=["charts"])
    async def trend(query: Annotated[Component, Query()]):
        return await component(query, "trend")

    @app.get("/seasonality", tags=["charts"])
    async def seasonality(query: Annotated[Component, Query()]):
        return await component(query, "seasonality")

    @app.get("/correlation", tags=["charts"])
    async def correlation(window: Annotated[DateWindow, Query()]):
        snapshot = await active.snapshot(*window.bounds())
        if not summary(snapshot)["ready"]:
            return {"ready": False, "variables": [], "matrix": [], "samples": []}
        return {"ready": True, **snapshot["payload"]["correlation"], "summary": summary(snapshot)}

    @app.get("/forecast", tags=["forecast"])
    async def saved_forecast():
        return await forecast(active)

    @app.post("/forecast", tags=["forecast"])
    async def generate_forecast():
        return await forecast(active, generate=True)

    @app.get("/classification", tags=["forecast"])
    async def classification():
        result = await forecast(active)
        if result["ready"]:
            payload = result.pop("payload")
            result.update(classification=payload["classification"], threshold=payload["classification_threshold"],
                          observed_days=payload["observed_days"], provisional=payload["provisional"])
        return result

    @app.get("/jobs/latest", response_model=Job | None, tags=["operations"])
    async def latest_job():
        return app.state.runner.latest

    @app.post("/run", response_model=Job, tags=["operations"])
    async def run(window: DateWindow | None = None):
        bounds = window.bounds() if window else (None, None)
        try:
            return await app.state.runner.run_once(date_from=bounds[0], date_to=bounds[1])
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
