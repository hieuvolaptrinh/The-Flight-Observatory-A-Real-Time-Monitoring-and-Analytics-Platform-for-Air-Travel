"""Check isolated service imports (each container owns a package named app)."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def run_service(service, script, *args):
    result = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]);\n" + script,
        str(ROOT / service), *map(str, args)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_prediction_without_model_is_waiting(tmp_path):
    run_service("prediction", '''
from app.config import Settings
from app.pipeline import Pipeline
from app.jobs import JobRunner
import asyncio
settings = Settings(live_api_mode=True, model_path=sys.argv[2])
runner = JobRunner("prediction", Pipeline(settings))
asyncio.run(runner.run_once())
assert runner.results.ready is False
assert runner.results.output.metadata["reason"] == "model_missing"
''', tmp_path / "missing.joblib")


def test_clustering_empty_live_database_no_csv(tmp_path):
    run_service("clustering", '''
from app.config import Settings
from app.pipeline import Pipeline
from app.jobs import JobRunner
import asyncio
settings = Settings(live_api_mode=True, database_url="sqlite:///"+sys.argv[2], source_database_url="sqlite:///"+sys.argv[2], model_path=sys.argv[3])
runner = JobRunner("clustering", Pipeline(settings))
asyncio.run(runner.run_once())
assert runner.results.ready is False
assert runner.results.output.metadata["reason"] == "insufficient_airports"
''', tmp_path / "clusters.db", tmp_path / "missing.joblib")


def test_prediction_reads_real_weather_and_excludes_cancelled(tmp_path):
    import asyncio
    from datetime import datetime, timezone
    from app.config import Settings
    from app.db import FlightRepository
    from app.pipeline import Pipeline
    from app.providers import normalize_schedule, normalize_weather
    from app.live_store import LiveStore
    repo = FlightRepository("sqlite:///" + str(tmp_path / "live.db"))
    now = datetime.now(timezone.utc)
    pipeline = Pipeline(Settings(database_url=repo.database_url, airlabs_api_key="", airlabs_accounts=""), repo)
    raw = {"airline_iata": "AA", "flight_number": "1", "dep_iata": "JFK", "arr_iata": "LAX", "dep_time": now.strftime("%Y-%m-%d 10:00"), "status": "scheduled"}
    weather = normalize_weather({"dt": now.timestamp(), "main": {"temp": 0, "pressure": 1005}, "wind": {"speed": 5}, "visibility": 5000}, now.isoformat())
    LiveStore(repo).weather("JFK", weather)
    script = '''
from app.config import Settings
from app.pipeline import Pipeline
settings = Settings(live_api_mode=True, source_database_url=sys.argv[2])
rows = Pipeline(settings)._load_candidate_flights_sync()
assert len(rows) == int(sys.argv[3])
if rows:
    assert rows[0]["temperature_c"] == 0
    assert rows[0]["wind_speed_kmh"] == 18
    assert rows[0]["wind_gust_kmh"] is None
    assert rows[0]["weather_source"] == "openweather"
'''
    for status, expected in (("scheduled", 1), ("cancelled", 0)):
        raw["status"] = status
        mapped = normalize_schedule(raw, {}, {}, now.isoformat())
        asyncio.run(pipeline.ingest_payload({"source": "airlabs", "data": [mapped]}))
        run_service("prediction", script, repo.database_url, expected)


def test_compose_has_no_simulator_or_csv_and_no_duplicate_keys():
    class StrictLoader(yaml.SafeLoader):
        pass
    def construct(loader, node, deep=False):
        # YAML merge aliases are intentional; only reject duplicate explicit keys.
        keys = [k.value for k, _ in node.value if k.value != "<<"]
        assert len(keys) == len(set(keys)), f"Duplicate YAML keys: {keys}"
        loader.flatten_mapping(node)
        return dict(loader.construct_pairs(node, deep))
    StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct)
    compose = yaml.load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"), Loader=StrictLoader)
    assert "data-simulator" not in compose["services"]
    for service in compose["services"].values():
        assert "data-simulator" not in service.get("depends_on", {})
        assert all("data-simulator" not in mount for mount in service.get("volumes", []))
    assert "ingestion" in compose["services"]["prediction"]["depends_on"]
    assert "ingestion" in compose["services"]["analytics"]["depends_on"]


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="Requires a dedicated PostgreSQL test database")
def test_postgres_live_migration_and_upsert():
    import asyncio
    import psycopg
    from app.config import Settings
    from app.db import FlightRepository
    from app.pipeline import Pipeline
    from app.providers import normalize_schedule
    url = os.environ["TEST_DATABASE_URL"]
    with psycopg.connect(url) as conn:
        assert conn.info.dbname.startswith("test"), "Use a disposable database whose name starts with test"
        conn.execute((ROOT / "ingestion/db/schema.sql").read_text(encoding="utf-8"))
        conn.execute((ROOT / "db/init.sql").read_text(encoding="utf-8"))
    repo = FlightRepository(url)
    settings = Settings(database_url=url, airlabs_api_key="", airlabs_accounts="", openweather_api_key="")
    pipeline = Pipeline(settings, repo)
    raw = {"airline_iata": "AA", "flight_number": "9999", "dep_iata": "JFK", "arr_iata": "LAX", "dep_time": "2026-11-17 10:00", "arr_time": "2026-11-17 13:00"}
    for estimate in (None, 25):
        raw["dep_delayed"] = estimate
        record = normalize_schedule(raw, {"timezone": "America/New_York"}, {"timezone": "America/Los_Angeles"}, "2026-11-17T15:00:00+00:00")
        asyncio.run(pipeline.ingest_payload({"source": "airlabs", "data": [record]}))
    found = repo.query_flights(search="9999")
    assert found["metadata"]["filtered_count"] == 1
    assert found["items"][0]["delay_minutes"] == 25
    with psycopg.connect(url) as conn:
        row = conn.execute("SELECT o.arr_delay_min,o.dep_delay_min FROM flight_data.flight_outcomes o JOIN flight_data.flights f USING(flight_id) WHERE f.flight_number='9999'").fetchone()
        assert row == (None, None)
