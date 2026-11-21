import asyncio
from datetime import date

import httpx

from app.config import Settings
from app.db import FlightRepository
from app.historical import backfill
from app.pipeline import Pipeline


def test_historical_archives_and_imports_only_matching_new_flights(tmp_path):
    repo = FlightRepository(f"sqlite:///{(tmp_path / 'flights.db').as_posix()}")
    settings = Settings(database_url=repo.database_url, airlabs_api_key="fixture-key", airlabs_airports="JFK")
    pipeline = Pipeline(settings, repo)
    for airport in ("JFK", "LAX", "LGA"):
        pipeline.providers.store.cache(f"airport:{airport}", {"timezone": "UTC", "lat": 30, "lng": 70})
    row = {
        "dep_iata": "JFK", "arr_iata": "LAX", "dep_time": "2025-11-22 01:00",
        "arr_time": "2025-11-22 05:00", "dep_actual": "2025-11-22 01:20", "status": "landed",
    }
    offsets = []

    def respond(request):
        offset = int(request.url.params["offset"])
        offsets.append(offset)
        if offset == 0:
            return httpx.Response(200, json={"request": {"has_more": True},
                "response": [row, {**row, "dep_iata": "LGA"}]})
        return httpx.Response(200, json=[row])

    pipeline.providers.transport = httpx.MockTransport(respond)
    summary = asyncio.run(backfill(pipeline, "JFK", ["AA171"], date(2025, 11, 1), date(2025, 12, 1), 2))
    assert offsets == [0, 2]
    assert summary["imported"] == 1
    assert summary["observed_days"] == 1
    with pipeline.raw_store.connect() as conn:
        rows = conn.execute("SELECT processing_status, raw_json FROM raw_flights").fetchall()
        assert sorted(row["processing_status"] for row in rows) == ["duplicate", "processed", "rejected"]
        assert all("fixture-key" not in row["raw_json"] for row in rows)
    with repo._connect_sqlite() as conn:
        processed = conn.execute("SELECT delay_minutes FROM ingested_flights").fetchone()
        assert processed["delay_minutes"] == 20
