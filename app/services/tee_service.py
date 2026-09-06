from app.services.tee_provider import TeeProvider, UnavailableTeeProvider


def get_tee_provider() -> TeeProvider:
    return UnavailableTeeProvider()


def get_tee_status() -> dict[str, object]:
    provider = get_tee_provider()
    provider_status = provider.status()
    return {
        "module": "M67",
        "capability": "trusted_execution_environment",
        "status": "available" if provider_status.available else "integration_pending",
        "production_ready": provider_status.production_ready,
        "confidential_compute_backend_connected": provider_status.available,
        "provider": provider_status.provider,
        "attestation_available": provider_status.attestation_available,
        "message": provider_status.message,
    }
