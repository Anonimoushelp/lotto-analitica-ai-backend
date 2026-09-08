from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent


def record_audit_event(
    db: Session,
    *,
    tenant_id: int,
    actor_user_id: int | None,
    action: str,
    resource_type: str,
    resource_id: int | str | None,
    outcome: str = "success",
    details: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=None if resource_id is None else str(resource_id),
        outcome=outcome,
        details=details,
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    return event
