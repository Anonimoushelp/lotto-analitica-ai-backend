from typing import Literal

from pydantic import BaseModel, ConfigDict


class ModelStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str
    version: str
    status: Literal["INITIALIZED", "TRAINING", "IDLE", "UNAVAILABLE"]
