import importlib.util
import json
import os
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit, urlunsplit

import pytest


@pytest.mark.skipif(not (os.getenv("TEST_DATABASE_URL") and os.getenv("TEST_RAW_DATABASE_URL")), reason="Requires PostgreSQL test databases")
def test_database_rename_and_raw_backfill_are_idempotent():
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    from app.db import FlightRepository
    from test_live_ingestion import SCHEDULE

    suffix = uuid4().hex[:10]
    old, new = "test_migration_old_" + suffix, "test_migration_new_" + suffix
    base_url, raw_url = os.environ["TEST_DATABASE_URL"], os.environ["TEST_RAW_DATABASE_URL"]
    for url in (base_url, raw_url):
        with psycopg.connect(url) as conn:
            assert conn.info.dbname.startswith("test")
    with psycopg.connect(make_conninfo(base_url, dbname="postgres"), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(old)))
        try:
            parsed = urlsplit(base_url)
            old_url = urlunsplit(parsed._replace(path="/" + old))
            new_url = urlunsplit(parsed._replace(path="/" + new))
            repo = FlightRepository(old_url)
            key = "test-flight-" + suffix
            with repo._connect_postgres() as conn:
                conn.execute("""INSERT INTO ingested_flights
                    (flight_key,fl_date,op_unique_carrier,op_carrier_fl_num,flight_code,origin,dest,route,
                     delay_status,fetched_at,ingested_at) VALUES (%s,'2026-11-17','AA','123','AA 123','JFK','LAX','JFK-LAX',
                     'unknown','2026-11-17','2026-11-17')""", (key,))
                conn.execute("INSERT INTO live_flight_details VALUES (%s,%s)", (key, json.dumps({"raw": SCHEDULE})))
            script = Path(__file__).resolve().parents[2] / "database/migrate_databases.py"
            spec = importlib.util.spec_from_file_location("test_migration", script)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            assert module.migrate(new_url, raw_url, old) == {"flights": 1, "weather": 0}
            assert module.migrate(new_url, raw_url, old) == {"flights": 0, "weather": 0}
            with psycopg.connect(new_url) as conn:
                response_id, = conn.execute("SELECT raw_response_id FROM ingested_flights WHERE flight_key=%s", (key,)).fetchone()
                assert response_id is not None
            with psycopg.connect(raw_url) as conn:
                payload, = conn.execute("SELECT raw_json FROM raw_flights WHERE response_id=%s", (response_id,)).fetchone()
                assert json.loads(payload) == SCHEDULE
        finally:
            for name in (old, new):
                admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s", (name,))
                admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
