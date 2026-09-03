import logging

from app.models.user import User

logger = logging.getLogger("lotto_analitica.audit")


def log_mutation(
    *,
    action: str,
    resource: str,
    resource_id: int,
    actor: User,
) -> None:
    logger.info(
        "audit.%s resource=%s resource_id=%s actor_user_id=%s actor_role=%s",
        action,
        resource,
        resource_id,
        actor.id,
        actor.role,
    )
