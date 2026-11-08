from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, model_validator


@dataclass(frozen=True)
class ReplayPosition:
    source: str
    start: int
    next_start: int


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


def save_flight(db, flight: Flight) -> None:
    carrier = flight.OP_UNIQUE_CARRIER.strip().upper()
    db.execute("INSERT INTO flight_data.airlines (carrier_code) VALUES (%s) ON CONFLICT DO NOTHING", (carrier,))
    airports = [
        (flight.ORIGIN_AIRPORT_ID, flight.ORIGIN_AIRPORT_SEQ_ID, flight.ORIGIN, flight.ORIGIN_CITY_MARKET_ID),
        (flight.DEST_AIRPORT_ID, flight.DEST_AIRPORT_SEQ_ID, flight.DEST, flight.DEST_CITY_MARKET_ID),
    ]
    for airport_id, seq_id, code, market_id in sorted(airports):
        db.execute("INSERT INTO flight_data.airports VALUES (%s) ON CONFLICT DO NOTHING", (airport_id,))
        db.execute("""
            INSERT INTO flight_data.airport_versions (airport_seq_id, airport_id, airport_code, city_market_id)
            VALUES (%s, %s, %s, %s) ON CONFLICT (airport_seq_id) DO NOTHING
        """, (seq_id, airport_id, code, market_id))
        db.execute("""
            SELECT 1 FROM flight_data.airport_versions
            WHERE airport_seq_id = %s AND airport_id = %s AND airport_code = %s AND city_market_id = %s
        """, (seq_id, airport_id, code, market_id))
        if db.fetchone() is None:
            raise ValueError("Conflicting simulator airport version")

    db.execute("""
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
