import asyncio
import json
import logging
from datetime import datetime, timedelta
from statistics import median

import httpx
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
STANDARD_OBSERVED_DAYS = 5


class Estimate(BaseModel):
    predicted_flight_count: int = Field(ge=0)
    explanation: str = Field(min_length=1, max_length=800)


async def ask_gemini(settings, history, target, airports):
    key = settings.gemini_api_key
    if not key or not key.get_secret_value():
        raise HTTPException(503, "Configure GEMINI_API_KEY in the Analytics environment")
    prompt = (
        "Estimate tomorrow's departure count for the listed airports at the same observed schedule coverage. "
        "These partial schedule counts do not measure total airport traffic or actual departures. "
        "With fewer than five observed days, describe the estimate as provisional and avoid claiming a trend. "
        "Treat unlisted days as unknown. Give a non-negative whole count and a short Vietnamese explanation "
        "that states the coverage limitation. Use only the supplied counts.\n"
        + json.dumps({"forecast_date": target.isoformat(), "airports": airports, "history": history})
    )
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            result = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent",
                headers={"x-goog-api-key": key.get_secret_value()},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "responseJsonSchema": {
                            "type": "object",
                            "properties": {
                                "predicted_flight_count": {"type": "integer", "minimum": 0},
                                "explanation": {"type": "string"},
                            },
                            "required": ["predicted_flight_count", "explanation"],
                        },
                    },
                },
            )
        result.raise_for_status()
        candidate = result.json()["candidates"][0]
        parts = candidate["content"]["parts"]
        return Estimate.model_validate_json("".join(part.get("text", "") for part in parts if not part.get("thought")))
    except httpx.HTTPStatusError as error:
        code = error.response.status_code
        raise HTTPException(503 if code == 429 else 502, f"Gemini returned HTTP {code}") from None
    except (httpx.RequestError, ValueError, KeyError, IndexError, TypeError):
        raise HTTPException(502, "Gemini response is unavailable or invalid") from None


async def forecast(pipeline, *, generate=False):
    settings = pipeline.settings
    today = datetime.now(settings.forecast_timezone).date()
    target = today + timedelta(days=1)
    airports = sorted(set(settings.forecast_airports.replace(" ", "").split(",")))
    scope = {"airports": airports, "timezone": settings.forecast_timezone.key}
    basis = "live_schedule_sample_v2"
    minimum_days = settings.forecast_min_observed_days
    async with await pipeline.connect() as db:
        if settings.forecast_snapshot_only:
            if generate:
                raise HTTPException(409, "Chế độ demo chỉ đọc dự báo đã lưu.")
            cached = await (await db.execute("""
                SELECT forecast_date, computed_at, model, payload
                FROM analytics.forecasts
                ORDER BY forecast_date DESC, computed_at DESC
                LIMIT 1
            """)).fetchone()
            if cached:
                return {"ready": True, "snapshot_only": True, **cached}
            return {"ready": False, "snapshot_only": True, "forecast_date": target, "scope": scope,
                    "observed_days": 0, "required_days": minimum_days}
        if generate:
            await db.execute("SELECT pg_advisory_xact_lock(540417, %s::date - DATE '2000-01-01')", (target,))
        cached = await (await db.execute("""
            SELECT forecast_date, computed_at, model, payload FROM analytics.forecasts
            WHERE forecast_date = %s AND payload->'scope' = %s AND payload->>'basis' = %s
                AND payload->'minimum_days' = %s
        """, (target, Jsonb(scope), basis, Jsonb(minimum_days)))).fetchone()
        if cached:
            return {"ready": True, **cached}

        cursor = await db.execute("""
            SELECT f.fl_date AS date, count(*) AS flight_count
            FROM ingested_flights f JOIN live_flight_details d USING (flight_key)
            WHERE f.fl_date >= %s AND f.fl_date < %s AND f.origin = ANY(%s)
              AND COALESCE(d.payload::jsonb->>'feed', 'schedules') = 'schedules'
            GROUP BY f.fl_date ORDER BY f.fl_date
        """, ((today - timedelta(days=28)).isoformat(), today.isoformat(), airports))
        history = await cursor.fetchall()
        available_days = len(history)
        if not generate:
            return {
                "ready": False, "forecast_date": target, "scope": scope,
                "observed_days": available_days, "required_days": minimum_days,
            }
        if available_days < minimum_days:
            raise HTTPException(409, f"Cần ít nhất {minimum_days} ngày đã qua có dữ liệu trong 28 ngày gần nhất. Hiện có {available_days} ngày.")
        estimate = await ask_gemini(settings, history, target, airports)
        threshold = median(row["flight_count"] for row in history)
        payload = estimate.model_dump() | {
            "classification": "high" if estimate.predicted_flight_count >= threshold else "low",
            "classification_threshold": threshold,
            "observed_days": available_days,
            "minimum_days": minimum_days,
            "provisional": available_days < STANDARD_OBSERVED_DAYS,
            "basis": basis,
            "scope": scope,
        }
        cursor = await db.execute("""
            INSERT INTO analytics.forecasts (forecast_date, model, payload) VALUES (%s, %s, %s)
            ON CONFLICT (forecast_date) DO UPDATE SET
                computed_at = CURRENT_TIMESTAMP, model = EXCLUDED.model, payload = EXCLUDED.payload
            RETURNING forecast_date, computed_at, model, payload
        """, (target, settings.gemini_model, Jsonb(payload)))
        return {"ready": True, **await cursor.fetchone()}


async def schedule_forecasts(pipeline):
    while True:
        try:
            await forecast(pipeline, generate=True)
        except HTTPException as error:
            if error.status_code != 409:
                logger.warning("Scheduled forecast unavailable: HTTP %s", error.status_code)
        except Exception:
            logger.exception("Scheduled forecast failed")
        await asyncio.sleep(3600)
