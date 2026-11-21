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

CREATE TABLE IF NOT EXISTS public.live_flight_details (
    flight_key text PRIMARY KEY,
    payload text NOT NULL
);

CREATE OR REPLACE VIEW flight_data.model_flights AS
WITH candidates AS (
    SELECT f.flight_date, f.carrier_code, ltrim(f.flight_number, '0') AS flight_number,
           f.origin, f.dest, f.scheduled_dep_local, f.day_of_week,
           f.distance_miles AS distance, f.scheduled_elapsed_min AS crs_elapsed_time,
           b.scheduled_departure_utc AS scheduled_at,
           CASE WHEN NOT o.cancelled AND NOT o.diverted THEN o.dep_delay_min END AS delay_minutes,
           'bts'::text AS source, f.flight_id::text AS source_id
    FROM flight_data.bts_imported_flights b
    JOIN flight_data.flight_schedule f USING (flight_id)
    LEFT JOIN flight_data.flight_outcomes o USING (flight_id)
    UNION ALL
    SELECT f.fl_date::date, upper(f.op_unique_carrier), ltrim(f.op_carrier_fl_num::text, '0'),
           f.origin, f.dest, f.crs_dep_time::time, f.day_of_week,
           f.distance, f.crs_elapsed_time, (d.payload::jsonb->>'scheduled_dep_utc')::timestamptz,
           CASE WHEN d.payload::jsonb->>'flight_status' = 'landed'
                THEN (d.payload::jsonb->>'dep_delay_min')::double precision END,
           'airlabs', f.flight_key
    FROM public.ingested_flights f
    JOIN public.live_flight_details d USING (flight_key)
    WHERE d.payload::jsonb->>'source' = 'airlabs'
)
SELECT DISTINCT ON (flight_date, carrier_code, flight_number, origin, dest, scheduled_dep_local)
       candidates.*, extract(hour FROM scheduled_dep_local)::integer % 24 AS dep_hour
FROM candidates
ORDER BY flight_date, carrier_code, flight_number, origin, dest, scheduled_dep_local,
         (delay_minutes IS NOT NULL) DESC, source DESC, source_id;

CREATE OR REPLACE VIEW flight_data.dashboard_flights AS
SELECT CASE WHEN m.source = 'airlabs' THEN m.source_id ELSE 'bts:' || m.source_id END AS flight_key,
       m.flight_date::text AS fl_date, m.day_of_week, m.carrier_code AS op_unique_carrier,
       a.carrier_name, COALESCE(a.tail_num, s.tail_number) AS tail_num,
       m.flight_number AS op_carrier_fl_num, m.carrier_code || m.flight_number AS flight_code,
       COALESCE(a.origin_airport_id,s.origin_airport_id) AS origin_airport_id, m.origin,
       COALESCE(a.dest_airport_id,s.dest_airport_id) AS dest_airport_id, m.dest,
       m.origin || ' → ' || m.dest AS route,
       to_char(m.scheduled_dep_local, 'HH24:MI') AS crs_dep_time,
       COALESCE(a.crs_arr_time,to_char(s.scheduled_arr_local, 'HH24:MI')) AS crs_arr_time,
       m.dep_hour, m.crs_elapsed_time, m.distance, m.delay_minutes,
       CASE WHEN m.delay_minutes IS NULL THEN 'unknown'
            WHEN m.delay_minutes < 15 THEN 'on_time'
            WHEN m.delay_minutes < 45 THEN 'moderate_delay' ELSE 'severe_delay' END AS delay_status,
       CASE WHEN m.delay_minutes >= 15 THEN 1 WHEN m.delay_minutes IS NOT NULL THEN 0 END AS is_delayed,
       COALESCE(a.fetched_at,s.loaded_at::text) AS fetched_at,
       COALESCE(a.ingested_at,s.loaded_at::text) AS ingested_at,
       to_jsonb(a)->>'raw_response_id' AS raw_response_id,
       (to_jsonb(a)->>'raw_row_index')::integer AS raw_row_index,
       jsonb_build_object('source', m.source, 'scheduled_dep_utc', m.scheduled_at,
           'delay_kind', CASE WHEN m.delay_minutes IS NOT NULL THEN 'observed_departure' ELSE 'unknown' END,
           'flight_status', COALESCE(d.payload::jsonb->>'flight_status',
               CASE WHEN o.cancelled THEN 'cancelled' WHEN o.diverted THEN 'diverted'
                    WHEN b.actual_departure_local IS NOT NULL THEN 'landed' ELSE 'unknown' END))::text AS payload
FROM flight_data.model_flights m
LEFT JOIN public.ingested_flights a ON m.source = 'airlabs' AND a.flight_key = m.source_id
LEFT JOIN public.live_flight_details d ON d.flight_key = a.flight_key
LEFT JOIN flight_data.flights s ON s.flight_id = CASE WHEN m.source = 'bts' THEN m.source_id::bigint END
LEFT JOIN flight_data.flight_outcomes o ON o.flight_id = s.flight_id
LEFT JOIN flight_data.bts_imported_flights b ON b.flight_id = s.flight_id;
