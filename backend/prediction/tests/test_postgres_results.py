"""Exercise the demo recovery workflow against a disposable PostgreSQL database."""
import os
from unittest import TestCase, skipUnless
from unittest.mock import AsyncMock

import psycopg
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.pipeline import Pipeline
from app.schemas import PipelineOutput


@skipUnless(os.getenv("TEST_PREDICTION_DATABASE_URL"), "Requires a disposable prediction database")
class PredictionResultsTest(TestCase):
    def test_persistence_restart_and_recovery(self):
        url = os.environ["TEST_PREDICTION_DATABASE_URL"]
        with psycopg.connect(url) as conn:
            self.assertTrue(conn.info.dbname.startswith("test_prediction_"))
            self.assertIsNone(conn.execute("SELECT to_regclass('analytics.flight_predictions')").fetchone()[0])

        settings = Settings(database_url=url, scheduler_enabled=False, run_on_startup=False)
        pipeline = Pipeline(settings)
        pipeline.run = AsyncMock(return_value=PipelineOutput(
            items=[{"flight_key": "airlabs:fixture", "flight_date": "2026-11-22", "flight": "AA100",
                    "delay": 12, "probability": 30, "risk_level": "medium"}],
            metadata={"model_version": "fixture", "ready": True},
        ))

        with TestClient(create_app(settings, pipeline)) as client:
            self.assertFalse(client.get("/results").json()["ready"])
            self.assertEqual(client.post("/run").json()["status"], "completed")
            saved = client.get("/results").json()
            self.assertTrue(saved["ready"])
            self.assertEqual(saved["storage"], "postgresql")

        with TestClient(create_app(settings, pipeline)) as client:
            self.assertEqual(client.get("/predictions").json(), saved)
            with psycopg.connect(url) as conn:
                conn.execute("DELETE FROM analytics.flight_predictions")
            self.assertFalse(client.get("/results").json()["ready"])
            self.assertEqual(client.post("/run").json()["status"], "completed")
            self.assertEqual(client.get("/results").json()["output"], saved["output"])
        self.assertEqual(pipeline.run.await_count, 2)

    def test_schedule_window_includes_tomorrow_beyond_twenty_four_hours(self):
        url = os.environ["TEST_PREDICTION_DATABASE_URL"]
        with psycopg.connect(url) as conn:
            self.assertTrue(conn.info.dbname.startswith("test_prediction_"))
            conn.execute("""
                CREATE TABLE provider_poll_state (id integer, last_started_epoch double precision);
                INSERT INTO provider_poll_state VALUES (1, extract(epoch FROM timestamptz '2026-11-21 16:00+00'));
                CREATE TABLE provider_cache (cache_key text, payload text);
                INSERT INTO provider_cache VALUES ('airport:JFK', '{"timezone":"America/New_York"}');
                CREATE TABLE ingested_flights (
                    flight_key text, flight_code text, op_unique_carrier text, origin text, dest text,
                    fl_date text, crs_dep_time text, day_of_week integer, distance real, crs_elapsed_time real
                );
                INSERT INTO ingested_flights VALUES
                    ('today', 'AA1', 'AA', 'JFK', 'LAX', '2026-11-21', '14:00', 6, 2400, 360),
                    ('tomorrow', 'AA2', 'AA', 'JFK', 'LAX', '2026-11-22', '13:30', 7, 2400, 360),
                    ('after', 'AA3', 'AA', 'JFK', 'LAX', '2026-11-23', '01:00', 1, 2400, 360);
                CREATE TABLE live_flight_details (flight_key text, payload text);
                INSERT INTO live_flight_details VALUES
                    ('today', '{"source":"airlabs","flight_status":"scheduled","scheduled_dep_utc":"2026-11-21T19:00Z"}'),
                    ('tomorrow', '{"source":"airlabs","flight_status":"scheduled","scheduled_dep_utc":"2026-11-22T18:30Z"}'),
                    ('after', '{"source":"airlabs","flight_status":"scheduled","scheduled_dep_utc":"2026-11-23T06:00Z"}');
            """)
        settings = Settings(source_database_url=url, saved_schedule_clock=True)
        rows = Pipeline(settings)._load_scheduled_departures_sync()
        self.assertEqual([(row["flight_key"], row["is_tomorrow"]) for row in rows],
                         [("tomorrow", True), ("today", False)])
