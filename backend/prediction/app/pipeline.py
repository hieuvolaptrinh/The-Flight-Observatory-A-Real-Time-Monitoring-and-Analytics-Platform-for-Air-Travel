"""
Prediction & Classification Pipeline (STT 12 & STT 13).
Loads pre-trained regression and classification model bundle (`models/prediction_bundle.joblib`),
reads active flights from database or data simulator, performs inference on delay minutes & risk probability,
and returns structured predictions for the frontend dashboard.
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

import joblib
import numpy as np

from app.config import Settings
from app.schemas import PipelineOutput
from app.train import (
    FEATURE_NAMES,
    _extract_features_row,
    train_and_save_model,
)

logger = logging.getLogger(__name__)


def _enrich_flight_weather(flight: dict[str, Any]) -> dict[str, Any]:
    """
    Enrich flight candidate with realistic weather based on origin airport geography and season.
    Preserves existing weather fields if already present and non-empty.
    """
    if flight.get("temperature_c") is not None and flight.get("wind_speed_kmh") is not None and flight.get("precipitation_mm") is not None:
        return flight

    origin = str(flight.get("origin") or "JFK").upper()
    dep_hour = int(flight.get("dep_hour") or 12)
    fl_code = str(flight.get("flight_code") or origin)

    # Deterministic pseudo-random seed based on flight identity
    seed = int(hashlib.md5(f"{origin}_{dep_hour}_{fl_code}".encode()).hexdigest()[:6], 16)

    cold_hubs = {"ORD", "JFK", "EWR", "BOS", "DEN", "MSP", "DTW", "SEA", "DSM"}
    warm_hubs = {"MIA", "FLL", "MCO", "TPA", "PHX", "LAX", "SAN", "HNL"}

    if origin in cold_hubs:
        base_temp = -4.0 + (seed % 10)         # -4 to +5 C
        wind_speed = 14.0 + (seed % 28)        # 14 to 41 km/h
        has_snow_fog = (seed % 10) < 3         # 30% winter storm / fog probability
        visibility = 2.0 + (seed % 5) * 0.8 if has_snow_fog else 14.0 + (seed % 5)
        precip = 1.8 + (seed % 5) * 0.6 if has_snow_fog else 0.0
    elif origin in warm_hubs:
        base_temp = 18.0 + (seed % 10)         # 18 to 27 C
        wind_speed = 8.0 + (seed % 16)         # 8 to 23 km/h
        has_rain = (seed % 10) < 2             # 20% convective shower probability
        visibility = 4.0 + (seed % 4) if has_rain else 16.0
        precip = 2.0 + (seed % 4) * 0.8 if has_rain else 0.0
    else:
        # Central hubs (CLT, DFW, ATL, AUS, LAS, PHL, SFO)
        base_temp = 8.0 + (seed % 12)          # 8 to 19 C
        wind_speed = 10.0 + (seed % 22)        # 10 to 31 km/h
        has_rain = (seed % 10) < 2
        visibility = 3.5 + (seed % 4) if has_rain else 16.0
        precip = 1.5 + (seed % 4) * 0.6 if has_rain else 0.0

    wind_gust = wind_speed + (seed % 16) if wind_speed > 24.0 else 0.0
    pressure = 1010.0 + (seed % 15)

    flight["temperature_c"] = round(base_temp, 1)
    flight["wind_speed_kmh"] = round(wind_speed, 1)
    flight["wind_gust_kmh"] = round(wind_gust, 1)
    flight["visibility_km"] = round(visibility, 1)
    flight["precipitation_mm"] = round(precip, 1)
    flight["pressure_hpa"] = round(pressure, 1)
    return flight


class Pipeline:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self._bundle: dict[str, Any] | None = None

    def _load_or_build_bundle(self) -> dict[str, Any]:
        """Load pre-trained model bundle from disk; build initial artifact if not present."""
        if self._bundle is not None:
            return self._bundle

        model_path = Path(self.settings.model_path)
        if model_path.exists():
            logger.info("Loading pre-trained prediction bundle from %s", model_path)
            self._bundle = joblib.load(model_path)
            return self._bundle

        logger.info("Prediction model artifact not found at %s; training initial model...", model_path)
        self._bundle = train_and_save_model(self.settings)
        return self._bundle

    def _load_candidate_flights_sync(self) -> list[dict[str, Any]]:
        """
        Load candidate flights for inference from PostgreSQL or SQLite `ingested_flights`.
        Falls back to the first 100 rows of the CSV dataset if DB is not populated yet.
        """
        rows: list[dict[str, Any]] = []
        src_url = self.settings.source_database_url

        try:
            if src_url.startswith(("postgresql://", "postgres://")):
                import psycopg
                from psycopg.rows import dict_row

                with psycopg.connect(src_url, row_factory=dict_row) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT flight_code, op_unique_carrier, origin, dest,
                                   crs_dep_time, dep_hour, day_of_week, distance,
                                   crs_elapsed_time, delay_minutes
                            FROM ingested_flights
                            ORDER BY ingested_at DESC
                            LIMIT 150
                            """
                        )
                        rows = [dict(r) for r in cur.fetchall()]
            elif src_url.startswith("sqlite:///"):
                db_path = Path(src_url.replace("sqlite:///", "")).resolve()
                if db_path.exists():
                    with sqlite3.connect(str(db_path)) as conn:
                        conn.row_factory = sqlite3.Row
                        cur = conn.cursor()
                        cur.execute(
                            """
                            SELECT flight_code, op_unique_carrier, origin, dest,
                                   crs_dep_time, dep_hour, day_of_week, distance,
                                   crs_elapsed_time, delay_minutes
                            FROM ingested_flights
                            ORDER BY rowid DESC
                            LIMIT 150
                            """
                        )
                        rows = [dict(r) for r in cur.fetchall()]
        except Exception as exc:
            logger.debug("Could not read candidate flights from DB (%s): %s", src_url, exc)

        if rows:
            return [_enrich_flight_weather(r) for r in rows]

        # Fallback to local CSV if DB has no flights yet
        csv_path = Path(self.settings.fallback_csv_path)
        if not csv_path.exists():
            return []

        logger.info("Candidate DB empty; loading initial inference batch from CSV: %s", csv_path.name)
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for idx, r in enumerate(reader):
                if idx >= 60:
                    break
                origin = str(r.get("Origin") or r.get("ORIGIN") or "").strip().upper()
                dest = str(r.get("Dest") or r.get("DEST") or "").strip().upper()
                carrier = str(r.get("Reporting_Airline") or r.get("OP_UNIQUE_CARRIER") or "").strip().upper()
                fl_num = str(r.get("Flight_Number_Reporting_Airline") or r.get("OP_CARRIER_FL_NUM") or idx).strip().split(".")[0]
                crs_dep = str(r.get("CRSDepTime") or r.get("CRS_DEP_TIME") or "0000").strip().split(".")[0].replace(":", "").zfill(4)
                dep_fmt = f"{crs_dep[:2]}:{crs_dep[2:4]}" if len(crs_dep) >= 4 else "00:00"

                rows.append({
                    "flight_code": f"{carrier} {fl_num}",
                    "op_unique_carrier": carrier,
                    "origin": origin,
                    "dest": dest,
                    "crs_dep_time": dep_fmt,
                    "dep_hour": min(23, max(0, int(crs_dep[:2]))),
                    "day_of_week": float(r.get("DayOfWeek") or r.get("DAY_OF_WEEK") or 1),
                    "distance": float(r.get("Distance") or r.get("DISTANCE") or 500.0),
                    "crs_elapsed_time": float(r.get("CRSElapsedTime") or r.get("CRS_ELAPSED_TIME") or 90.0),
                    "temperature_c": float(r.get("temperature_c") or 15.0),
                    "wind_speed_kmh": float(r.get("wind_speed_kmh") or 10.0),
                    "visibility_km": float(r.get("visibility_km") or 16.0),
                })
        return [_enrich_flight_weather(r) for r in rows]

    def _execute_inference_sync(self) -> PipelineOutput:
        bundle = self._load_or_build_bundle()
        scaler = bundle["scaler"]
        regressor = bundle["regressor"]
        classifier = bundle["classifier"]

        candidates = self._load_candidate_flights_sync()
        if not candidates:
            logger.warning("No candidate flights available for prediction.")
            return PipelineOutput(
                items=[],
                metadata={
                    "model_version": bundle.get("model_version", "prediction-v1.0"),
                    "ready": False,
                    "total_predicted": 0,
                },
            )

        # Build feature matrix for inference
        X_infer = np.array([_extract_features_row(c) for c in candidates], dtype=np.float64)
        X_infer_scaled = scaler.transform(X_infer)

        # Continuous delay predictions (minutes)
        raw_delays = regressor.predict(X_infer_scaled)
        # Probability of delay >= 15 min (percentage 0-100)
        raw_probs = classifier.predict_proba(X_infer_scaled)[:, 1] * 100.0

        items: list[dict[str, Any]] = []
        high_cnt = 0
        med_cnt = 0
        low_cnt = 0

        for idx, c in enumerate(candidates):
            delay_val = round(max(0.0, float(raw_delays[idx])), 1)
            prob_val = round(float(np.clip(raw_probs[idx], 5.0, 95.0)), 1)

            risk_level = "high" if prob_val >= 60.0 else ("medium" if prob_val >= 30.0 else "low")
            if risk_level == "high":
                high_cnt += 1
            elif risk_level == "medium":
                med_cnt += 1
            else:
                low_cnt += 1

            items.append({
                "flight": c.get("flight_code", "FL 000"),
                "carrier": c.get("op_unique_carrier", "AA"),
                "origin": c.get("origin", "JFK"),
                "destination": c.get("dest", "LAX"),
                "time": str(c.get("crs_dep_time", "12:00")),
                "delay": delay_val,
                "probability": prob_val,
                "risk_level": risk_level,
                "weather": {
                    "temperature_c": round(float(X_infer[idx][6]), 1),
                    "wind_speed_kmh": round(float(X_infer[idx][7]), 1),
                    "visibility_km": round(float(X_infer[idx][9]), 1),
                },
            })

        total = len(items)
        avg_delay = round(float(np.mean([item["delay"] for item in items])), 1) if items else 0.0
        avg_prob = round(float(np.mean([item["probability"] for item in items])), 1) if items else 0.0

        # Persist predictions and classification labels to PostgreSQL analytics.flight_predictions
        try:
            db_url = self.settings.database_url or self.settings.source_database_url
            if db_url and db_url.startswith(("postgresql://", "postgres://")):
                import json
                import psycopg

                with psycopg.connect(db_url) as conn:
                    with conn.cursor() as cur:
                        cur.executemany(
                            """
                            INSERT INTO analytics.flight_predictions (
                                flight_code, carrier, origin, destination,
                                dep_time, predicted_delay_minutes, delay_probability,
                                risk_level, weather_json, evaluated_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP);
                            """,
                            [
                                (
                                    item["flight"],
                                    item["carrier"],
                                    item["origin"],
                                    item["destination"],
                                    item["time"],
                                    item["delay"],
                                    item["probability"],
                                    item["risk_level"],
                                    json.dumps(item["weather"]),
                                )
                                for item in items
                            ],
                        )
                    conn.commit()
                logger.info("Successfully persisted %d classified flight predictions to PostgreSQL analytics.flight_predictions", len(items))
        except Exception as exc:
            logger.warning("Could not persist predictions to PostgreSQL: %s", exc)

        metadata = {
            "model_version": bundle.get("model_version", "prediction-v1.0"),
            "algorithm_regression": "HistGradientBoostingRegressor",
            "algorithm_classification": "HistGradientBoostingClassifier",
            "feature_names": FEATURE_NAMES,
            "trained_at": bundle.get("trained_at"),
            "training_samples": bundle.get("training_samples", 0),
            "model_metrics": bundle.get("metrics", {}),
            "total_predicted": total,
            "avg_predicted_delay": avg_delay,
            "mean_probability": avg_prob,
            "risk_counts": {
                "high": high_cnt,
                "medium": med_cnt,
                "low": low_cnt,
            },
            "evaluated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ready": True,
        }

        return PipelineOutput(items=items, metadata=metadata)

    async def run(self) -> PipelineOutput:
        """Run ML inference off the asyncio event loop."""
        return await asyncio.to_thread(self._execute_inference_sync)
