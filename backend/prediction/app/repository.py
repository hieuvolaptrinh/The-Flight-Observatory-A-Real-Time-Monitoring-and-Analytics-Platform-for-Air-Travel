from datetime import datetime

from app.schemas import PipelineOutput, Results


class PredictionRepository:
    """Store each complete prediction run atomically in the processed database."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def migrate(self) -> None:
        import psycopg

        with psycopg.connect(self.database_url) as conn:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext('analytics.flight_predictions'))")
            conn.execute("CREATE SCHEMA IF NOT EXISTS analytics")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS analytics.flight_predictions (
                    run_id uuid PRIMARY KEY,
                    evaluated_at timestamptz NOT NULL,
                    model_version text NOT NULL,
                    payload jsonb NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS flight_predictions_latest_idx
                ON analytics.flight_predictions (evaluated_at DESC, run_id DESC)
            """)

    def save(self, run_id: str, evaluated_at: datetime, output: PipelineOutput) -> None:
        import psycopg
        from psycopg.types.json import Jsonb

        with psycopg.connect(self.database_url) as conn:
            conn.execute("""
                INSERT INTO analytics.flight_predictions (run_id, evaluated_at, model_version, payload)
                VALUES (%s, %s, %s, %s)
            """, (run_id, evaluated_at, output.metadata["model_version"], Jsonb(output.model_dump(mode="json"))))

    def latest(self, service: str) -> Results | None:
        import psycopg

        with psycopg.connect(self.database_url) as conn:
            row = conn.execute("""
                SELECT evaluated_at, payload FROM analytics.flight_predictions
                ORDER BY evaluated_at DESC, run_id DESC
                LIMIT 1
            """).fetchone()
        if row is None:
            return None
        evaluated_at, payload = row
        return Results(service=service, storage="postgresql", ready=True,
                       updated_at=evaluated_at, output=PipelineOutput.model_validate(payload))
