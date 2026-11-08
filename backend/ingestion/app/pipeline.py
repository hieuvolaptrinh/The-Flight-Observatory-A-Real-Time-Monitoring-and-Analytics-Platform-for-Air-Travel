from datetime import date, datetime

import httpx
import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, model_validator

from app.config import Settings
from app.schemas import PipelineOutput


def hhmm(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.isascii() or not value.isdigit() or len(value) > 4:
        raise ValueError("Invalid scheduled HHMM time")
    value = value.zfill(4)
    if value != "2400" and (value[:2] > "23" or value[2:] > "59"):
        raise ValueError("Invalid scheduled HHMM time")
    return f"{value[:2]}:{value[2:]}"


class Flight(BaseModel):
    DAY_OF_WEEK: int
    FL_DATE: date
    OP_UNIQUE_CARRIER: str
    TAIL_NUM: str | None
    OP_CARRIER_FL_NUM: int | str
    ORIGIN_AIRPORT_ID: int
    ORIGIN_AIRPORT_SEQ_ID: int
    ORIGIN_CITY_MARKET_ID: int
    ORIGIN: str
    DEST_AIRPORT_ID: int
    DEST_AIRPORT_SEQ_ID: int
    DEST_CITY_MARKET_ID: int
    DEST: str
    CRS_DEP_TIME: str
    CRS_ARR_TIME: str | None
    CRS_ELAPSED_TIME: float | None
    DISTANCE: float | None

    @model_validator(mode="after")
    def check_schedule(self):
        if self.DAY_OF_WEEK != self.FL_DATE.isoweekday():
            raise ValueError("DAY_OF_WEEK does not match FL_DATE")
        return self


class SimulatorBatch(BaseModel):
    fetched_at: datetime
    window_start: int = Field(ge=0)
    total: int = Field(gt=0)
    data: list[Flight] = Field(min_length=1)


class Pipeline:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def run(self) -> PipelineOutput:
        source = self.settings.simulator_base_url.rstrip("/")
        async with await psycopg.AsyncConnection.connect(self.settings.database_url, row_factory=dict_row) as db:
            await db.execute("""
                INSERT INTO flight_data.simulator_offsets (source_url, next_start) VALUES (%s, 0)
                ON CONFLICT (source_url) DO NOTHING
            """, (source,))
            cursor = await db.execute("""
                SELECT next_start FROM flight_data.simulator_offsets WHERE source_url = %s FOR UPDATE
            """, (source,))
            start = (await cursor.fetchone())["next_start"]
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(f"{source}/flights", params={
                    "start": start, "window_size": self.settings.ingestion_batch_size,
                })
                response.raise_for_status()
            batch = SimulatorBatch.model_validate(response.json())
            if (batch.window_start != start % batch.total
                    or len(batch.data) != min(batch.total, self.settings.ingestion_batch_size)):
                raise ValueError("Simulator did not honor the requested cursor and batch size")

            inserted = 0
            for flight in batch.data:
                inserted += await self.save_flight(db, flight)
            next_start = (batch.window_start + len(batch.data)) % batch.total
            await db.execute("""
                UPDATE flight_data.simulator_offsets SET next_start = %s, updated_at = statement_timestamp()
                WHERE source_url = %s
            """, (next_start, source))

        return PipelineOutput(items=[flight.model_dump(mode="json") for flight in batch.data], metadata={
            "fetched_at": batch.fetched_at.isoformat(), "received": len(batch.data), "inserted": inserted,
            "duplicates": len(batch.data) - inserted, "next_start": next_start,
        })

    @staticmethod
    async def save_flight(db, flight: Flight) -> int:
        carrier = flight.OP_UNIQUE_CARRIER.strip().upper()
        await db.execute("INSERT INTO flight_data.airlines (carrier_code) VALUES (%s) ON CONFLICT DO NOTHING", (carrier,))
        airports = [
            (flight.ORIGIN_AIRPORT_ID, flight.ORIGIN_AIRPORT_SEQ_ID, flight.ORIGIN, flight.ORIGIN_CITY_MARKET_ID),
            (flight.DEST_AIRPORT_ID, flight.DEST_AIRPORT_SEQ_ID, flight.DEST, flight.DEST_CITY_MARKET_ID),
        ]
        for airport_id, seq_id, code, market_id in sorted(airports):
            await db.execute("INSERT INTO flight_data.airports VALUES (%s) ON CONFLICT DO NOTHING", (airport_id,))
            await db.execute("""
                INSERT INTO flight_data.airport_versions (airport_seq_id, airport_id, airport_code, city_market_id)
                VALUES (%s, %s, %s, %s) ON CONFLICT (airport_seq_id) DO NOTHING
            """, (seq_id, airport_id, code, market_id))
            cursor = await db.execute("""
                SELECT 1 FROM flight_data.airport_versions
                WHERE airport_seq_id = %s AND airport_id = %s AND airport_code = %s AND city_market_id = %s
            """, (seq_id, airport_id, code, market_id))
            if await cursor.fetchone() is None:
                raise ValueError("Conflicting simulator airport version")

        cursor = await db.execute("""
            INSERT INTO flight_data.flights (
                flight_date, carrier_code, flight_number, tail_number,
                origin_airport_id, origin_airport_seq_id, dest_airport_id, dest_airport_seq_id,
                scheduled_dep_local, scheduled_arr_local, scheduled_elapsed_min, distance_miles
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::time, %s::time, %s, %s)
            ON CONFLICT ON CONSTRAINT flights_schedule_key DO NOTHING
        """, (
            flight.FL_DATE, carrier, str(flight.OP_CARRIER_FL_NUM).strip(), flight.TAIL_NUM or None,
            flight.ORIGIN_AIRPORT_ID, flight.ORIGIN_AIRPORT_SEQ_ID, flight.DEST_AIRPORT_ID, flight.DEST_AIRPORT_SEQ_ID,
            hhmm(flight.CRS_DEP_TIME), hhmm(flight.CRS_ARR_TIME), flight.CRS_ELAPSED_TIME, flight.DISTANCE,
        ))
        return cursor.rowcount

    async def flights(self, limit: int, offset: int) -> PipelineOutput:
        async with await psycopg.AsyncConnection.connect(self.settings.database_url, row_factory=dict_row) as db:
            cursor = await db.execute("""
                SELECT flight_id, flight_date, carrier_code, flight_number, origin, dest,
                       scheduled_dep_local::text, scheduled_arr_local::text, scheduled_elapsed_min, distance_miles
                FROM flight_data.flight_schedule ORDER BY flight_id DESC LIMIT %s OFFSET %s
            """, (limit + 1, offset))
            rows = await cursor.fetchall()
        return PipelineOutput(items=rows[:limit], metadata={
            "limit": limit, "offset": offset, "has_more": len(rows) > limit,
        })
