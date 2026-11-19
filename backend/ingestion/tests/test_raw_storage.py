import asyncio
import json
import os
import sqlite3

import httpx
import pytest

from app.config import Settings
from app.db import FlightRepository
from app.pipeline import Pipeline
from app.raw_store import RawStore

from test_live_ingestion import AIRPORTS, SCHEDULE, WEATHER


def make_pipeline(tmp_path, schedules, processed_url=None, raw_url=None):
    processed = FlightRepository(processed_url or "sqlite:///" + str(tmp_path / "processed.db"))
    settings = Settings(database_url=processed.database_url, raw_database_url=raw_url or "sqlite:///" + str(tmp_path / "raw.db"),
        airlabs_api_key="flight-secret", airlabs_accounts="", openweather_api_key="weather-secret")
    pipeline = Pipeline(settings, processed)
    def handler(request):
        if request.url.path.endswith("/schedules"):
            return httpx.Response(200, json={"response": schedules, "request": {"has_more": False}})
        if request.url.path.endswith("/airports"):
            return httpx.Response(200, json={"response": [AIRPORTS[request.url.params["iata_code"]]]})
        return httpx.Response(200, json=WEATHER)
    pipeline.providers.transport = httpx.MockTransport(handler)
    return pipeline


def test_raw_retains_invalid_and_duplicate_rows_before_cleaning(tmp_path):
    invalid = {**SCHEDULE, "dep_time": "invalid date"}
    pipeline = make_pipeline(tmp_path, [SCHEDULE, invalid, SCHEDULE, "not a flight"])
    asyncio.run(pipeline.run())
    raw = pipeline.raw_store.flights(0, 100)
    assert raw["total"] == 4
    assert sorted(row["processing_status"] for row in raw["data"]) == ["duplicate", "processed", "rejected", "rejected"]
    assert pipeline.repository.query_flights()["metadata"]["total_stored"] == 1
    assert any(row["raw"] == invalid for row in raw["data"])
    with pipeline.raw_store.connect() as conn:
        snapshot = conn.execute("SELECT payload_json FROM raw_api_responses WHERE endpoint LIKE '%/schedules'").fetchone()
        assert json.loads(snapshot["payload_json"])["response"] == [SCHEDULE, invalid, SCHEDULE, "not a flight"]


def test_repeated_polls_keep_history_and_link_latest_processed_flight(tmp_path):
    schedules = [dict(SCHEDULE)]
    pipeline = make_pipeline(tmp_path, schedules)
    asyncio.run(pipeline.run())
    schedules[0]["dep_delayed"] = 25
    asyncio.run(pipeline.run())
    raw = pipeline.raw_store.flights(0, 100)
    assert raw["total"] == 2
    assert raw["data"][1]["raw"] == SCHEDULE
    with pipeline.repository._connect_sqlite() as conn:
        processed = conn.execute("SELECT * FROM ingested_flights").fetchone()
        assert processed["raw_response_id"] == raw["data"][0]["response_id"]
        assert processed["raw_row_index"] == raw["data"][0]["row_index"]
        assert processed["delay_minutes"] == 25
    with pipeline.raw_store.connect() as conn:
        serialized = json.dumps([dict(row) for row in conn.execute("SELECT * FROM raw_api_responses")])
        assert "flight-secret" not in serialized
        assert "weather-secret" not in serialized


def test_weather_shows_original_and_converted_units_in_separate_databases(tmp_path):
    pipeline = make_pipeline(tmp_path, [SCHEDULE])
    asyncio.run(pipeline.run())
    with pipeline.raw_store.connect() as conn:
        raw = conn.execute("SELECT * FROM raw_weather").fetchone()
        assert json.loads(raw["raw_json"]) == WEATHER
        assert raw["wind_speed_ms"] == 10
        assert raw["visibility_m"] == 8000
    with pipeline.repository._connect_sqlite() as conn:
        processed = conn.execute("SELECT * FROM airport_weather").fetchone()
        assert processed["wind_speed_kmh"] == 36
        assert processed["visibility_km"] == 8
        assert processed["raw_response_id"] == raw["response_id"]


def test_raw_commit_failure_prevents_processed_write(tmp_path, monkeypatch):
    pipeline = make_pipeline(tmp_path, [SCHEDULE])
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("Raw database unavailable")
    monkeypatch.setattr(pipeline.raw_store, "archive", fail)
    with pytest.raises(sqlite3.OperationalError):
        asyncio.run(pipeline.run())
    assert pipeline.repository.query_flights()["metadata"]["total_stored"] == 0


