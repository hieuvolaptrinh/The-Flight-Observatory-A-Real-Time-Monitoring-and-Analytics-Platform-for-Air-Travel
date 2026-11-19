"""Rename the existing database and recover available raw snapshots without API calls.

Stop the worker services and take a pg_dump backup before running this script.
Uses backend/ingestion/.env; all work is idempotent and retains existing tables.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from uuid import NAMESPACE_URL, uuid5

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from dotenv import dotenv_values

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "ingestion"))
from app.db import FlightRepository
from app.raw_store import RawStore


def migrate(processed_url, raw_url, old_name="analytics_db"):
    processed_name = conninfo_to_dict(processed_url)["dbname"]
    raw_name = conninfo_to_dict(raw_url)["dbname"]
    if raw_name == processed_name:
        raise ValueError("Raw and processed database names must differ")
    with psycopg.connect(make_conninfo(processed_url, dbname="postgres"), autocommit=True) as conn:
        names = {row[0] for row in conn.execute("SELECT datname FROM pg_database")}
        if processed_name not in names:
            if old_name in names:
                conn.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()", (old_name,))
                conn.execute(sql.SQL("ALTER DATABASE {} RENAME TO {}").format(sql.Identifier(old_name), sql.Identifier(processed_name)))
                print(f"Renamed {old_name} -> {processed_name}")
            else:
                conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(processed_name)))
        if raw_name not in names:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(raw_name)))
    with psycopg.connect(processed_url) as conn:
        conn.execute((BACKEND / "ingestion/db/schema.sql").read_text(encoding="utf-8"))
        # Live workers create their own public tables; preserve all legacy schemas.
    repo = FlightRepository(processed_url)
    raw_store = RawStore(processed_url, raw_url)
    counts = {"flights": 0, "weather": 0}
    with repo._connect_postgres() as conn:
        flights = conn.execute("SELECT flight_key,payload FROM live_flight_details").fetchall()
        for row in flights:
            details = json.loads(row["payload"])
            if details.get("raw_response_id") or "raw" not in details:
                continue
            response_id = str(uuid5(NAMESPACE_URL, "legacy-flight:" + row["flight_key"]))
            raw_store.archive("airlabs", "legacy/schedules", {}, {"response": [details["raw"]]},
                archive_kind="legacy_snapshot", response_id=response_id, fetched_at=details.get("fetched_at"))
            raw_store.mark(response_id, 0, "processed", flight_key=row["flight_key"])
            details.update(raw_response_id=response_id, raw_row_index=0)
            conn.execute("UPDATE live_flight_details SET payload=%s WHERE flight_key=%s", (json.dumps(details), row["flight_key"]))
            conn.execute("UPDATE ingested_flights SET raw_response_id=%s,raw_row_index=0 WHERE flight_key=%s AND raw_response_id IS NULL", (response_id, row["flight_key"]))
            counts["flights"] += 1
        for row in conn.execute("SELECT airport_code,observed_at,raw_json,raw_response_id FROM airport_weather").fetchall():
            if row["raw_response_id"]:
                continue
            payload = json.loads(row["raw_json"])
            if "raw" not in payload:
                continue
            response_id = str(uuid5(NAMESPACE_URL, f"legacy-weather:{row['airport_code']}:{row['observed_at']}"))
            raw_store.archive("openweather", "legacy/weather", {"airport_code": row["airport_code"]}, payload["raw"],
                archive_kind="legacy_snapshot", response_id=response_id, fetched_at=payload.get("fetched_at"))
            conn.execute("UPDATE airport_weather SET raw_response_id=%s WHERE airport_code=%s AND observed_at=%s", (response_id, row["airport_code"], row["observed_at"]))
            counts["weather"] += 1
    print(f"Recovered available legacy snapshots: {counts}; earlier API history cannot be reconstructed.")
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-name", default="analytics_db")
    args = parser.parse_args()
    env = dotenv_values(BACKEND / "ingestion/.env")
    migrate(env["DATABASE_URL"], env["RAW_DATABASE_URL"], args.old_name)
