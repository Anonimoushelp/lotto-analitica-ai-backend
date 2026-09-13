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
_ALLOWED_ROLES = {"admin", "analyst", "viewer", "service"}


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
    safe_role = _safe_log_value(actor.role)
    if (safe_action, safe_resource) not in _ALLOWED_MUTATIONS:
        raise ValueError("Unsupported audit mutation")
    if not isinstance(resource_id, int) or isinstance(resource_id, bool) or resource_id <= 0:
        raise ValueError("Invalid audit resource identifier")
    if actor.id is None or not isinstance(actor.id, int) or isinstance(actor.id, bool) or actor.id <= 0:
        raise ValueError("Invalid audit actor identifier")
    role_name = safe_role.split(" ", 1)[0]
    if role_name not in _ALLOWED_ROLES:
        raise ValueError("Invalid audit actor role")

    logger.info(
        "audit.%s resource=%s resource_id=%s actor_user_id=%s actor_role=%s",
        safe_action,
        safe_resource,
        resource_id,
        actor.id,
        safe_role,
    )
