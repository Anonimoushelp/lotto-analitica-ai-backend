from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    actor_user_id: int | None
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    details: str | None
    created_at: datetime
