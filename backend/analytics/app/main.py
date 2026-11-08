import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import date
import logging
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import Settings
from app.forecast import forecast
from app.jobs import JobAlreadyRunning, JobRunner
from app.pipeline import Pipeline, decompose, summary
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


class Component(Page):
    grain: Literal["auto", "week", "month"] = "auto"


def create_app(settings: Settings | None = None, pipeline: Pipeline | None = None) -> FastAPI:
    settings = settings or Settings()
    active = pipeline if pipeline is not None else Pipeline(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runner = JobRunner(settings.service_name, active)
        app.state.runner = runner
        task = (
            asyncio.create_task(runner.schedule(settings.job_interval_seconds))
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
        title=settings.service_name,
        description="PostgreSQL-backed flight charts and Gemini forecasts for the simulator timeline.",
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

    @app.get("/results", response_model=Results, tags=["results"])
    @app.get("/summary", response_model=Results, tags=["results"])
    async def results(window: Annotated[DateWindow, Query()]):
        snapshot = await active.snapshot(*window.bounds())
        metadata = summary(snapshot)
        return Results(service=settings.service_name, ready=metadata["ready"], updated_at=metadata.get("updated_at"),
                       output=PipelineOutput(metadata=metadata))

    async def snapshot_chart(key, query):
        snapshot = await active.snapshot(*query.bounds())
        rows = snapshot["payload"][key] if snapshot else []
        return query.response(query.slice([row for row in rows if row["grain"] == query.grain]),
                              grain=query.grain, summary=summary(snapshot))

    @app.get("/line", tags=["charts"])
    async def line(query: Annotated[Chart, Query()]):
        return await snapshot_chart("series", query)

    @app.get("/histogram", tags=["charts"])
    async def histogram(query: Annotated[Chart, Query()]):
        return await snapshot_chart("histogram", query)

    @app.get("/scatter", tags=["charts"])
    async def scatter(query: Annotated[Chart, Query()]):
        rows = await active.scatter(*query.bounds(), query.grain, query.limit + 1, query.offset)
        return query.response(rows, grain=query.grain)

    async def component(query, field):
        snapshot = await active.snapshot(*query.bounds())
        series = snapshot["payload"]["series"] if snapshot else []
        grain = query.grain
        if grain == "auto":
            months = sum(row["grain"] == "month" and row["flight_count"] > 0 for row in series)
            grain = "month" if months >= (24 if field == "seasonal" else 6) else "week"
        rows, period = decompose(series, grain)
        usable = [{"period_start": row["period_start"], "flight_count": row["flight_count"], field: row[field]}
                  for row in rows if row[field] is not None]
        return query.response(query.slice(usable), grain=grain, ready=bool(usable),
                              seasonal_period=period if field == "seasonal" else None)

    @app.get("/trend", tags=["charts"])
    async def trend(query: Annotated[Component, Query()]):
        return await component(query, "trend")

    @app.get("/seasonality", tags=["charts"])
    async def seasonality(query: Annotated[Component, Query()]):
        return await component(query, "seasonal")

    @app.get("/correlation", tags=["charts"])
    async def correlation(window: Annotated[DateWindow, Query()]):
        return await active.correlations(*window.bounds())

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
            result.update(classification=payload["classification"], threshold=payload["classification_threshold"])
        return result

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
