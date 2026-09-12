import logging
import re
import time
import uuid

from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.functional_encryption import router as functional_encryption_router
from app.api.routes.lotteries import router as lotteries_router
from app.api.routes.lottery_draws import router as lottery_draws_router
from app.api.routes.predictions import router as predictions_router
from app.api.routes.statistics import router as statistics_router
from app.api.routes.tee import router as tee_router
from app.api.routes.users import router as users_router
from app.core.config import settings
from app.core.rate_limit import login_rate_limiter
from app.db.session import get_db

logger = logging.getLogger(__name__)
MAX_REQUEST_BODY_BYTES = 1_048_576
REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _get_request_id(request: Request) -> str:
    supplied_request_id = request.headers.get(REQUEST_ID_HEADER, "")
    if _REQUEST_ID_PATTERN.fullmatch(supplied_request_id):
        return supplied_request_id
    return str(uuid.uuid4())


class RequestBodyLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header"})
            if declared_length < 0:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header"})
            if declared_length > MAX_REQUEST_BODY_BYTES:
                return JSONResponse(status_code=413, content={"detail": "Request body too large"})
        return await call_next(request)


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = _get_request_id(request)
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "request_failed request_id=%s method=%s path=%s duration_ms=%.2f",
                request_id, request.method, request.url.path, duration_ms,
            )
            raise
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request_completed request_id=%s method=%s path=%s status_code=%s duration_ms=%.2f",
            request_id, request.method, request.url.path, response.status_code, duration_ms,
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if request.url.path.startswith("/api/v1/auth/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        if settings.environment.lower() == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
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

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
app.add_middleware(RequestBodyLimitMiddleware)
app.add_middleware(RequestObservabilityMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

if settings.cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None) or _get_request_id(request)
    logger.exception(
        "Unhandled application exception request_id=%s on %s %s",
        request_id, request.method, request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers={REQUEST_ID_HEADER: request_id},
    )


@app.get("/")
def root():
    return {"app": "Lotto Analítica AI", "version": "0.1.0", "status": "online"}


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Health check failed: PostgreSQL unavailable")
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"status": "unhealthy", "service": "Lotto Analítica AI"})

    if settings.environment.lower() == "production":
        try:
            login_rate_limiter.health_check()
        except Exception:
            logger.exception("Health check failed: Redis unavailable")
            return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"status": "unhealthy", "service": "Lotto Analítica AI"})

    return {"status": "healthy", "service": "Lotto Analítica AI"}


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(functional_encryption_router)
app.include_router(tee_router)
app.include_router(lotteries_router)
app.include_router(lottery_draws_router)
app.include_router(statistics_router)
app.include_router(predictions_router)
