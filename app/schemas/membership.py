from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MembershipRole = Literal["admin", "analyst", "viewer", "service"]


class MembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    user_id: int
    role: MembershipRole
    is_active: bool


class MembershipCreate(BaseModel):
    user_id: int = Field(gt=0)
    role: MembershipRole = "viewer"


class MembershipUpdate(BaseModel):
    role: MembershipRole | None = None
    is_active: bool | None = None
