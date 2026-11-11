"""
Offline / On-demand Training & Feature Engineering for Flight Clustering (STT 11).
Can be run standalone:
    python -m app.train
to build and save `models/clustering_bundle.joblib`.
During normal operation (`POST /run`), Pipeline loads the pre-built model artifact without re-training
and clusters the flights stored in PostgreSQL / SQLite (`ingested_flights`).
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import logging
import math
from pathlib import Path
import sqlite3
from typing import Any

import joblib
import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from app.config import Settings

logger = logging.getLogger(__name__)

AIRPORT_NAMES: dict[str, str] = {
    "ATL": "Hartsfield-Jackson Atlanta Intl",
    "DFW": "Dallas/Fort Worth Intl",
    "DEN": "Denver International",
    "ORD": "Chicago O'Hare Intl",
    "LAX": "Los Angeles International",
    "JFK": "John F. Kennedy Intl (New York)",
    "CLT": "Charlotte Douglas Intl",
    "LAS": "Harry Reid Intl (Las Vegas)",
    "MCO": "Orlando International",
    "MIA": "Miami International",
    "PHX": "Phoenix Sky Harbor Intl",
    "SEA": "Seattle-Tacoma Intl",
    "SFO": "San Francisco International",
    "EWR": "Newark Liberty Intl",
    "IAH": "George Bush Intercontinental (Houston)",
    "BOS": "Boston Logan International",
    "MSP": "Minneapolis-St. Paul Intl",
    "FLL": "Fort Lauderdale-Hollywood Intl",
    "LGA": "LaGuardia (New York)",
    "DTW": "Detroit Metropolitan",
    "PHL": "Philadelphia International",
    "SLC": "Salt Lake City Intl",
    "BWI": "Baltimore/Washington Intl",
    "DCA": "Ronald Reagan Washington National",
    "SAN": "San Diego International",
    "IAD": "Washington Dulles Intl",
    "TPA": "Tampa International",
    "BNA": "Nashville International",
    "AUS": "Austin-Bergstrom Intl",
    "MDW": "Chicago Midway Intl",
}

BUSY_HUBS = {"JFK", "ORD", "LAX", "ATL", "DFW", "SFO", "DEN", "EWR", "LGA", "MIA", "CLT", "BOS"}

CLUSTER_DEFINITIONS: list[dict[str, str]] = [
    {
        "cluster_name": "Cụm 0 · Sân bay trục quốc gia (Mega-Hub) áp lực trễ cao",
        "short_label": "Mega-Hub & Áp lực cao",
        "color_code": "#ef4444",
        "interpretation": (
            "Nhóm sân bay trung chuyển huyết mạch có lưu lượng chuyến bay và số tuyến kết nối rất lớn. "
            "Mật độ khai thác dày đặc vào khung giờ cao điểm (15:00–21:00) khiến nhóm này nhạy cảm với trễ dây chuyền."
        ),
    },
    {
        "cluster_name": "Cụm 1 · Tuyến & Sân bay đường dài xuyên lục địa (Long-Haul)",
        "short_label": "Đường dài xuyên lục địa",
        "color_code": "#0b9d87",
        "interpretation": (
            "Nhóm sân bay và hành trình có cự ly trung bình xa và thời gian bay kéo dài (kết nối hai bờ Đông–Tây hoặc hải đảo). "
            "Số lượng chuyến vừa phải nhưng yêu cầu điều phối thời gian quay đầu tàu bay dài."
        ),
    },
    {
        "cluster_name": "Cụm 2 · Sân bay thương mại tầm trung nhịp độ ổn định",
        "short_label": "Thương mại tầm trung",
        "color_code": "#3b82f6",
        "interpretation": (
            "Nhóm sân bay đô thị quy mô vừa với lưu lượng khai thác ổn định, cự ly bay trung bình (600–1.000 dặm) "
            "và mức độ trễ nằm trong ngưỡng kiểm soát."
        ),
    },
    {
        "cluster_name": "Cụm 3 · Sân bay khu vực chặng ngắn (Regional Spoke) đúng giờ cao",
        "short_label": "Chặng ngắn · Đúng giờ cao",
        "color_code": "#8b5cf6",
        "interpretation": (
            "Nhóm sân bay vệ tinh/địa phương phục vụ các chặng bay ngắn kết nối vào Hub gần nhất. "
            "Mật độ đường băng thông thoáng giúp thời gian chờ thấp và tỷ lệ đúng giờ cao."
        ),
    },
]


def _normalize_date(raw: Any) -> str:
    if not raw:
        return "2025-01-06"
    s = str(raw).strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return s
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s[:10]


def _estimate_row_delay(origin: str, dest: str, dep_hour: int, distance: float, key: str) -> float:
    """Canonical deterministic delay calculation matching data-simulator and ingestion."""
    digest = int(hashlib.md5(key.encode("utf-8")).hexdigest()[:8], 16)
    bucket = digest % 100
    hub_boost = (8 if origin in BUSY_HUBS else 0) + (5 if dest in BUSY_HUBS else 0)
    hour_boost = 12 if 15 <= dep_hour <= 21 else (5 if 11 <= dep_hour <= 14 else 0)
    dist_boost = 4 if distance >= 1800 else 0
    threshold = 74 - hub_boost - hour_boost - dist_boost
    if bucket < threshold:
        return float(digest % 12)
    if bucket < threshold + 18:
        return float(15 + (digest % 28))
    return float(45 + (digest % 75))


def load_flight_rows(settings: Settings) -> list[dict[str, Any]]:
    """
    Load flight rows from the shared database (`ingested_flights`) first.
    Uses DB rows whenever there are enough distinct origin airports to form clusters.
    Falls back to local CSV only for standalone offline training when DB is empty.
    """
    rows: list[dict[str, Any]] = []
    src_url = settings.source_database_url
    try:
        if src_url.startswith(("postgresql://", "postgres://")):
            import psycopg
            from psycopg.rows import dict_row
            with psycopg.connect(src_url, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT origin, dest, dep_hour, crs_elapsed_time, distance, delay_minutes "
                        "FROM ingested_flights LIMIT %s",
                        (settings.max_sample_rows,),
                    )
                    rows = [dict(r) for r in cur.fetchall()]
        elif src_url.startswith("sqlite:///"):
            db_path = Path(src_url.replace("sqlite:///", "")).resolve()
            if db_path.exists():
                with sqlite3.connect(str(db_path)) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT origin, dest, dep_hour, crs_elapsed_time, distance, delay_minutes "
                        "FROM ingested_flights LIMIT ?",
                        (settings.max_sample_rows,),
                    )
                    rows = [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.debug("Could not read rows from source DB (%s): %s", src_url, exc)

    unique_origins = {r["origin"] for r in rows if r.get("origin")}
    if len(unique_origins) >= settings.n_clusters:
        return rows

    csv_path = Path(settings.fallback_csv_path)
    if not csv_path.exists():
        if rows:
            return rows
        raise RuntimeError(
            f"Database `ingested_flights` has insufficient airports ({len(unique_origins)}) "
            f"and no fallback CSV exists at {csv_path}. Run Ingestion first."
        )

    logger.info(
        "DB has %d rows (%d unique origins); reading offline training dataset from %s",
        len(rows),
        len(unique_origins),
        csv_path,
    )
    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for idx, r in enumerate(reader):
            if idx >= settings.max_sample_rows:
                break
            origin = str(r.get("ORIGIN") or r.get("Origin") or "").strip().upper()
            dest = str(r.get("DEST") or r.get("Dest") or "").strip().upper()
            if not origin or not dest:
                continue
            fl_date = _normalize_date(r.get("FL_DATE") or r.get("FlightDate"))
            carrier = str(r.get("OP_UNIQUE_CARRIER") or r.get("Reporting_Airline") or "").strip().upper()
            fl_num = str(r.get("OP_CARRIER_FL_NUM") or r.get("Flight_Number_Reporting_Airline") or idx).strip().split(".")[0]
            raw_dep = str(r.get("CRS_DEP_TIME") or r.get("CRSDepTime") or "0").strip().split(".")[0].replace(":", "")
            crs_dep_padded = f"{int(raw_dep):04d}" if raw_dep.isdigit() else "0000"
            dep_hour = min(23, max(0, int(crs_dep_padded[:2])))
            distance = float(r.get("DISTANCE") or r.get("Distance") or 0.0)
            elapsed = float(r.get("CRS_ELAPSED_TIME") or r.get("CRSElapsedTime") or 0.0)
            key = f"{fl_date}_{carrier}_{fl_num}_{origin}_{dest}_{crs_dep_padded}"

            dep_del = r.get("DepDel15") or r.get("DEP_DEL15")
            if dep_del is not None and str(dep_del).strip() != "":
                hval = int(hashlib.md5(key.encode("utf-8")).hexdigest()[:8], 16)
                delay = float(15 + (hval % 55)) if str(dep_del).strip() in ("1", "1.0") else float(hval % 12)
            else:
                delay = _estimate_row_delay(origin, dest, dep_hour, distance, key)
            rows.append({
                "origin": origin,
                "dest": dest,
                "dep_hour": dep_hour,
                "crs_elapsed_time": elapsed,
                "distance": distance,
                "delay_minutes": delay,
            })
    return rows


def aggregate_features(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Aggregate operational features per airport and per top route."""
    airport_buckets: dict[str, dict[str, Any]] = {}
    route_buckets: dict[str, dict[str, Any]] = {}

    for r in rows:
        origin = r["origin"]
        dest = r["dest"]
        dep_hour = int(r.get("dep_hour") or 0)
        dist = float(r.get("distance") or 0.0)
        elapsed = float(r.get("crs_elapsed_time") or 0.0)
        delay = float(r.get("delay_minutes") or 0.0)
        is_peak = 1 if 15 <= dep_hour <= 21 else 0
        is_delayed = 1 if delay >= 15.0 else 0

        ab = airport_buckets.setdefault(
            origin,
            {"count": 0, "dests": set(), "dist_sum": 0.0, "elap_sum": 0.0, "peak_sum": 0, "delay_sum": 0.0, "delayed_cnt": 0},
        )
        ab["count"] += 1
        ab["dests"].add(dest)
        ab["dist_sum"] += dist
        ab["elap_sum"] += elapsed
        ab["peak_sum"] += is_peak
        ab["delay_sum"] += delay
        ab["delayed_cnt"] += is_delayed

        route_code = f"{origin} → {dest}"
        rb = route_buckets.setdefault(
            route_code,
            {"origin": origin, "dest": dest, "count": 0, "dist_sum": 0.0, "elap_sum": 0.0, "peak_sum": 0, "delay_sum": 0.0, "delayed_cnt": 0},
        )
        rb["count"] += 1
        rb["dist_sum"] += dist
        rb["elap_sum"] += elapsed
        rb["peak_sum"] += is_peak
        rb["delay_sum"] += delay
        rb["delayed_cnt"] += is_delayed

    # Adapt minimum flight threshold to dataset size so clustering works on both 100-row streaming windows and 60k-row datasets
    min_airport_cnt = 5 if len(rows) >= 1000 else 1
    min_route_cnt = 3 if len(rows) >= 1000 else 1

    airport_entities: list[dict[str, Any]] = []
    for code, b in airport_buckets.items():
        cnt = b["count"]
        if cnt < min_airport_cnt:
            continue
        airport_entities.append({
            "entity_type": "airport",
            "entity_code": code,
            "entity_name": AIRPORT_NAMES.get(code, f"Airport {code}"),
            "flight_count": cnt,
            "log_flight_count": math.log1p(cnt),
            "route_count": len(b["dests"]),
            "avg_distance": round(b["dist_sum"] / cnt, 1),
            "avg_elapsed_time": round(b["elap_sum"] / cnt, 1),
            "peak_hour_ratio": round(b["peak_sum"] / cnt * 100.0, 1),
            "avg_delay_minutes": round(b["delay_sum"] / cnt, 1),
            "delay_rate_pct": round(b["delayed_cnt"] / cnt * 100.0, 1),
        })

    sorted_routes = sorted(route_buckets.items(), key=lambda kv: kv[1]["count"], reverse=True)[:120]
    route_entities: list[dict[str, Any]] = []
    for rcode, b in sorted_routes:
        cnt = b["count"]
        if cnt < min_route_cnt:
            continue
        route_entities.append({
            "entity_type": "route",
            "entity_code": rcode,
            "entity_name": f"Tuyến {b['origin']} đi {b['dest']}",
            "flight_count": cnt,
            "log_flight_count": math.log1p(cnt),
            "route_count": 1,
            "avg_distance": round(b["dist_sum"] / cnt, 1),
            "avg_elapsed_time": round(b["elap_sum"] / cnt, 1),
            "peak_hour_ratio": round(b["peak_sum"] / cnt * 100.0, 1),
            "avg_delay_minutes": round(b["delay_sum"] / cnt, 1),
            "delay_rate_pct": round(b["delayed_cnt"] / cnt * 100.0, 1),
        })

    return airport_entities, route_entities


