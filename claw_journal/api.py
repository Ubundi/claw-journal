from __future__ import annotations

from fastapi import FastAPI, Query

from .service import UsageService


def create_app(usage_service: UsageService) -> FastAPI:
    app = FastAPI(title="Claw Journal", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/usage/daily")
    def daily_usage(days: int = Query(default=30, ge=1, le=365)) -> dict[str, object]:
        return {"days": days, "rows": usage_service.daily_usage(days=days)}

    @app.get("/api/usage/sessions")
    def session_usage(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
        return {"limit": limit, "rows": usage_service.session_usage(limit=limit)}

    @app.get("/api/reasoning")
    def reasoning(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
        return {"limit": limit, "rows": usage_service.reasoning_events(limit=limit)}

    return app
