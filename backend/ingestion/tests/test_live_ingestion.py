import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import sqlite3

import httpx
import pytest

from app.config import Settings
from app.db import FlightRepository, SCHEMA_SQL
from app.live_store import LiveStore, quota_period
from app.pipeline import Pipeline, normalize_record
from app.providers import LiveProviders, normalize_schedule, normalize_weather, accounts_from_settings
from app.schedule import Flight, outcome_params


AIRPORTS = {
    "JFK": {"iata_code": "JFK", "lat": 40.64, "lng": -73.78, "timezone": "America/New_York"},
    "LAX": {"iata_code": "LAX", "lat": 33.94, "lng": -118.41, "timezone": "America/Los_Angeles"},
}
SCHEDULE = {"airline_iata": "AA", "flight_number": "123", "dep_iata": "JFK", "arr_iata": "LAX",
    "dep_time": "2026-11-17 10:00", "arr_time": "2026-11-17 13:00", "status": "scheduled"}
WEATHER = {"dt": 1794927600, "main": {"temp": 0, "pressure": 1012}, "wind": {"speed": 10}, "visibility": 8000}


@pytest.fixture
def repo(tmp_path):
    return FlightRepository("sqlite:///" + str(tmp_path / "flights.db"))


def settings(repo, **kwargs):
    return Settings(database_url=repo.database_url, airlabs_api_key="test-key", openweather_api_key="weather-key", airlabs_accounts="", **kwargs)


def normalize(raw):
    return normalize_schedule(raw, AIRPORTS["JFK"], AIRPORTS["LAX"], "2026-11-17T15:00:00+00:00")


def test_timezones_unknown_and_zero_delay():
    record = normalize(SCHEDULE)
    assert record["CRS_ELAPSED_TIME"] == 360
    assert 2400 < record["DISTANCE"] < 2600
    assert record["DELAY_MINUTES"] is None
    normalized = normalize_record(record, "now", "now")
    assert normalized["delay_status"] == "unknown"
    assert normalized["is_delayed"] is None
    assert normalize({**SCHEDULE, "dep_delayed": 0})["DELAY_MINUTES"] == 0


def test_actual_departure_arrival_are_separate_and_estimates_not_outcomes():
    record = normalize({**SCHEDULE, "dep_actual": "2026-11-17 10:10", "arr_actual": "2026-11-17 12:55"})
    assert record["_details"]["dep_delay_min"] == 10
    assert record["_details"]["arr_delay_min"] == -5
    assert record["DELAY_MINUTES"] == -5
    estimate = normalize({**SCHEDULE, "arr_delayed": 20})
    assert estimate["_details"]["delay_kind"] == "estimated"
    assert estimate["_details"]["arr_delay_min"] is None
    assert normalize({**SCHEDULE, "status": "cancelled", "arr_delayed": 20})["DELAY_MINUTES"] is None


def test_weather_units_and_optional_gust():
    weather = normalize_weather(WEATHER, "now")
    assert weather["temperature_c"] == 0
    assert weather["wind_speed_kmh"] == 36
    assert weather["wind_gust_kmh"] is None
    assert weather["visibility_km"] == 8
    assert weather["precipitation_mm"] == 0
    assert normalize_weather({**WEATHER, "rain": {"1h": 2}, "snow": {"1h": 1}}, "now")["precipitation_mm"] == 3


def test_api_to_database_refresh_cache_and_no_duplicates(repo):
    calls = []
    delay = [None]
    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/schedules"):
            row = dict(SCHEDULE)
            if delay[0] is not None:
                row["dep_delayed"] = delay[0]
            return httpx.Response(200, json={"response": [row, row], "request": {"has_more": False}})
        if request.url.path.endswith("/airports"):
            return httpx.Response(200, json={"response": [AIRPORTS[request.url.params["iata_code"]]]})
        return httpx.Response(200, json=WEATHER)
    pipeline = Pipeline(settings(repo), repo)
    pipeline.providers.transport = httpx.MockTransport(handler)
    asyncio.run(pipeline.run())
    first = repo.query_flights()
    assert first["metadata"]["total_stored"] == 1
    assert first["metadata"]["unknown_delay_count"] == 1
    assert first["items"][0]["origin_coordinate"]["lat"] == AIRPORTS["JFK"]["lat"]
    assert first["items"][0]["dest_coordinate"]["lon"] == AIRPORTS["LAX"]["lng"]
    delay[0] = 25
    asyncio.run(pipeline.run())
    refreshed = repo.query_flights()
    assert refreshed["items"][0]["delay_minutes"] == 25
    assert refreshed["items"][0]["source"] == "airlabs"
    assert refreshed["metadata"]["total_stored"] == 1
    assert refreshed["metadata"]["last_batch"]["inserted_count"] == 0
    assert refreshed["metadata"]["last_batch"]["updated_count"] == 1
    assert refreshed["metadata"]["delay_rate_pct"] == 100
    assert calls.count("/api/v9/airports") == 2
    assert calls.count("/data/2.5/weather") == 1
    usage = LiveStore(repo).usage()
    assert sum(row["requests"] for row in usage if row["quota_group"] == "airlabs:default") == 4