def test_processing_failure_leaves_raw_available(tmp_path, monkeypatch):
    pipeline = make_pipeline(tmp_path, [SCHEDULE])
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("Processed database unavailable")
    monkeypatch.setattr(pipeline.repository, "insert_batch", fail)
    with pytest.raises(sqlite3.OperationalError):
        asyncio.run(pipeline.run())
    raw = pipeline.raw_store.flights(0, 100)
    assert raw["data"][0]["raw"] == SCHEDULE
    assert raw["data"][0]["processing_status"] == "pending"


def test_raw_and_processed_cannot_share_a_database(tmp_path):
    url = "sqlite:///" + str(tmp_path / "same.db")
    with pytest.raises(ValueError, match="different"):
        RawStore(url, url)


def test_error_response_is_archived_with_credentials_redacted(tmp_path):
    pipeline = make_pipeline(tmp_path, [])
    pipeline.providers.transport = httpx.MockTransport(lambda _: httpx.Response(401,
        json={"error": {"message": "flight-secret"}, "api_key": "flight-secret"}))
    asyncio.run(pipeline.run())
    with pipeline.raw_store.connect() as conn:
        row = conn.execute("SELECT * FROM raw_api_responses").fetchone()
        assert row["http_status"] == 401
        assert "flight-secret" not in row["payload_json"] + row["request_params"]


def test_raw_processed_comparison_and_weather_endpoints(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app
    schedules = [dict(SCHEDULE), {**SCHEDULE, "dep_time": "bad"}]
    pipeline = make_pipeline(tmp_path, schedules)
    asyncio.run(pipeline.run())
    rows = pipeline.raw_store.flights(0, 100)["data"]
    valid = next(row for row in rows if row["processing_status"] == "processed")
    rejected = next(row for row in rows if row["processing_status"] == "rejected")
    configured = pipeline.settings.model_copy(update={"scheduler_enabled": False})
    with TestClient(create_app(configured, pipeline)) as client:
        result = client.get(f"/raw/{valid['RAW_ID']}/comparison").json()
        assert result["raw"]["raw"] == SCHEDULE
        assert result["processed"]["crs_dep_time"] == "10:00"
        assert result["matches_current_source"] is True
        assert client.get(f"/raw/{rejected['RAW_ID']}/comparison").json()["processed"] is None
        assert client.get("/raw/999999/comparison").status_code == 404
        weather = client.get("/weather").json()["items"][0]
        assert weather["raw"]["wind_speed_ms"] == 10
        assert weather["processed"]["wind_speed_kmh"] == 36
        schedules[0]["dep_delayed"] = 20
        asyncio.run(pipeline.run())
        latest = client.get(f"/raw/{valid['RAW_ID']}/comparison").json()
        assert latest["matches_current_source"] is False
        assert latest["processed"]["delay_minutes"] == 20


@pytest.mark.skipif(not (os.getenv("TEST_DATABASE_URL") and os.getenv("TEST_RAW_DATABASE_URL")), reason="Requires two dedicated PostgreSQL test databases")
def test_postgres_archives_and_processes_api_responses(tmp_path):
    import psycopg
    from pathlib import Path
    processed_url, raw_url = os.environ["TEST_DATABASE_URL"], os.environ["TEST_RAW_DATABASE_URL"]
    for url in (processed_url, raw_url):
        with psycopg.connect(url) as conn:
            assert conn.info.dbname.startswith("test"), "Only use disposable test databases"
    with psycopg.connect(processed_url) as conn:
        conn.execute((Path(__file__).resolve().parents[1] / "db/schema.sql").read_text(encoding="utf-8"))
    pipeline = make_pipeline(tmp_path, [SCHEDULE, {**SCHEDULE, "dep_time": "bad"}], processed_url, raw_url)
    asyncio.run(pipeline.run())
    with pipeline.raw_store.connect() as conn:
        raw_weather = conn.execute("SELECT * FROM raw_weather WHERE airport_code='JFK' ORDER BY response_id LIMIT 1").fetchone()
        assert raw_weather["wind_speed_ms"] == 10
        assert conn.execute("SELECT count(*) AS n FROM raw_flights WHERE processing_status='rejected'").fetchone()["n"] >= 1
    with pipeline.repository._connect_postgres() as conn:
        processed_weather = conn.execute("SELECT * FROM airport_weather WHERE airport_code='JFK'").fetchone()
        assert processed_weather["wind_speed_kmh"] == 36
        assert processed_weather["raw_response_id"] == raw_weather["response_id"]
