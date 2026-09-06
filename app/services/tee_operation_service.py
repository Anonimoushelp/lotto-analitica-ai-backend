from fastapi import HTTPException, status

from app.services.tee_provider import TeeProvider, UnavailableTeeProvider


def get_tee_provider() -> TeeProvider:
    return UnavailableTeeProvider()


def execute_tee_attestation(nonce: str) -> dict[str, object]:
    provider = get_tee_provider()
    provider_status = provider.attest(nonce)
    if not provider_status.available or not provider_status.attestation_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TEE attestation provider unavailable",
        )

    return {
        "module": "M67",
        "operation": "attest",
        "status": "completed",
        "provider": provider_status.provider,
        "production_ready": provider_status.production_ready,
        "attestation_available": provider_status.attestation_available,
        "message": provider_status.message,
    }