FEATURE_COLS = [
    "log_flight_count",
    "route_count",
    "avg_distance",
    "avg_elapsed_time",
    "peak_hour_ratio",
    "avg_delay_minutes",
]


def _build_feature_matrix(entities: list[dict[str, Any]]) -> np.ndarray:
    return np.array([[float(e[c]) for c in FEATURE_COLS] for e in entities], dtype=np.float64)


def train_and_save_model(settings: Settings | None = None) -> dict[str, Any]:
    """Train StandardScaler + KMeans + PCA on airport features and save artifact to disk."""
    settings = settings or Settings()
    rows = load_flight_rows(settings)
    airports, _ = aggregate_features(rows)
    if len(airports) < settings.n_clusters:
        raise ValueError(f"Not enough airports ({len(airports)}) to fit {settings.n_clusters} clusters.")

    X = _build_feature_matrix(airports)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    k = settings.n_clusters
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=15)
    raw_labels = kmeans.fit_predict(X_scaled)
    sil_score = float(silhouette_score(X_scaled, raw_labels)) if len(airports) > k else 0.0

    pca = PCA(n_components=2, random_state=42)
    pca.fit(X_scaled)

    centers_orig = scaler.inverse_transform(kmeans.cluster_centers_)
    remaining = set(range(k))

    hub_raw = max(remaining, key=lambda idx: centers_orig[idx][0] * 1.5 + centers_orig[idx][1])
    remaining.remove(hub_raw)

    long_haul_raw = max(remaining, key=lambda idx: centers_orig[idx][2]) if remaining else 0
    remaining.discard(long_haul_raw)

    short_haul_raw = min(remaining, key=lambda idx: centers_orig[idx][2] + centers_orig[idx][0] * 100) if remaining else 0
    remaining.discard(short_haul_raw)

    ordered_raw = [hub_raw, long_haul_raw, *sorted(remaining), short_haul_raw][:k]
    raw_to_semantic = {raw_idx: sem_idx for sem_idx, raw_idx in enumerate(ordered_raw)}

    bundle = {
        "model_version": "kmeans-v1.1",
        "algorithm": "KMeans + StandardScaler + PCA(2D)",
        "n_clusters": k,
        "feature_cols": FEATURE_COLS,
        "scaler": scaler,
        "kmeans": kmeans,
        "pca": pca,
        "raw_to_semantic": raw_to_semantic,
        "silhouette_score": round(sil_score, 4),
        "inertia": round(float(kmeans.inertia_), 2),
        "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "training_flights_count": len(rows),
        "training_airports_count": len(airports),
    }

    model_path = Path(settings.model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, model_path)
    logger.info(
        "Saved clustering model bundle to %s (airports=%d, silhouette=%.4f)",
        model_path,
        len(airports),
        sil_score,
    )
    return bundle


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    train_and_save_model()
