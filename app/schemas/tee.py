from pydantic import BaseModel, ConfigDict


class TeeStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module: str
    capability: str
    status: str
    production_ready: bool
    confidential_compute_backend_connected: bool
    provider: str
    attestation_available: bool
    message: str
