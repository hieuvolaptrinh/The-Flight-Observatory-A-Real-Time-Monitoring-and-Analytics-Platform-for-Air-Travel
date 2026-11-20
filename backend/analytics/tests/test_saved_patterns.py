import asyncio
from datetime import date, datetime, timedelta
import os
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
import pytest

from app.config import Settings
from app.forecast import Estimate
from app.main import create_app
from app.pipeline import Pipeline


@pytest.fixture
def database():
    url = os.getenv("TEST_ANALYTICS_DATABASE_URL")
    if not url:
        pytest.skip("Requires a dedicated TEST_ANALYTICS_DATABASE_URL")
    with psycopg.connect(url) as conn:
        assert conn.info.dbname.startswith("test"), "Never use a production database"
        conn.execute((Path(__file__).resolve().parents[2] / "ingestion/db/schema.sql").read_text(encoding="utf-8"))
        conn.execute("TRUNCATE flight_data.flights CASCADE")
        conn.execute("DELETE FROM analytics.schedule_snapshots")
        conn.execute("INSERT INTO flight_data.airlines VALUES ('AA','Test airline') ON CONFLICT DO NOTHING")
        conn.execute("INSERT INTO flight_data.airports VALUES (1),(2) ON CONFLICT DO NOTHING")
        conn.execute("INSERT INTO flight_data.airport_versions VALUES (101,1,'JFK',199),(201,2,'LAX',299) ON CONFLICT DO NOTHING")
        for week in range(8):
            for index in range(1 + week % 4):
                conn.execute("""INSERT INTO flight_data.flights
                    (flight_date,carrier_code,flight_number,origin_airport_id,origin_airport_seq_id,
                     dest_airport_id,dest_airport_seq_id,scheduled_dep_local,scheduled_elapsed_min,distance_miles)
                    VALUES (%s,'AA',%s,1,101,2,201,%s,%s,%s)""",
                    (date(2025,1,6)+timedelta(weeks=week), str(index+1), f"{8+index:02}:00", 100+week*7+index, 500+week*100+index*15))
    return url


@pytest.fixture
def client(database):
    settings = Settings(database_url=database, scheduler_enabled=False)
    loop_options = {"loop_factory": asyncio.SelectorEventLoop} if os.name == "nt" else {}
    with TestClient(create_app(settings), backend_options=loop_options) as client:
        yield client


def publish(client):
    response = client.post("/run")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"


def test_api_returns_exact_persisted_patterns(client, database):
    publish(client)
    with psycopg.connect(database, row_factory=dict_row) as db:
        snapshot = db.execute("SELECT * FROM analytics.schedule_snapshots").fetchone()
    payload = snapshot["payload"]
    assert payload["version"] == 2
    assert client.get("/correlation").json()["matrix"] == payload["correlation"]["matrix"]
    assert client.get("/scatter?limit=500").json()["items"] == [dict(row, period_start=row["date"]) for row in payload["scatter"]]
    for grain in ("day","week","month"):
        for endpoint, key in (("line","series"),("histogram","histogram")):
            assert client.get(f"/{endpoint}?grain={grain}&limit=500").json()["items"] == [r for r in payload[key] if r["grain"] == grain]
    for endpoint in ("trend","seasonality"):
        for grain in ("week","month"):
            assert client.get(f"/{endpoint}?grain={grain}&limit=500").json()["items"] == payload[endpoint][grain]["items"]
    assert client.get("/seasonality").json()["ready"] is True


def test_gets_do_not_recompute_from_changed_source(client, database):
    publish(client)
    paths = ["/summary","/line?limit=500","/histogram?limit=500","/scatter?limit=500","/trend","/seasonality","/correlation"]
    before = {p: client.get(p).json() for p in paths}
    with psycopg.connect(database) as db:
        db.execute("UPDATE flight_data.flights SET distance_miles=distance_miles+1000,scheduled_elapsed_min=10")
    assert {p: client.get(p).json() for p in paths} == before
    publish(client)
    assert client.get("/scatter?limit=500").json() != before["/scatter?limit=500"]


def test_delete_results_then_run_restores_every_pattern(client, database):
    publish(client)
    with psycopg.connect(database) as db:
        db.execute("DELETE FROM analytics.schedule_snapshots")
    assert client.get("/summary").json()["ready"] is False
    assert client.get("/scatter").json()["items"] == []
    assert client.get("/trend").json()["ready"] is False
    assert client.get("/correlation").json()["ready"] is False
    client.get("/line?date_from=2025-01-06&date_to=2025-02-25")
    with psycopg.connect(database) as db:
        assert db.execute("SELECT count(*) FROM analytics.schedule_snapshots").fetchone()[0] == 0
    publish(client)
    assert client.get("/summary").json()["ready"] is True
    assert client.get("/seasonality").json()["ready"] is True
    assert client.get("/correlation").json()["ready"] is True


def test_failed_publish_preserves_previous_snapshot(client, database, monkeypatch):
    publish(client)
    before = client.get("/scatter?limit=500").json()
    async def fail(*args):
        raise RuntimeError("Failed derived calculation")
    monkeypatch.setattr(Pipeline, "_correlations", fail)
    response = client.post("/run")
    assert response.status_code == 500
    assert client.get("/scatter?limit=500").json() == before


