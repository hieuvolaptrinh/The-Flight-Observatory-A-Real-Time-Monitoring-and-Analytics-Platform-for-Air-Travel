-- Immutable API snapshots. Processing metadata never changes the original JSON.
CREATE TABLE IF NOT EXISTS raw_api_responses (
    response_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    request_params TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    http_status INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    archive_kind TEXT NOT NULL DEFAULT 'api'
);
CREATE INDEX IF NOT EXISTS raw_responses_time ON raw_api_responses(fetched_at);

CREATE TABLE IF NOT EXISTS raw_flights (
    raw_id BIGSERIAL PRIMARY KEY,
    response_id TEXT NOT NULL REFERENCES raw_api_responses(response_id),
    row_index INTEGER NOT NULL,
    airline_iata TEXT,
    flight_number TEXT,
    dep_iata TEXT,
    arr_iata TEXT,
    dep_time TEXT,
    arr_time TEXT,
    raw_json TEXT NOT NULL,
    processing_status TEXT NOT NULL DEFAULT 'pending',
    processing_error TEXT,
    processed_flight_key TEXT,
    processed_at TEXT,
    UNIQUE(response_id, row_index)
);

CREATE TABLE IF NOT EXISTS raw_weather (
    response_id TEXT PRIMARY KEY REFERENCES raw_api_responses(response_id),
    airport_code TEXT,
    observed_unix BIGINT,
    temperature_c REAL,
    wind_speed_ms REAL,
    visibility_m REAL,
    raw_json TEXT NOT NULL
);
