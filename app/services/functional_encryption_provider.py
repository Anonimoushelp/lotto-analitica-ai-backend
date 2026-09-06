from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FunctionalEncryptionProviderStatus:
    provider: str
    available: bool
    production_ready: bool
    message: str


class FunctionalEncryptionProvider(Protocol):
    def status(self) -> FunctionalEncryptionProviderStatus:
        """Return verified provider capability status without synthetic evidence."""


class UnavailableFunctionalEncryptionProvider:
    """Fail-closed provider used until a verified FE/IPFE implementation is installed."""

    def status(self) -> FunctionalEncryptionProviderStatus:
        return FunctionalEncryptionProviderStatus(
            provider="none",
            available=False,
            production_ready=False,
            message="No verified Functional Encryption provider is installed",
        )
