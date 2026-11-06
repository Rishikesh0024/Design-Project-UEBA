from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints import (
    activity,
    alerts,
    analytics,
    auth,
    datasets,
    detection,
    evaluation,
    profiles,
)
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="UEBA Platform API",
    version="1.0.0",
    description="Authenticated API for dataset ingestion, behavioral analysis, and alert review.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=(
        r"https?://(localhost|127\.0\.0\.1):\d+"
        if settings.ENVIRONMENT.lower() != "production"
        else None
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

for router in (
    auth.router,
    datasets.router,
    activity.router,
    profiles.router,
    detection.router,
    alerts.router,
    analytics.router,
    evaluation.router,
):
    app.include_router(router, prefix="/api/v1")

app.include_router(datasets.demo_router, prefix="/api")


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
