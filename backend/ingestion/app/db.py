"""
Database layer for Flight Ingestion Service.
Supports both PostgreSQL (via psycopg) and SQLite (via sqlite3).
- Uses batch execution (`executemany`) instead of row-by-row network round-trips.
- Uses static SQL constants and parameterized named bindings (`%(param)s` / `:param`)
  with a strict whitelist dictionary for `ORDER BY` — zero dynamic SQL string interpolation.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
import json
from pathlib import Path
import sqlite3
from typing import Any

from app.schedule import Flight, ReplayPosition, save_flights_batch
from app.live_store import LiveStore

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
    delay_minutes REAL,
    delay_status TEXT NOT NULL,
    is_delayed INTEGER,
    fetched_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    raw_response_id TEXT,
    raw_row_index INTEGER
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
    "fetched_at", "ingested_at", "raw_response_id", "raw_row_index",
)

PG_INSERT_INGESTED_FLIGHT_SQL = """
INSERT INTO ingested_flights (
    flight_key, fl_date, day_of_week, op_unique_carrier, carrier_name,
    tail_num, op_carrier_fl_num, flight_code, origin_airport_id, origin,
    dest_airport_id, dest, route, crs_dep_time, crs_arr_time, dep_hour,
    crs_elapsed_time, distance, delay_minutes, delay_status, is_delayed,
    fetched_at, ingested_at, raw_response_id, raw_row_index
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s
)
ON CONFLICT (flight_key) DO UPDATE SET
    crs_arr_time=EXCLUDED.crs_arr_time, crs_elapsed_time=EXCLUDED.crs_elapsed_time,
    distance=EXCLUDED.distance, delay_minutes=EXCLUDED.delay_minutes,
    delay_status=EXCLUDED.delay_status, is_delayed=EXCLUDED.is_delayed,
    tail_num=COALESCE(EXCLUDED.tail_num, ingested_flights.tail_num),
    fetched_at=EXCLUDED.fetched_at, ingested_at=EXCLUDED.ingested_at,
    raw_response_id=EXCLUDED.raw_response_id, raw_row_index=EXCLUDED.raw_row_index
"""

SQLITE_INSERT_INGESTED_FLIGHT_SQL = """
INSERT INTO ingested_flights (
    flight_key, fl_date, day_of_week, op_unique_carrier, carrier_name,
    tail_num, op_carrier_fl_num, flight_code, origin_airport_id, origin,
    dest_airport_id, dest, route, crs_dep_time, crs_arr_time, dep_hour,
    crs_elapsed_time, distance, delay_minutes, delay_status, is_delayed,
    fetched_at, ingested_at, raw_response_id, raw_row_index
) VALUES (
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?
)
ON CONFLICT (flight_key) DO UPDATE SET
    crs_arr_time=excluded.crs_arr_time, crs_elapsed_time=excluded.crs_elapsed_time,
    distance=excluded.distance, delay_minutes=excluded.delay_minutes,
    delay_status=excluded.delay_status, is_delayed=excluded.is_delayed,
    tail_num=COALESCE(excluded.tail_num, ingested_flights.tail_num),
    fetched_at=excluded.fetched_at, ingested_at=excluded.ingested_at,
    raw_response_id=excluded.raw_response_id, raw_row_index=excluded.raw_row_index
"""

STATS_SELECT = """
SELECT
    COUNT(*) AS filtered_count,
    COUNT(delay_minutes) AS known_delay_count,
    SUM(CASE WHEN is_delayed = 1 THEN 1 ELSE 0 END) AS delayed_count,
    SUM(CASE WHEN delay_status = 'on_time' THEN 1 ELSE 0 END) AS on_time_count,
    SUM(CASE WHEN delay_status = 'moderate_delay' THEN 1 ELSE 0 END) AS moderate_delay_count,
    SUM(CASE WHEN delay_status = 'severe_delay' THEN 1 ELSE 0 END) AS severe_delay_count,
    AVG(delay_minutes) AS avg_delay_minutes,
    AVG(distance) AS avg_distance,
    AVG(crs_elapsed_time) AS avg_elapsed_time,
    MAX(ingested_at) AS latest_ingested_at,
    MIN(fl_date) AS first_flight_date,
    MAX(fl_date) AS last_flight_date
