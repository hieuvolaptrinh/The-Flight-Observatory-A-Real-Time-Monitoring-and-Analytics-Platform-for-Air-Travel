"""Import official monthly BTS reporting-carrier ZIPs into the processed database."""

import argparse
from collections import Counter
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import re
from zipfile import ZipFile
from zoneinfo import ZoneInfo

import psycopg

from app.config import Settings
from app.schedule import hhmm


SOURCE_FIELDS = (
    "FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline", "Tail_Number",
    "Origin", "OriginAirportID", "OriginAirportSeqID", "OriginCityMarketID",
    "Dest", "DestAirportID", "DestAirportSeqID", "DestCityMarketID",
    "CRSDepTime", "CRSArrTime", "CRSElapsedTime", "Distance", "DepTime", "ArrTime",
    "DepDelay", "ArrDelay", "Cancelled", "Diverted",
)
AIRPORT_TIMEZONES = {airport: ZoneInfo("America/New_York") for airport in ("JFK", "LGA")}
SQL = Path(__file__).with_name("bts_import.sql").read_text(encoding="utf-8")


def optional_number(value: str | None) -> Decimal | None:
    if value is None or not value.strip():
        return None
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError("Nonfinite numeric value")
    return number


def flag(value: str | None) -> bool:
    status = optional_number(value)
    if status not in (0, 1):
        raise ValueError("Unknown BTS flight status flag")
    return bool(status)


def stage_row(row, month: str, source: str, checksum: str, line: int):
    day = date.fromisoformat(row["FlightDate"])
    if day.isoformat()[:7] != month:
        raise ValueError("Flight date falls outside the archive month")
    departure, arrival = hhmm(row["CRSDepTime"]), hhmm(row["CRSArrTime"])
    flight_number = row["Flight_Number_Reporting_Airline"].strip()
    if departure is None or not flight_number.isascii() or not flight_number.isdigit():
        raise ValueError("Missing scheduled departure or invalid flight number")
    hour, minute = map(int, departure.split(":"))
    origin = row["Origin"].strip().upper()
    scheduled = datetime(day.year, day.month, day.day, tzinfo=AIRPORT_TIMEZONES[origin])
    scheduled = (scheduled + timedelta(hours=hour, minutes=minute)).astimezone(timezone.utc)
    cancelled, diverted = flag(row["Cancelled"]), flag(row["Diverted"])
    actual_departure, actual_arrival = hhmm(row["DepTime"]), hhmm(row["ArrTime"])
    dep_delay = optional_number(row["DepDelay"]) if actual_departure and not cancelled and not diverted else None
    arr_delay = optional_number(row["ArrDelay"]) if actual_arrival and not cancelled and not diverted else None
    elapsed = optional_number(row["CRSElapsedTime"])
    distance = optional_number(row["Distance"])
    if (elapsed is not None and elapsed <= 0) or (distance is not None and distance <= 0):
        raise ValueError("Invalid scheduled elapsed time or distance")
    return (
        day, row["Reporting_Airline"].strip().upper(), str(int(flight_number)),
        row["Tail_Number"].strip() or None,
        origin, int(row["OriginAirportID"]), int(row["OriginAirportSeqID"]), int(row["OriginCityMarketID"]),
        row["Dest"].strip().upper(), int(row["DestAirportID"]), int(row["DestAirportSeqID"]),
        int(row["DestCityMarketID"]), departure, arrival, elapsed, distance, scheduled,
        actual_departure, actual_arrival, dep_delay, arr_delay, cancelled, diverted, source, checksum, line,
    )


def archive_month(path: Path) -> str:
    match = re.search(r"(?:^|[_-])([0-9]{4})[_-]([0-9]{1,2})\.zip$", path.name, re.I)
    if match is None:
        raise ValueError(f"Expected a year and month in {path.name}")
    return date(int(match[1]), int(match[2]), 1).isoformat()[:7]


def stage_archive(cursor, path: Path, airports: set[str]) -> Counter:
    month = archive_month(path)
    with path.open("rb") as source:
        checksum = hashlib.file_digest(source, "sha256").hexdigest()
    counts = Counter()
    with ZipFile(path) as archive:
        csv_files = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(csv_files) != 1:
            raise ValueError(f"Expected one CSV in {path.name}")
        with archive.open(csv_files[0]) as file:
            reader = csv.DictReader(io.TextIOWrapper(file, encoding="utf-8-sig", newline=""))
            missing = set(SOURCE_FIELDS) - set(reader.fieldnames or ())
            if missing:
                raise ValueError(f"{path.name} is missing columns: {', '.join(sorted(missing))}")
            with cursor.copy("COPY bts_stage FROM STDIN") as copy:
                for line, row in enumerate(reader, start=2):
                    if row["Origin"] not in airports:
                        continue
                    counts["selected"] += 1
                    try:
                        values = stage_row(row, month, path.name, checksum, line)
                    except (ValueError, TypeError, InvalidOperation) as error:
                        raise ValueError(f"{path.name} row {line}: {error}") from error
                    copy.write_row(values)
                    counts["observed_departures"] += values[19] is not None
    if not counts["selected"]:
        raise ValueError(f"{path.name} has no flights for the selected airports")
    return counts


def import_history(url: str, archives: list[Path], airports: set[str]) -> dict:
    if not url.startswith(("postgresql://", "postgres://")):
        raise ValueError("BTS import needs a PostgreSQL DATABASE_URL")
    setup, merge = SQL.split("-- Merge staged BTS records.", maxsplit=1)
    with psycopg.connect(url) as conn, conn.cursor() as cursor:
        cursor.execute(setup)
        for path in archives:
            print(json.dumps({"archive": path.name, **stage_archive(cursor, path, airports)}), flush=True)
        cursor.execute(merge)
        while cursor.nextset():
            pass
        result = cursor.fetchone()
        return dict(zip([col.name for col in cursor.description], result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", type=Path, nargs="+")
    parser.add_argument("--airport", choices=sorted(AIRPORT_TIMEZONES), action="append")
    args = parser.parse_args()
    try:
        print(json.dumps(import_history(Settings().database_url, args.archives,
                                        set(args.airport or AIRPORT_TIMEZONES))), flush=True)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
