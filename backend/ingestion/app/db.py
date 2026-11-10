"""
Database layer for Flight Ingestion Service.
Supports both PostgreSQL (via psycopg) and SQLite (via sqlite3).
- Uses batch execution (`executemany`) instead of row-by-row network round-trips.
- Uses static SQL constants and parameterized named bindings (`%(param)s` / `:param`)
  with a strict whitelist dictionary for `ORDER BY` — zero dynamic SQL string interpolation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import sqlite3
from typing import Any

from app.schedule import Flight, ReplayPosition, save_flights_batch

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ingested_flights (
    flight_key TEXT PRIMARY KEY,
    fl_date TEXT NOT NULL,
    day_of_week INTEGER,
    op_unique_carrier TEXT NOT NULL,
    carrier_name TEXT,
    tail_num TEXT,
    op_carrier_fl_num TEXT NOT NULL,
    flight_code TEXT NOT NULL,
    origin_airport_id INTEGER,
    origin TEXT NOT NULL,
    dest_airport_id INTEGER,
    dest TEXT NOT NULL,
    route TEXT NOT NULL,
    crs_dep_time TEXT,
    crs_arr_time TEXT,
    dep_hour INTEGER,
    crs_elapsed_time REAL,
    distance REAL,
    delay_minutes REAL NOT NULL,
    delay_status TEXT NOT NULL,
    is_delayed INTEGER NOT NULL,
    fetched_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_flights_origin ON ingested_flights(origin);
CREATE INDEX IF NOT EXISTS idx_flights_dest ON ingested_flights(dest);
CREATE INDEX IF NOT EXISTS idx_flights_carrier ON ingested_flights(op_unique_carrier);
CREATE INDEX IF NOT EXISTS idx_flights_status ON ingested_flights(delay_status);
CREATE INDEX IF NOT EXISTS idx_flights_date ON ingested_flights(fl_date);
CREATE INDEX IF NOT EXISTS idx_flights_ingested_at ON ingested_flights(ingested_at DESC);

CREATE TABLE IF NOT EXISTS ingestion_batches (
    batch_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    window_start INTEGER,
    window_end INTEGER,
    received_count INTEGER NOT NULL,
    inserted_count INTEGER NOT NULL,
    duplicate_count INTEGER NOT NULL,
    total_stored INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
"""

INGESTED_FLIGHT_COLS = (
    "flight_key", "fl_date", "day_of_week", "op_unique_carrier", "carrier_name",
    "tail_num", "op_carrier_fl_num", "flight_code", "origin_airport_id", "origin",
    "dest_airport_id", "dest", "route", "crs_dep_time", "crs_arr_time", "dep_hour",
    "crs_elapsed_time", "distance", "delay_minutes", "delay_status", "is_delayed",
    "fetched_at", "ingested_at",
)

PG_INSERT_INGESTED_FLIGHT_SQL = """
INSERT INTO ingested_flights (
    flight_key, fl_date, day_of_week, op_unique_carrier, carrier_name,
    tail_num, op_carrier_fl_num, flight_code, origin_airport_id, origin,
    dest_airport_id, dest, route, crs_dep_time, crs_arr_time, dep_hour,
    crs_elapsed_time, distance, delay_minutes, delay_status, is_delayed,
    fetched_at, ingested_at
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s
)
ON CONFLICT (flight_key) DO NOTHING
"""

SQLITE_INSERT_INGESTED_FLIGHT_SQL = """
INSERT OR IGNORE INTO ingested_flights (
    flight_key, fl_date, day_of_week, op_unique_carrier, carrier_name,
    tail_num, op_carrier_fl_num, flight_code, origin_airport_id, origin,
    dest_airport_id, dest, route, crs_dep_time, crs_arr_time, dep_hour,
    crs_elapsed_time, distance, delay_minutes, delay_status, is_delayed,
    fetched_at, ingested_at
) VALUES (
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
    ?, ?, ?
)
"""

