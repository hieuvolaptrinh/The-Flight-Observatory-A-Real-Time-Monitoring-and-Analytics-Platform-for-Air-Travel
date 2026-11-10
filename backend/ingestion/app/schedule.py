"""
Normalized Flight Schedule & Outcome Persistence for Analytics Schema (`flight_data.*`).
All SQL statements are defined as static module-level constants using named bind parameters
(`%(param_name)s`) so queries are 100% immune to SQL injection.
"""
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, model_validator

UPSERT_AIRLINE_SQL = """
INSERT INTO flight_data.airlines (carrier_code, carrier_name)
VALUES (%(carrier_code)s, %(carrier_name)s)
ON CONFLICT (carrier_code) DO UPDATE
SET carrier_name = COALESCE(EXCLUDED.carrier_name, flight_data.airlines.carrier_name)
"""

INSERT_AIRPORT_SQL = """
INSERT INTO flight_data.airports (airport_id)
VALUES (%(airport_id)s)
ON CONFLICT DO NOTHING
"""

INSERT_AIRPORT_VERSION_SQL = """
INSERT INTO flight_data.airport_versions (
    airport_seq_id, airport_id, airport_code, city_market_id
) VALUES (
    %(airport_seq_id)s, %(airport_id)s, %(airport_code)s, %(city_market_id)s
) ON CONFLICT (airport_seq_id) DO NOTHING
"""

VERIFY_AIRPORT_VERSION_SQL = """
SELECT 1 FROM flight_data.airport_versions
WHERE airport_seq_id = %(airport_seq_id)s
  AND airport_id = %(airport_id)s
  AND airport_code = %(airport_code)s
  AND city_market_id = %(city_market_id)s
"""

UPSERT_FLIGHT_SCHEDULE_SQL = """
INSERT INTO flight_data.flights (
    flight_date, carrier_code, flight_number, tail_number,
    origin_airport_id, origin_airport_seq_id, dest_airport_id, dest_airport_seq_id,
    scheduled_dep_local, scheduled_arr_local, scheduled_elapsed_min, distance_miles
) VALUES (
    %(flight_date)s, %(carrier_code)s, %(flight_number)s, %(tail_number)s,
    %(origin_airport_id)s, %(origin_airport_seq_id)s, %(dest_airport_id)s, %(dest_airport_seq_id)s,
    %(scheduled_dep_local)s::time, %(scheduled_arr_local)s::time, %(scheduled_elapsed_min)s, %(distance_miles)s
)
ON CONFLICT ON CONSTRAINT flights_schedule_key DO UPDATE
    SET tail_number = COALESCE(EXCLUDED.tail_number, flight_data.flights.tail_number)
RETURNING flight_id
"""

UPSERT_FLIGHT_OUTCOME_SQL = """
INSERT INTO flight_data.flight_outcomes (
    flight_id, dep_delay_min, arr_delay_min, cancelled, diverted
) VALUES (
    %(flight_id)s, %(dep_delay_min)s, %(arr_delay_min)s, FALSE, FALSE
)
ON CONFLICT (flight_id) DO UPDATE SET
    dep_delay_min = EXCLUDED.dep_delay_min,
    arr_delay_min = EXCLUDED.arr_delay_min
"""


@dataclass(frozen=True)
class ReplayPosition:
    source: str
    start: int
    next_start: int


