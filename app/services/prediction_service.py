from app.core.config import settings


class PredictionService:
    @staticmethod
    def model_status() -> dict[str, str]:
        configured = bool(getattr(settings, "gemini_api_key", ""))
        return {
            "model_name": "Lotto-Net Gemini AI Core",
            "version": "2.5-pro-ready" if configured else "not-configured",
            "status": "IDLE" if configured else "UNAVAILABLE",
        }
