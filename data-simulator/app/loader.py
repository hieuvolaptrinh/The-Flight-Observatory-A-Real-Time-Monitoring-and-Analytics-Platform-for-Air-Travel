"""
Raw Flight Data Store & Chunked Queue Worker for Data Simulator.
- Streams CSV rows in chunks (default 5,000 rows/chunk) into Raw DB (`raw_source_files`, `raw_flights`, `raw_simulator_state`).
- Uses bounded `asyncio.Queue` backpressure so Python RAM stays under ~15 MB even for 540k+ rows.
- Uses PostgreSQL `COPY FROM STDIN` + `SET LOCAL synchronous_commit = off` (or SQLite `executemany` fallback).
- Serves sliding-window batches via O(log N) keyset seek (`WHERE file_id = :fid AND row_number > :start AND row_number <= :end`).
"""
from __future__ import annotations

import asyncio
import csv
from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import sqlite3
from typing import Any

log = logging.getLogger("simulator.loader")

REQUIRED_COLS = {
    "DAY_OF_WEEK", "FL_DATE", "OP_UNIQUE_CARRIER", "TAIL_NUM",
    "OP_CARRIER_FL_NUM", "ORIGIN_AIRPORT_ID", "ORIGIN_AIRPORT_SEQ_ID",
    "ORIGIN_CITY_MARKET_ID", "ORIGIN", "DEST_AIRPORT_ID",
    "DEST_AIRPORT_SEQ_ID", "DEST_CITY_MARKET_ID", "DEST",
    "CRS_DEP_TIME", "CRS_ARR_TIME", "CRS_ELAPSED_TIME", "DISTANCE",
}

