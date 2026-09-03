# Production Deployment Checklist

## Required environment

- `ENVIRONMENT=production`
- `SECRET_KEY`: non-empty secret of at least 32 characters.
- `DATABASE_URL`: PostgreSQL URL with `sslmode=require`, `verify-ca`, or `verify-full`.
- `REDIS_URL`: `rediss://` URL.
- `CORS_ALLOWED_ORIGINS`: explicit frontend origin(s); no wildcard.
- `TRUSTED_HOSTS`: explicit production hostname(s).
- `ALLOW_INITIAL_REGISTRATION=false`.

## Pre-deployment gates

- Apply Alembic migrations before serving production traffic.
- Run the repository CI workflow successfully for the exact release commit.
- Provision PostgreSQL backups and verify restore procedures.
- Provision Redis with TLS and network restrictions appropriate to the deployment.
- Terminate HTTPS at the trusted edge/reverse proxy and forward traffic only to the backend network.
- Configure the production hostname in `TRUSTED_HOSTS`.
- Configure the frontend origin(s) in `CORS_ALLOWED_ORIGINS`.
- Store secrets in the deployment platform's secret manager; do not commit them.

## Runtime checks

- `/health` returns healthy only when the service is running; verify database readiness separately during deployment validation.
- Verify authentication, authorization, rate limiting, security headers, and production docs behavior after deployment.
- Confirm logs contain no credentials, tokens, password hashes, or connection strings.

## Rollback

- Keep the previous application image/release available.
- Do not roll back database schema independently of application compatibility.
- Verify migration downgrade/forward strategy before production changes.
