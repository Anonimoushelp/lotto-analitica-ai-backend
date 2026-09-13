from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read_checklist(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_release_checklist_covers_release_identity_and_rollback():
    checklist = _read_checklist("RELEASE_CHECKLIST.md")

    required_controls = (
        "Registrar commit SHA exacto desplegado.",
        "Confirmar CI exitoso para ese SHA.",
        "Registrar la versión/release anterior disponible para rollback.",
        "Identificar SHA estable anterior.",
        "Restaurar la versión de aplicación anterior sin downgrade automático del esquema.",
    )

    for control in required_controls:
        assert control in checklist


def test_release_checklist_covers_runtime_and_privacy_controls():
    checklist = _read_checklist("RELEASE_CHECKLIST.md")

    required_controls = (
        "`/health` responde correctamente.",
        "Readiness de base de datos validada.",
        "Rutas críticas verificadas.",
        "No almacenar contraseñas, tokens, hashes de contraseña ni payloads con PII en logs.",
        "Revisar anualmente usuarios inactivos",
    )

    for control in required_controls:
        assert control in checklist


def test_production_deployment_checklist_requires_secure_runtime_baseline():
    checklist = _read_checklist("DEPLOYMENT_PRODUCTION_CHECKLIST.md")

    required_controls = (
        "`ENVIRONMENT=production`",
        "`DATABASE_URL`: PostgreSQL URL with `sslmode=require`, `verify-ca`, or `verify-full`.",
        "`REDIS_URL`: `rediss://` URL.",
        "`CORS_ALLOWED_ORIGINS`: explicit frontend origin(s); no wildcard.",
        "`TRUSTED_HOSTS`: explicit production hostname(s).",
        "`ALLOW_INITIAL_REGISTRATION=false`.",
        "Store secrets in the deployment platform's secret manager; do not commit them.",
    )

    for control in required_controls:
        assert control in checklist
