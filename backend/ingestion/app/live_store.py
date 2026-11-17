"""Durable provider cache, request budgets and idempotent live-data migration."""
import calendar
import json
from datetime import datetime, timezone


LIVE_SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_cache (
    cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_epoch REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS provider_usage (
    quota_group TEXT NOT NULL, period TEXT NOT NULL, requests INTEGER NOT NULL,
    PRIMARY KEY (quota_group, period)
);
CREATE TABLE IF NOT EXISTS airport_weather (
    airport_code TEXT NOT NULL, observed_at TEXT NOT NULL, fetched_at TEXT NOT NULL,
    temperature_c REAL, wind_speed_kmh REAL, wind_gust_kmh REAL,
    visibility_km REAL, precipitation_mm REAL, pressure_hpa REAL,
    source TEXT NOT NULL, raw_json TEXT NOT NULL,
    PRIMARY KEY (airport_code, observed_at)
);
CREATE TABLE IF NOT EXISTS live_flight_details (
    flight_key TEXT PRIMARY KEY, payload TEXT NOT NULL
);
"""


def quota_period(now: datetime, reset_day: int) -> str:
    """UTC billing-cycle start; supports days 1..28 without month-end ambiguity."""
    start = now.replace(day=reset_day, hour=0, minute=0, second=0, microsecond=0)
    if now < start:
        month = start.month - 1 or 12
        year = start.year - (start.month == 1)
        start = start.replace(year=year, month=month, day=min(reset_day, calendar.monthrange(year, month)[1]))
    return start.date().isoformat()


class LiveStore:
    def __init__(self, repository):
        self.repository = repository
        self.pg = repository.is_postgres

    def connect(self):
        return self.repository._connect_postgres() if self.pg else self.repository._connect_sqlite()

    def sql(self, statement):
        return statement.replace("?", "%s") if self.pg else statement

    def migrate(self):
        with self.connect() as conn:
            if self.pg:
                conn.execute(LIVE_SCHEMA)
                conn.execute("ALTER TABLE ingested_flights ALTER COLUMN delay_minutes DROP NOT NULL")
                conn.execute("ALTER TABLE ingested_flights ALTER COLUMN is_delayed DROP NOT NULL")
                conn.execute("ALTER TABLE ingestion_batches ADD COLUMN IF NOT EXISTS updated_count INTEGER NOT NULL DEFAULT 0")
            else:
                conn.executescript(LIVE_SCHEMA)
                columns = conn.execute("PRAGMA table_info(ingested_flights)").fetchall()
                if any(row["name"] == "delay_minutes" and row["notnull"] for row in columns):
                    # Preserve all existing rows and indexes during the one-time SQLite migration.
                    original = conn.execute("SELECT sql FROM sqlite_master WHERE name='ingested_flights'").fetchone()[0]
                    indexes = [r[0] for r in conn.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='ingested_flights' AND sql IS NOT NULL")]
                    conn.execute("ALTER TABLE ingested_flights RENAME TO ingested_flights_before_live")
                    conn.execute(original.replace("delay_minutes REAL NOT NULL", "delay_minutes REAL").replace("is_delayed INTEGER NOT NULL", "is_delayed INTEGER"))
                    conn.execute("INSERT INTO ingested_flights SELECT * FROM ingested_flights_before_live")
                    conn.execute("DROP TABLE ingested_flights_before_live")
                    for statement in indexes:
                        conn.execute(statement)
                if not any(row["name"] == "updated_count" for row in conn.execute("PRAGMA table_info(ingestion_batches)")):
                    conn.execute("ALTER TABLE ingestion_batches ADD COLUMN updated_count INTEGER NOT NULL DEFAULT 0")
            conn.commit()

    def cached(self, key):
        with self.connect() as conn:
            row = conn.execute(self.sql("SELECT payload, fetched_epoch FROM provider_cache WHERE cache_key=?"), (key,)).fetchone()
            return (json.loads(row["payload"]), row["fetched_epoch"]) if row else (None, 0)

    def cache(self, key, payload, epoch=None):
        epoch = datetime.now(timezone.utc).timestamp() if epoch is None else epoch
        with self.connect() as conn:
            conn.execute(self.sql("INSERT INTO provider_cache VALUES (?, ?, ?) ON CONFLICT(cache_key) DO UPDATE SET payload=excluded.payload, fetched_epoch=excluded.fetched_epoch"), (key, json.dumps(payload), epoch))
            conn.commit()

    def reserve(self, group, budget, reset_day, now=None):
        period = quota_period(now or datetime.now(timezone.utc), reset_day)
        with self.connect() as conn:
            result = conn.execute(self.sql("""
                INSERT INTO provider_usage VALUES (?, ?, 1)
                ON CONFLICT(quota_group, period) DO UPDATE SET requests=provider_usage.requests+1
                WHERE provider_usage.requests < ? RETURNING requests
            """), (group, period, budget)).fetchone() if budget > 0 else None
            conn.commit()
            return result is not None

    def usage(self):
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM provider_usage ORDER BY period DESC, quota_group")]

    def weather(self, code, payload):
        fields = ("observed_at", "fetched_at", "temperature_c", "wind_speed_kmh", "wind_gust_kmh", "visibility_km", "precipitation_mm", "pressure_hpa", "source")
        with self.connect() as conn:
            conn.execute(self.sql("""INSERT INTO airport_weather VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(airport_code, observed_at) DO UPDATE SET fetched_at=excluded.fetched_at
            """), (code, *(payload.get(k) for k in fields), json.dumps(payload)))
            conn.commit()
