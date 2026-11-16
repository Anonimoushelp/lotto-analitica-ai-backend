#!/usr/bin/env bash
set -euo pipefail

: "${PGHOST:?PGHOST is required}"
: "${PGPORT:?PGPORT is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGPASSWORD:?PGPASSWORD is required}"
: "${PGDATABASE:?PGDATABASE is required}"

restore_db="ci_restore_verify"
backup_file="$(mktemp --suffix=.dump)"
backup_dir="$(dirname "$backup_file")"
backup_name="$(basename "$backup_file")"
pg_client_image="${PG_CLIENT_IMAGE:-postgres:16}"

cleanup() {
  rm -f "$backup_file"
  PGPASSWORD="$PGPASSWORD" psql --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$PGDATABASE" --set=ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"$restore_db\" WITH (FORCE);" >/dev/null 2>&1 || true
}
trap cleanup EXIT

psql_cmd=(psql --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$PGDATABASE" --set=ON_ERROR_STOP=1)

"${psql_cmd[@]}" <<'SQL'
CREATE TABLE IF NOT EXISTS backup_restore_probe (
  id integer PRIMARY KEY,
  marker text NOT NULL,
  payload jsonb NOT NULL
);
TRUNCATE backup_restore_probe;
INSERT INTO backup_restore_probe (id, marker, payload)
VALUES (1, 'bcp-restore-ok', '{"schema":"v1","numbers":[5,12,23,31,42]}'::jsonb);
SQL

expected_migration="$(psql --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$PGDATABASE" --tuples-only --no-align --set=ON_ERROR_STOP=1 -c "SELECT version_num FROM alembic_version LIMIT 1;")"

# Match the PostgreSQL client major version to the CI server image. Newer
# pg_dump clients can emit settings (for example transaction_timeout) that
# older PostgreSQL servers do not recognize during restore.
docker run --rm --network host \
  --env "PGPASSWORD=$PGPASSWORD" \
  --volume "$backup_dir:/backup" \
  "$pg_client_image" \
  pg_dump --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" \
    --dbname="$PGDATABASE" --format=custom --file="/backup/$backup_name"

"${psql_cmd[@]}" -c "DROP DATABASE IF EXISTS \"$restore_db\" WITH (FORCE);"
"${psql_cmd[@]}" -c "CREATE DATABASE \"$restore_db\";"

docker run --rm --network host \
  --env "PGPASSWORD=$PGPASSWORD" \
  --volume "$backup_dir:/backup:ro" \
  "$pg_client_image" \
  pg_restore --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" \
    --dbname="$restore_db" --no-owner --exit-on-error "/backup/$backup_name"

restored_marker="$(psql --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$restore_db" --tuples-only --no-align --set=ON_ERROR_STOP=1 -c "SELECT marker FROM backup_restore_probe WHERE id = 1;")"
restored_payload="$(psql --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$restore_db" --tuples-only --no-align --set=ON_ERROR_STOP=1 -c "SELECT payload->>'schema' FROM backup_restore_probe WHERE id = 1;")"
restored_migration="$(psql --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$restore_db" --tuples-only --no-align --set=ON_ERROR_STOP=1 -c "SELECT version_num FROM alembic_version LIMIT 1;")"
restored_tables="$(psql --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$restore_db" --tuples-only --no-align --set=ON_ERROR_STOP=1 -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('lotteries', 'lottery_draws', 'ingestion_schedule_states', 'alembic_version');")"

[[ "$restored_marker" == "bcp-restore-ok" ]]
[[ "$restored_payload" == "v1" ]]
[[ "$restored_migration" == "$expected_migration" ]]
[[ "$restored_tables" == "4" ]]

echo "PostgreSQL backup/restore verification passed."