POSTGRES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS raw_source_files (
    file_id SERIAL PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_sha256 TEXT NOT NULL UNIQUE,
    total_rows INTEGER NOT NULL DEFAULT 0,
    loaded_rows INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'LOADING',
    loaded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_flights (
    raw_id BIGSERIAL PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES raw_source_files(file_id) ON DELETE CASCADE,
    row_number INTEGER NOT NULL,
    day_of_week TEXT,
    fl_date TEXT,
    op_unique_carrier TEXT,
    carrier_name TEXT,
    tail_num TEXT,
    op_carrier_fl_num TEXT,
    origin_airport_id TEXT,
    origin_airport_seq_id TEXT,
    origin_city_market_id TEXT,
    origin TEXT,
    dest_airport_id TEXT,
    dest_airport_seq_id TEXT,
    dest_city_market_id TEXT,
    dest TEXT,
    crs_dep_time TEXT,
    crs_arr_time TEXT,
    crs_elapsed_time TEXT,
    distance TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (file_id, row_number)
);

CREATE INDEX IF NOT EXISTS idx_raw_flights_seek ON raw_flights(file_id, row_number);

CREATE TABLE IF NOT EXISTS raw_simulator_state (
    stream_name TEXT PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES raw_source_files(file_id) ON DELETE CASCADE,
    window_start INTEGER NOT NULL DEFAULT 0,
    default_window_size INTEGER NOT NULL DEFAULT 100,
    default_step INTEGER NOT NULL DEFAULT 100,
    total_requests BIGINT NOT NULL DEFAULT 0,
    last_served_at TEXT
);
"""

SQLITE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS raw_source_files (
    file_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    file_sha256 TEXT NOT NULL UNIQUE,
    total_rows INTEGER NOT NULL DEFAULT 0,
    loaded_rows INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'LOADING',
    loaded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_flights (
    raw_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL REFERENCES raw_source_files(file_id) ON DELETE CASCADE,
    row_number INTEGER NOT NULL,
    day_of_week TEXT,
    fl_date TEXT,
    op_unique_carrier TEXT,
    carrier_name TEXT,
    tail_num TEXT,
    op_carrier_fl_num TEXT,
    origin_airport_id TEXT,
    origin_airport_seq_id TEXT,
    origin_city_market_id TEXT,
    origin TEXT,
    dest_airport_id TEXT,
    dest_airport_seq_id TEXT,
    dest_city_market_id TEXT,
    dest TEXT,
    crs_dep_time TEXT,
    crs_arr_time TEXT,
    crs_elapsed_time TEXT,
    distance TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (file_id, row_number)
);

CREATE INDEX IF NOT EXISTS idx_raw_flights_seek ON raw_flights(file_id, row_number);

CREATE TABLE IF NOT EXISTS raw_simulator_state (
    stream_name TEXT PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES raw_source_files(file_id) ON DELETE CASCADE,
    window_start INTEGER NOT NULL DEFAULT 0,
    default_window_size INTEGER NOT NULL DEFAULT 100,
    default_step INTEGER NOT NULL DEFAULT 100,
    total_requests INTEGER NOT NULL DEFAULT 0,
    last_served_at TEXT
);
"""

RAW_FLIGHT_INSERT_COLS = (
    "file_id",
    "row_number",
    "day_of_week",
    "fl_date",
    "op_unique_carrier",
    "carrier_name",
    "tail_num",
    "op_carrier_fl_num",
    "origin_airport_id",
    "origin_airport_seq_id",
    "origin_city_market_id",
    "origin",
    "dest_airport_id",
    "dest_airport_seq_id",
    "dest_city_market_id",
    "dest",
    "crs_dep_time",
    "crs_arr_time",
    "crs_elapsed_time",
    "distance",
    "created_at",
)


def resolve_first_csv(csv_path: str) -> Path:
    """Return the first CSV file inside `csv_path` directory or `csv_path` itself."""
    p = Path(csv_path)
    if p.is_file():
        return p
    files = sorted(p.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"Không tìm thấy *.csv trong: {csv_path}")
    return files[0]


def _clean_raw_cell(val: str | None) -> str | None:
    if val is None:
        return None
    s = val.strip()
    return s if s != "" else None


def _row_to_raw_tuple(file_id: int, row_number: int, row: dict[str, Any], created_at: str) -> tuple[Any, ...]:
    return (
        file_id,
        row_number,
        _clean_raw_cell(row.get("DAY_OF_WEEK")),
        _clean_raw_cell(row.get("FL_DATE")),
        _clean_raw_cell(row.get("OP_UNIQUE_CARRIER")),
        _clean_raw_cell(row.get("CARRIER_NAME")),
        _clean_raw_cell(row.get("TAIL_NUM")),
        _clean_raw_cell(row.get("OP_CARRIER_FL_NUM")),
        _clean_raw_cell(row.get("ORIGIN_AIRPORT_ID")),
        _clean_raw_cell(row.get("ORIGIN_AIRPORT_SEQ_ID")),
        _clean_raw_cell(row.get("ORIGIN_CITY_MARKET_ID")),
        _clean_raw_cell(row.get("ORIGIN")),
        _clean_raw_cell(row.get("DEST_AIRPORT_ID")),
        _clean_raw_cell(row.get("DEST_AIRPORT_SEQ_ID")),
        _clean_raw_cell(row.get("DEST_CITY_MARKET_ID")),
        _clean_raw_cell(row.get("DEST")),
        _clean_raw_cell(row.get("CRS_DEP_TIME")),
        _clean_raw_cell(row.get("CRS_ARR_TIME")),
        _clean_raw_cell(row.get("CRS_ELAPSED_TIME")),
        _clean_raw_cell(row.get("DISTANCE")),
        created_at,
    )


def _db_row_to_api_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "RAW_ID": row["raw_id"],
        "ROW_NUMBER": row["row_number"],
        "DAY_OF_WEEK": row["day_of_week"],
        "FL_DATE": row["fl_date"],
        "OP_UNIQUE_CARRIER": row["op_unique_carrier"],
        "CARRIER_NAME": row["carrier_name"],
        "TAIL_NUM": row["tail_num"],
        "OP_CARRIER_FL_NUM": row["op_carrier_fl_num"],
        "ORIGIN_AIRPORT_ID": row["origin_airport_id"],
        "ORIGIN_AIRPORT_SEQ_ID": row["origin_airport_seq_id"],
        "ORIGIN_CITY_MARKET_ID": row["origin_city_market_id"],
        "ORIGIN": row["origin"],
        "DEST_AIRPORT_ID": row["dest_airport_id"],
        "DEST_AIRPORT_SEQ_ID": row["dest_airport_seq_id"],
        "DEST_CITY_MARKET_ID": row["dest_city_market_id"],
        "DEST": row["dest"],
        "CRS_DEP_TIME": row["crs_dep_time"],
        "CRS_ARR_TIME": row["crs_arr_time"],
        "CRS_ELAPSED_TIME": row["crs_elapsed_time"],
        "DISTANCE": row["distance"],
    }


