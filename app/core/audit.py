import logging

from app.models.user import User

logger = logging.getLogger("lotto_analitica.audit")


def _safe_log_value(value: object) -> str:
    return str(value).replace("\r", " ").replace("\n", " ")


def log_mutation(
    *,
    action: str,
    resource: str,
    resource_id: int,
    actor: User,
) -> None:
    logger.info(
        "audit.%s resource=%s resource_id=%s actor_user_id=%s actor_role=%s",
        _safe_log_value(action),
        _safe_log_value(resource),
        resource_id,
        actor.id,
        _safe_log_value(actor.role),
    )
