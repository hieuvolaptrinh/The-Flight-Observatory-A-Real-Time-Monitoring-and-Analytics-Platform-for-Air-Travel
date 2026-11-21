"""Load completed AirLabs flights for explicit IATA codes and local departure dates."""

import argparse
import asyncio
from datetime import date, datetime, timezone
import re

import httpx

from app.live_store import LiveStore
from app.pipeline import Pipeline
from app.providers import ProviderError, normalize_schedule


ENDPOINT = "https://airlabs.co/api/v10/historical"


async def backfill(pipeline, airport, flights, start, end, pages, probe=False, *, initial_offset=0):
    providers = pipeline.providers
    account = next((account for account in providers.accounts if airport in account.airports and account.key), None)
    if account is None:
        raise ProviderError(f"No AirLabs account configured for {airport}")

    fetched_at = datetime.now(timezone.utc).isoformat()
    observed_days, imported_days = set(), set()
    seen = set()
    summary = {"pages": 0, "rows": 0, "matched": 0, "imported": 0, "possibly_more": False}
    async with httpx.AsyncClient(timeout=20, transport=providers.transport) as client:
        for flight in flights:
            offset = initial_offset
            for _ in range(pages):
                payload, response_id = await providers.request(
                    client, "airlabs", ENDPOINT, {"flight_iata": flight, "offset": offset, "api_key": account.key},
                    account.quota_group, account.budget, account.reset_day, account.key,
                    airport_code=airport, allow_list=True,
                )
                rows = payload.get("response") if isinstance(payload, dict) else payload
                if not isinstance(rows, list):
                    raise ProviderError("Historical response did not contain a list of flights")
                summary["pages"] += 1
                summary["rows"] += len(rows)
                batch = []
                for index, raw in enumerate(rows):
                    flight_day = departure_date(raw, airport)
                    if flight_day is not None:
                        observed_days.add(flight_day)
                    if flight_day is None or not start <= flight_day < end:
                        await asyncio.to_thread(providers.raw_store.mark, response_id, index, "rejected",
                                                reason="Outside the selected historical scope or invalid departure date")
                        continue
                    summary["matched"] += 1
                    if probe:
                        continue
                    try:
                        origin = await providers.airport(client, account, airport)
                        destination = await providers.airport(client, account, raw["arr_iata"])
                        record = normalize_schedule(
                            {**raw, "airline_iata": raw.get("airline_iata") or flight[:2],
                             "flight_number": raw.get("flight_number") or flight[2:]},
                            origin, destination, fetched_at,
                        )
                    except (ValueError, TypeError, KeyError, OverflowError):
                        record = None
                    if record is None:
                        await asyncio.to_thread(providers.raw_store.mark, response_id, index, "rejected",
                                                reason="Missing or invalid historical flight fields")
                        continue
                    key = record["FLIGHT_KEY"]
                    if key in seen or await asyncio.to_thread(flight_exists, providers.store, key):
                        await asyncio.to_thread(providers.raw_store.mark, response_id, index, "duplicate",
                                                flight_key=key)
                        continue
                    seen.add(key)
                    record["_details"].update(raw=raw, raw_response_id=response_id, raw_row_index=index,
                                              feed="historical")
                    batch.append(record)
                if batch:
                    counts = await pipeline.ingest_payload(
                        {"source": "airlabs_historical", "fetched_at": fetched_at, "data": batch})
                    summary["imported"] += counts["inserted_count"]
                    imported_days.update(record["FL_DATE"] for record in batch)
                offset += len(rows)
                request = payload.get("request") if isinstance(payload, dict) else None
                has_more = request.get("has_more") if isinstance(request, dict) else None
                if not rows or has_more is False:
                    break
            else:
                summary["possibly_more"] = True

    return summary | {
        "observed_days": len(observed_days), "first_date": min(observed_days, default=None),
        "last_date": max(observed_days, default=None), "imported_days": len(imported_days),
    }


def departure_date(raw, airport):
    if not isinstance(raw, dict) or raw.get("dep_iata") != airport:
        return None
    try:
        return datetime.fromisoformat(raw["dep_time"]).date()
    except (KeyError, TypeError, ValueError):
        return None


def flight_exists(store: LiveStore, key: str) -> bool:
    with store.connect() as conn:
        return conn.execute(store.sql("SELECT 1 FROM ingested_flights WHERE flight_key=?"), (key,)).fetchone() is not None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--airport", required=True, type=str.upper)
    parser.add_argument("--flight", required=True, action="append", type=str.upper)
    parser.add_argument("--from", dest="start", required=True, type=date.fromisoformat)
    parser.add_argument("--to", dest="end", required=True, type=date.fromisoformat, help="Exclusive local date")
    parser.add_argument("--pages", type=int, default=1, help="Maximum pages per flight code")
    parser.add_argument("--offset", type=int, default=0, help="Provider offset for the first page")
    parser.add_argument("--probe", action="store_true", help="Inspect and archive one page without importing flights")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Z]{3}", args.airport):
        parser.error("--airport must be a three-letter IATA airport code")
    if any(not re.fullmatch(r"[A-Z0-9]{2}[0-9]{1,5}", flight) for flight in args.flight):
        parser.error("--flight must be an IATA flight number such as B61007")
    if len(set(args.flight)) != len(args.flight):
        parser.error("--flight codes must be unique")
    if not 1 <= args.pages * len(args.flight) <= (1 if args.probe else 20):
        parser.error("The command allows one historical request for a probe, or at most 20 per import")
    if args.offset < 0:
        parser.error("--offset cannot be negative")
    if args.end <= args.start or args.end > datetime.now(timezone.utc).date():
        parser.error("Provide a past date range with an exclusive end no later than today's UTC date")
    try:
        print(asyncio.run(backfill(Pipeline(), args.airport, args.flight, args.start, args.end, args.pages,
                                   args.probe, initial_offset=args.offset)))
    except ProviderError as exc:
        parser.exit(1, f"{exc}\n")
