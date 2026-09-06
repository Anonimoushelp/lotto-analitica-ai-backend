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

    def execute(self, operation: str, payload: dict[str, object]) -> dict[str, object]:
        """Execute a verified FE/IPFE operation or fail closed."""


class UnavailableFunctionalEncryptionProvider:
    """Fail-closed provider used until a verified FE/IPFE implementation is installed."""

    def status(self) -> FunctionalEncryptionProviderStatus:
        return FunctionalEncryptionProviderStatus(
            provider="none",
            available=False,
            production_ready=False,
            message="No verified Functional Encryption provider is installed",
        )

    def execute(self, operation: str, payload: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("No verified Functional Encryption provider is installed")