class RawFlightStore:
    """
    Manages the Raw DB tables (`raw_source_files`, `raw_flights`, `raw_simulator_state`),
    streams CSV chunks via bounded `asyncio.Queue`, and serves keyset-seek windows.
    """

    def __init__(
        self,
        csv_path: str,
        database_url: str,
        window_size: int = 100,
        slide_step: int = 20,
        chunk_size: int = 5000,
        queue_maxsize: int = 4,
        max_seed_rows: int = 0,
        stream_name: str = "default",
    ) -> None:
        self.csv_file = resolve_first_csv(csv_path)
        self.database_url = database_url
        self.is_postgres = database_url.startswith(("postgresql://", "postgres://"))
        self.storage_type = "postgresql" if self.is_postgres else "sqlite"
        self.window_size = window_size
        self.slide_step = slide_step
        self.chunk_size = max(100, chunk_size)
        self.queue_maxsize = max(1, queue_maxsize)
        self.max_seed_rows = max(0, max_seed_rows)
        self.stream_name = stream_name

        if not self.is_postgres:
            raw_path = database_url.replace("sqlite:///", "")
            self.sqlite_path = Path(raw_path).resolve()
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

        self.file_id: int = 0
        self.file_sha256: str = ""
        self.total_rows: int = 0
        self.loaded_rows: int = 0
        self.status: str = "LOADING"

        self.init_schema()
        self.prepare_source_file()

    def _connect_sqlite(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.sqlite_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _connect_postgres(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self.database_url, row_factory=dict_row)

    def init_schema(self) -> None:
        if self.is_postgres:
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute(POSTGRES_SCHEMA_SQL)
                    # Ensure extra airport sequence/market columns exist if table was created earlier
                    for col in (
                        "origin_airport_seq_id",
                        "origin_city_market_id",
                        "dest_airport_seq_id",
                        "dest_city_market_id",
                    ):
                        cur.execute(f"ALTER TABLE raw_flights ADD COLUMN IF NOT EXISTS {col} TEXT")
                conn.commit()
        else:
            with self._connect_sqlite() as conn:
                conn.executescript(SQLITE_SCHEMA_SQL)
                conn.commit()

    def _compute_sha256(self) -> str:
        hasher = hashlib.sha256()
        with open(self.csv_file, "rb") as f:
            while chunk := f.read(1024 * 1024):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _count_csv_rows_and_validate(self) -> int:
        with open(self.csv_file, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            cols = set(reader.fieldnames or [])
            missing = REQUIRED_COLS - cols
            if missing:
                raise ValueError(f"{self.csv_file.name} thiếu cột: {missing}")
            count = sum(1 for _ in reader)
        if self.max_seed_rows > 0:
            return min(count, self.max_seed_rows)
        return count

    def prepare_source_file(self) -> None:
        """Register or resume the CSV source file in `raw_source_files` and `raw_simulator_state`."""
        self.file_sha256 = self._compute_sha256()
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        if self.is_postgres:
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT * FROM raw_source_files WHERE file_sha256 = %s",
                        (self.file_sha256,),
                    )
                    existing = cur.fetchone()
                    if existing:
                        self.file_id = int(existing["file_id"])
                        total_rows = int(existing["total_rows"])
                        if self.max_seed_rows > 0:
                            total_rows = min(total_rows, self.max_seed_rows)
                        cur.execute(
                            "SELECT COUNT(*) AS cnt, COALESCE(MAX(row_number), 0) AS max_row "
                            "FROM raw_flights WHERE file_id = %s",
                            (self.file_id,),
                        )
                        stats = cur.fetchone()
                        actual_loaded = int(stats["max_row"] or 0)
                        status = "READY" if actual_loaded >= total_rows and total_rows > 0 else "LOADING"
                        cur.execute(
                            "UPDATE raw_source_files SET loaded_rows = %s, total_rows = %s, status = %s WHERE file_id = %s",
                            (actual_loaded, total_rows, status, self.file_id),
                        )
                        self.total_rows = total_rows
                        self.loaded_rows = actual_loaded
                        self.status = status
                    else:
                        total_rows = self._count_csv_rows_and_validate()
                        cur.execute(
                            """
                            INSERT INTO raw_source_files (file_name, file_sha256, total_rows, loaded_rows, status, loaded_at)
                            VALUES (%s, %s, %s, 0, 'LOADING', %s)
                            RETURNING file_id
                            """,
                            (self.csv_file.name, self.file_sha256, total_rows, now_iso),
                        )
                        self.file_id = int(cur.fetchone()["file_id"])
                        self.total_rows = total_rows
                        self.loaded_rows = 0
                        self.status = "LOADING"

                    cur.execute(
                        """
                        INSERT INTO raw_simulator_state (
                            stream_name, file_id, window_start, default_window_size, default_step, total_requests
                        ) VALUES (%s, %s, 0, %s, %s, 0)
                        ON CONFLICT (stream_name) DO UPDATE SET
                            file_id = EXCLUDED.file_id,
                            default_window_size = EXCLUDED.default_window_size,
                            default_step = EXCLUDED.default_step
                        """,
                        (self.stream_name, self.file_id, self.window_size, self.slide_step),
                    )
                conn.commit()
        else:
            with self._connect_sqlite() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM raw_source_files WHERE file_sha256 = ?",
                    (self.file_sha256,),
                )
                existing = cur.fetchone()
                if existing:
                    self.file_id = int(existing["file_id"])
                    total_rows = int(existing["total_rows"])
                    if self.max_seed_rows > 0:
                        total_rows = min(total_rows, self.max_seed_rows)
                    cur.execute(
                        "SELECT COUNT(*) AS cnt, COALESCE(MAX(row_number), 0) AS max_row "
                        "FROM raw_flights WHERE file_id = ?",
                        (self.file_id,),
                    )
                    stats = cur.fetchone()
                    actual_loaded = int(stats["max_row"] or 0)
                    status = "READY" if actual_loaded >= total_rows and total_rows > 0 else "LOADING"
                    cur.execute(
                        "UPDATE raw_source_files SET loaded_rows = ?, total_rows = ?, status = ? WHERE file_id = ?",
                        (actual_loaded, total_rows, status, self.file_id),
                    )
                    self.total_rows = total_rows
                    self.loaded_rows = actual_loaded
                    self.status = status
                else:
                    total_rows = self._count_csv_rows_and_validate()
                    cur.execute(
                        """
                        INSERT INTO raw_source_files (file_name, file_sha256, total_rows, loaded_rows, status, loaded_at)
                        VALUES (?, ?, ?, 0, 'LOADING', ?)
                        """,
                        (self.csv_file.name, self.file_sha256, total_rows, now_iso),
                    )
                    self.file_id = int(cur.lastrowid)
                    self.total_rows = total_rows
                    self.loaded_rows = 0
                    self.status = "LOADING"

                cur.execute(
                    """
                    INSERT INTO raw_simulator_state (
                        stream_name, file_id, window_start, default_window_size, default_step, total_requests
                    ) VALUES (?, ?, 0, ?, ?, 0)
                    ON CONFLICT (stream_name) DO UPDATE SET
                        file_id = excluded.file_id,
                        default_window_size = excluded.default_window_size,
                        default_step = excluded.default_step
                    """,
                    (self.stream_name, self.file_id, self.window_size, self.slide_step),
                )
                conn.commit()

    def _write_chunk_to_db(self, chunk: list[tuple[Any, ...]]) -> int:
        """Persist a single chunk of raw rows and checkpoint `loaded_rows` in `raw_source_files`."""
        if not chunk:
            return self.loaded_rows

        max_row_in_chunk = int(chunk[-1][1])
        new_loaded = max(self.loaded_rows, max_row_in_chunk)
        new_status = "READY" if new_loaded >= self.total_rows else "LOADING"
        cols_csv = ", ".join(RAW_FLIGHT_INSERT_COLS)

        if self.is_postgres:
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL synchronous_commit = off")
                    try:
                        with cur.copy(f"COPY raw_flights ({cols_csv}) FROM STDIN") as copy:
                            for row_tuple in chunk:
                                copy.write_row(row_tuple)
                    except Exception:
                        conn.rollback()
                        cur.execute("SET LOCAL synchronous_commit = off")
                        placeholders = ", ".join(["%s"] * len(RAW_FLIGHT_INSERT_COLS))
                        cur.executemany(
                            f"INSERT INTO raw_flights ({cols_csv}) VALUES ({placeholders}) "
                            "ON CONFLICT (file_id, row_number) DO NOTHING",
                            chunk,
                        )
                    cur.execute(
                        "UPDATE raw_source_files SET loaded_rows = %s, status = %s WHERE file_id = %s",
                        (new_loaded, new_status, self.file_id),
                    )
                conn.commit()
        else:
            placeholders = ", ".join(["?"] * len(RAW_FLIGHT_INSERT_COLS))
            sql = f"INSERT OR IGNORE INTO raw_flights ({cols_csv}) VALUES ({placeholders})"
            with self._connect_sqlite() as conn:
                cur = conn.cursor()
                cur.executemany(sql, chunk)
                cur.execute(
                    "UPDATE raw_source_files SET loaded_rows = ?, status = ? WHERE file_id = ?",
                    (new_loaded, new_status, self.file_id),
                )
                conn.commit()

        self.loaded_rows = new_loaded
        self.status = new_status
        return new_loaded

    def _read_csv_chunk_range(self, start_row_exclusive: int, max_rows: int) -> list[tuple[Any, ...]]:
        """Read up to `max_rows` rows starting after 1-based `start_row_exclusive`."""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        chunk: list[tuple[Any, ...]] = []
        with open(self.csv_file, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=1):
                if idx <= start_row_exclusive:
                    continue
                if idx > self.total_rows:
                    break
                chunk.append(_row_to_raw_tuple(self.file_id, idx, row, now_iso))
                if len(chunk) >= max_rows:
                    break
        return chunk

    def seed_initial_chunk_sync(self) -> int:
        """
        Synchronously seed the first chunk (e.g. 5,000 rows in ~50ms) if `loaded_rows == 0`
        so `GET /flights` is immediately available when the server starts.
        """
        if self.loaded_rows > 0:
            return self.loaded_rows
        initial_target = min(self.chunk_size, self.total_rows)
        if initial_target <= 0:
            return 0
        chunk = self._read_csv_chunk_range(0, initial_target)
        return self._write_chunk_to_db(chunk)

    async def run_background_queue_worker(self) -> None:
        """
        Stream remaining CSV rows (`loaded_rows + 1 .. total_rows`) into `raw_flights`
        using a bounded `asyncio.Queue(maxsize=self.queue_maxsize)` producer-consumer pipeline.
        """
        if self.loaded_rows >= self.total_rows:
            log.info(
                "✓ Raw DB đã sẵn sàng (%d/%d rows, file=%s, storage=%s)",
                self.loaded_rows,
                self.total_rows,
                self.csv_file.name,
                self.storage_type,
            )
            return

        start_from = self.loaded_rows
        log.info(
            "Bắt đầu Queue Worker nạp Raw DB từ row %d -> %d (chunk=%d, queue_maxsize=%d, storage=%s)…",
            start_from + 1,
            self.total_rows,
            self.chunk_size,
            self.queue_maxsize,
            self.storage_type,
        )
        queue: asyncio.Queue[list[tuple[Any, ...]] | None] = asyncio.Queue(maxsize=self.queue_maxsize)

        async def _producer() -> None:
            cursor = start_from
            while cursor < self.total_rows:
                batch_limit = min(self.chunk_size, self.total_rows - cursor)
                chunk = await asyncio.to_thread(self._read_csv_chunk_range, cursor, batch_limit)
                if not chunk:
                    break
                cursor = int(chunk[-1][1])
                await queue.put(chunk)
            await queue.put(None)

        async def _consumer() -> None:
            chunks_written = 0
            while True:
                chunk = await queue.get()
                try:
                    if chunk is None:
                        break
                    loaded = await asyncio.to_thread(self._write_chunk_to_db, chunk)
                    chunks_written += 1
                    if chunks_written % 10 == 0 or loaded >= self.total_rows:
                        log.info(
                            "Queue Worker checkpoint: %d/%d rows (%.1f%%) [%s]",
                            loaded,
                            self.total_rows,
                            (loaded / self.total_rows * 100.0) if self.total_rows else 100.0,
                            self.status,
                        )
                finally:
                    queue.task_done()

        await asyncio.gather(_producer(), _consumer())
        log.info(
            "✓ Queue Worker hoàn tất nạp Raw DB: %d/%d rows (%s)",
            self.loaded_rows,
            self.total_rows,
            self.status,
        )

    def _seek_range(self, cur: Any, low_exclusive: int, high_inclusive: int) -> list[dict[str, Any]]:
        if high_inclusive <= low_exclusive:
            return []
        ph = "%s" if self.is_postgres else "?"
        sql = f"""
            SELECT * FROM raw_flights
            WHERE file_id = {ph}
              AND row_number > {ph}
              AND row_number <= {ph}
            ORDER BY row_number ASC
        """
        cur.execute(sql, (self.file_id, low_exclusive, high_inclusive))
        return [_db_row_to_api_dict(dict(r)) for r in cur.fetchall()]

    def get_window(
        self,
        window_size: int | None = None,
        slide_step: int | None = None,
        start: int | None = None,
    ) -> dict[str, Any]:
        """
        Fetch a sliding window of raw records from `raw_flights` using keyset seek
        on `(file_id, row_number)` instead of slow OFFSET pagination.
        """
        size = window_size or self.window_size
        step = slide_step if slide_step is not None else self.slide_step
        explicit_start = start is not None
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        if self.is_postgres:
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT loaded_rows, total_rows, status FROM raw_source_files WHERE file_id = %s",
                        (self.file_id,),
                    )
                    src_row = cur.fetchone()
                    total = int(src_row["loaded_rows"]) if src_row else 0
                    if total <= 0:
                        raise RuntimeError("No flights loaded in raw_flights")

                    cur.execute(
                        "SELECT window_start, total_requests FROM raw_simulator_state WHERE stream_name = %s",
                        (self.stream_name,),
                    )
                    st_row = cur.fetchone()
                    db_window_start = int(st_row["window_start"]) if st_row else 0

                    if explicit_start:
                        size = min(size, total)
                    win_start = (start if explicit_start else db_window_start) % total
                    win_end = win_start + size

                    if win_end <= total:
                        batch = self._seek_range(cur, win_start, win_end)
                    else:
                        part1 = self._seek_range(cur, win_start, total)
                        part2 = self._seek_range(cur, 0, win_end - total)
                        batch = part1 + part2

                    if not explicit_start:
                        next_window_start = (win_start + step) % total
                        cur.execute(
                            """
                            UPDATE raw_simulator_state
                            SET window_start = %s,
                                total_requests = total_requests + 1,
                                last_served_at = %s
                            WHERE stream_name = %s
                            """,
                            (next_window_start, now_iso, self.stream_name),
                        )
                conn.commit()
        else:
            with self._connect_sqlite() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT loaded_rows, total_rows, status FROM raw_source_files WHERE file_id = ?",
                    (self.file_id,),
                )
                src_row = cur.fetchone()
                total = int(src_row["loaded_rows"]) if src_row else 0
                if total <= 0:
                    raise RuntimeError("No flights loaded in raw_flights")

                cur.execute(
                    "SELECT window_start, total_requests FROM raw_simulator_state WHERE stream_name = ?",
                    (self.stream_name,),
                )
                st_row = cur.fetchone()
                db_window_start = int(st_row["window_start"]) if st_row else 0

                if explicit_start:
                    size = min(size, total)
                win_start = (start if explicit_start else db_window_start) % total
                win_end = win_start + size

                if win_end <= total:
                    batch = self._seek_range(cur, win_start, win_end)
                else:
                    part1 = self._seek_range(cur, win_start, total)
                    part2 = self._seek_range(cur, 0, win_end - total)
                    batch = part1 + part2

                if not explicit_start:
                    next_window_start = (win_start + step) % total
                    cur.execute(
                        """
                        UPDATE raw_simulator_state
                        SET window_start = ?,
                            total_requests = total_requests + 1,
                            last_served_at = ?
                        WHERE stream_name = ?
                        """,
                        (next_window_start, now_iso, self.stream_name),
                    )
                conn.commit()

        return {
            "fetched_at": now_iso,
            "window_start": win_start,
            "window_end": win_end % total if win_end > total else win_end,
            "window_size": len(batch),
            "slide_step": step,
            "total": total,
            "data": batch,
        }

    def get_status(self) -> dict[str, Any]:
        """Return health & checkpoint status from Raw DB."""
        ph = "%s" if self.is_postgres else "?"
        src_sql = f"SELECT * FROM raw_source_files WHERE file_id = {ph}"
        st_sql = f"SELECT * FROM raw_simulator_state WHERE stream_name = {ph}"

        if self.is_postgres:
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute(src_sql, (self.file_id,))
                    src = dict(cur.fetchone() or {})
                    cur.execute(st_sql, (self.stream_name,))
                    st = dict(cur.fetchone() or {})
        else:
            with self._connect_sqlite() as conn:
                cur = conn.cursor()
                cur.execute(src_sql, (self.file_id,))
                src = dict(cur.fetchone() or {})
                cur.execute(st_sql, (self.stream_name,))
                st = dict(cur.fetchone() or {})

        loaded_rows = int(src.get("loaded_rows") or self.loaded_rows)
        total_rows = int(src.get("total_rows") or self.total_rows)
        return {
            "status": "ok",
            "storage_type": self.storage_type,
            "file_id": self.file_id,
            "file_name": src.get("file_name", self.csv_file.name),
            "seed_status": src.get("status", self.status),
            "total_records": loaded_rows,
            "target_records": total_rows,
            "window_start": int(st.get("window_start") or 0),
            "window_size": self.window_size,
            "slide_step": self.slide_step,
            "total_requests": int(st.get("total_requests") or 0),
            "last_served_at": st.get("last_served_at"),
        }


