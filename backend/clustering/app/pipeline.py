"""
Clustering Pipeline (STT 11: BE · Clustering).
Loads pre-trained KMeans + StandardScaler + PCA bundle (`models/clustering_bundle.joblib`),
assigns airports and routes to semantic clusters, computes centroids + radar metrics + membership
probabilities, and persists results into DB (`clustering_runs`, `cluster_centroids`, `cluster_assignments`).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import joblib
import numpy as np

from app.config import Settings
from app.db import ClusteringRepository
from app.schemas import PipelineOutput
from app.train import (
    CLUSTER_DEFINITIONS,
    FEATURE_COLS,
    _build_feature_matrix,
    aggregate_features,
    load_flight_rows,
    train_and_save_model,
)

logger = logging.getLogger(__name__)


def _compute_membership_probs(
    x_scaled: np.ndarray,
    centers_scaled: np.ndarray,
    raw_to_semantic: dict[int, int],
) -> tuple[dict[str, float], float]:
    """
    Calculate membership probability (%) for each semantic cluster based on inverse distance
    to centroids in scaled feature space (per Week 8 Clustering lecture).
    """
    dists = np.linalg.norm(centers_scaled - x_scaled, axis=1)
    inv_weights = 1.0 / (dists + 0.15) ** 2
    probs = (inv_weights / np.sum(inv_weights)) * 100.0

    sem_probs: dict[str, float] = {}
    sem_dists: dict[int, float] = {}
    for raw_idx, sem_idx in raw_to_semantic.items():
        sem_probs[f"cluster_{sem_idx}"] = round(float(probs[raw_idx]), 1)
        sem_dists[sem_idx] = round(float(dists[raw_idx]), 3)

    assigned_raw = int(np.argmin(dists))
    assigned_sem = raw_to_semantic[assigned_raw]
    return sem_probs, sem_dists[assigned_sem]


class Pipeline:
    def __init__(self, settings: Settings | None = None, repository: ClusteringRepository | None = None):
        self.settings = settings or Settings()
        self.repository = repository or ClusteringRepository(self.settings.database_url)

    def _load_or_build_bundle(self) -> dict[str, Any]:
        model_path = Path(self.settings.model_path)
        if model_path.exists():
            logger.info("Loading pre-trained clustering model from %s", model_path)
            return joblib.load(model_path)
        logger.info("Model artifact not found at %s; building initial model artifact...", model_path)
        return train_and_save_model(self.settings)

    def _execute_sync(self) -> PipelineOutput:
        bundle = self._load_or_build_bundle()
        scaler = bundle["scaler"]
        kmeans = bundle["kmeans"]
        pca = bundle["pca"]
        raw_to_semantic: dict[int, int] = bundle["raw_to_semantic"]
        k = int(bundle["n_clusters"])

        rows = load_flight_rows(self.settings)
        airports, routes = aggregate_features(rows)

        run_id = str(uuid4())
        created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        all_assignments: list[dict[str, Any]] = []
        airport_by_cluster: dict[int, list[dict[str, Any]]] = {i: [] for i in range(k)}

        for entities in (airports, routes):
            if not entities:
                continue
            X = _build_feature_matrix(entities)
            X_scaled = scaler.transform(X)
            raw_preds = kmeans.predict(X_scaled)
            X_pca = pca.transform(X_scaled)

            for idx, entity in enumerate(entities):
                raw_cid = int(raw_preds[idx])
                sem_cid = int(raw_to_semantic.get(raw_cid, raw_cid))
                cdef = CLUSTER_DEFINITIONS[sem_cid % len(CLUSTER_DEFINITIONS)]
                probs, dist_to_center = _compute_membership_probs(
                    X_scaled[idx],
                    kmeans.cluster_centers_,
                    raw_to_semantic,
                )

                record = {
                    "run_id": run_id,
                    "entity_type": entity["entity_type"],
                    "entity_code": entity["entity_code"],
                    "entity_name": entity["entity_name"],
                    "cluster_id": sem_cid,
                    "cluster_name": cdef["cluster_name"],
                    "short_label": cdef["short_label"],
                    "flight_count": int(entity["flight_count"]),
                    "route_count": int(entity["route_count"]),
                    "avg_distance": float(entity["avg_distance"]),
                    "avg_elapsed_time": float(entity["avg_elapsed_time"]),
                    "peak_hour_ratio": float(entity["peak_hour_ratio"]),
                    "avg_delay_minutes": float(entity["avg_delay_minutes"]),
                    "delay_rate_pct": float(entity["delay_rate_pct"]),
                    "pca_x": round(float(X_pca[idx, 0]), 3),
                    "pca_y": round(float(X_pca[idx, 1]), 3),
                    "distance_to_centroid": dist_to_center,
                    "membership_probabilities_json": json.dumps(probs, ensure_ascii=False),
                }
                all_assignments.append(record)
                if entity["entity_type"] == "airport":
                    airport_by_cluster[sem_cid].append(record)

        # Build cluster centroids and normalized Spider/Radar chart metrics
        centers_orig = scaler.inverse_transform(kmeans.cluster_centers_)
        semantic_to_raw = {sem: raw for raw, sem in raw_to_semantic.items()}
        total_airports = max(1, len(airports))

        raw_stats_per_cluster: list[dict[str, Any]] = []
        for sem_cid in range(k):
            members = airport_by_cluster.get(sem_cid, [])
            raw_cid = semantic_to_raw.get(sem_cid, sem_cid)
            center_vec = centers_orig[raw_cid]

            if members:
                avg_flights = round(float(np.mean([m["flight_count"] for m in members])), 1)
                avg_routes = round(float(np.mean([m["route_count"] for m in members])), 1)
                avg_distance = round(float(np.mean([m["avg_distance"] for m in members])), 1)
                avg_elapsed = round(float(np.mean([m["avg_elapsed_time"] for m in members])), 1)
                peak_ratio = round(float(np.mean([m["peak_hour_ratio"] for m in members])), 1)
                avg_delay = round(float(np.mean([m["avg_delay_minutes"] for m in members])), 1)
                delay_rate = round(float(np.mean([m["delay_rate_pct"] for m in members])), 1)
            else:
                avg_flights = round(float(np.expm1(center_vec[0])), 1)
                avg_routes = round(float(center_vec[1]), 1)
                avg_distance = round(float(center_vec[2]), 1)
                avg_elapsed = round(float(center_vec[3]), 1)
                peak_ratio = round(float(center_vec[4]), 1)
                avg_delay = round(float(center_vec[5]), 1)
                delay_rate = 20.0

            top_airports = [
                m["entity_code"]
                for m in sorted(members, key=lambda x: x["flight_count"], reverse=True)[:6]
            ]

            raw_stats_per_cluster.append({
                "cluster_id": sem_cid,
                "entity_count": len(members),
                "share_pct": round(len(members) / total_airports * 100.0, 1),
                "avg_flights": avg_flights,
                "avg_routes": avg_routes,
                "avg_distance": avg_distance,
                "avg_elapsed_time": avg_elapsed,
                "peak_hour_ratio": peak_ratio,
                "avg_delay_minutes": avg_delay,
                "delay_rate_pct": delay_rate,
                "centroid_vector": {col: round(float(center_vec[i]), 3) for i, col in enumerate(FEATURE_COLS)},
                "top_airports": top_airports,
            })

        # Compute 0-100 radar chart scores across clusters for Spider Chart visualization
        max_flights = max((c["avg_flights"] for c in raw_stats_per_cluster), default=1.0) or 1.0
        max_routes = max((c["avg_routes"] for c in raw_stats_per_cluster), default=1.0) or 1.0
        max_dist = max((c["avg_distance"] for c in raw_stats_per_cluster), default=1.0) or 1.0
        max_peak = max((c["peak_hour_ratio"] for c in raw_stats_per_cluster), default=1.0) or 1.0
        max_delay = max((c["avg_delay_minutes"] for c in raw_stats_per_cluster), default=1.0) or 1.0

        centroids_to_save: list[dict[str, Any]] = []
        for cstat in raw_stats_per_cluster:
            sem_cid = cstat["cluster_id"]
            cdef = CLUSTER_DEFINITIONS[sem_cid % len(CLUSTER_DEFINITIONS)]
            radar = {
                "Lưu lượng bay": round(min(100.0, cstat["avg_flights"] / max_flights * 100.0), 1),
                "Độ phủ tuyến": round(min(100.0, cstat["avg_routes"] / max_routes * 100.0), 1),
                "Cự ly trung bình": round(min(100.0, cstat["avg_distance"] / max_dist * 100.0), 1),
                "Tỷ lệ giờ cao điểm": round(min(100.0, cstat["peak_hour_ratio"] / max_peak * 100.0), 1),
                "Áp lực trễ chuyến": round(min(100.0, cstat["avg_delay_minutes"] / max_delay * 100.0), 1),
            }
            centroids_to_save.append({
                "run_id": run_id,
                "cluster_id": sem_cid,
                "cluster_name": cdef["cluster_name"],
                "short_label": cdef["short_label"],
                "color_code": cdef["color_code"],
                "interpretation": cdef["interpretation"],
                "entity_count": cstat["entity_count"],
                "share_pct": cstat["share_pct"],
                "avg_flights": cstat["avg_flights"],
                "avg_routes": cstat["avg_routes"],
                "avg_distance": cstat["avg_distance"],
                "avg_elapsed_time": cstat["avg_elapsed_time"],
                "peak_hour_ratio": cstat["peak_hour_ratio"],
                "avg_delay_minutes": cstat["avg_delay_minutes"],
                "delay_rate_pct": cstat["delay_rate_pct"],
                "centroid_vector_json": json.dumps(cstat["centroid_vector"], ensure_ascii=False),
                "radar_metrics_json": json.dumps(radar, ensure_ascii=False),
                "top_airports_json": json.dumps(cstat["top_airports"], ensure_ascii=False),
            })

        run_meta = {
            "run_id": run_id,
            "model_version": bundle["model_version"],
            "algorithm": bundle["algorithm"],
            "n_clusters": k,
            "silhouette_score": float(bundle["silhouette_score"]),
            "inertia": float(bundle["inertia"]),
            "total_airports": len(airports),
            "total_routes": len(routes),
            "source_flights_count": len(rows),
            "created_at": created_at,
        }

        self.repository.save_clustering_result(run_meta, centroids_to_save, all_assignments)
        logger.info(
            "Clustering run saved: run_id=%s airports=%d routes=%d silhouette=%.4f",
            run_id,
            len(airports),
            len(routes),
            run_meta["silhouette_score"],
        )

        latest = self.repository.get_latest_clustering(entity_type="airport")
        return PipelineOutput(items=latest["items"], metadata=latest["metadata"])

    async def run(self) -> PipelineOutput:
        return await asyncio.to_thread(self._execute_sync)
