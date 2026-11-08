"""
Database layer for Flight Clustering Service (STT 7: DB · Clustering).
Stores cluster runs, cluster centroids + interpretations, and airport/route cluster assignments.
Preserves historical runs by run_id (with retention of latest 10 runs) and uses executemany for batch inserts.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

CLUSTERING_SCHEMA_SQL = """
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
"""


class ClusteringRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.is_postgres = database_url.startswith(("postgresql://", "postgres://"))
        self.storage_type = "postgresql" if self.is_postgres else "sqlite"
        if not self.is_postgres:
            raw_path = database_url.replace("sqlite:///", "")
            self.sqlite_path = Path(raw_path).resolve()
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _connect_sqlite(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.sqlite_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _connect_postgres(self):
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def init_db(self) -> None:
        if self.is_postgres:
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute(CLUSTERING_SCHEMA_SQL)
                conn.commit()
        else:
            with self._connect_sqlite() as conn:
                conn.executescript(CLUSTERING_SCHEMA_SQL)
                conn.commit()

    def save_clustering_result(
        self,
        run_meta: dict[str, Any],
        centroids: list[dict[str, Any]],
        assignments: list[dict[str, Any]],
        keep_latest_runs: int = 10,
    ) -> None:
        """
        Persist a new clustering run using executemany while preserving historical runs
        (pruning runs older than `keep_latest_runs`).
        """
        run_cols = [
            "run_id", "model_version", "algorithm", "n_clusters",
            "silhouette_score", "inertia", "total_airports", "total_routes",
            "source_flights_count", "created_at",
        ]
        centroid_cols = [
            "run_id", "cluster_id", "cluster_name", "short_label", "color_code",
            "interpretation", "entity_count", "share_pct", "avg_flights", "avg_routes",
            "avg_distance", "avg_elapsed_time", "peak_hour_ratio", "avg_delay_minutes",
            "delay_rate_pct", "centroid_vector_json", "radar_metrics_json", "top_airports_json",
        ]
        assign_cols = [
            "run_id", "entity_type", "entity_code", "entity_name", "cluster_id",
            "cluster_name", "short_label", "flight_count", "route_count", "avg_distance",
            "avg_elapsed_time", "peak_hour_ratio", "avg_delay_minutes", "delay_rate_pct",
            "pca_x", "pca_y", "distance_to_centroid", "membership_probabilities_json",
        ]

        centroid_params = [tuple(c_row[c] for c in centroid_cols) for c_row in centroids]
        assign_params = [tuple(a_row[c] for c in assign_cols) for a_row in assignments]

        if self.is_postgres:
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"INSERT INTO clustering_runs ({', '.join(run_cols)}) VALUES ({', '.join(['%s']*len(run_cols))})",
                        [run_meta[c] for c in run_cols],
                    )
                    if centroid_params:
                        cur.executemany(
                            f"INSERT INTO cluster_centroids ({', '.join(centroid_cols)}) VALUES ({', '.join(['%s']*len(centroid_cols))})",
                            centroid_params,
                        )
                    if assign_params:
                        cur.executemany(
                            f"INSERT INTO cluster_assignments ({', '.join(assign_cols)}) VALUES ({', '.join(['%s']*len(assign_cols))})",
                            assign_params,
                        )
                    # Prune old runs beyond keep_latest_runs
                    cur.execute(
                        """
                        SELECT run_id FROM clustering_runs
                        ORDER BY created_at DESC
                        OFFSET %s
                        """,
                        (keep_latest_runs,),
                    )
                    old_ids = [r["run_id"] for r in cur.fetchall()]
                    if old_ids:
                        cur.execute("DELETE FROM cluster_assignments WHERE run_id = ANY(%s)", (old_ids,))
                        cur.execute("DELETE FROM cluster_centroids WHERE run_id = ANY(%s)", (old_ids,))
                        cur.execute("DELETE FROM clustering_runs WHERE run_id = ANY(%s)", (old_ids,))
                conn.commit()
        else:
            with self._connect_sqlite() as conn:
                cur = conn.cursor()
                cur.execute(
                    f"INSERT INTO clustering_runs ({', '.join(run_cols)}) VALUES ({', '.join(['?']*len(run_cols))})",
                    [run_meta[c] for c in run_cols],
                )
                if centroid_params:
                    cur.executemany(
                        f"INSERT INTO cluster_centroids ({', '.join(centroid_cols)}) VALUES ({', '.join(['?']*len(centroid_cols))})",
                        centroid_params,
                    )
                if assign_params:
                    cur.executemany(
                        f"INSERT INTO cluster_assignments ({', '.join(assign_cols)}) VALUES ({', '.join(['?']*len(assign_cols))})",
                        assign_params,
                    )
                cur.execute(
                    """
                    SELECT run_id FROM clustering_runs
                    ORDER BY created_at DESC
                    LIMIT -1 OFFSET ?
                    """,
                    (keep_latest_runs,),
                )
                old_ids = [r["run_id"] for r in cur.fetchall()]
                for oid in old_ids:
                    cur.execute("DELETE FROM cluster_assignments WHERE run_id = ?", (oid,))
                    cur.execute("DELETE FROM cluster_centroids WHERE run_id = ?", (oid,))
                    cur.execute("DELETE FROM clustering_runs WHERE run_id = ?", (oid,))
                conn.commit()

    def get_latest_clustering(
        self,
        entity_type: str = "airport",
        cluster_id: int | None = None,
    ) -> dict[str, Any]:
        """Read latest clustering run, centroids, and entity assignments from DB."""
        ph = "%s" if self.is_postgres else "?"
        run_sql = "SELECT * FROM clustering_runs ORDER BY created_at DESC LIMIT 1"

        if self.is_postgres:
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute(run_sql)
                    run_row = cur.fetchone()
                    if not run_row:
                        return {"ready": False, "updated_at": None, "items": [], "metadata": {}}
                    run_dict = dict(run_row)
                    run_id = run_dict["run_id"]
                    cur.execute(
                        f"SELECT * FROM cluster_centroids WHERE run_id = {ph} ORDER BY cluster_id ASC",
                        (run_id,),
                    )
                    centroid_rows = [dict(r) for r in cur.fetchall()]

                    assign_where = f"WHERE run_id = {ph} AND entity_type = {ph}"
                    assign_params: list[Any] = [run_id, entity_type]
                    if cluster_id is not None:
                        assign_where += f" AND cluster_id = {ph}"
                        assign_params.append(cluster_id)
                    cur.execute(
                        f"SELECT * FROM cluster_assignments {assign_where} ORDER BY flight_count DESC",
                        assign_params,
                    )
                    assign_rows = [dict(r) for r in cur.fetchall()]
        else:
            with self._connect_sqlite() as conn:
                cur = conn.cursor()
                cur.execute(run_sql)
                run_row = cur.fetchone()
                if not run_row:
                    return {"ready": False, "updated_at": None, "items": [], "metadata": {}}
                run_dict = dict(run_row)
                run_id = run_dict["run_id"]
                cur.execute(
                    f"SELECT * FROM cluster_centroids WHERE run_id = {ph} ORDER BY cluster_id ASC",
                    (run_id,),
                )
                centroid_rows = [dict(r) for r in cur.fetchall()]

                assign_where = f"WHERE run_id = {ph} AND entity_type = {ph}"
                assign_params = [run_id, entity_type]
                if cluster_id is not None:
                    assign_where += f" AND cluster_id = {ph}"
                    assign_params.append(cluster_id)
                cur.execute(
                    f"SELECT * FROM cluster_assignments {assign_where} ORDER BY flight_count DESC",
                    assign_params,
                )
                assign_rows = [dict(r) for r in cur.fetchall()]

        centroids_parsed = []
        for c in centroid_rows:
            c_copy = dict(c)
            c_copy["centroid_vector"] = json.loads(c_copy.pop("centroid_vector_json", "{}"))
            c_copy["radar_metrics"] = json.loads(c_copy.pop("radar_metrics_json", "{}"))
            c_copy["top_airports"] = json.loads(c_copy.pop("top_airports_json", "[]"))
            centroids_parsed.append(c_copy)

        items_parsed = []
        for a in assign_rows:
            a_copy = dict(a)
            a_copy["membership_probabilities"] = json.loads(a_copy.pop("membership_probabilities_json", "{}"))
            items_parsed.append(a_copy)

        try:
            updated_at = datetime.fromisoformat(run_dict["created_at"].replace("Z", "+00:00"))
        except ValueError:
            updated_at = datetime.now(timezone.utc)

        metadata = {
            "run": run_dict,
            "entity_type": entity_type,
            "n_clusters": run_dict["n_clusters"],
            "silhouette_score": run_dict["silhouette_score"],
            "inertia": run_dict["inertia"],
            "total_airports": run_dict["total_airports"],
            "total_routes": run_dict["total_routes"],
            "source_flights_count": run_dict["source_flights_count"],
            "centroids": centroids_parsed,
            "feature_columns": [
                "log_flight_count",
                "route_count",
                "avg_distance",
                "avg_elapsed_time",
                "peak_hour_ratio",
                "avg_delay_minutes",
            ],
        }

        return {
            "ready": True,
            "updated_at": updated_at,
            "items": items_parsed,
            "metadata": metadata,
        }

    def clear_all(self) -> int:
        """Delete all cluster results from DB (used for Demo scenario: delete DB -> web shows empty -> run recovers)."""
        if self.is_postgres:
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM cluster_assignments")
                    deleted = cur.rowcount
                    cur.execute("DELETE FROM cluster_centroids")
                    cur.execute("DELETE FROM clustering_runs")
                conn.commit()
        else:
            with self._connect_sqlite() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM cluster_assignments")
                deleted = cur.rowcount
                cur.execute("DELETE FROM cluster_centroids")
                cur.execute("DELETE FROM clustering_runs")
                conn.commit()
        return deleted
