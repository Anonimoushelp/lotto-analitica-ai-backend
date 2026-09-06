from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TeeOperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["attest"]
    nonce: str = Field(min_length=16, max_length=128)


class TeeOperationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module: str
    operation: Literal["attest"]
    status: Literal["completed", "integration_pending"]
    provider: str
    production_ready: bool
    attestation_available: bool
    message: str
