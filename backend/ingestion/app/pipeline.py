"""
Ingestion Pipeline:
1. Pull sliding-window flight batch from data-simulator API (with local CSV fallback only when running standalone).
2. Validate, normalize, and enrich flight records using canonical flight_key and delay values from simulator.
3. Deduplicate on natural flight_key and persist to database via asyncio.to_thread + executemany.
4. Optionally trigger downstream services (analytics, prediction) asynchronously when new flights arrive.
"""
from __future__ import annotations

import asyncio
import csv
from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from app.config import Settings
from app.db import FlightRepository
from app.schedule import Flight, ReplayPosition
from app.schemas import PipelineOutput

logger = logging.getLogger(__name__)

CARRIER_NAMES: dict[str, str] = {
    "AA": "American Airlines",
    "AS": "Alaska Airlines",
    "B6": "JetBlue Airways",
    "DL": "Delta Air Lines",
    "F9": "Frontier Airlines",
    "G4": "Allegiant Air",
    "HA": "Hawaiian Airlines",
    "NK": "Spirit Airlines",
    "OO": "SkyWest Airlines",
    "UA": "United Airlines",
    "WN": "Southwest Airlines",
    "YX": "Republic Airways",
    "MQ": "Envoy Air",
    "OH": "PSA Airlines",
    "9E": "Endeavor Air",
}

BUSY_HUBS = {"JFK", "ORD", "LAX", "ATL", "DFW", "SFO", "DEN", "EWR", "LGA", "MIA", "CLT", "BOS"}


def _format_hhmm(raw: Any) -> tuple[str | None, int | None]:
    if raw is None:
        return None, None
    s = str(raw).strip().split(".")[0].replace(":", "")
    if not s or not s.isdigit():
        return None, None
    padded = f"{int(s):04d}"
    hh = min(23, max(0, int(padded[:2])))
    mm = min(59, max(0, int(padded[2:])))
    return f"{hh:02d}:{mm:02d}", hh


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


def _estimate_delay(
    flight_key: str,
    origin: str,
    dest: str,
    dep_hour: int | None,
    distance: float,
    raw_row: dict[str, Any],
) -> tuple[float, str, int]:
    """
    Use DELAY_MINUTES / ARR_DELAY / DEP_DELAY provided by data-simulator;
    otherwise compute canonical deterministic delay from normalized flight_key.
    """
    for col in ("DELAY_MINUTES", "ARR_DELAY", "DEP_DELAY", "delay_minutes"):
        val = raw_row.get(col)
        if val is not None and str(val).strip() != "":
            try:
                d = round(max(0.0, float(val)), 1)
                status = "severe_delay" if d >= 45 else "moderate_delay" if d >= 15 else "on_time"
                return d, status, 1 if d >= 15 else 0
            except ValueError:
                pass

    digest = int(hashlib.md5(flight_key.encode("utf-8")).hexdigest()[:8], 16)
    bucket = digest % 100

    hub_boost = (8 if origin in BUSY_HUBS else 0) + (5 if dest in BUSY_HUBS else 0)
    hour_boost = 12 if (dep_hour is not None and 15 <= dep_hour <= 21) else (5 if (dep_hour is not None and 11 <= dep_hour <= 14) else 0)
    dist_boost = 4 if distance >= 1800 else 0
    threshold = 74 - hub_boost - hour_boost - dist_boost

    if bucket < threshold:
        delay = float(digest % 12)
        return delay, "on_time", 0
    if bucket < threshold + 18:
        delay = float(15 + (digest % 28))
        return delay, "moderate_delay", 1
    delay = float(45 + (digest % 75))
    return delay, "severe_delay", 1


