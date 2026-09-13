import logging

from app.models.user import User

logger = logging.getLogger("lotto_analitica.audit")

_ALLOWED_MUTATIONS = {
    ("create", "bootstrap_admin"),
    ("create", "lottery"),
    ("update", "lottery"),
    ("delete", "lottery"),
    ("create", "draw"),
    ("update", "draw"),
    ("delete", "draw"),
    ("update_credentials", "user"),
}


def _safe_log_value(value: object) -> str:
    return str(value).replace("\r", " ").replace("\n", " ")


def log_mutation(
    *,
    action: str,
    resource: str,
    resource_id: int,
    actor: User,
) -> None:
    safe_action = _safe_log_value(action)
    safe_resource = _safe_log_value(resource)
    if (safe_action, safe_resource) not in _ALLOWED_MUTATIONS:
        raise ValueError("Unsupported audit mutation")

    logger.info(
        "audit.%s resource=%s resource_id=%s actor_user_id=%s actor_role=%s",
        safe_action,
        safe_resource,
        resource_id,
        actor.id,
        _safe_log_value(actor.role),
    )
