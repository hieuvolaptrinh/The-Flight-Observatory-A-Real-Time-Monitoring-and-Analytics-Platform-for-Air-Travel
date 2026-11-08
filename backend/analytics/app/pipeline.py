from datetime import date, datetime, timedelta, timezone
from statistics import mean

import psycopg
from psycopg.rows import dict_row

from app.config import Settings
from app.schemas import PipelineOutput


class Pipeline:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def connect(self):
        return await psycopg.AsyncConnection.connect(self.settings.database_url, row_factory=dict_row)

    async def run(self) -> PipelineOutput:
        snapshot = await self.snapshot(force=True)
        return PipelineOutput(metadata={"snapshot": summary(snapshot)})

    async def bounds(self, db, date_from, date_to):
        if date_from is not None:
            return date_from, date_to
        cursor = await db.execute("SELECT min(flight_date) AS first, max(flight_date) AS last FROM flight_data.flights")
        dates = await cursor.fetchone()
        if dates["last"] is None:
            return None
        end = dates["last"] + timedelta(days=1)
        return max(dates["first"], end - timedelta(days=366)), end

    async def snapshot(self, date_from=None, date_to=None, *, force=False):
        async with await self.connect() as db:
            bounds = await self.bounds(db, date_from, date_to)
            if bounds is None:
                return None
            lookup = """
                SELECT date_from, date_to, computed_at, flight_count, payload
                FROM analytics.schedule_snapshots WHERE date_from = %s AND date_to = %s
            """
            snapshot = await (await db.execute(lookup, bounds)).fetchone()
            if (force or snapshot is None or (datetime.now(timezone.utc) - snapshot["computed_at"]).total_seconds()
                    >= self.settings.job_interval_seconds):
                await db.execute("SELECT analytics.refresh_schedule(%s, %s)", bounds)
                snapshot = await (await db.execute(lookup, bounds)).fetchone()
            return snapshot

    async def scatter(self, date_from, date_to, grain, limit, offset):
        async with await self.connect() as db:
            bounds = await self.bounds(db, date_from, date_to)
            if bounds is None:
                return []
            cursor = await db.execute("""
                SELECT date_trunc(%s, flight_date::timestamp)::date AS period_start,
                       flight_date AS date, scheduled_dep_local::text AS departure_local,
                       scheduled_elapsed_min, distance_miles, flight_id
                FROM flight_data.flights WHERE flight_date >= %s AND flight_date < %s
                    AND scheduled_elapsed_min IS NOT NULL
                ORDER BY flight_date, scheduled_dep_local, flight_id LIMIT %s OFFSET %s
            """, (grain, *bounds, limit, offset))
            return await cursor.fetchall()

    async def correlations(self, date_from, date_to):
        variables = ["distance_miles", "scheduled_elapsed_min", "departure_hour"]
        async with await self.connect() as db:
            bounds = await self.bounds(db, date_from, date_to)
            if bounds is None:
                return {"variables": variables, "matrix": [[None] * 3 for _ in variables], "samples": [[0] * 3 for _ in variables]}
            cursor = await db.execute("""
                WITH input AS (
                    SELECT distance_miles::double precision AS x, scheduled_elapsed_min::double precision AS y,
                           (EXTRACT(EPOCH FROM scheduled_dep_local)::integer %% 86400) / 3600.0 AS z
                    FROM flight_data.flights WHERE flight_date >= %s AND flight_date < %s
                )
                SELECT corr(x,x) AS xx, corr(y,y) AS yy, corr(z,z) AS zz,
                       corr(x,y) AS xy, corr(x,z) AS xz, corr(y,z) AS yz,
                       count(x) AS nx, count(y) AS ny, count(z) AS nz,
                       regr_count(x,y) AS nxy, regr_count(x,z) AS nxz, regr_count(y,z) AS nyz
                FROM input
            """, bounds)
            row = await cursor.fetchone()
        return {
            "variables": variables,
            "matrix": [[row["xx"], row["xy"], row["xz"]], [row["xy"], row["yy"], row["yz"]], [row["xz"], row["yz"], row["zz"]]],
            "samples": [[row["nx"], row["nxy"], row["nxz"]], [row["nxy"], row["ny"], row["nyz"]], [row["nxz"], row["nyz"], row["nz"]]],
        }


def summary(snapshot):
    if snapshot is None:
        return {"ready": False, "flight_count": 0, "observed_arrivals": 0, "arrival_delay_pct": None}
    daily = [row for row in snapshot["payload"]["series"] if row["grain"] == "day"]
    observed = sum(row["observed_arrivals"] for row in daily)
    delayed = sum(row["delayed_arrivals"] for row in daily)
    return {
        "ready": snapshot["flight_count"] > 0, "flight_count": snapshot["flight_count"],
        "date_from": snapshot["date_from"], "date_to": snapshot["date_to"], "updated_at": snapshot["computed_at"],
        "observed_arrivals": observed, "arrival_delay_pct": round(100 * delayed / observed, 2) if observed else None,
    }


def decompose(series, grain):
    points = [row for row in series if row["grain"] == grain and row["flight_count"] > 0]
    if len(points) < 2:
        return [], None
    dates = [date.fromisoformat(row["period_start"]) for row in points]
    if grain == "month":
        positions = [(day.year - dates[0].year) * 12 + day.month - dates[0].month for day in dates]
        period = 12
    else:
        positions = [(day - dates[0]).days // 7 for day in dates]
        period = 4
    counts = [row["flight_count"] for row in points]
    x_avg, y_avg = mean(positions), mean(counts)
    slope = sum((x - x_avg) * (y - y_avg) for x, y in zip(positions, counts)) / sum((x - x_avg) ** 2 for x in positions)
    trend = [y_avg + slope * (x - x_avg) for x in positions]
    groups = [[] for _ in range(period)]
    for x, y, fitted in zip(positions, counts, trend):
        groups[x % period].append(y - fitted)
    seasonal = [mean(group) for group in groups] if min(map(len, groups)) >= 2 else None
    center = mean(seasonal) if seasonal is not None else 0
    return [{
        "period_start": row["period_start"], "flight_count": row["flight_count"], "trend": round(fitted, 2),
        "seasonal": round(seasonal[x % period] - center, 2) if seasonal is not None else None,
    } for row, x, fitted in zip(points, positions, trend)], period
