from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.accounts import ImpalaAccounts, router as accounts_router
from app.config import Settings
from app.db import DataUnavailable, query
from app.demo_data import DemoAccounts, demo_features
from app.events import router as events_router
from app.features import load_features
from app.rules import router as rules_router

STATIC = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Held-away assets", version="1.0.0")
    app.state.settings = settings
    if settings.demo_mode:
        app.state.account_source = DemoAccounts()
        app.state.feature_loader = demo_features
    else:
        app.state.account_source = ImpalaAccounts(settings)
        if settings.client_id_column:
            app.state.feature_loader = lambda client_id: load_features(settings, client_id)
        else:
            app.state.feature_loader = None

    @app.get("/health")
    def health() -> dict[str, str]:
        if settings.demo_mode:
            return {"status": "ok"}
        try:
            query(settings, "SELECT 1")
        except DataUnavailable as exc:
            from fastapi import HTTPException

            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"status": "ok"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    app.include_router(accounts_router)
    app.include_router(events_router)
    app.include_router(rules_router)
    return app


app = create_app()