# ── Legacy helper preserved for backwards compatibility ──────────────────────
def load_records(csv_path: str) -> list[dict[str, Any]]:
    p = resolve_first_csv(csv_path)
    all_records: list[dict[str, Any]] = []
    with open(p, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames or [])
        missing = REQUIRED_COLS - cols
        if missing:
            raise ValueError(f"{p.name} thiếu cột: {missing}")
        for idx, row in enumerate(reader, start=1):
            all_records.append({
                "ROW_NUMBER": idx,
                "DAY_OF_WEEK": _clean_raw_cell(row.get("DAY_OF_WEEK")),
                "FL_DATE": _clean_raw_cell(row.get("FL_DATE")),
                "OP_UNIQUE_CARRIER": _clean_raw_cell(row.get("OP_UNIQUE_CARRIER")),
                "TAIL_NUM": _clean_raw_cell(row.get("TAIL_NUM")),
                "OP_CARRIER_FL_NUM": _clean_raw_cell(row.get("OP_CARRIER_FL_NUM")),
                "ORIGIN_AIRPORT_ID": _clean_raw_cell(row.get("ORIGIN_AIRPORT_ID")),
                "ORIGIN_AIRPORT_SEQ_ID": _clean_raw_cell(row.get("ORIGIN_AIRPORT_SEQ_ID")),
                "ORIGIN_CITY_MARKET_ID": _clean_raw_cell(row.get("ORIGIN_CITY_MARKET_ID")),
                "ORIGIN": _clean_raw_cell(row.get("ORIGIN")),
                "DEST_AIRPORT_ID": _clean_raw_cell(row.get("DEST_AIRPORT_ID")),
                "DEST_AIRPORT_SEQ_ID": _clean_raw_cell(row.get("DEST_AIRPORT_SEQ_ID")),
                "DEST_CITY_MARKET_ID": _clean_raw_cell(row.get("DEST_CITY_MARKET_ID")),
                "DEST": _clean_raw_cell(row.get("DEST")),
                "CRS_DEP_TIME": _clean_raw_cell(row.get("CRS_DEP_TIME")),
                "CRS_ARR_TIME": _clean_raw_cell(row.get("CRS_ARR_TIME")),
                "CRS_ELAPSED_TIME": _clean_raw_cell(row.get("CRS_ELAPSED_TIME")),
                "DISTANCE": _clean_raw_cell(row.get("DISTANCE")),
            })
    return all_records