PG_STATS_SQL = """
SELECT
    COUNT(*) AS filtered_count,
    SUM(CASE WHEN is_delayed = 1 THEN 1 ELSE 0 END) AS delayed_count,
    SUM(CASE WHEN delay_status = 'on_time' THEN 1 ELSE 0 END) AS on_time_count,
    SUM(CASE WHEN delay_status = 'moderate_delay' THEN 1 ELSE 0 END) AS moderate_delay_count,
    SUM(CASE WHEN delay_status = 'severe_delay' THEN 1 ELSE 0 END) AS severe_delay_count,
    AVG(delay_minutes) AS avg_delay_minutes,
    AVG(distance) AS avg_distance,
    AVG(crs_elapsed_time) AS avg_elapsed_time,
    MAX(ingested_at) AS latest_ingested_at
FROM ingested_flights
WHERE (%(origin)s::text IS NULL OR origin = %(origin)s)
  AND (%(dest)s::text IS NULL OR dest = %(dest)s)
  AND (%(carrier)s::text IS NULL OR op_unique_carrier = %(carrier)s)
  AND (%(status)s::text IS NULL OR delay_status = %(status)s)
  AND (
      %(search)s::text IS NULL
      OR UPPER(flight_code) LIKE %(search)s
      OR UPPER(origin) LIKE %(search)s
      OR UPPER(dest) LIKE %(search)s
      OR UPPER(COALESCE(tail_num, '')) LIKE %(search)s
      OR UPPER(COALESCE(carrier_name, '')) LIKE %(search)s
  )
"""

SQLITE_STATS_SQL = """
SELECT
    COUNT(*) AS filtered_count,
    SUM(CASE WHEN is_delayed = 1 THEN 1 ELSE 0 END) AS delayed_count,
    SUM(CASE WHEN delay_status = 'on_time' THEN 1 ELSE 0 END) AS on_time_count,
    SUM(CASE WHEN delay_status = 'moderate_delay' THEN 1 ELSE 0 END) AS moderate_delay_count,
    SUM(CASE WHEN delay_status = 'severe_delay' THEN 1 ELSE 0 END) AS severe_delay_count,
    AVG(delay_minutes) AS avg_delay_minutes,
    AVG(distance) AS avg_distance,
    AVG(crs_elapsed_time) AS avg_elapsed_time,
    MAX(ingested_at) AS latest_ingested_at
FROM ingested_flights
WHERE (:origin IS NULL OR origin = :origin)
  AND (:dest IS NULL OR dest = :dest)
  AND (:carrier IS NULL OR op_unique_carrier = :carrier)
  AND (:status IS NULL OR delay_status = :status)
  AND (
      :search IS NULL
      OR UPPER(flight_code) LIKE :search
      OR UPPER(origin) LIKE :search
      OR UPPER(dest) LIKE :search
      OR UPPER(COALESCE(tail_num, '')) LIKE :search
      OR UPPER(COALESCE(carrier_name, '')) LIKE :search
  )
"""

PG_CARRIER_STATS_SQL = """
SELECT
    op_unique_carrier AS code,
    AVG(delay_minutes) AS avg_delay,
    COUNT(*) AS flight_count
FROM ingested_flights
WHERE (%(origin)s::text IS NULL OR origin = %(origin)s)
  AND (%(dest)s::text IS NULL OR dest = %(dest)s)
  AND (%(carrier)s::text IS NULL OR op_unique_carrier = %(carrier)s)
  AND (%(status)s::text IS NULL OR delay_status = %(status)s)
  AND (
      %(search)s::text IS NULL
      OR UPPER(flight_code) LIKE %(search)s
      OR UPPER(origin) LIKE %(search)s
      OR UPPER(dest) LIKE %(search)s
      OR UPPER(COALESCE(tail_num, '')) LIKE %(search)s
      OR UPPER(COALESCE(carrier_name, '')) LIKE %(search)s
  )
GROUP BY op_unique_carrier
ORDER BY flight_count DESC, op_unique_carrier ASC
LIMIT 8
"""