def test_budget_persists_and_is_atomic(repo):
    store = LiveStore(repo)
    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(lambda _: store.reserve("test", 3, 1), range(12)))
    assert sum(results) == 3
    reopened = LiveStore(FlightRepository(repo.database_url))
    assert not reopened.reserve("test", 3, 1)


def test_poll_window_is_shared_across_runners_and_restarts(repo):
    started = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)
    workers = [LiveStore(repo) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        delays = list(pool.map(lambda store: store.reserve_poll(300, started), workers))
    assert sorted(delays) == [0, 300, 300, 300]

    reopened = LiveStore(FlightRepository(repo.database_url))
    assert reopened.reserve_poll(300, started + timedelta(seconds=299)) == 1
    assert reopened.reserve_poll(300, started + timedelta(seconds=300)) == 0


def test_route_cluster_filter_runs_before_pagination_and_overview_uses_full_scope(repo):
    pipeline = Pipeline(settings(repo), repo)
    schedules = [normalize({**SCHEDULE, "flight_number": str(n), "dep_delayed": n * 10}) for n in range(1, 4)]
    asyncio.run(pipeline.ingest_payload({"source": "airlabs", "data": schedules}))
    with repo._connect_sqlite() as conn:
        conn.executescript("""
            CREATE TABLE clustering_runs (run_id TEXT, created_at TEXT);
            CREATE TABLE cluster_assignments (run_id TEXT, entity_type TEXT, entity_code TEXT, cluster_id INTEGER);
            INSERT INTO clustering_runs VALUES ('old', '2026-11-17'), ('new', '2026-11-18');
            INSERT INTO cluster_assignments VALUES ('old', 'route', 'JFK → LAX', 1), ('new', 'route', 'JFK → LAX', 2);
        """)

    scoped = repo.query_flights(source="airlabs", cluster_id=2, limit=1, offset=1, include_overview=True)
    assert len(scoped["items"]) == 1
    assert scoped["metadata"]["filtered_count"] == 3
    assert scoped["metadata"]["hourly"] == [{"hour": 10, "flights": 3, "known": 3, "delayed": 2}]
    assert scoped["metadata"]["airport_stats"][0]["flight_count"] == 3
    assert repo.query_flights(cluster_id=1)["metadata"]["filtered_count"] == 0
    assert repo.query_flights(source="legacy")["metadata"]["total_stored"] == 0


def test_billing_cycle():
    assert quota_period(datetime(2026, 11, 17, tzinfo=timezone.utc), 18) == "2026-10-18"
    assert quota_period(datetime(2026, 11, 18, tzinfo=timezone.utc), 18) == "2026-11-18"


def test_missing_keys_does_not_call_network(repo):
    configured = Settings(database_url=repo.database_url, airlabs_api_key="", airlabs_accounts="", openweather_api_key="")
    providers = LiveProviders(configured, repo, httpx.MockTransport(lambda _: pytest.fail("unexpected network call")))
    assert asyncio.run(providers.fetch())["data"] == []
    assert any("missing AirLabs key" in w for w in providers.last_status["warnings"])


def test_quota_error_redacted_and_cooldown_survives_restart(repo):
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"error": {"code": "month_limit_exceeded", "message": "secret test-key"}})
    for _ in range(2):
        providers = LiveProviders(settings(repo), repo, httpx.MockTransport(handler))
        assert asyncio.run(providers.fetch())["data"] == []
        assert "test-key" not in json.dumps(providers.last_status)
    assert len(calls) == 1


def test_pagination_is_capped_and_counted(repo):
    providers = LiveProviders(settings(repo, airlabs_max_pages=2), repo, httpx.MockTransport(
        lambda _: httpx.Response(200, json={"response": [], "request": {"has_more": True}})))
    asyncio.run(providers.fetch())
    assert providers.last_status["schedule_requests_succeeded"] == 2
    assert any("partial" in warning for warning in providers.last_status["warnings"])


def test_shared_quota_and_airport_assignment(repo):
    config = settings(repo)
    from pydantic import SecretStr
    config.airlabs_accounts = SecretStr(json.dumps([
        {"name": "a", "key": "a-secret", "airports": ["JFK"], "quota_group": "team"},
        {"name": "b", "key": "b-secret", "airports": ["ORD"], "quota_group": "team"},
    ]))
    accounts = accounts_from_settings(config)
    assert accounts[0].quota_group == accounts[1].quota_group
    assert "a-secret" not in repr(accounts)
    config.airlabs_accounts = SecretStr('[{"name":"a","key":"x","airports":["JFK","JFK"]}]')
    with pytest.raises(ValueError):
        accounts_from_settings(config)


