#!/bin/sh
set -eu

# The official PostgreSQL image runs this only when initializing an empty volume.
psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
    --set=raw_db="$RAW_POSTGRES_DB" --set=processed_db="$POSTGRES_DB" <<'SQL'
SELECT format('CREATE DATABASE %I', :'processed_db')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'processed_db') \gexec
SELECT format('CREATE DATABASE %I', :'raw_db')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'raw_db') \gexec
SQL

psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /opt/plant-db/processed-schema.sql
psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /opt/plant-db/processed-legacy.sql
psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$RAW_POSTGRES_DB" -f /opt/plant-db/raw-schema.sql
