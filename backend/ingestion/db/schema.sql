BEGIN;

CREATE SCHEMA IF NOT EXISTS flight_data;
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS flight_data.simulator_offsets (
    source_url text PRIMARY KEY,
    next_start integer NOT NULL CHECK (next_start >= 0),
    updated_at timestamptz NOT NULL DEFAULT statement_timestamp()
);

CREATE TABLE IF NOT EXISTS flight_data.airlines (
    carrier_code text PRIMARY KEY CHECK (carrier_code <> ''),
    carrier_name text
);

CREATE TABLE IF NOT EXISTS flight_data.airports (
    airport_id integer PRIMARY KEY CHECK (airport_id > 0)
);

CREATE TABLE IF NOT EXISTS flight_data.airport_versions (
    airport_seq_id integer PRIMARY KEY CHECK (airport_seq_id > 0),
    airport_id integer NOT NULL REFERENCES flight_data.airports,
    airport_code text NOT NULL CHECK (airport_code ~ '^[A-Z0-9]{3}$'),
    city_market_id integer NOT NULL CHECK (city_market_id > 0),
    UNIQUE (airport_id, airport_seq_id)
);

CREATE TABLE IF NOT EXISTS flight_data.flights (
    flight_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    flight_date date NOT NULL,
    carrier_code text NOT NULL REFERENCES flight_data.airlines,
    flight_number text NOT NULL CHECK (flight_number ~ '^[0-9]+$'),
    tail_number text,
    origin_airport_id integer NOT NULL,
    origin_airport_seq_id integer NOT NULL,
    dest_airport_id integer NOT NULL,
    dest_airport_seq_id integer NOT NULL,
    scheduled_dep_local time(0) NOT NULL,
    scheduled_arr_local time(0),
    scheduled_elapsed_min numeric(8, 2) CHECK (
        scheduled_elapsed_min >= 0 AND scheduled_elapsed_min <> 'NaN'::numeric
    ),
    distance_miles numeric(8, 2) CHECK (distance_miles >= 0 AND distance_miles <> 'NaN'::numeric),
    loaded_at timestamptz NOT NULL DEFAULT statement_timestamp(),
    FOREIGN KEY (origin_airport_id, origin_airport_seq_id)
        REFERENCES flight_data.airport_versions (airport_id, airport_seq_id),
    FOREIGN KEY (dest_airport_id, dest_airport_seq_id)
        REFERENCES flight_data.airport_versions (airport_id, airport_seq_id),
    CONSTRAINT flights_schedule_key UNIQUE (
        flight_date, carrier_code, flight_number, origin_airport_id, dest_airport_id, scheduled_dep_local
    )
);

CREATE INDEX IF NOT EXISTS flights_carrier_date_idx
    ON flight_data.flights (carrier_code, flight_date);
CREATE INDEX IF NOT EXISTS flights_route_date_idx
    ON flight_data.flights (origin_airport_id, dest_airport_id, flight_date);

-- Populate only from a source with observed outcomes. Signed values retain early arrivals/departures.
CREATE TABLE IF NOT EXISTS flight_data.flight_outcomes (
    flight_id bigint PRIMARY KEY REFERENCES flight_data.flights ON DELETE CASCADE,
    dep_delay_min numeric(8, 2) CHECK (dep_delay_min <> 'NaN'::numeric),
    arr_delay_min numeric(8, 2) CHECK (arr_delay_min <> 'NaN'::numeric),
    cancelled boolean NOT NULL,
    diverted boolean NOT NULL
);

CREATE OR REPLACE VIEW flight_data.flight_schedule AS
SELECT f.flight_id, EXTRACT(ISODOW FROM f.flight_date)::smallint AS day_of_week,
       f.flight_date, f.carrier_code, f.tail_number, f.flight_number,
       f.origin_airport_id, f.origin_airport_seq_id,
       origin.city_market_id AS origin_city_market_id, origin.airport_code AS origin,
       f.dest_airport_id, f.dest_airport_seq_id,
       dest.city_market_id AS dest_city_market_id, dest.airport_code AS dest,
       f.scheduled_dep_local, f.scheduled_arr_local, f.scheduled_elapsed_min, f.distance_miles