def hhmm(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip().split(".")[0].replace(":", "")
    if not cleaned:
        return None
    if not cleaned.isascii() or not cleaned.isdigit() or len(cleaned) > 4:
        raise ValueError("Invalid scheduled HHMM time")
    cleaned = cleaned.zfill(4)
    if cleaned != "2400" and (cleaned[:2] > "23" or cleaned[2:] > "59"):
        raise ValueError("Invalid scheduled HHMM time")
    return f"{cleaned[:2]}:{cleaned[2:]}"


class Flight(BaseModel):
    DAY_OF_WEEK: int
    FL_DATE: date
    OP_UNIQUE_CARRIER: str
    CARRIER_NAME: str | None = None
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
    DELAY_MINUTES: float = 0.0

    @model_validator(mode="after")
    def check_schedule(self):
        if self.DAY_OF_WEEK != self.FL_DATE.isoweekday():
            raise ValueError("DAY_OF_WEEK does not match FL_DATE")
        return self


def save_flight(db, flight: Flight) -> None:
    carrier = flight.OP_UNIQUE_CARRIER.strip().upper()
    carrier_name = (flight.CARRIER_NAME or "").strip() or None
    db.execute(
        UPSERT_AIRLINE_SQL,
        {"carrier_code": carrier, "carrier_name": carrier_name},
    )

    airports = [
        (flight.ORIGIN_AIRPORT_ID, flight.ORIGIN_AIRPORT_SEQ_ID, flight.ORIGIN, flight.ORIGIN_CITY_MARKET_ID),
        (flight.DEST_AIRPORT_ID, flight.DEST_AIRPORT_SEQ_ID, flight.DEST, flight.DEST_CITY_MARKET_ID),
    ]
    for airport_id, seq_id, code, market_id in sorted(airports):
        airport_params = {
            "airport_id": airport_id,
            "airport_seq_id": seq_id,
            "airport_code": code,
            "city_market_id": market_id,
        }
        db.execute(INSERT_AIRPORT_SQL, {"airport_id": airport_id})
        db.execute(INSERT_AIRPORT_VERSION_SQL, airport_params)
        db.execute(VERIFY_AIRPORT_VERSION_SQL, airport_params)
        if db.fetchone() is None:
            raise ValueError("Conflicting simulator airport version")

    db.execute(
        UPSERT_FLIGHT_SCHEDULE_SQL,
        {
            "flight_date": flight.FL_DATE,
            "carrier_code": carrier,
            "flight_number": str(flight.OP_CARRIER_FL_NUM).strip(),
            "tail_number": flight.TAIL_NUM or None,
            "origin_airport_id": flight.ORIGIN_AIRPORT_ID,
            "origin_airport_seq_id": flight.ORIGIN_AIRPORT_SEQ_ID,
            "dest_airport_id": flight.DEST_AIRPORT_ID,
            "dest_airport_seq_id": flight.DEST_AIRPORT_SEQ_ID,
            "scheduled_dep_local": hhmm(flight.CRS_DEP_TIME),
            "scheduled_arr_local": hhmm(flight.CRS_ARR_TIME),
            "scheduled_elapsed_min": flight.CRS_ELAPSED_TIME,
            "distance_miles": flight.DISTANCE,
        },
    )
    flight_row = db.fetchone()
    if flight_row is not None:
        flight_id = flight_row["flight_id"] if isinstance(flight_row, dict) else flight_row[0]
        delay_val = round(float(flight.DELAY_MINUTES or 0.0), 2)
        db.execute(
            UPSERT_FLIGHT_OUTCOME_SQL,
            {
                "flight_id": flight_id,
                "dep_delay_min": delay_val,
                "arr_delay_min": delay_val,
            },
        )


def save_flights_batch(db, flights: tuple[Flight, ...] | list[Flight]) -> None:
    """
    Persist a batch of scheduled flights by deduplicating airlines and airports in memory first,
    avoiding redundant SQL round-trips across flights in the same batch.
    """
    if not flights:
        return

    unique_airlines: dict[str, str | None] = {}
    unique_airports: dict[int, tuple[int, str, int]] = {}

    for flight in flights:
        carrier = flight.OP_UNIQUE_CARRIER.strip().upper()
        carrier_name = (flight.CARRIER_NAME or "").strip() or None
        if carrier not in unique_airlines or (unique_airlines[carrier] is None and carrier_name is not None):
            unique_airlines[carrier] = carrier_name

        for airport_id, seq_id, code, market_id in (
            (flight.ORIGIN_AIRPORT_ID, flight.ORIGIN_AIRPORT_SEQ_ID, flight.ORIGIN, flight.ORIGIN_CITY_MARKET_ID),
            (flight.DEST_AIRPORT_ID, flight.DEST_AIRPORT_SEQ_ID, flight.DEST, flight.DEST_CITY_MARKET_ID),
        ):
            unique_airports[seq_id] = (airport_id, code, market_id)

    for carrier, carrier_name in sorted(unique_airlines.items()):
        db.execute(
            UPSERT_AIRLINE_SQL,
            {"carrier_code": carrier, "carrier_name": carrier_name},
        )

    for seq_id, (airport_id, code, market_id) in sorted(unique_airports.items(), key=lambda kv: (kv[1][0], kv[0])):
        airport_params = {
            "airport_id": airport_id,
            "airport_seq_id": seq_id,
            "airport_code": code,
            "city_market_id": market_id,
        }
        db.execute(INSERT_AIRPORT_SQL, {"airport_id": airport_id})
        db.execute(INSERT_AIRPORT_VERSION_SQL, airport_params)
        db.execute(VERIFY_AIRPORT_VERSION_SQL, airport_params)
        if db.fetchone() is None:
            raise ValueError("Conflicting simulator airport version")

    for flight in flights:
        carrier = flight.OP_UNIQUE_CARRIER.strip().upper()
        db.execute(
            UPSERT_FLIGHT_SCHEDULE_SQL,
            {
                "flight_date": flight.FL_DATE,
                "carrier_code": carrier,
                "flight_number": str(flight.OP_CARRIER_FL_NUM).strip(),
                "tail_number": flight.TAIL_NUM or None,
                "origin_airport_id": flight.ORIGIN_AIRPORT_ID,
                "origin_airport_seq_id": flight.ORIGIN_AIRPORT_SEQ_ID,
                "dest_airport_id": flight.DEST_AIRPORT_ID,
                "dest_airport_seq_id": flight.DEST_AIRPORT_SEQ_ID,
                "scheduled_dep_local": hhmm(flight.CRS_DEP_TIME),
                "scheduled_arr_local": hhmm(flight.CRS_ARR_TIME),
                "scheduled_elapsed_min": flight.CRS_ELAPSED_TIME,
                "distance_miles": flight.DISTANCE,
            },
        )
        flight_row = db.fetchone()
        if flight_row is not None:
            flight_id = flight_row["flight_id"] if isinstance(flight_row, dict) else flight_row[0]
            delay_val = round(float(flight.DELAY_MINUTES or 0.0), 2)
            db.execute(
                UPSERT_FLIGHT_OUTCOME_SQL,
                {
                    "flight_id": flight_id,
                    "dep_delay_min": delay_val,
                    "arr_delay_min": delay_val,
                },
            )
