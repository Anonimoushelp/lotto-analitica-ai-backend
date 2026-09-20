#!/usr/bin/env bash
set -euo pipefail

: "${PGHOST:?PGHOST is required}"
: "${PGPORT:?PGPORT is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGPASSWORD:?PGPASSWORD is required}"
: "${PGDATABASE:?PGDATABASE is required}"

restore_db="ci_restore_verify"
backup_file="$(mktemp --suffix=.dump)"

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

pg_dump --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$PGDATABASE" --format=custom --file="$backup_file"

"${psql_cmd[@]}" -c "DROP DATABASE IF EXISTS \"$restore_db\" WITH (FORCE);"
"${psql_cmd[@]}" -c "CREATE DATABASE \"$restore_db\";"

pg_restore --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$restore_db" --no-owner --exit-on-error "$backup_file"

restored_marker="$(psql --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$restore_db" --tuples-only --no-align --set=ON_ERROR_STOP=1 -c "SELECT marker FROM backup_restore_probe WHERE id = 1;")"
restored_payload="$(psql --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$restore_db" --tuples-only --no-align --set=ON_ERROR_STOP=1 -c "SELECT payload->>'schema' FROM backup_restore_probe WHERE id = 1;")"
restored_migration="$(psql --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$restore_db" --tuples-only --no-align --set=ON_ERROR_STOP=1 -c "SELECT version_num FROM alembic_version LIMIT 1;")"
restored_tables="$(psql --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --dbname="$restore_db" --tuples-only --no-align --set=ON_ERROR_STOP=1 -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('lotteries', 'lottery_draws', 'alembic_version');")"

[[ "$restored_marker" == "bcp-restore-ok" ]]
[[ "$restored_payload" == "v1" ]]
[[ "$restored_migration" == "d1e4f7a9c2b6" ]]
[[ "$restored_tables" == "3" ]]

echo "PostgreSQL backup/restore verification passed."
