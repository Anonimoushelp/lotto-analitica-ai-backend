from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FunctionalEncryptionOperation(StrEnum):
    encrypt = "encrypt"
    evaluate = "evaluate"
    decrypt = "decrypt"


class FunctionalEncryptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: FunctionalEncryptionOperation
    payload: dict[str, object] = Field(default_factory=dict)


class FunctionalEncryptionOperationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module: str
    capability: str
    operation: FunctionalEncryptionOperation
    status: str
    production_ready: bool
    cryptographic_backend_connected: bool
    provider: str
    message: str
    result: dict[str, object] | None = None
