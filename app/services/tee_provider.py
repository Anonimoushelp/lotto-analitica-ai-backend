from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TeeProviderStatus:
    provider: str
    available: bool
    production_ready: bool
    attestation_available: bool
    message: str


class TeeProvider(Protocol):
    def status(self) -> TeeProviderStatus:
        """Return verified confidential-computing capability status."""


class UnavailableTeeProvider:
    """Fail-closed provider until verified TEE infrastructure is connected."""

    def status(self) -> TeeProviderStatus:
        return TeeProviderStatus(
            provider="none",
            available=False,
            production_ready=False,
            attestation_available=False,
            message="No verified TEE provider is connected",
        )