SQLITE_CARRIER_STATS_SQL = """
SELECT
    op_unique_carrier AS code,
    AVG(delay_minutes) AS avg_delay,
    COUNT(*) AS flight_count
FROM ingested_flights
WHERE (:origin IS NULL OR origin = :origin)
  AND (:dest IS NULL OR dest = :dest)
  AND (:carrier IS NULL OR op_unique_carrier = :carrier)
  AND (:status IS NULL OR delay_status = :status)
  AND (
      :search IS NULL
      OR UPPER(flight_code) LIKE :search
      OR UPPER(origin) LIKE :search
      OR UPPER(dest) LIKE :search
      OR UPPER(COALESCE(tail_num, '')) LIKE :search
      OR UPPER(COALESCE(carrier_name, '')) LIKE :search
  )
GROUP BY op_unique_carrier
ORDER BY flight_count DESC, op_unique_carrier ASC
LIMIT 8
"""

PG_ITEMS_SQL_BY_SORT: dict[str, str] = {
    "time": """
        SELECT * FROM ingested_flights
        WHERE (%(origin)s::text IS NULL OR origin = %(origin)s)
          AND (%(dest)s::text IS NULL OR dest = %(dest)s)
          AND (%(carrier)s::text IS NULL OR op_unique_carrier = %(carrier)s)
          AND (%(status)s::text IS NULL OR delay_status = %(status)s)
          AND (
              %(search)s::text IS NULL
              OR UPPER(flight_code) LIKE %(search)s
              OR UPPER(origin) LIKE %(search)s
              OR UPPER(dest) LIKE %(search)s
              OR UPPER(COALESCE(tail_num, '')) LIKE %(search)s
              OR UPPER(COALESCE(carrier_name, '')) LIKE %(search)s
          )
        ORDER BY crs_dep_time ASC, ingested_at DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """,
    "delay": """
        SELECT * FROM ingested_flights
        WHERE (%(origin)s::text IS NULL OR origin = %(origin)s)
          AND (%(dest)s::text IS NULL OR dest = %(dest)s)
          AND (%(carrier)s::text IS NULL OR op_unique_carrier = %(carrier)s)
          AND (%(status)s::text IS NULL OR delay_status = %(status)s)
          AND (
              %(search)s::text IS NULL
              OR UPPER(flight_code) LIKE %(search)s
              OR UPPER(origin) LIKE %(search)s
              OR UPPER(dest) LIKE %(search)s
              OR UPPER(COALESCE(tail_num, '')) LIKE %(search)s
              OR UPPER(COALESCE(carrier_name, '')) LIKE %(search)s
          )
        ORDER BY delay_minutes DESC, crs_dep_time ASC
        LIMIT %(limit)s OFFSET %(offset)s
    """,
    "distance": """
        SELECT * FROM ingested_flights
        WHERE (%(origin)s::text IS NULL OR origin = %(origin)s)
          AND (%(dest)s::text IS NULL OR dest = %(dest)s)
          AND (%(carrier)s::text IS NULL OR op_unique_carrier = %(carrier)s)
          AND (%(status)s::text IS NULL OR delay_status = %(status)s)
          AND (
              %(search)s::text IS NULL
              OR UPPER(flight_code) LIKE %(search)s
              OR UPPER(origin) LIKE %(search)s
              OR UPPER(dest) LIKE %(search)s
              OR UPPER(COALESCE(tail_num, '')) LIKE %(search)s
              OR UPPER(COALESCE(carrier_name, '')) LIKE %(search)s
          )
        ORDER BY distance DESC, crs_dep_time ASC
        LIMIT %(limit)s OFFSET %(offset)s
    """,
}

