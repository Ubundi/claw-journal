from __future__ import annotations

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .service import UsageService


def create_app(usage_service: UsageService) -> FastAPI:
    app = FastAPI(title="Claw Journal", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "name": "Claw Journal API",
            "dashboard": "Run the React dashboard from frontend/ (npm run dev)",
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/dashboard-data")
    def dashboard_data() -> dict[str, object]:
        return usage_service.get_dashboard_data()

    @app.get("/api/usage/daily")
    def daily_usage(days: int = Query(default=30, ge=1, le=365)) -> dict[str, object]:
        return {"days": days, "rows": usage_service.daily_usage(days=days)}

    @app.get("/api/usage/sessions")
    def session_usage(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
        return {"limit": limit, "rows": usage_service.session_usage(limit=limit)}

    @app.get("/api/reasoning")
    def reasoning(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
        return {"limit": limit, "rows": usage_service.reasoning_events(limit=limit)}

    @app.get("/api/usage/reconciled")
    def reconciled_usage(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
        return {"limit": limit, "rows": usage_service.reconciled_session_usage(limit=limit)}

    @app.get("/api/usage/cost-sources")
    def cost_sources() -> dict[str, object]:
        return {"rows": usage_service.cost_source_summary()}

    @app.get("/api/system/profile")
    def system_profile() -> dict[str, object]:
        return usage_service.system_profile()

    @app.get("/api/system/models")
    def system_models() -> dict[str, object]:
        return usage_service.model_catalog()

    @app.get("/api/system/connection")
    def system_connection() -> dict[str, object]:
        return usage_service.connection_info()

    @app.get("/api/system/token-accuracy")
    def token_accuracy(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
        return usage_service.token_accuracy(limit=limit)

    @app.get("/api/system/session-snapshots")
    def session_snapshots(limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
        return usage_service.session_snapshots(limit=limit)

    @app.get("/api/system/logs-explorer")
    def logs_explorer(
        file_limit: int = Query(default=12, ge=1, le=30),
        tail_lines: int = Query(default=80, ge=1, le=300),
    ) -> dict[str, object]:
        return usage_service.logs_explorer(file_limit=file_limit, tail_lines=tail_lines)

    @app.get("/api/chat/sessions")
    def chat_sessions(
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, object]:
        return usage_service.chat_sessions(limit=limit, offset=offset)

    @app.get("/api/chat/session/{session_id}")
    def chat_session_messages(
        session_id: str,
        limit: int = Query(default=300, ge=1, le=2000),
        before_id: int | None = Query(default=None, ge=1),
    ) -> dict[str, object]:
        return usage_service.chat_session_messages(
            session_id=session_id,
            limit=limit,
            before_id=before_id,
        )

    @app.get("/api/usage/session/{session_id}")
    def session_detail(session_id: str, limit: int = Query(default=300, ge=1, le=2000)) -> dict[str, object]:
        return usage_service.session_detail(session_id=session_id, limit=limit)

    @app.get("/api/pricing")
    def pricing_table() -> dict[str, object]:
        return usage_service.pricing_table()

    @app.get("/api/usage/plan-cost")
    def plan_cost() -> dict[str, object]:
        return usage_service.plan_cost_summary()

    @app.post("/api/pricing/upsert")
    def pricing_upsert(payload: dict = Body(...)) -> dict[str, object]:
        provider = str(payload.get("provider") or "").strip()
        model = str(payload.get("model") or "").strip()
        if not provider or not model:
            raise HTTPException(status_code=400, detail="provider and model are required")

        input_per_million = float(payload.get("input_per_million") or 0.0)
        output_per_million = float(payload.get("output_per_million") or 0.0)
        if input_per_million < 0 or output_per_million < 0:
            raise HTTPException(
                status_code=400,
                detail="input_per_million and output_per_million must be >= 0",
            )

        return usage_service.upsert_model_pricing(
            provider=provider,
            model=model,
            input_per_million=input_per_million,
            output_per_million=output_per_million,
        )

    return app
