SELECT pg_advisory_xact_lock(hashtext('flight_data.bts_imported_flights'));

CREATE TABLE IF NOT EXISTS flight_data.bts_imported_flights (
    flight_id bigint PRIMARY KEY REFERENCES flight_data.flights ON DELETE CASCADE,
    archive_name text NOT NULL,
    archive_sha256 text NOT NULL,
    archive_line integer NOT NULL,
    scheduled_departure_utc timestamptz NOT NULL,
    actual_departure_local time,
    actual_arrival_local time,
    imported_at timestamptz NOT NULL DEFAULT statement_timestamp()
);

CREATE TEMP TABLE bts_stage (
    flight_date date NOT NULL,
    carrier_code text NOT NULL,
    flight_number text NOT NULL,
    tail_number text,
    origin text NOT NULL,
    origin_airport_id integer NOT NULL,
    origin_airport_seq_id integer NOT NULL,
    origin_city_market_id integer NOT NULL,
    dest text NOT NULL,
    dest_airport_id integer NOT NULL,
    dest_airport_seq_id integer NOT NULL,
    dest_city_market_id integer NOT NULL,
    scheduled_dep_local time NOT NULL,
    scheduled_arr_local time,
    scheduled_elapsed_min numeric(8,2),
    distance_miles numeric(8,2),
    scheduled_departure_utc timestamptz NOT NULL,
    actual_departure_local time,
    actual_arrival_local time,
    dep_delay_min numeric(8,2),
    arr_delay_min numeric(8,2),
    cancelled boolean NOT NULL,
    diverted boolean NOT NULL,
    archive_name text NOT NULL,
    archive_sha256 text NOT NULL,
    archive_line integer NOT NULL
) ON COMMIT DROP;

-- Merge staged BTS records.
CREATE TEMP TABLE bts_distinct ON COMMIT DROP AS
SELECT DISTINCT ON (flight_date, carrier_code, flight_number, origin, dest, scheduled_dep_local) *
FROM bts_stage
ORDER BY flight_date, carrier_code, flight_number, origin, dest, scheduled_dep_local,
         (dep_delay_min IS NOT NULL) DESC, (arr_delay_min IS NOT NULL) DESC, archive_name, archive_line;

-- Compare IATA codes across sources. The same airport can have distinct database IDs.
CREATE TEMP TABLE bts_new ON COMMIT DROP AS
SELECT s.* FROM bts_distinct AS s
WHERE NOT EXISTS (
    SELECT 1 FROM flight_data.flight_schedule AS f
    WHERE f.flight_date = s.flight_date AND f.carrier_code = s.carrier_code
      AND ltrim(f.flight_number, '0') = ltrim(s.flight_number, '0')
      AND f.origin = s.origin AND f.dest = s.dest
      AND f.scheduled_dep_local = s.scheduled_dep_local
);

CREATE TEMP TABLE bts_airports ON COMMIT DROP AS
SELECT origin_airport_seq_id AS airport_seq_id, origin_airport_id AS airport_id,
       origin AS airport_code, origin_city_market_id AS city_market_id FROM bts_new
UNION
SELECT dest_airport_seq_id, dest_airport_id, dest, dest_city_market_id FROM bts_new;

INSERT INTO flight_data.airlines (carrier_code)
SELECT DISTINCT carrier_code FROM bts_new
ON CONFLICT DO NOTHING;

INSERT INTO flight_data.airports (airport_id)
SELECT DISTINCT airport_id FROM bts_airports
ON CONFLICT DO NOTHING;

INSERT INTO flight_data.airport_versions (airport_seq_id, airport_id, airport_code, city_market_id)
SELECT airport_seq_id, airport_id, airport_code, city_market_id FROM bts_airports
ON CONFLICT DO NOTHING;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM bts_airports AS s JOIN flight_data.airport_versions AS v USING (airport_seq_id)
        WHERE (s.airport_id, s.airport_code, s.city_market_id)
           <> (v.airport_id, v.airport_code, v.city_market_id)
    ) THEN
        RAISE EXCEPTION 'BTS airport version metadata conflicts with the processed database';
    END IF;
END;
$$;

CREATE TEMP TABLE bts_inserted ON COMMIT DROP AS
WITH added AS (
    INSERT INTO flight_data.flights (
        flight_date, carrier_code, flight_number, tail_number,
        origin_airport_id, origin_airport_seq_id, dest_airport_id, dest_airport_seq_id,
        scheduled_dep_local, scheduled_arr_local, scheduled_elapsed_min, distance_miles
    )
    SELECT flight_date, carrier_code, flight_number, tail_number,
           origin_airport_id, origin_airport_seq_id, dest_airport_id, dest_airport_seq_id,
           scheduled_dep_local, scheduled_arr_local, scheduled_elapsed_min, distance_miles
    FROM bts_new
    ON CONFLICT ON CONSTRAINT flights_schedule_key DO NOTHING
    RETURNING flight_id, flight_date, carrier_code, flight_number, origin_airport_id,
              dest_airport_id, scheduled_dep_local
)
SELECT a.flight_id, n.* FROM added AS a
JOIN bts_new AS n USING (flight_date, carrier_code, flight_number, origin_airport_id,
                         dest_airport_id, scheduled_dep_local);

INSERT INTO flight_data.bts_imported_flights (
    flight_id, archive_name, archive_sha256, archive_line,
    scheduled_departure_utc, actual_departure_local, actual_arrival_local
)
SELECT flight_id, archive_name, archive_sha256, archive_line,
       scheduled_departure_utc, actual_departure_local, actual_arrival_local
FROM bts_inserted;

INSERT INTO flight_data.flight_outcomes (flight_id, dep_delay_min, arr_delay_min, cancelled, diverted)
SELECT flight_id, dep_delay_min, arr_delay_min, cancelled, diverted FROM bts_inserted;

SELECT (SELECT count(*) FROM bts_stage) AS staged,
       (SELECT count(*) FROM bts_stage) - (SELECT count(*) FROM bts_distinct) AS duplicate_rows_in_batch,
       (SELECT count(*) FROM bts_distinct) - count(*) AS existing_flights_skipped,
       count(*) AS inserted, count(dep_delay_min) AS observed_departures FROM bts_inserted;