SQLITE_ITEMS_SQL_BY_SORT: dict[str, str] = {
    "time": """
        SELECT * FROM ingested_flights
        WHERE (:origin IS NULL OR origin = :origin)
          AND (:dest IS NULL OR dest = :dest)
          AND (:carrier IS NULL OR op_unique_carrier = :carrier)
          AND (:status IS NULL OR delay_status = :status)
          AND (
              :search IS NULL
              OR UPPER(flight_code) LIKE :search
              OR UPPER(origin) LIKE :search
              OR UPPER(dest) LIKE :search
              OR UPPER(COALESCE(tail_num, '')) LIKE :search
              OR UPPER(COALESCE(carrier_name, '')) LIKE :search
          )
        ORDER BY crs_dep_time ASC, ingested_at DESC
        LIMIT :limit OFFSET :offset
    """,
    "delay": """
        SELECT * FROM ingested_flights
        WHERE (:origin IS NULL OR origin = :origin)
          AND (:dest IS NULL OR dest = :dest)
          AND (:carrier IS NULL OR op_unique_carrier = :carrier)
          AND (:status IS NULL OR delay_status = :status)
          AND (
              :search IS NULL
              OR UPPER(flight_code) LIKE :search
              OR UPPER(origin) LIKE :search
              OR UPPER(dest) LIKE :search
              OR UPPER(COALESCE(tail_num, '')) LIKE :search
              OR UPPER(COALESCE(carrier_name, '')) LIKE :search
          )
        ORDER BY delay_minutes DESC, crs_dep_time ASC
        LIMIT :limit OFFSET :offset
    """,
    "distance": """
        SELECT * FROM ingested_flights
        WHERE (:origin IS NULL OR origin = :origin)
          AND (:dest IS NULL OR dest = :dest)
          AND (:carrier IS NULL OR op_unique_carrier = :carrier)
          AND (:status IS NULL OR delay_status = :status)
          AND (
              :search IS NULL
              OR UPPER(flight_code) LIKE :search
              OR UPPER(origin) LIKE :search
              OR UPPER(dest) LIKE :search
              OR UPPER(COALESCE(tail_num, '')) LIKE :search
              OR UPPER(COALESCE(carrier_name, '')) LIKE :search
          )
        ORDER BY distance DESC, crs_dep_time ASC
        LIMIT :limit OFFSET :offset
    """,
}

TOTAL_SQL = "SELECT COUNT(*) AS total_stored FROM ingested_flights"
LAST_BATCH_SQL = "SELECT * FROM ingestion_batches ORDER BY created_at DESC LIMIT 1"
SQLITE_FACETS_SQL = """
SELECT
    (SELECT GROUP_CONCAT(DISTINCT origin) FROM ingested_flights) AS origins,
    (SELECT GROUP_CONCAT(DISTINCT dest) FROM ingested_flights) AS dests,
    (SELECT GROUP_CONCAT(DISTINCT op_unique_carrier) FROM ingested_flights) AS carriers
"""


class FlightRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.is_postgres = database_url.startswith(("postgresql://", "postgres://"))
        self.storage_type = "postgresql" if self.is_postgres else "sqlite"
        self.has_schedule = False
        if not self.is_postgres:
            raw_path = database_url.replace("sqlite:///", "")
            self.sqlite_path = Path(raw_path).resolve()
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _connect_sqlite(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.sqlite_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _connect_postgres(self):
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def init_db(self) -> None:
        if self.is_postgres:
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute(SCHEMA_SQL)
                    cur.execute("SELECT to_regclass('flight_data.simulator_offsets') IS NOT NULL AS enabled")
                    self.has_schedule = cur.fetchone()["enabled"]
                conn.commit()
        else:
            with self._connect_sqlite() as conn:
                conn.executescript(SCHEMA_SQL)
                conn.commit()

    def simulator_offset(self, source: str) -> int:
        with self._connect_postgres() as conn, conn.cursor() as cur:
            cur.execute("SELECT next_start FROM flight_data.simulator_offsets WHERE source_url = %s", (source,))
            row = cur.fetchone()
            return row["next_start"] if row else 0

    def insert_batch(
        self,
        records: list[dict[str, Any]],
        batch_meta: dict[str, Any],
        scheduled: tuple[Flight, ...] = (),
        replay: ReplayPosition | None = None,
    ) -> dict[str, int]:
        """
        Insert normalized flight records in a single batch using executemany
        with deduplication on flight_key.
        """
        received = len(records)
        inserted = 0
        param_rows = [tuple(r.get(c) for c in INGESTED_FLIGHT_COLS) for r in records]

        if self.is_postgres:
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    if replay is not None:
                        cur.execute("""
                            INSERT INTO flight_data.simulator_offsets (source_url, next_start) VALUES (%s, 0)
                            ON CONFLICT (source_url) DO NOTHING
                        """, (replay.source,))
                        cur.execute("""
                            SELECT next_start FROM flight_data.simulator_offsets WHERE source_url = %s FOR UPDATE
                        """, (replay.source,))
                        if cur.fetchone()["next_start"] != replay.start:
                            raise RuntimeError("Another ingestion run advanced the simulator offset")
                    if scheduled:
                        save_flights_batch(cur, scheduled)
                    if param_rows:
                        cur.executemany(PG_INSERT_INGESTED_FLIGHT_SQL, param_rows)
                        inserted = cur.rowcount
                    cur.execute("SELECT COUNT(*) AS cnt FROM ingested_flights")
                    total_stored = int(cur.fetchone()["cnt"])
                    cur.execute(
                        """
                        INSERT INTO ingestion_batches (
                            batch_id, source, fetched_at, window_start, window_end,
                            received_count, inserted_count, duplicate_count, total_stored, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            batch_meta["batch_id"],
                            batch_meta["source"],
                            batch_meta["fetched_at"],
                            batch_meta.get("window_start"),
                            batch_meta.get("window_end"),
                            received,
                            inserted,
                            max(0, received - inserted),
                            total_stored,
                            batch_meta["created_at"],
                        ),
                    )
                    if replay is not None:
                        cur.execute("""
                            UPDATE flight_data.simulator_offsets SET next_start = %s, updated_at = statement_timestamp()
                            WHERE source_url = %s
                        """, (replay.next_start, replay.source))
                conn.commit()
        else:
            with self._connect_sqlite() as conn:
                cur = conn.cursor()
                if param_rows:
                    cur.executemany(SQLITE_INSERT_INGESTED_FLIGHT_SQL, param_rows)
                    inserted = cur.rowcount
                cur.execute("SELECT COUNT(*) AS cnt FROM ingested_flights")
                total_stored = int(cur.fetchone()["cnt"])
                cur.execute(
                    """
                    INSERT INTO ingestion_batches (
                        batch_id, source, fetched_at, window_start, window_end,
                        received_count, inserted_count, duplicate_count, total_stored, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        batch_meta["batch_id"],
                        batch_meta["source"],
                        batch_meta["fetched_at"],
                        batch_meta.get("window_start"),
                        batch_meta.get("window_end"),
                        received,
                        inserted,
                        max(0, received - inserted),
                        total_stored,
                        batch_meta["created_at"],
                    ),
                )
                conn.commit()

        duplicates = max(0, received - inserted)
        return {
            "received_count": received,
            "inserted_count": inserted,
            "duplicate_count": duplicates,
            "total_stored": total_stored,
        }

    def query_flights(
        self,
        origin: str | None = None,
        dest: str | None = None,
        carrier: str | None = None,
        status: str | None = None,
        search: str | None = None,
        sort: str | None = "time",
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Query flights from DB with parameterized filters, whitelist sorting, pagination, and KPIs."""
        filter_params: dict[str, Any] = {
            "origin": origin.strip().upper() if (origin and origin.strip().lower() != "all") else None,
            "dest": dest.strip().upper() if (dest and dest.strip().lower() != "all") else None,
            "carrier": carrier.strip().upper() if (carrier and carrier.strip().lower() != "all") else None,
            "status": status.strip() if (status and status.strip().lower() != "all") else None,
            "search": f"%{search.strip().upper()}%" if (search and search.strip()) else None,
        }

        requested_sort = (sort or "time").strip().lower()
        sort_key = requested_sort if requested_sort in PG_ITEMS_SQL_BY_SORT else "time"
        items_params = {**filter_params, "limit": int(limit), "offset": int(offset)}

        if self.is_postgres:
            items_sql = PG_ITEMS_SQL_BY_SORT[sort_key]
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute(TOTAL_SQL)
                    total_stored = int(cur.fetchone()["total_stored"])
                    cur.execute(PG_STATS_SQL, filter_params)
                    stats_row = dict(cur.fetchone() or {})
                    cur.execute(PG_CARRIER_STATS_SQL, filter_params)
                    carrier_rows = [dict(r) for r in cur.fetchall()]
                    cur.execute(items_sql, items_params)
                    items = [dict(r) for r in cur.fetchall()]
                    cur.execute(LAST_BATCH_SQL)
                    last_batch = cur.fetchone()
                    last_batch_dict = dict(last_batch) if last_batch else None
                    cur.execute("SELECT DISTINCT origin FROM ingested_flights ORDER BY origin")
                    origins = [r["origin"] for r in cur.fetchall() if r["origin"]]
                    cur.execute("SELECT DISTINCT dest FROM ingested_flights ORDER BY dest")
                    dests = [r["dest"] for r in cur.fetchall() if r["dest"]]
                    cur.execute("SELECT DISTINCT op_unique_carrier FROM ingested_flights ORDER BY op_unique_carrier")
                    carriers = [r["op_unique_carrier"] for r in cur.fetchall() if r["op_unique_carrier"]]
        else:
            items_sql = SQLITE_ITEMS_SQL_BY_SORT[sort_key]
            with self._connect_sqlite() as conn:
                cur = conn.cursor()
                cur.execute(TOTAL_SQL)
                total_stored = int(cur.fetchone()["total_stored"])
                cur.execute(SQLITE_STATS_SQL, filter_params)
                stats_row = dict(cur.fetchone() or {})
                cur.execute(SQLITE_CARRIER_STATS_SQL, filter_params)
                carrier_rows = [dict(r) for r in cur.fetchall()]
                cur.execute(items_sql, items_params)
                items = [dict(r) for r in cur.fetchall()]
                cur.execute(LAST_BATCH_SQL)
                last_batch = cur.fetchone()
                last_batch_dict = dict(last_batch) if last_batch else None
                cur.execute(SQLITE_FACETS_SQL)
                facet_row = dict(cur.fetchone() or {})
                origins = sorted((facet_row.get("origins") or "").split(",")) if facet_row.get("origins") else []
                dests = sorted((facet_row.get("dests") or "").split(",")) if facet_row.get("dests") else []
                carriers = sorted((facet_row.get("carriers") or "").split(",")) if facet_row.get("carriers") else []

        filtered_count = int(stats_row.get("filtered_count") or 0)
        delayed_count = int(stats_row.get("delayed_count") or 0)
        delay_rate_pct = round((delayed_count / filtered_count * 100.0), 1) if filtered_count > 0 else 0.0
        latest_ingested_at_str = stats_row.get("latest_ingested_at")
        updated_at = None
        if latest_ingested_at_str:
            try:
                updated_at = datetime.fromisoformat(latest_ingested_at_str.replace("Z", "+00:00"))
            except ValueError:
                updated_at = datetime.now(timezone.utc)

        metadata = {
            "total_stored": total_stored,
            "filtered_count": filtered_count,
            "returned_count": len(items),
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(items) < filtered_count,
            "sort": sort_key,
            "delayed_count": delayed_count,
            "on_time_count": int(stats_row.get("on_time_count") or 0),
            "moderate_delay_count": int(stats_row.get("moderate_delay_count") or 0),
            "severe_delay_count": int(stats_row.get("severe_delay_count") or 0),
            "delay_rate_pct": delay_rate_pct,
            "avg_delay_minutes": round(float(stats_row.get("avg_delay_minutes") or 0.0), 1),
            "avg_distance": round(float(stats_row.get("avg_distance") or 0.0), 1),
            "avg_elapsed_time": round(float(stats_row.get("avg_elapsed_time") or 0.0), 1),
            "carrier_delays": [
                {
                    "code": r["code"],
                    "avg_delay": round(float(r.get("avg_delay") or 0.0), 1),
                    "flight_count": int(r.get("flight_count") or 0),
                }
                for r in carrier_rows
            ],
            "last_batch": last_batch_dict,
            "available_filters": {
                "origins": origins,
                "destinations": dests,
                "carriers": carriers,
            },
        }

        return {
            "ready": total_stored > 0,
            "updated_at": updated_at,
            "items": items,
            "metadata": metadata,
        }

    def clear_all(self) -> int:
        """Delete all ingested flights and batch logs (useful for Demo reset)."""
        if self.is_postgres:
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM ingested_flights")
                    deleted = cur.rowcount
                    cur.execute("DELETE FROM ingestion_batches")
                conn.commit()
        else:
            with self._connect_sqlite() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM ingested_flights")
                deleted = cur.rowcount
                cur.execute("DELETE FROM ingestion_batches")
                conn.commit()
        return deleted
