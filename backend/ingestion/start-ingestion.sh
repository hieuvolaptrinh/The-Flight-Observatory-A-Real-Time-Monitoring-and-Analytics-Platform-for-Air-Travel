#!/usr/bin/env bash
set -euo pipefail

postgres_pid=
api_pid=
postgres_stop_signal=TERM

shutdown() {
    trap '' TERM INT
    if [[ -n "$api_pid" ]]; then
        kill -TERM "$api_pid" 2>/dev/null || true
        wait "$api_pid" || true
    fi
    if [[ -n "$postgres_pid" ]]; then
        kill -s "$postgres_stop_signal" "$postgres_pid" 2>/dev/null || true
        wait "$postgres_pid" || true
    fi
}

trap shutdown EXIT
trap 'exit 0' TERM INT

docker-entrypoint.sh postgres -c 'listen_addresses=*' &
postgres_pid=$!

# The temporary server used by initdb accepts only Unix socket connections.
until pg_isready -q -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do
    if ! kill -0 "$postgres_pid" 2>/dev/null; then
        wait "$postgres_pid"
        exit 1
    fi
    sleep 1
done
postgres_stop_signal=INT

psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /opt/analytics-db/schema.sql

gosu appuser "$@" &
api_pid=$!

# Restart the container if either process exits on its own.
wait -n "$postgres_pid" "$api_pid"
exit 1