def normalize_record(raw: dict[str, Any], fetched_at: str, ingested_at: str) -> dict[str, Any] | None:
    fl_date = _normalize_date(raw.get("FL_DATE"))
    carrier = str(raw.get("OP_UNIQUE_CARRIER") or "").strip().upper()
    fl_num = str(raw.get("OP_CARRIER_FL_NUM") or "").strip().split(".")[0]
    origin = str(raw.get("ORIGIN") or "").strip().upper()
    dest = str(raw.get("DEST") or "").strip().upper()

    if not carrier or not fl_num or not origin or not dest:
        return None

    crs_dep_fmt, dep_hour = _format_hhmm(raw.get("CRS_DEP_TIME"))
    crs_arr_fmt, _ = _format_hhmm(raw.get("CRS_ARR_TIME"))
    crs_dep_raw = (crs_dep_fmt or "00:00").replace(":", "")

    flight_key = str(raw.get("FLIGHT_KEY") or f"{fl_date}_{carrier}_{fl_num}_{origin}_{dest}_{crs_dep_raw}")
    distance = float(raw.get("DISTANCE") or 0.0)
    elapsed = float(raw.get("CRS_ELAPSED_TIME") or 0.0)
    delay_minutes, delay_status, is_delayed = _estimate_delay(
        flight_key=flight_key,
        origin=origin,
        dest=dest,
        dep_hour=dep_hour,
        distance=distance,
        raw_row=raw,
    )

    def _opt_int(val: Any) -> int | None:
        if val is None or str(val).strip() == "":
            return None
        try:
            return int(float(val))
        except ValueError:
            return None

    tail_num = str(raw.get("TAIL_NUM") or "").strip() or None

    return {
        "flight_key": flight_key,
        "fl_date": fl_date,
        "day_of_week": _opt_int(raw.get("DAY_OF_WEEK")),
        "op_unique_carrier": carrier,
        "carrier_name": CARRIER_NAMES.get(carrier, f"Carrier {carrier}"),
        "tail_num": tail_num,
        "op_carrier_fl_num": fl_num,
        "flight_code": f"{carrier} {fl_num}",
        "origin_airport_id": _opt_int(raw.get("ORIGIN_AIRPORT_ID")),
        "origin": origin,
        "dest_airport_id": _opt_int(raw.get("DEST_AIRPORT_ID")),
        "dest": dest,
        "route": f"{origin} → {dest}",
        "crs_dep_time": crs_dep_fmt or "00:00",
        "crs_arr_time": crs_arr_fmt or "00:00",
        "dep_hour": dep_hour if dep_hour is not None else 0,
        "crs_elapsed_time": elapsed,
        "distance": distance,
        "delay_minutes": delay_minutes,
        "delay_status": delay_status,
        "is_delayed": is_delayed,
        "fetched_at": fetched_at,
        "ingested_at": ingested_at,
    }