"""

FLIGHT_SORTS = {
    "time": "fl_date DESC, crs_dep_time ASC, ingested_at DESC",
    "delay": "delay_minutes DESC NULLS LAST, fl_date DESC, crs_dep_time ASC",
    "distance": "distance DESC NULLS LAST, fl_date DESC, crs_dep_time ASC",
}

FLIGHT_SCOPE = """
FROM ingested_flights AS f
LEFT JOIN live_flight_details AS live ON live.flight_key = f.flight_key
"""

ROUTE_CLUSTER_FILTER = """
EXISTS (
    SELECT 1 FROM cluster_assignments AS a
    WHERE a.run_id = (SELECT run_id FROM clustering_runs ORDER BY created_at DESC, run_id DESC LIMIT 1)
      AND a.entity_type = 'route' AND a.cluster_id = ?
      AND a.entity_code = f.origin || ' → ' || f.dest
)
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
        LiveStore(self).migrate()

    def airport_identity(self, code):
        with self._connect_postgres() as conn:
            row = conn.execute("SELECT airport_id, airport_seq_id, city_market_id FROM flight_data.airport_versions WHERE airport_code=%s ORDER BY airport_seq_id DESC LIMIT 1", (code,)).fetchone()
            return dict(row) if row else None

    def raw_live_flights(self, offset, limit):
        store = LiveStore(self)
        with store.connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM live_flight_details").fetchone()["n"]
            rows = conn.execute(store.sql("SELECT flight_key,payload FROM live_flight_details ORDER BY flight_key LIMIT ? OFFSET ?"), (limit, offset)).fetchall()
        data = []
        for index, row in enumerate(rows):
            raw = json.loads(row["payload"])["raw"]
            data.append({
                "RAW_ID": row["flight_key"], "ROW_NUMBER": offset+index+1,
                "FL_DATE": str(raw.get("dep_time", ""))[:10],
                "OP_UNIQUE_CARRIER": raw.get("airline_iata"), "OP_CARRIER_FL_NUM": raw.get("flight_number"),
                "ORIGIN": raw.get("dep_iata"), "DEST": raw.get("arr_iata"),
                "CRS_DEP_TIME": raw.get("dep_time"), "CRS_ARR_TIME": raw.get("arr_time"),
                "TAIL_NUM": raw.get("reg_number"), "raw": raw,
            })
        return {"source": "airlabs", "total": total, "data": data, "window_start": offset, "window_end": offset+len(data)}

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
                    cur.execute("SELECT to_regclass('flight_data.flights') IS NOT NULL AS enabled")
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
        updated = 0
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
                        for record in records:
                            cur.execute("SELECT 1 FROM ingested_flights WHERE flight_key=%s", (record["flight_key"],))
                            updated += int(cur.fetchone() is not None)
                        cur.executemany(PG_INSERT_INGESTED_FLIGHT_SQL, param_rows)
                        inserted = received - updated
                    for record in records:
                        if record.get("_details"):
                            cur.execute("INSERT INTO live_flight_details VALUES (%s, %s) ON CONFLICT(flight_key) DO UPDATE SET payload=excluded.payload", (record["flight_key"], json.dumps(record["_details"])))
                    cur.execute("SELECT COUNT(*) AS cnt FROM ingested_flights")
                    total_stored = int(cur.fetchone()["cnt"])
                    cur.execute(
                        """
                        INSERT INTO ingestion_batches (
                            batch_id, source, fetched_at, window_start, window_end,
                            received_count, inserted_count, duplicate_count, total_stored, created_at, updated_count
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            batch_meta["batch_id"],
                            batch_meta["source"],
                            batch_meta["fetched_at"],
                            batch_meta.get("window_start"),
                            batch_meta.get("window_end"),
                            received,
                            inserted,
                            0,
                            total_stored,
                            batch_meta["created_at"],
                            updated,
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
                    for record in records:
                        cur.execute("SELECT 1 FROM ingested_flights WHERE flight_key=?", (record["flight_key"],))
                        updated += int(cur.fetchone() is not None)
                    cur.executemany(SQLITE_INSERT_INGESTED_FLIGHT_SQL, param_rows)
                    inserted = received - updated
                for record in records:
                    if record.get("_details"):
                        cur.execute("INSERT INTO live_flight_details VALUES (?, ?) ON CONFLICT(flight_key) DO UPDATE SET payload=excluded.payload", (record["flight_key"], json.dumps(record["_details"])))
                cur.execute("SELECT COUNT(*) AS cnt FROM ingested_flights")
                total_stored = int(cur.fetchone()["cnt"])
                cur.execute(
                    """
                    INSERT INTO ingestion_batches (
                        batch_id, source, fetched_at, window_start, window_end,
                        received_count, inserted_count, duplicate_count, total_stored, created_at, updated_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        batch_meta["batch_id"],
                        batch_meta["source"],
                        batch_meta["fetched_at"],
                        batch_meta.get("window_start"),
                        batch_meta.get("window_end"),
                        received,
                        inserted,
                        0,
                        total_stored,
                        batch_meta["created_at"],
                        updated,
                    ),
                )
                conn.commit()

        duplicates = 0
        return {
            "received_count": received,
            "inserted_count": inserted,
            "updated_count": updated,
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
        source: str = "all",
        cluster_id: int | None = None,
        include_overview: bool = False,
        hourly_days: int = 1,
    ) -> dict[str, Any]:
        """Query flights from DB with parameterized filters, whitelist sorting, pagination, and KPIs."""
        conditions = []
        params = []
        for column, value in (("origin", origin), ("dest", dest), ("op_unique_carrier", carrier), ("delay_status", status)):
            if value and value.strip() and value.strip().lower() != "all":
                conditions.append(f"f.{column} = ?")
                params.append(value.strip() if column == "delay_status" else value.strip().upper())
        if search and search.strip():
            conditions.append("""(
                UPPER(f.flight_code) LIKE ? OR UPPER(f.origin) LIKE ? OR UPPER(f.dest) LIKE ?
                OR UPPER(COALESCE(f.tail_num, '')) LIKE ? OR UPPER(COALESCE(f.carrier_name, '')) LIKE ?
            )""")
            params.extend([f"%{search.strip().upper()}%"] * 5)

        scope_where = ""
        if source == "airlabs":
            scope_where = " WHERE live.flight_key IS NOT NULL"
        elif source == "legacy":
            scope_where = " WHERE live.flight_key IS NULL"

        requested_sort = (sort or "time").strip().lower()
        sort_key = requested_sort if requested_sort in FLIGHT_SORTS else "time"
        store = LiveStore(self)
        with store.connect() as conn:
            if self.is_postgres:
                conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            if cluster_id is not None:
                tables_present = self.is_postgres or conn.execute(
                    "SELECT COUNT(*) AS n FROM sqlite_master WHERE type='table' "
                    "AND name IN ('cluster_assignments', 'clustering_runs')"
                ).fetchone()["n"] == 2
                conditions.append(ROUTE_CLUSTER_FILTER if tables_present else "1 = 0")
                if tables_present:
                    params.append(cluster_id)
            filtered = FLIGHT_SCOPE + scope_where
            if conditions:
                filtered += (" AND " if scope_where else " WHERE ") + " AND ".join(conditions)
            total_stored = conn.execute(
                "SELECT COUNT(*) AS total_stored " + FLIGHT_SCOPE + scope_where
            ).fetchone()["total_stored"]
            stats_row = dict(conn.execute(store.sql(STATS_SELECT + filtered), params).fetchone())
            carrier_limit = "" if include_overview else " LIMIT 8"
            carrier_rows = conn.execute(store.sql("""
                SELECT f.op_unique_carrier AS code, MAX(f.carrier_name) AS name,
                       AVG(f.delay_minutes) AS avg_delay, COUNT(*) AS flight_count,
                       COUNT(f.delay_minutes) AS known_count,
                       SUM(CASE WHEN f.is_delayed = 1 THEN 1 ELSE 0 END) AS delayed_count
            """ + filtered + """
                GROUP BY f.op_unique_carrier ORDER BY flight_count DESC, code
            """ + carrier_limit), params).fetchall()
            items = [dict(row) for row in conn.execute(store.sql(
                "SELECT f.*, live.payload AS live_payload " + filtered
                + f" ORDER BY {FLIGHT_SORTS[sort_key]}, f.flight_key LIMIT ? OFFSET ?"
            ), [*params, limit, offset]).fetchall()]
            airport_keys = sorted({f"airport:{item[side]}" for item in items for side in ("origin", "dest")})
            coordinates = {}
            if airport_keys:
                placeholders = ", ".join("?" for _ in airport_keys)
                for row in conn.execute(store.sql(
                    f"SELECT cache_key, payload FROM provider_cache WHERE cache_key IN ({placeholders})"
                ), airport_keys):
                    airport = json.loads(row["payload"])
                    try:
                        lat, lon = float(airport["lat"]), float(airport["lng"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                        code = row["cache_key"].removeprefix("airport:")
                        coordinates[code] = {
                            "lat": lat, "lon": lon,
                            "name": str(airport.get("name") or code),
                            "city": str(airport.get("city") or code),
                        }
            last_batch = conn.execute("SELECT * FROM ingestion_batches ORDER BY created_at DESC LIMIT 1").fetchone()
            last_batch_dict = dict(last_batch) if last_batch else None
            facets = [
                [row["code"] for row in conn.execute(
                    f"SELECT DISTINCT f.{column} AS code " + FLIGHT_SCOPE + scope_where + " ORDER BY code"
                ).fetchall() if row["code"]]
                for column in ("origin", "dest", "op_unique_carrier")
            ]
            origins, dests, carriers = facets
            hourly = []
            hourly_date_from = None
            airports = []
            if include_overview:
                join = " AND " if " WHERE " in filtered else " WHERE "
                if stats_row["last_flight_date"]:
                    last_day = date.fromisoformat(stats_row["last_flight_date"])
                    first_day = date.fromisoformat(stats_row["first_flight_date"])
                    hourly_date_from = max(first_day, last_day - timedelta(days=hourly_days - 1)).isoformat()
                    hourly = [dict(row) for row in conn.execute(store.sql("""
                        SELECT f.dep_hour AS hour, COUNT(*) AS flights, COUNT(f.delay_minutes) AS known,
                               SUM(CASE WHEN f.is_delayed = 1 THEN 1 ELSE 0 END) AS delayed
                    """ + filtered + join + """
                        f.fl_date BETWEEN ? AND ? AND f.dep_hour BETWEEN 0 AND 23
                        GROUP BY f.dep_hour ORDER BY f.dep_hour
                    """), [*params, hourly_date_from, last_day.isoformat()]).fetchall()]
                airports = [dict(row) for row in conn.execute(store.sql("""
                    SELECT f.origin AS code, COUNT(*) AS flight_count, COUNT(f.delay_minutes) AS known_count,
                           AVG(f.delay_minutes) AS avg_delay,
                           SUM(CASE WHEN f.is_delayed = 1 THEN 1 ELSE 0 END) AS delayed_count
                """ + filtered + " GROUP BY f.origin ORDER BY flight_count DESC, code"), params).fetchall()]

        for item in items:
            item["origin_coordinate"] = coordinates.get(item["origin"])
            item["dest_coordinate"] = coordinates.get(item["dest"])
            payload = item.pop("live_payload")
            if payload is not None:
                info = json.loads(payload)
                item.update({key: info.get(key) for key in ("source", "flight_status", "delay_kind", "distance_source", "scheduled_dep_utc")})
            else:
                item["source"] = "legacy"
        provider_status, _ = store.cached("ingestion_status")
        filtered_count = int(stats_row.get("filtered_count") or 0)
        delayed_count = int(stats_row.get("delayed_count") or 0)
        known_delay_count = int(stats_row.get("known_delay_count") or 0)
        delay_rate_pct = round(delayed_count / known_delay_count * 100.0, 1) if known_delay_count else 0.0
        latest_ingested_at_str = stats_row.get("latest_ingested_at")
        updated_at = None
        if latest_ingested_at_str:
            try:
                updated_at = datetime.fromisoformat(latest_ingested_at_str.replace("Z", "+00:00"))
            except ValueError:
                updated_at = datetime.now(timezone.utc)

        metadata = {
            "first_flight_date": stats_row.get("first_flight_date"),
            "last_flight_date": stats_row.get("last_flight_date"),
            "total_stored": total_stored,
            "filtered_count": filtered_count,
            "returned_count": len(items),
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(items) < filtered_count,
            "sort": sort_key,
            "delayed_count": delayed_count,
            "known_delay_count": known_delay_count,
            "unknown_delay_count": filtered_count - known_delay_count,
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
                    "avg_delay": round(float(r["avg_delay"] or 0.0), 1),
                    "flight_count": int(r["flight_count"] or 0),
                }
                for r in carrier_rows[:8]
            ],
            "source": source,
            "hourly": hourly,
            "hourly_date_from": hourly_date_from,
            "airport_stats": airports,
            "carrier_stats": [dict(row) for row in carrier_rows] if include_overview else [],
            "last_batch": last_batch_dict,
            "provider_status": provider_status,
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
                    cur.execute("DELETE FROM live_flight_details")
                conn.commit()
        else:
            with self._connect_sqlite() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM ingested_flights")
                deleted = cur.rowcount
                cur.execute("DELETE FROM ingestion_batches")
                cur.execute("DELETE FROM live_flight_details")
                conn.commit()
        return deleted