def test_filtered_run_and_validation(client, database):
    publish(client)
    default = client.get("/summary").json()
    query = "date_from=2025-01-06&date_to=2025-01-21"
    assert client.get("/line?"+query).json()["summary"]["ready"] is False
    response = client.post("/run",json={"date_from":"2025-01-06","date_to":"2025-01-21"})
    assert response.status_code == 200
    assert client.get("/line?"+query).json()["summary"]["ready"] is True
    assert client.get("/summary").json() == default
    assert client.post("/run",json={"date_from":"2025-01-06"}).status_code == 422
    assert client.post("/run",json={"date_from":"2025-01-10","date_to":"2025-01-01"}).status_code == 422


def test_short_history_shows_daily_trend_and_hourly_profile(client, database):
    with psycopg.connect(database) as db:
        db.execute("""
            UPDATE flight_data.flights
            SET flight_date = DATE '2025-01-06' + mod(flight_id, 2)::int, flight_number = flight_id::text
        """)
    publish(client)
    trend = client.get("/trend").json()
    assert trend["ready"] and trend["grain"] == "day" and len(trend["items"]) == 2
    assert not client.get("/trend?grain=week").json()["ready"]
    seasonality = client.get("/seasonality").json()
    assert not seasonality["ready"] and not seasonality["items"]
    assert sum(row["flight_count"] for row in seasonality["hourly_profile"]) == 20


def test_forecast_requires_recent_live_days_and_reuses_exact_scope(database, monkeypatch):
    database = make_conninfo(database, options="-c search_path=forecast_test,public")
    settings = Settings(
        database_url=database, scheduler_enabled=False,
        forecast_airports="JFK,LGA", forecast_min_observed_days=5,
    )
    today = datetime.now(settings.forecast_timezone).date()
    target = today + timedelta(days=1)
    estimate = AsyncMock(return_value=Estimate(predicted_flight_count=3, explanation="Dữ liệu kiểm thử."))
    monkeypatch.setattr("app.forecast.ask_gemini", estimate)
    with psycopg.connect(database) as db:
        db.execute("DELETE FROM analytics.forecasts")
        db.execute("CREATE SCHEMA IF NOT EXISTS forecast_test")
        db.execute("CREATE TABLE IF NOT EXISTS forecast_test.ingested_flights (flight_key text PRIMARY KEY, fl_date text, origin text)")
        db.execute("CREATE TABLE IF NOT EXISTS forecast_test.live_flight_details (flight_key text PRIMARY KEY)")
        db.execute("TRUNCATE forecast_test.live_flight_details, forecast_test.ingested_flights")
        rows = [(str(day), (today - timedelta(days=day)).isoformat(), "JFK") for day in range(1, 6)]
        rows += [("today", today.isoformat(), "LGA"), ("future", target.isoformat(), "JFK"),
                 ("other", rows[0][1], "LAX"), ("csv", rows[0][1], "JFK")]
        with db.cursor() as cursor:
            cursor.executemany("INSERT INTO ingested_flights VALUES (%s,%s,%s)", rows)
            cursor.executemany(
                "INSERT INTO live_flight_details VALUES (%s)", [(key,) for key, _, _ in rows if key not in {"5", "csv"}],
            )

    loop_options = {"loop_factory": asyncio.SelectorEventLoop} if os.name == "nt" else {}
    with TestClient(create_app(settings), backend_options=loop_options) as client:
        pending = client.get("/forecast").json()
        assert pending["forecast_date"] == target.isoformat()
        assert pending["observed_days"] == 4
        assert client.post("/forecast").status_code == 409
        estimate.assert_not_awaited()
        demo = settings.model_copy(update={"forecast_min_observed_days": 1})
        with TestClient(create_app(demo), backend_options=loop_options) as demo_client:
            preliminary = demo_client.post("/forecast").json()["payload"]
            assert preliminary["provisional"] is True
            assert preliminary["observed_days"] == 4
            assert demo_client.get("/classification").json()["provisional"] is True
        assert client.get("/forecast").json()["ready"] is False
        estimate.reset_mock()
        with psycopg.connect(database) as db:
            db.execute("INSERT INTO live_flight_details VALUES ('5')")
        assert client.post("/forecast").json()["payload"]["classification"] == "high"
        assert client.get("/classification").json()["classification"] == "high"
        assert client.post("/forecast").status_code == 200
        estimate.assert_awaited_once()
        _, history, _, airports = estimate.await_args.args
        assert airports == ["JFK", "LGA"]
        assert [row["flight_count"] for row in history] == [1] * 5

    estimate.return_value = Estimate(predicted_flight_count=0, explanation="Dữ liệu kiểm thử.")
    jfk_only = settings.model_copy(update={"forecast_airports": "JFK"})
    with TestClient(create_app(jfk_only), backend_options=loop_options) as client:
        assert client.get("/forecast").json()["ready"] is False
        assert client.post("/forecast").json()["payload"]["classification"] == "low"
    assert estimate.await_count == 2
