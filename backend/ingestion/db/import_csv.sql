\set ON_ERROR_STOP on

BEGIN;
SET LOCAL DateStyle TO 'ISO, MDY';

CREATE TEMP TABLE staging_flights (
    "DAY_OF_WEEK" smallint NOT NULL,
    "FL_DATE" text NOT NULL,
    "OP_UNIQUE_CARRIER" text NOT NULL,
    "TAIL_NUM" text,
    "OP_CARRIER_FL_NUM" text NOT NULL,
    "ORIGIN_AIRPORT_ID" integer NOT NULL,
    "ORIGIN_AIRPORT_SEQ_ID" integer NOT NULL,
    "ORIGIN_CITY_MARKET_ID" integer NOT NULL,
    "ORIGIN" text NOT NULL,
    "DEST_AIRPORT_ID" integer NOT NULL,
    "DEST_AIRPORT_SEQ_ID" integer NOT NULL,
    "DEST_CITY_MARKET_ID" integer NOT NULL,
    "DEST" text NOT NULL,
    "CRS_DEP_TIME" text NOT NULL CHECK ("CRS_DEP_TIME" ~ '^[0-9]{1,4}$'),
    "CRS_ARR_TIME" text CHECK ("CRS_ARR_TIME" ~ '^[0-9]{1,4}$'),
    "CRS_ELAPSED_TIME" numeric(8, 2),
    "DISTANCE" numeric(8, 2),
    CHECK ("DAY_OF_WEEK" = EXTRACT(ISODOW FROM split_part(btrim("FL_DATE"), ' ', 1)::date))
) ON COMMIT DROP;

COPY staging_flights FROM :'csv_path' WITH (
    FORMAT csv, HEADER MATCH, FORCE_NULL ("TAIL_NUM", "CRS_ARR_TIME", "CRS_ELAPSED_TIME", "DISTANCE")
);

CREATE TEMP TABLE staging_airport_versions ON COMMIT DROP AS
SELECT "ORIGIN_AIRPORT_SEQ_ID" AS airport_seq_id, "ORIGIN_AIRPORT_ID" AS airport_id,
       upper(btrim("ORIGIN")) AS airport_code, "ORIGIN_CITY_MARKET_ID" AS city_market_id
FROM staging_flights
UNION
SELECT "DEST_AIRPORT_SEQ_ID", "DEST_AIRPORT_ID", upper(btrim("DEST")), "DEST_CITY_MARKET_ID"
FROM staging_flights;

INSERT INTO flight_data.airlines (carrier_code)
SELECT DISTINCT upper(btrim("OP_UNIQUE_CARRIER")) FROM staging_flights ORDER BY 1
ON CONFLICT (carrier_code) DO NOTHING;

INSERT INTO flight_data.airports (airport_id)
SELECT DISTINCT airport_id FROM staging_airport_versions ORDER BY 1
ON CONFLICT (airport_id) DO NOTHING;

INSERT INTO flight_data.airport_versions (airport_seq_id, airport_id, airport_code, city_market_id)
SELECT airport_seq_id, airport_id, airport_code, city_market_id
FROM staging_airport_versions ORDER BY airport_seq_id
ON CONFLICT (airport_seq_id) DO NOTHING;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM staging_airport_versions AS s
        JOIN flight_data.airport_versions AS v USING (airport_seq_id)
        WHERE (s.airport_id, s.airport_code, s.city_market_id)
           <> (v.airport_id, v.airport_code, v.city_market_id)
    ) THEN
        RAISE EXCEPTION 'An airport sequence ID has conflicting airport metadata';
    END IF;
END;
$$;

WITH inserted AS (
    INSERT INTO flight_data.flights (
        flight_date, carrier_code, flight_number, tail_number,
        origin_airport_id, origin_airport_seq_id, dest_airport_id, dest_airport_seq_id,
        scheduled_dep_local, scheduled_arr_local, scheduled_elapsed_min, distance_miles
    )
    SELECT split_part(btrim(s."FL_DATE"), ' ', 1)::date, upper(btrim(s."OP_UNIQUE_CARRIER")),
           btrim(s."OP_CARRIER_FL_NUM"), NULLIF(upper(btrim(s."TAIL_NUM")), ''),
           s."ORIGIN_AIRPORT_ID", s."ORIGIN_AIRPORT_SEQ_ID", s."DEST_AIRPORT_ID", s."DEST_AIRPORT_SEQ_ID",
           (left(t.departure, 2) || ':' || right(t.departure, 2))::time,
           (left(t.arrival, 2) || ':' || right(t.arrival, 2))::time,
           s."CRS_ELAPSED_TIME", s."DISTANCE"
    FROM staging_flights AS s
    CROSS JOIN LATERAL (VALUES (lpad(s."CRS_DEP_TIME", 4, '0'), lpad(s."CRS_ARR_TIME", 4, '0'))) AS t(departure, arrival)
    ON CONFLICT ON CONSTRAINT flights_schedule_key DO NOTHING
    RETURNING 1
)
SELECT incoming.csv_rows, saved.inserted_rows, incoming.csv_rows - saved.inserted_rows AS duplicate_rows
FROM (SELECT count(*) AS csv_rows FROM staging_flights) AS incoming
CROSS JOIN (SELECT count(*) AS inserted_rows FROM inserted) AS saved;

COMMIT;
