import json
from datetime import timedelta
from statistics import median

import httpx
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field


class Estimate(BaseModel):
    predicted_flight_count: int = Field(ge=0)
    explanation: str = Field(min_length=1, max_length=800)


async def ask_gemini(settings, history, target):
    key = settings.gemini_api_key
    if not key or not key.get_secret_value():
        raise HTTPException(503, "Configure GEMINI_API_KEY in the Analytics environment")
    prompt = (
        "Estimate the next day's flight count at the same observed replay coverage. "
        "The counts below are partial observations of historical scheduled flights, not actual traffic or delays. "
        "Treat unlisted days as unknown. Give a non-negative whole count and a short Vietnamese explanation "
        "that states the coverage limitation. Use only the supplied counts.\n"
        + json.dumps({"forecast_date": target.isoformat(), "history": history})
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
    async with await pipeline.connect() as db:
        cursor = await db.execute("SELECT max(flight_date) AS last FROM flight_data.flights")
        last = (await cursor.fetchone())["last"]
        if last is None:
            if generate:
                raise HTTPException(409, "Load flight data before generating a forecast")
            return {"ready": False}
        target = last + timedelta(days=1)
        if generate:
            await db.execute("SELECT pg_advisory_xact_lock(540417, %s::date - DATE '2000-01-01')", (target,))
        query = "SELECT forecast_date, computed_at, model, payload FROM analytics.forecasts WHERE forecast_date = %s"
        cached = await (await db.execute(query, (target,))).fetchone()
        if cached:
            return {"ready": True, **cached}
        if not generate:
            return {"ready": False, "forecast_date": target}

        cursor = await db.execute("""
            SELECT flight_date::text AS date, count(*) AS flight_count
            FROM flight_data.flights WHERE flight_date BETWEEN %s AND %s
            GROUP BY flight_date ORDER BY flight_date
        """, (last - timedelta(days=27), last))
        history = await cursor.fetchall()
        if len(history) < 5:
            raise HTTPException(409, "Forecast needs at least five observed dates in the last 28 dataset days")
        estimate = await ask_gemini(pipeline.settings, history, target)
        threshold = median(row["flight_count"] for row in history)
        payload = estimate.model_dump() | {
            "classification": "high" if estimate.predicted_flight_count >= threshold else "low",
            "classification_threshold": threshold,
            "observed_days": len(history),
            "basis": "observed_schedule_sample",
        }
        cursor = await db.execute("""
            INSERT INTO analytics.forecasts (forecast_date, model, payload) VALUES (%s, %s, %s)
            RETURNING forecast_date, computed_at, model, payload
        """, (target, pipeline.settings.gemini_model, Jsonb(payload)))
        return {"ready": True, **await cursor.fetchone()}
