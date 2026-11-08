-- Initial Database Schema for The Flight Observatory Platform
-- Automatically executed by PostgreSQL container on first startup.

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