def test_migration_preserves_existing_sqlite_rows(tmp_path):
    path = tmp_path / "old.db"
    old_schema = SCHEMA_SQL.replace("delay_minutes REAL,", "delay_minutes REAL NOT NULL,").replace("is_delayed INTEGER,", "is_delayed INTEGER NOT NULL,")
    with sqlite3.connect(path) as conn:
        conn.executescript(old_schema)
        conn.execute("INSERT INTO ingested_flights (flight_key,fl_date,op_unique_carrier,op_carrier_fl_num,flight_code,origin,dest,route,delay_minutes,delay_status,is_delayed,fetched_at,ingested_at) VALUES ('old','2025-01-01','AA','1','AA 1','JFK','LAX','JFK-LAX',5,'on_time',0,'2025-01-01','2025-01-01')")
    repo = FlightRepository("sqlite:///" + str(path))
    assert repo.query_flights()["metadata"]["total_stored"] == 1
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE ingested_flights SET delay_minutes=NULL,is_delayed=NULL")


def test_operating_codeshare_key():
    operating = normalize(SCHEDULE)
    marketed = normalize({**SCHEDULE, "airline_iata": "BA", "flight_number": "999", "cs_airline_iata": "AA", "cs_flight_number": "123"})
    assert operating["FLIGHT_KEY"] == marketed["FLIGHT_KEY"]


def test_health_and_raw_endpoints_without_secrets(repo):
    from fastapi.testclient import TestClient
    from app.main import create_app
    configured = settings(repo, scheduler_enabled=False)
    pipeline = Pipeline(configured, repo)
    asyncio.run(pipeline.ingest_payload({"source": "airlabs", "data": [normalize(SCHEDULE)]}))
    with TestClient(create_app(configured, pipeline)) as client:
        assert client.get("/health").json()["source"] == "airlabs"
        raw = client.get("/raw").json()
        assert raw["total"] == 1
        assert raw["data"][0]["raw"] == SCHEDULE
        assert client.get("/raw?cursor=-1").status_code == 422
        providers = client.get("/providers")
        assert "test-key" not in providers.text
        assert client.post("/run").status_code == 404
        assert client.get("/providers").json()["usage"] == providers.json()["usage"] == []


def test_failed_source_preserves_previous_flights(repo):
    pipeline = Pipeline(settings(repo), repo)
    asyncio.run(pipeline.ingest_payload({"source": "airlabs", "data": [normalize(SCHEDULE)]}))
    pipeline.providers.transport = httpx.MockTransport(lambda _: httpx.Response(503, text="secret test-key"))
    output = asyncio.run(pipeline.run())
    assert len(output.items) == 1
    assert output.items[0]["delay_minutes"] is None
    assert "test-key" not in json.dumps(output.metadata)


def test_partial_failure_keeps_other_account_working(repo):
    from pydantic import SecretStr
    config = settings(repo)
    config.airlabs_accounts = SecretStr(json.dumps([
        {"name": "bad", "key": "bad-key", "airports": ["ORD"]},
        {"name": "good", "key": "good-key", "airports": ["JFK"]},
    ]))
    def handler(request):
        if request.url.params.get("api_key") == "bad-key":
            return httpx.Response(401)
        if request.url.path.endswith("/schedules"):
            return httpx.Response(200, json={"response": [SCHEDULE]})
        if request.url.path.endswith("/airports"):
            return httpx.Response(200, json={"response": [AIRPORTS[request.url.params["iata_code"]]]})
        return httpx.Response(200, json=WEATHER)
    providers = LiveProviders(config, repo, httpx.MockTransport(handler))
    assert len(asyncio.run(providers.fetch())["data"]) == 1
    assert any("bad/ORD" in message for message in providers.last_status["warnings"])


def test_postgres_outcome_binding_preserves_missing_values():
    record = normalize({**SCHEDULE, "arr_delayed": 20})
    flight = Flight.model_validate({**record,
        "TAIL_NUM": None, "ORIGIN_AIRPORT_ID": 1, "ORIGIN_AIRPORT_SEQ_ID": 101,
        "ORIGIN_CITY_MARKET_ID": 199, "DEST_AIRPORT_ID": 2, "DEST_AIRPORT_SEQ_ID": 201,
        "DEST_CITY_MARKET_ID": 299, "LIVE": True,
    })
    params = outcome_params(flight, 1)
    assert params["dep_delay_min"] is None and params["arr_delay_min"] is None
