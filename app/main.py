import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.lotteries import router as lotteries_router
from app.api.routes.lottery_draws import router as lottery_draws_router
from app.core.config import settings

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response


is_development = settings.environment.lower() == "development"

app = FastAPI(
    title="Lotto Analítica AI",
    version="0.1.0",
    description="Backend analítico para resultados históricos y análisis de loterías.",
    docs_url="/docs" if is_development else None,
    redoc_url="/redoc" if is_development else None,
    openapi_url="/openapi.json" if is_development else None,
)

app.add_middleware(SecurityHeadersMiddleware)

if settings.cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled application exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/")
def root():
    return {"app": "Lotto Analítica AI", "version": "0.1.0", "status": "online"}


@app.get("/health")
def health():
    return {"status": "healthy", "service": "Lotto Analítica AI"}


app.include_router(auth_router)
app.include_router(lotteries_router)
app.include_router(lottery_draws_router)