class Pipeline:
    def __init__(self, settings: Settings | None = None, repository: FlightRepository | None = None):
        self.settings = settings or Settings()
        self.repository = repository or FlightRepository(self.settings.database_url)
        self._fallback_cursor = 0

    async def _fetch_from_simulator(self) -> tuple[dict[str, Any], ReplayPosition | None]:
        base_url = self.settings.simulator_base_url.strip().rstrip("/")
        if not base_url:
            raise ValueError("SIMULATOR_BASE_URL is empty")
        url = f"{base_url}/flights"
        params = {
            "window_size": self.settings.simulator_window_size,
            "slide_step": self.settings.simulator_slide_step,
        }
        start = None
        if self.repository.has_schedule:
            start = await asyncio.to_thread(self.repository.simulator_offset, base_url)
            params = {"start": start, "window_size": self.settings.ingestion_batch_size}
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
        payload["source"] = f"simulator ({url})"
        if start is None:
            return payload, None

        total = payload["total"]
        size = len(payload["data"])
        if total <= 0 or payload["window_start"] != start % total or size != min(total, params["window_size"]):
            raise ValueError("Simulator did not honor the requested cursor and batch size")
        return payload, ReplayPosition(base_url, start, (start + size) % total)

    def _fetch_from_fallback_csv(self) -> dict[str, Any]:
        csv_path = Path(self.settings.fallback_csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(f"Neither simulator nor fallback CSV found at {csv_path}")

        if self.repository.has_schedule:
            window_size = slide_step = self.settings.ingestion_batch_size
        else:
            window_size = self.settings.simulator_window_size
            slide_step = self.settings.simulator_slide_step
        start = self._fallback_cursor
        end = start + window_size
        rows: list[dict[str, Any]] = []

        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                if idx < start:
                    continue
                if idx >= end:
                    break
                rows.append(row)

        if not rows and start > 0:
            self._fallback_cursor = 0
            return self._fetch_from_fallback_csv()

        return {
            "source": f"csv-fallback ({csv_path.name})",
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window_start": start,
            "window_end": start + len(rows),
            "window_size": len(rows),
            "slide_step": slide_step,
            "data": rows,
        }

    async def _notify_downstream(self) -> None:
        raw_urls = self.settings.trigger_downstream_urls.strip()
        if not raw_urls:
            return
        urls = [u.strip() for u in raw_urls.split(",") if u.strip()]
        if not urls:
            return
        async with httpx.AsyncClient(timeout=15.0) as client:
            for url in urls:
                try:
                    resp = await client.post(url)
                    logger.info("Triggered downstream service %s -> HTTP %s", url, resp.status_code)
                except Exception as exc:
                    logger.debug("Downstream trigger %s skipped: %s", url, exc)

    async def run(self) -> PipelineOutput:
        replay = None
        using_csv = False
        try:
            payload, replay = await self._fetch_from_simulator()
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Simulator unreachable (%s); falling back to local CSV sliding window.", exc)
            payload = await asyncio.to_thread(self._fetch_from_fallback_csv)
            using_csv = True

        fetched_at = payload.get("fetched_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ingested_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        raw_items = payload.get("data") or []

        normalized: list[dict[str, Any]] = []
        scheduled: list[Flight] = []
        seen_in_batch: set[str] = set()
        for raw in raw_items:
            rec = normalize_record(raw, fetched_at=fetched_at, ingested_at=ingested_at)
            if rec and self.repository.has_schedule and (
                replay is not None or (raw.get("ORIGIN_AIRPORT_SEQ_ID") and raw.get("DEST_AIRPORT_SEQ_ID"))
            ):
                schedule_record = {key: None if value == "" else value for key, value in raw.items()}
                scheduled.append(Flight.model_validate(schedule_record | {
                    "FL_DATE": rec["fl_date"], "OP_CARRIER_FL_NUM": rec["op_carrier_fl_num"],
                }))
            if rec and rec["flight_key"] not in seen_in_batch:
                seen_in_batch.add(rec["flight_key"])
                normalized.append(rec)

        batch_meta = {
            "batch_id": str(uuid4()),
            "source": payload.get("source", "simulator"),
            "fetched_at": fetched_at,
            "window_start": payload.get("window_start", 0),
            "window_end": payload.get("window_end", len(normalized)),
            "created_at": ingested_at,
        }

        counts = await asyncio.to_thread(self.repository.insert_batch, normalized, batch_meta, tuple(scheduled), replay)
        if using_csv:
            self._fallback_cursor = payload["window_start"] + payload["slide_step"]
        logger.info(
            "Ingestion batch completed: source=%s window=[%s..%s] received=%d inserted=%d duplicates=%d total_stored=%d",
            batch_meta["source"],
            batch_meta["window_start"],
            batch_meta["window_end"],
            counts["received_count"],
            counts["inserted_count"],
            counts["duplicate_count"],
            counts["total_stored"],
        )

        if counts["inserted_count"] > 0:
            asyncio.create_task(self._notify_downstream())

        queried = await asyncio.to_thread(self.repository.query_flights, limit=200, offset=0)
        return PipelineOutput(
            items=queried["items"],
            metadata=queried["metadata"],
        )
