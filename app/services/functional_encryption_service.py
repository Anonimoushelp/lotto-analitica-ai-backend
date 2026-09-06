from app.core.config import settings
from app.services.functional_encryption_provider import (
    FunctionalEncryptionProvider,
    UnavailableFunctionalEncryptionProvider,
)


def get_functional_encryption_provider() -> FunctionalEncryptionProvider:
    if settings.functional_encryption_provider == "none":
        return UnavailableFunctionalEncryptionProvider()
    raise RuntimeError("Unsupported Functional Encryption provider")


def get_functional_encryption_status() -> dict[str, object]:
    provider = get_functional_encryption_provider()
    provider_status = provider.status()
    return {
        "module": "M66",
        "capability": "functional_encryption",
        "status": "available" if provider_status.available else "integration_pending",
        "production_ready": provider_status.production_ready,
        "cryptographic_backend_connected": provider_status.available,
        "provider": provider_status.provider,
        "message": provider_status.message,
    }


def execute_functional_encryption(
    operation: str, payload: dict[str, object]
) -> dict[str, object]:
    provider = get_functional_encryption_provider()
    return provider.execute(operation, payload)