FROM flight_data.flights AS f
JOIN flight_data.airport_versions AS origin ON origin.airport_seq_id = f.origin_airport_seq_id
JOIN flight_data.airport_versions AS dest ON dest.airport_seq_id = f.dest_airport_seq_id;

-- One complete dashboard payload per requested half-open date range.
CREATE TABLE IF NOT EXISTS analytics.schedule_snapshots (
    date_from date NOT NULL,
    date_to date NOT NULL,
    computed_at timestamptz NOT NULL,
    flight_count bigint NOT NULL CHECK (flight_count >= 0),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    PRIMARY KEY (date_from, date_to),
    CONSTRAINT schedule_snapshots_window CHECK (date_to - date_from BETWEEN 1 AND 1096)
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'analytics.schedule_snapshots'::regclass
                    AND conname = 'schedule_snapshots_window') THEN
        ALTER TABLE analytics.schedule_snapshots DROP CONSTRAINT IF EXISTS schedule_snapshots_check;
        ALTER TABLE analytics.schedule_snapshots ADD CONSTRAINT schedule_snapshots_window
            CHECK (date_to - date_from BETWEEN 1 AND 1096);
    END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS analytics.forecasts (
    forecast_date date PRIMARY KEY,
    computed_at timestamptz NOT NULL DEFAULT statement_timestamp(),
    model text NOT NULL,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object')
);

CREATE OR REPLACE FUNCTION analytics.refresh_schedule(p_from date, p_to date)
RETURNS timestamptz
LANGUAGE plpgsql
AS $$
DECLARE
    refreshed_at timestamptz;
