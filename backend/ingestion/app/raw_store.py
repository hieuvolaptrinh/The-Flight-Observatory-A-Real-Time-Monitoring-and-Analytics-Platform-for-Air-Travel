"""Archive provider responses in a separate database before any normalization."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4


RAW_SCHEMA = (Path(__file__).resolve().parents[1] / "db" / "raw_schema.sql").read_text(encoding="utf-8")


def raw_database_url(processed_url: str, configured_url: str = "") -> str:
    if configured_url:
        return configured_url
    if processed_url.startswith(("postgresql://", "postgres://")):
        from psycopg.conninfo import make_conninfo
        return make_conninfo(processed_url, dbname="flight_raw_db")
    path = Path(processed_url.removeprefix("sqlite:///"))
    return "sqlite:///" + str(path.with_name(path.stem + "_raw" + path.suffix))


class RawStore:
    def __init__(self, processed_url: str, configured_url: str = ""):
        self.database_url = raw_database_url(processed_url, configured_url)
        self.pg = not self.database_url.startswith("sqlite:///")
        if self.pg:
            from psycopg.conninfo import conninfo_to_dict
            self.database_name = conninfo_to_dict(self.database_url).get("dbname", "flight_raw_db")
            # Comparing database names alone is insufficient across different hosts.
            processed = conninfo_to_dict(processed_url)
            raw = conninfo_to_dict(self.database_url)
            import os
            keys = (("host", "PGHOST", "localhost"), ("port", "PGPORT", "5432"), ("dbname", "PGDATABASE", ""))
            if all(raw.get(k, os.getenv(env, default)) == processed.get(k, os.getenv(env, default)) for k, env, default in keys):
                raise ValueError("RAW_DATABASE_URL must point to a different database from DATABASE_URL")
        else:
            self.path = Path(self.database_url.removeprefix("sqlite:///")).resolve()
            if self.path == Path(processed_url.removeprefix("sqlite:///")).resolve():
                raise ValueError("Raw and processed SQLite files must be different")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.database_name = self.path.name
        with self.connect() as conn:
            if self.pg:
                conn.execute(RAW_SCHEMA)
            else:
                conn.executescript(RAW_SCHEMA.replace("BIGSERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT"))
            conn.commit()

    def connect(self):
        if self.pg:
            import psycopg
            from psycopg.rows import dict_row
            return psycopg.connect(self.database_url, row_factory=dict_row)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def sql(self, statement):
        return statement.replace("?", "%s") if self.pg else statement

    def archive(self, provider, endpoint, params, payload, http_status=200, *, credential="", archive_kind="api", response_id=None, fetched_at=None):
        """Commit raw first; an archive failure prevents downstream processing."""
        response_id = response_id or str(uuid4())
        fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
        def redact(value):
            if isinstance(value, dict):
                return {k: redact(v) for k, v in value.items() if k.lower() not in {"api_key", "appid", "authorization", "password", "access_token"}}
            if isinstance(value, list):
                return [redact(v) for v in value]
            if credential and isinstance(value, str):
                return value.replace(credential, "[redacted]")
            return value
        params, payload = redact(params), redact(payload)
        with self.connect() as conn:
            inserted = conn.execute(self.sql("""INSERT INTO raw_api_responses
                (response_id,provider,endpoint,request_params,fetched_at,http_status,payload_json,archive_kind)
                VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(response_id) DO NOTHING RETURNING response_id"""),
                (response_id, provider, endpoint, json.dumps(params), fetched_at, http_status, json.dumps(payload), archive_kind)).fetchone()
            if inserted and provider == "airlabs" and endpoint.endswith("/schedules") and isinstance(payload, dict):
                for index, raw in enumerate(payload.get("response", []) if isinstance(payload.get("response"), list) else []):
                    values = raw if isinstance(raw, dict) else {}
                    conn.execute(self.sql("""INSERT INTO raw_flights
                        (response_id,row_index,airline_iata,flight_number,dep_iata,arr_iata,dep_time,arr_time,raw_json)
                        VALUES (?,?,?,?,?,?,?,?,?)"""), (response_id, index,
                        *(str(values[k]) if values.get(k) is not None else None for k in ("airline_iata", "flight_number", "dep_iata", "arr_iata", "dep_time", "arr_time")), json.dumps(raw)))
            if inserted and provider == "openweather" and isinstance(payload, dict):
                main = payload.get("main") if isinstance(payload.get("main"), dict) else {}
                wind = payload.get("wind") if isinstance(payload.get("wind"), dict) else {}
                def numeric(value):
                    return value if isinstance(value, (float, int)) and not isinstance(value, bool) else None
                conn.execute(self.sql("""INSERT INTO raw_weather
                    (response_id,airport_code,observed_unix,temperature_c,wind_speed_ms,visibility_m,raw_json)
                    VALUES (?,?,?,?,?,?,?)"""), (response_id, params.get("airport_code"), numeric(payload.get("dt")),
                    numeric(main.get("temp")), numeric(wind.get("speed")), numeric(payload.get("visibility")), json.dumps(payload)))
            conn.commit()
        return response_id

    def mark(self, response_id, row_index, status, *, reason=None, flight_key=None):
        with self.connect() as conn:
            conn.execute(self.sql("""UPDATE raw_flights SET processing_status=?,processing_error=?,
                processed_flight_key=?,processed_at=? WHERE response_id=? AND row_index=?"""),
                (status, reason, flight_key, datetime.now(timezone.utc).isoformat(), response_id, row_index))
            conn.commit()

    def flights(self, offset, limit):
        with self.connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM raw_flights").fetchone()["n"]
            rows = conn.execute(self.sql("SELECT * FROM raw_flights ORDER BY raw_id DESC LIMIT ? OFFSET ?"), (limit, offset)).fetchall()
        data = []
        for index, row in enumerate(rows):
            raw = json.loads(row["raw_json"])
            values = raw if isinstance(raw, dict) else {}
            data.append({
                "RAW_ID": row["raw_id"], "ROW_NUMBER": offset + index + 1,
                "FL_DATE": str(values.get("dep_time") or "")[:10],
                "OP_UNIQUE_CARRIER": values.get("airline_iata"), "OP_CARRIER_FL_NUM": values.get("flight_number"),
                "ORIGIN": values.get("dep_iata"), "DEST": values.get("arr_iata"),
                "CRS_DEP_TIME": values.get("dep_time"), "CRS_ARR_TIME": values.get("arr_time"),
                "TAIL_NUM": values.get("reg_number"), "raw": raw,
                "response_id": row["response_id"], "row_index": row["row_index"],
                "processing_status": row["processing_status"], "processing_error": row["processing_error"],
                "processed_flight_key": row["processed_flight_key"],
            })
        return {"source": "airlabs", "database": self.database_name, "total": total, "data": data,
                "window_start": offset, "window_end": offset + len(data), "window_size": limit}

    def flight(self, raw_id):
        with self.connect() as conn:
            row = conn.execute(self.sql("""SELECT f.*,r.fetched_at,r.archive_kind FROM raw_flights f
                JOIN raw_api_responses r USING(response_id) WHERE f.raw_id=?"""), (raw_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["raw"] = json.loads(result.pop("raw_json"))
        return result

    def weather(self, response_id):
        with self.connect() as conn:
            row = conn.execute(self.sql("SELECT * FROM raw_weather WHERE response_id=?"), (response_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["raw"] = json.loads(result.pop("raw_json"))
        return result
