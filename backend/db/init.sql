-- Initial Database Schema for The Flight Observatory Platform
-- Automatically executed by PostgreSQL container on first startup.

-- =============================================================================
-- 1. RAW DATABASE LAYER (Source of Truth for Data Simulator)
-- =============================================================================

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

-- =============================================================================
-- 2. CLEAN INGESTION LAYER (Normalized, Deduplicated & Enriched Flights)
-- =============================================================================

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

-- =============================================================================
-- 3. CLUSTERING LAYER (Unsupervised Airport & Route Archetypes)
-- =============================================================================

CREATE TABLE IF NOT EXISTS clustering_runs (
    run_id TEXT PRIMARY KEY,
    model_version TEXT NOT NULL,
    algorithm TEXT NOT NULL,
    n_clusters INTEGER NOT NULL,
    silhouette_score REAL NOT NULL,
    inertia REAL NOT NULL,
    total_airports INTEGER NOT NULL,
    total_routes INTEGER NOT NULL,
    source_flights_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_clustering_runs_created ON clustering_runs(created_at DESC);

CREATE TABLE IF NOT EXISTS cluster_centroids (
    run_id TEXT NOT NULL REFERENCES clustering_runs(run_id) ON DELETE CASCADE,
    cluster_id INTEGER NOT NULL,
    cluster_name TEXT NOT NULL,
    short_label TEXT NOT NULL,
    color_code TEXT NOT NULL,
    interpretation TEXT NOT NULL,
    entity_count INTEGER NOT NULL,
    share_pct REAL NOT NULL,
    avg_flights REAL NOT NULL,
    avg_routes REAL NOT NULL,
    avg_distance REAL NOT NULL,
    avg_elapsed_time REAL NOT NULL,
    peak_hour_ratio REAL NOT NULL,
    avg_delay_minutes REAL NOT NULL,
    delay_rate_pct REAL NOT NULL,
    centroid_vector_json TEXT NOT NULL,
    radar_metrics_json TEXT NOT NULL,
    top_airports_json TEXT NOT NULL,
    PRIMARY KEY (run_id, cluster_id)
);

CREATE TABLE IF NOT EXISTS cluster_assignments (
    run_id TEXT NOT NULL REFERENCES clustering_runs(run_id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_code TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    cluster_id INTEGER NOT NULL,
    cluster_name TEXT NOT NULL,
    short_label TEXT NOT NULL,
    flight_count INTEGER NOT NULL,
    route_count INTEGER NOT NULL,
    avg_distance REAL NOT NULL,
    avg_elapsed_time REAL NOT NULL,
    peak_hour_ratio REAL NOT NULL,
    avg_delay_minutes REAL NOT NULL,
    delay_rate_pct REAL NOT NULL,
    pca_x REAL NOT NULL,
    pca_y REAL NOT NULL,
    distance_to_centroid REAL NOT NULL,
    membership_probabilities_json TEXT NOT NULL,
    PRIMARY KEY (run_id, entity_type, entity_code)
);

CREATE INDEX IF NOT EXISTS idx_cluster_assign_run ON cluster_assignments(run_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_cluster_assign_cluster ON cluster_assignments(cluster_id);

-- =============================================================================
-- 4. PREDICTION & CLASSIFICATION LAYER (Delay Regression & Risk Classification)
-- =============================================================================

CREATE TABLE IF NOT EXISTS prediction_runs (
    run_id TEXT PRIMARY KEY,
    model_version TEXT NOT NULL,
    regressor_algorithm TEXT NOT NULL,
    classifier_algorithm TEXT NOT NULL,
    total_predicted INTEGER NOT NULL,
    predicted_delayed_count INTEGER NOT NULL,
    predicted_delay_rate_pct REAL NOT NULL,
    avg_predicted_delay_minutes REAL NOT NULL,
    avg_actual_delay_minutes REAL NOT NULL,
    mae REAL NOT NULL,
    rmse REAL NOT NULL,
    accuracy_pct REAL NOT NULL,
    high_risk_count INTEGER NOT NULL,
    medium_risk_count INTEGER NOT NULL,
    low_risk_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prediction_runs_created ON prediction_runs(created_at DESC);

CREATE TABLE IF NOT EXISTS flight_predictions (
    run_id TEXT NOT NULL REFERENCES prediction_runs(run_id) ON DELETE CASCADE,
    flight_key TEXT NOT NULL,
    fl_date TEXT NOT NULL,
    flight_code TEXT NOT NULL,
    op_unique_carrier TEXT NOT NULL,
    carrier_name TEXT,
    origin TEXT NOT NULL,
    dest TEXT NOT NULL,
    route TEXT NOT NULL,
    crs_dep_time TEXT,
    dep_hour INTEGER,
    distance REAL,
    crs_elapsed_time REAL,
    actual_delay_minutes REAL NOT NULL,
    actual_delay_status TEXT NOT NULL,
    predicted_delay_minutes REAL NOT NULL,
    delay_probability REAL NOT NULL,
    predicted_label TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    top_factors_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, flight_key)
);

CREATE INDEX IF NOT EXISTS idx_flight_predictions_run ON flight_predictions(run_id);
CREATE INDEX IF NOT EXISTS idx_flight_predictions_risk ON flight_predictions(run_id, risk_level);
CREATE INDEX IF NOT EXISTS idx_flight_predictions_route ON flight_predictions(run_id, route);