BEGIN
    IF p_from IS NULL OR p_to IS NULL OR NOT isfinite(p_from) OR NOT isfinite(p_to) THEN
        RAISE EXCEPTION 'Use finite start and end dates';
    END IF;
    IF p_to - p_from NOT BETWEEN 1 AND 1096 THEN
        RAISE EXCEPTION 'Use a date range of 1 to 1096 days with an exclusive end';
    END IF;

    -- Serialize refreshes for the same window before reading the source data.
    PERFORM pg_advisory_xact_lock(hashtextextended(
        'analytics.refresh_schedule/' || (p_from - DATE '2000-01-01') || '/' || (p_to - DATE '2000-01-01'), 0
    ));

    WITH source_rows AS MATERIALIZED (
        SELECT f.flight_date, f.scheduled_elapsed_min, f.distance_miles,
               CASE WHEN NOT o.cancelled AND NOT o.diverted THEN o.arr_delay_min END AS arr_delay_min
        FROM flight_data.flights AS f
        LEFT JOIN flight_data.flight_outcomes AS o USING (flight_id)
        WHERE f.flight_date >= p_from AND f.flight_date < p_to
    ), day_stats AS (
        SELECT flight_date, count(*) AS flight_count,
               count(arr_delay_min) AS observed_arrivals,
               count(*) FILTER (WHERE arr_delay_min >= 15) AS delayed_arrivals,
               count(*) FILTER (WHERE distance_miles IS NOT NULL AND scheduled_elapsed_min IS NOT NULL) AS pair_count,
               sum(distance_miles) FILTER (WHERE scheduled_elapsed_min IS NOT NULL) AS distance_sum,
               sum(scheduled_elapsed_min) FILTER (WHERE distance_miles IS NOT NULL) AS elapsed_sum
        FROM source_rows
        GROUP BY flight_date
    ), daily AS (
        SELECT p_from + calendar.day_offset AS day,
               COALESCE(s.flight_count, 0) AS flight_count,
               COALESCE(s.observed_arrivals, 0) AS observed_arrivals,
               COALESCE(s.delayed_arrivals, 0) AS delayed_arrivals,
               COALESCE(s.pair_count, 0) AS pair_count,
               s.distance_sum, s.elapsed_sum
        FROM generate_series(0, p_to - p_from - 1) AS calendar(day_offset)
        LEFT JOIN day_stats AS s ON s.flight_date = p_from + calendar.day_offset
    ), series AS (
        SELECT g.grain, date_trunc(g.grain, d.day::timestamp)::date AS period_start,
               sum(d.flight_count) AS flight_count,
               sum(d.observed_arrivals) AS observed_arrivals,
               sum(d.delayed_arrivals) AS delayed_arrivals,
               round(100.0 * sum(d.delayed_arrivals) / NULLIF(sum(d.observed_arrivals), 0), 2) AS arrival_delay_pct,
               sum(d.pair_count) AS pair_count,
               round(sum(d.distance_sum) / NULLIF(sum(d.pair_count), 0), 2) AS avg_distance_miles,
               round(sum(d.elapsed_sum) / NULLIF(sum(d.pair_count), 0), 2) AS avg_scheduled_elapsed_min
        FROM daily AS d
        CROSS JOIN (VALUES ('day'), ('week'), ('month')) AS g(grain)
        GROUP BY g.grain, period_start
    ), daily_histogram AS (
        SELECT flight_date, floor(scheduled_elapsed_min / 30)::integer * 30 AS bin_start_min,
               count(*) AS flight_count
        FROM source_rows
        WHERE scheduled_elapsed_min IS NOT NULL
        GROUP BY flight_date, bin_start_min
    ), histogram AS (
        SELECT g.grain, date_trunc(g.grain, h.flight_date::timestamp)::date AS period_start,
               h.bin_start_min, h.bin_start_min + 30 AS bin_end_min, sum(h.flight_count) AS flight_count
        FROM daily_histogram AS h
        CROSS JOIN (VALUES ('day'), ('week'), ('month')) AS g(grain)
        GROUP BY g.grain, period_start, h.bin_start_min
    ), trend AS (
        SELECT day, flight_count,
               count(*) OVER trailing_week AS days_in_average,
               round(avg(flight_count) OVER trailing_week, 2) AS moving_avg_7d
        FROM daily
        WINDOW trailing_week AS (ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
    ), seasonality AS (
        SELECT pattern, season, count(*) AS days_in_range, sum(flight_count) AS flight_count,
               round(avg(flight_count), 2) AS avg_flights_per_day
        FROM daily
        CROSS JOIN LATERAL (VALUES ('weekday', EXTRACT(ISODOW FROM day)::integer),
                                   ('month_of_year', EXTRACT(MONTH FROM day)::integer)) AS s(pattern, season)
        GROUP BY pattern, season
    ), correlation AS (
        SELECT regr_count(scheduled_elapsed_min::double precision, distance_miles::double precision) AS pair_count,
               corr(scheduled_elapsed_min::double precision, distance_miles::double precision) AS pearson_r
        FROM source_rows
    )
    INSERT INTO analytics.schedule_snapshots (date_from, date_to, computed_at, flight_count, payload)
    SELECT p_from, p_to, clock_timestamp(),
           (SELECT sum(flight_count)::bigint FROM daily),
           jsonb_build_object(
               'series', (SELECT jsonb_agg(to_jsonb(s) ORDER BY s.grain, s.period_start) FROM series AS s),
               'histogram', COALESCE((SELECT jsonb_agg(to_jsonb(h) ORDER BY h.grain, h.period_start, h.bin_start_min)
                                     FROM histogram AS h), '[]'::jsonb),
               'trend', (SELECT jsonb_agg(to_jsonb(t) ORDER BY t.day) FROM trend AS t),
               'seasonality', (SELECT jsonb_agg(to_jsonb(s) ORDER BY s.pattern, s.season) FROM seasonality AS s),
               'correlation', (SELECT to_jsonb(c) FROM correlation AS c)
           )
    ON CONFLICT (date_from, date_to) DO UPDATE
        SET computed_at = EXCLUDED.computed_at, flight_count = EXCLUDED.flight_count, payload = EXCLUDED.payload
    RETURNING computed_at INTO refreshed_at;

    RETURN refreshed_at;
END;
$$;

COMMIT;
