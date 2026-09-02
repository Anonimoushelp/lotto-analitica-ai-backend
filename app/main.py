from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.lotteries import router as lotteries_router
from app.api.routes.lottery_draws import router as lottery_draws_router
from app.core.config import settings


app = FastAPI(
    title="Lotto Analítica AI",
    version="0.1.0",
    description="Backend analítico para resultados históricos y análisis de loterías.",
)


if settings.cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )


@app.get("/")
def root():
    return {
        "app": "Lotto Analítica AI",
        "version": "0.1.0",
        "environment": "development",
        "status": "online",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "Lotto Analítica AI",
    }


app.include_router(
    lotteries_router,
)

app.include_router(
    lottery_draws_router,
)
